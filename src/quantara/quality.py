"""Quality evaluator (component 5).

Runs explicit field, row, sequence, boundary, and reconciliation checks; emits
one finding per check with evidence counts; aggregates to PASS / WARN_BLOCKED /
WARN_APPROVED / FAIL under quality policy v1 where any warning blocks the
golden slice and aggregate scores never gate alone (spec §§4.1, 8, 13.3, 14).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from quantara.canonical import CanonicalRow
from quantara.descriptor import DatasetDescriptor
from quantara.errors import (
    NONZERO_SOURCE_IGNORE,
    SOURCE_ORDER_INVALID,
    ZERO_VOLUME_CANDLE,
)
from quantara.hashing import quality_identity

__all__ = ["QUALITY_POLICY_VERSION", "Finding", "QualityReport", "evaluate_quality"]

QUALITY_POLICY_VERSION = "1"


@dataclass(frozen=True)
class Finding:
    check_id: str
    outcome: str  # "pass" | "warn" | "fail"
    severity: str  # "hard" | "warning"
    count: int
    evidence: dict


@dataclass
class QualityReport:
    findings: list[Finding] = field(default_factory=list)
    state: str = "PASS"

    def identity(self) -> str:
        """Deterministic JCS identity; operational timestamps excluded."""
        return quality_identity(
            [
                {
                    "check_id": f.check_id,
                    "count": f.count,
                    "evidence": f.evidence,
                    "outcome": f.outcome,
                    "severity": f.severity,
                }
                for f in self.findings
            ]
        )


def evaluate_quality(
    rows: Sequence[CanonicalRow],
    descriptor: DatasetDescriptor,
    source_order_valid: bool,
    expected_count: int | None = None,
) -> QualityReport:
    findings: list[Finding] = []

    def record(check_id: str, ok: bool, count: int = 0, **evidence) -> None:
        findings.append(
            Finding(
                check_id=check_id,
                outcome="pass" if ok else "fail",
                severity="hard",
                count=count,
                evidence=evidence or {"violations": count},
            )
        )

    def warn(check_id: str, count: int, **evidence) -> None:
        findings.append(
            Finding(
                check_id=check_id,
                outcome="warn" if count else "pass",
                severity="warning",
                count=count,
                evidence={**evidence, "occurrences": count},
            )
        )

    # expected_count=None disables row-count enforcement (partial fixtures);
    # an integer enforces exactly that many rows.
    if expected_count is None:
        record("row_count_matches_expected", True, len(rows),
               skipped="row-count enforcement disabled")
        complete_month = False
    else:
        complete_month = len(rows) == expected_count
        record(
            "row_count_matches_expected",
            complete_month,
            len(rows),
            approved_rows=expected_count,
            actual_rows=len(rows),
        )

    start_ms = int(descriptor.start_utc.timestamp() * 1000)
    end_ms = int(descriptor.end_utc.timestamp() * 1000)
    if rows and complete_month:
        record("first_boundary_exact", rows[0].open_time_ms == start_ms,
               observed_first_open=rows[0].open_time_ms, approved_start=start_ms)
        record("last_boundary_exact", rows[-1].open_time_ms == end_ms - 60_000,
               observed_last_open=rows[-1].open_time_ms,
               approved_last_open=end_ms - 60_000)
    elif not rows:
        record("first_boundary_exact", False, reason="no rows")
        record("last_boundary_exact", False, reason="no rows")
    else:
        # Exact boundary equality is only decidable for a complete month;
        # unconditional period membership is enforced separately below.
        record("first_boundary_exact", True, skipped="incomplete fixture")
        record("last_boundary_exact", True, skipped="incomplete fixture")

    times = [row.open_time_ms for row in rows]
    record("unique_open_times", len(set(times)) == len(times),
           len(times) - len(set(times)))
    record(
        "strictly_ascending_open_times",
        all(a < b for a, b in zip(times, times[1:], strict=False)),
    )
    record(
        "adjacency_exactly_60000ms",
        all(b - a == 60_000 for a, b in zip(times, times[1:], strict=False)),
    )
    out_of_period = sum(1 for t in times if not (start_ms <= t < end_ms))
    record("period_membership_respected", out_of_period == 0, out_of_period)

    ohlc_violations = 0
    price_violations = 0
    volume_violations = 0
    taker_violations = 0
    close_time_violations = 0
    zero_volume = 0
    nonzero_ignore = 0
    for row in rows:
        if not (
            row.high >= row.open
            and row.high >= row.close
            and row.low <= row.open
            and row.low <= row.close
            and row.high >= row.low
        ):
            ohlc_violations += 1
        if not all(p > 0 for p in (row.open, row.high, row.low, row.close)):
            price_violations += 1
        if not all(
            v >= 0
            for v in (
                row.base_asset_volume,
                row.quote_asset_volume,
                row.taker_buy_base_volume,
                row.taker_buy_quote_volume,
            )
        ):
            volume_violations += 1
        if row.trade_count < 0:
            volume_violations += 1
        if row.close_time_ms != row.open_time_ms + 59_999:
            close_time_violations += 1
        if not (
            row.taker_buy_base_volume <= row.base_asset_volume
            and row.taker_buy_quote_volume <= row.quote_asset_volume
        ):
            taker_violations += 1
        if row.base_asset_volume == 0 and row.quote_asset_volume == 0:
            zero_volume += 1
        if row.source_ignore != "0":
            nonzero_ignore += 1

    record("ohlc_bounds_hold", ohlc_violations == 0, ohlc_violations)
    record("prices_strictly_positive", price_violations == 0, price_violations)
    record("volumes_and_counts_nonnegative", volume_violations == 0, volume_violations)
    record("close_time_equals_open_plus_59999", close_time_violations == 0,
           close_time_violations)
    record("taker_buy_within_counterpart_volumes", taker_violations == 0,
           taker_violations)

    warn(SOURCE_ORDER_INVALID, 0 if source_order_valid else 1,
         note="complete unique source rows required sorting")
    warn(ZERO_VOLUME_CANDLE, zero_volume)
    warn(NONZERO_SOURCE_IGNORE, nonzero_ignore)

    has_fail = any(f.outcome == "fail" for f in findings)
    has_warn = any(f.outcome == "warn" for f in findings)
    state = "FAIL" if has_fail else ("WARN_BLOCKED" if has_warn else "PASS")
    return QualityReport(findings=findings, state=state)
