"""Exact multi-timeframe bucket aggregation (data slice 002).

Reconstructs canonical rows from persisted tuples, validates the parent's
ordering contract (strictly ascending unique minute open times — unordered
input is rejected, never sorted), buckets minutes into epoch-aligned half-open
[B, B + timeframe) windows, hard-gates each bucket on completeness (exactly
``timeframe_minutes`` contiguous constituents fully covering the window; any
nonzero ``source_ignore`` rejects the group outright), and aggregates with
exact Decimal/integer arithmetic per design §7. No interpolation exists here.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from decimal import Decimal, localcontext

from quantara.canonical import CanonicalRow, DuplicateOpenTime
from quantara.errors import (
    DECIMAL_PRECISION_OR_SCALE_OVERFLOW,
    QuantaraError,
)

__all__ = [
    "IncompleteGroup",
    "NonzeroSourceIgnoreInGroup",
    "UnorderedMinuteInput",
    "aggregate_timeframe",
    "exact_volume_sum",
    "rows_from_persisted",
]


class UnorderedMinuteInput(QuantaraError):
    error_id = "unordered_minute_input"


class IncompleteGroup(QuantaraError):
    error_id = "incomplete_group"


class NonzeroSourceIgnoreInGroup(QuantaraError):
    error_id = "nonzero_source_ignore_in_group"


class DecimalPrecisionOrScaleOverflow(QuantaraError):
    error_id = DECIMAL_PRECISION_OR_SCALE_OVERFLOW


# decimal128(38,18) bounds: at most 38 coefficient digits with scale 18,
# i.e. |value| < 10**20. Sums are computed in a high-precision LOCAL context
# (the process-global context is never read or mutated), then re-checked for
# exact representability in the canonical persisted type per design §7.
_SUM_CONTEXT_PRECISION = 80
_CANONICAL_MAX_COEFFICIENT = 10**38
_CANONICAL_SCALE = -18


def exact_volume_sum(values: Iterable[Decimal], field_name: str) -> Decimal:
    """Exact Decimal sum of canonical constituents, independent of the
    ambient decimal context.

    Addition runs inside a local high-precision context so no rounding can
    occur; the exact total is then verified to fit decimal128(38,18). Any
    unrepresentable aggregate is a deterministic hard failure — rounding
    never happens.
    """
    total = Decimal(0)
    with localcontext() as ctx:
        ctx.prec = _SUM_CONTEXT_PRECISION
        for value in values:
            total += value
        scaled = total.scaleb(-_CANONICAL_SCALE)
    if scaled != scaled.to_integral_value():
        raise DecimalPrecisionOrScaleOverflow(
            f"exact {field_name} aggregate needs more than 18 fractional "
            f"digits ({total}); rounding is forbidden"
        )
    coefficient = abs(int(scaled))
    if coefficient >= _CANONICAL_MAX_COEFFICIENT:
        raise DecimalPrecisionOrScaleOverflow(
            f"exact {field_name} aggregate {total} does not fit "
            f"decimal128(38,18); refusing to round or overflow"
        )
    return total


def rows_from_persisted(rows: Iterable[tuple]) -> list[CanonicalRow]:
    """Positional reconstruction of CanonicalRow from read_canonical_rows
    output: timestamps arrive as epoch-ms ints and decimals as Decimal — any
    wrong tuple width or float instance is rejected."""
    restored: list[CanonicalRow] = []
    for position, values in enumerate(rows):
        values = tuple(values)
        if len(values) != 23:
            raise QuantaraError(
                f"persisted row {position} has width {len(values)}; expected "
                "23 canonical columns"
            )
        for value in values:
            if isinstance(value, float):
                raise QuantaraError(
                    f"binary float in persisted row {position}; contamination "
                    "is structurally forbidden"
                )
        restored.append(
            CanonicalRow(
                identity=tuple(values[:10]),  # type: ignore[arg-type]
                open_time_ms=values[10],
                close_time_ms=values[11],
                nominal_available_ms=values[12],
                open=values[13],
                high=values[14],
                low=values[15],
                close=values[16],
                base_asset_volume=values[17],
                quote_asset_volume=values[18],
                trade_count=values[19],
                taker_buy_base_volume=values[20],
                taker_buy_quote_volume=values[21],
                source_ignore=values[22],
            )
        )
    return restored


def _times_of(rows: Sequence[CanonicalRow]) -> list[int]:
    return [row.open_time_ms for row in rows]


def aggregate_timeframe(
    minutes: Sequence[CanonicalRow],
    identity: tuple[str, ...],
    timeframe_ms: int,
) -> list[CanonicalRow]:
    """Aggregate strictly ascending complete minute groups into bars."""
    times = _times_of(minutes)
    for previous, current in zip(times, times[1:], strict=False):
        if current < previous:
            raise UnorderedMinuteInput(
                f"minute at {current} follows {previous}; input must be "
                "strictly ascending and is never silently sorted"
            )
        if current == previous:
            raise DuplicateOpenTime(f"duplicate minute open time {current}")

    grouped: dict[int, list[CanonicalRow]] = defaultdict(list)
    for row in minutes:
        bucket = row.open_time_ms - (row.open_time_ms % timeframe_ms)
        grouped[bucket].append(row)

    expected_members = timeframe_ms // 60_000
    bars: list[CanonicalRow] = []
    for bucket in sorted(grouped):
        members = grouped[bucket]
        member_times = _times_of(members)
        if len(members) != expected_members:
            raise IncompleteGroup(
                f"bucket {bucket} holds {len(members)} of {expected_members} "
                "required minutes; incomplete groups are never interpolated"
            )
        contiguous = (
            member_times[0] == bucket
            and all(
                current - previous == 60_000
                for previous, current in zip(
                    member_times, member_times[1:], strict=False
                )
            )
            and member_times[-1] == bucket + timeframe_ms - 60_000
        )
        if not contiguous:
            raise IncompleteGroup(
                f"bucket {bucket} constituents do not contiguously cover "
                "[B, B + timeframe); gaps are a hard failure"
            )
        offenders = sum(1 for m in members if m.source_ignore != "0")
        if offenders:
            raise NonzeroSourceIgnoreInGroup(
                f"bucket {bucket} holds {offenders} nonzero source_ignore "
                "minutes; no faithful aggregate representation exists"
            )
        bars.append(
            CanonicalRow(
                identity=identity,
                open_time_ms=bucket,
                close_time_ms=bucket + timeframe_ms - 1,
                nominal_available_ms=bucket + timeframe_ms,
                open=members[0].open,
                high=max(m.high for m in members),
                low=min(m.low for m in members),
                close=members[-1].close,
                base_asset_volume=exact_volume_sum(
                    (m.base_asset_volume for m in members),
                    "base_asset_volume"),
                quote_asset_volume=exact_volume_sum(
                    (m.quote_asset_volume for m in members),
                    "quote_asset_volume"),
                trade_count=sum(m.trade_count for m in members),
                taker_buy_base_volume=exact_volume_sum(
                    (m.taker_buy_base_volume for m in members),
                    "taker_buy_base_volume"),
                taker_buy_quote_volume=exact_volume_sum(
                    (m.taker_buy_quote_volume for m in members),
                    "taker_buy_quote_volume"),
                source_ignore="0",
            )
        )
    return bars

