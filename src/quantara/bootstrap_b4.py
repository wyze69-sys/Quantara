"""Frozen Protocol-v1.1 B4 paired moving-block bootstrap.

The implementation uses only exact integer and ``Fraction`` arithmetic in the
statistic path. Integer observations are interpreted as units of the frozen
1e-18 storage quantum; ``Decimal`` observations must be exactly representable
at that quantum.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from fractions import Fraction

from quantara.errors import QuantaraError

_MASK_64 = 2**64 - 1
_TWO_TO_64 = 2**64
_GOLDEN_GAMMA = 0x9E3779B97F4A7C15
_MIX_MULTIPLIER_1 = 0xBF58476D1CE4E5B9
_MIX_MULTIPLIER_2 = 0x94D049BB133111EB
_STORAGE_SCALE = 10**18
_REPORT_QUANTUM = Decimal("0.000000000000000001")


class BootstrapB4InferenceError(QuantaraError):
    """Named fail-closed Protocol-v1.1 B4 inference outcome."""

    error_id = "bootstrap_b4_inference_fail_closed"

    def __init__(
        self,
        *,
        reason: str,
        year: int,
        replicate_index: int | None,
    ) -> None:
        self.reason = reason
        self.year = year
        self.replicate_index = replicate_index
        location = "observed grid" if replicate_index is None else f"replicate {replicate_index}"
        super().__init__(f"{reason}: year={year}, {location}")


class SplitMix64:
    """Frozen SplitMix64 stream with unbiased bounded draws."""

    def __init__(self, seed: int) -> None:
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise TypeError("SplitMix64 seed must be an integer")
        self._state = seed & _MASK_64

    def next_u64(self) -> int:
        self._state = (self._state + _GOLDEN_GAMMA) & _MASK_64
        value = self._state
        value = ((value ^ (value >> 30)) * _MIX_MULTIPLIER_1) & _MASK_64
        value = ((value ^ (value >> 27)) * _MIX_MULTIPLIER_2) & _MASK_64
        return value ^ (value >> 31)

    def below(self, bound: int) -> int:
        if not isinstance(bound, int) or isinstance(bound, bool) or bound <= 0:
            raise ValueError("bound must be a positive integer")
        if bound > _TWO_TO_64:
            raise ValueError("bound must not exceed 2**64")
        limit = _TWO_TO_64 - (_TWO_TO_64 % bound)
        while True:
            value = self.next_u64()
            if value < limit:
                return value % bound


@dataclass(frozen=True)
class BootstrapB4Result:
    """Exact output and deterministic fixture evidence for one comparison."""

    observed_mean: Fraction
    replicate_means: tuple[Fraction, ...]
    ci_lower: Fraction
    ci_upper: Fraction
    p_value: Fraction
    derived_seeds: dict[int, int]
    index_multiset_sha256: dict[int, str]


@dataclass(frozen=True)
class _PreparedYear:
    year: int
    values: tuple[int | None, ...]
    value_prefix: tuple[int, ...]
    valid_prefix: tuple[int, ...]
    observed_numerator: int
    observed_denominator: int


def derive_stream_seed(comparison_id: str, year: int) -> int:
    """Derive the frozen comparison/year stream seed."""

    if not isinstance(comparison_id, str) or not comparison_id:
        raise ValueError("comparison_id must be a non-empty ASCII string")
    try:
        comparison_id.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("comparison_id must be ASCII") from exc
    if not isinstance(year, int) or isinstance(year, bool):
        raise TypeError("year must be an integer")
    payload = f"quantara-protocol-v1_1|bootstrap-b4|{comparison_id}|{year}"
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def nominal_hours(year: int) -> int:
    """Derive a calendar year's nominal UTC-hour count."""

    if not isinstance(year, int) or isinstance(year, bool):
        raise TypeError("year must be an integer")
    start = datetime(year, 1, 1, tzinfo=UTC)
    end = datetime(year + 1, 1, 1, tzinfo=UTC)
    duration = end - start
    one_hour = timedelta(hours=1)
    if duration % one_hour:
        raise AssertionError("calendar-year duration is not an exact hour count")
    return duration // one_hour


def sample_block_starts(
    rng: SplitMix64,
    hours: int,
    block_hours: int = 168,
) -> tuple[int, ...]:
    """Draw the frozen number of eligible non-circular block starts."""

    _validate_geometry(hours, block_hours)
    draw_count = (hours + block_hours - 1) // block_hours
    eligible_start_count = hours - block_hours + 1
    return tuple(rng.below(eligible_start_count) for _ in range(draw_count))


def materialize_resampled_indices(
    starts: Sequence[int],
    hours: int,
    block_hours: int = 168,
) -> tuple[int, ...]:
    """Materialize starts, retaining only the first ``hours`` clock positions."""

    _validate_geometry(hours, block_hours)
    indices: list[int] = []
    remaining = hours
    for start in starts:
        _validate_start(start, hours, block_hours)
        consumed = min(block_hours, remaining)
        indices.extend(range(start, start + consumed))
        remaining -= consumed
        if remaining == 0:
            break
    if remaining:
        raise ValueError("block starts do not cover the nominal grid")
    return tuple(indices)


def aggregate_from_starts(
    values: Sequence[int | Decimal | None],
    starts: Sequence[int],
    block_hours: int = 168,
) -> tuple[int, int]:
    """Return exact scaled numerator and paired-valid denominator."""

    prepared_values = tuple(_scaled_integer(value) for value in values)
    value_prefix, valid_prefix = _prefixes(prepared_values)
    return _aggregate_prefixes(
        value_prefix,
        valid_prefix,
        starts,
        len(prepared_values),
        block_hours,
    )


def pooled_observed_mean(
    grids: Mapping[int, Sequence[int | Decimal | None]],
) -> Fraction:
    """Pool observed scaled values by paired-valid count."""

    numerator = 0
    denominator = 0
    for values in grids.values():
        for value in values:
            scaled = _scaled_integer(value)
            if scaled is not None:
                numerator += scaled
                denominator += 1
    if denominator == 0:
        raise ValueError("pooled observed grid has no paired-valid observations")
    return Fraction(numerator, denominator)


def pooled_resample_from_starts(
    grids: Mapping[int, Sequence[int | Decimal | None]],
    starts_by_year: Mapping[int, Sequence[int]],
    *,
    block_hours: int = 168,
    replicate_index: int,
) -> Fraction:
    """Pool one explicit replicate, failing closed for an empty required year."""

    numerator = 0
    denominator = 0
    for year in sorted(grids):
        if year not in starts_by_year:
            raise ValueError(f"missing starts for required year {year}")
        year_numerator, year_denominator = aggregate_from_starts(
            grids[year], starts_by_year[year], block_hours
        )
        if year_denominator == 0:
            raise BootstrapB4InferenceError(
                reason="empty_resampled_required_year",
                year=year,
                replicate_index=replicate_index,
            )
        numerator += year_numerator
        denominator += year_denominator
    if denominator == 0:
        raise AssertionError("per-year fail-closed checks allowed a zero pooled denominator")
    return Fraction(numerator, denominator)


def nearest_rank_interval(
    replicate_means: Sequence[Fraction],
) -> tuple[Fraction, Fraction]:
    """Return the non-interpolated 2.5%/97.5% nearest-rank interval."""

    if not replicate_means:
        raise ValueError("at least one replicate mean is required")
    ordered = sorted(replicate_means)
    count = len(ordered)
    lower_rank = (count + 40 - 1) // 40
    upper_rank = (39 * count + 40 - 1) // 40
    return ordered[lower_rank - 1], ordered[upper_rank - 1]


def render_fraction_18(value: Fraction) -> str:
    """Render an exact fraction at 18 decimal places using ROUND_HALF_EVEN."""

    with localcontext() as context:
        context.prec = max(80, len(str(abs(value.numerator))) + len(str(value.denominator)) + 24)
        rendered = (Decimal(value.numerator) / Decimal(value.denominator)).quantize(
            _REPORT_QUANTUM,
            rounding=ROUND_HALF_EVEN,
        )
    if rendered == 0:
        rendered = rendered.copy_abs()
    return format(rendered, "f")


def bootstrap_b4(
    grids: Mapping[int, Sequence[int | Decimal | None]],
    *,
    comparison_id: str,
    resamples: int = 20000,
    block_hours: int = 168,
) -> BootstrapB4Result:
    """Run the frozen year-stratified paired moving-block bootstrap."""

    if not isinstance(resamples, int) or isinstance(resamples, bool) or resamples <= 0:
        raise ValueError("resamples must be a positive integer")
    if block_hours != 168:
        raise ValueError("Protocol-v1.1 B4 block_hours is frozen at 168")
    if not grids:
        raise ValueError("at least one required year is needed")

    years = tuple(sorted(grids))
    prepared: dict[int, _PreparedYear] = {}
    observed_numerator = 0
    observed_denominator = 0
    for year in years:
        values = grids[year]
        expected_hours = nominal_hours(year)
        if len(values) != expected_hours:
            raise ValueError(
                f"year {year} has {len(values)} positions; expected nominal grid {expected_hours}"
            )
        prepared_year = _prepare_year(year, values)
        if prepared_year.observed_denominator < block_hours:
            raise BootstrapB4InferenceError(
                reason="insufficient_observed_paired_valid",
                year=year,
                replicate_index=None,
            )
        prepared[year] = prepared_year
        observed_numerator += prepared_year.observed_numerator
        observed_denominator += prepared_year.observed_denominator

    observed_mean = Fraction(
        observed_numerator,
        observed_denominator * _STORAGE_SCALE,
    )
    derived_seeds = {year: derive_stream_seed(comparison_id, year) for year in years}
    streams = {year: SplitMix64(derived_seeds[year]) for year in years}
    multiplicity_deltas = {
        year: [0] * (len(prepared[year].values) + 1) for year in years
    }
    replicate_means: list[Fraction] = []

    for replicate_index in range(resamples):
        pooled_numerator = 0
        pooled_denominator = 0
        for year in years:
            year_grid = prepared[year]
            hours = len(year_grid.values)
            starts = sample_block_starts(streams[year], hours, block_hours)
            year_numerator, year_denominator = _aggregate_prefixes(
                year_grid.value_prefix,
                year_grid.valid_prefix,
                starts,
                hours,
                block_hours,
                multiplicity_delta=multiplicity_deltas[year],
            )
            if year_denominator == 0:
                raise BootstrapB4InferenceError(
                    reason="empty_resampled_required_year",
                    year=year,
                    replicate_index=replicate_index,
                )
            pooled_numerator += year_numerator
            pooled_denominator += year_denominator
        replicate_means.append(
            Fraction(pooled_numerator, pooled_denominator * _STORAGE_SCALE)
        )

    exact_replicates = tuple(replicate_means)
    ci_lower, ci_upper = nearest_rank_interval(exact_replicates)
    exceedances = sum(value >= 2 * observed_mean for value in exact_replicates)
    p_value = Fraction(1 + exceedances, resamples + 1)
    digests = {
        year: _multiset_digest(multiplicity_deltas[year]) for year in years
    }
    return BootstrapB4Result(
        observed_mean=observed_mean,
        replicate_means=exact_replicates,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        p_value=p_value,
        derived_seeds=derived_seeds,
        index_multiset_sha256=digests,
    )


def _validate_geometry(hours: int, block_hours: int) -> None:
    if not isinstance(hours, int) or isinstance(hours, bool) or hours <= 0:
        raise ValueError("hours must be a positive integer")
    if not isinstance(block_hours, int) or isinstance(block_hours, bool):
        raise ValueError("block_hours must be an integer")
    if block_hours <= 0 or block_hours > hours:
        raise ValueError("block_hours must be positive and no greater than hours")


def _validate_start(start: int, hours: int, block_hours: int) -> None:
    if not isinstance(start, int) or isinstance(start, bool):
        raise ValueError("block start must be an integer")
    if start < 0 or start > hours - block_hours:
        raise ValueError("block start is outside the non-circular eligible range")


def _scaled_integer(value: int | Decimal | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise TypeError("boolean is not a scaled loss difference")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("loss difference must be finite")
        scaled = value * _STORAGE_SCALE
        integral = scaled.to_integral_value()
        if scaled != integral:
            raise ValueError("Decimal loss difference is not representable at 1e-18")
        return int(integral)
    raise TypeError("loss difference must be an integer scaled unit, Decimal, or None")


def _prefixes(values: Sequence[int | None]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    value_prefix = [0]
    valid_prefix = [0]
    running_value = 0
    running_valid = 0
    for value in values:
        if value is not None:
            running_value += value
            running_valid += 1
        value_prefix.append(running_value)
        valid_prefix.append(running_valid)
    return tuple(value_prefix), tuple(valid_prefix)


def _prepare_year(
    year: int,
    values: Sequence[int | Decimal | None],
) -> _PreparedYear:
    scaled_values = tuple(_scaled_integer(value) for value in values)
    value_prefix, valid_prefix = _prefixes(scaled_values)
    return _PreparedYear(
        year=year,
        values=scaled_values,
        value_prefix=value_prefix,
        valid_prefix=valid_prefix,
        observed_numerator=value_prefix[-1],
        observed_denominator=valid_prefix[-1],
    )


def _aggregate_prefixes(
    value_prefix: Sequence[int],
    valid_prefix: Sequence[int],
    starts: Sequence[int],
    hours: int,
    block_hours: int,
    *,
    multiplicity_delta: list[int] | None = None,
) -> tuple[int, int]:
    _validate_geometry(hours, block_hours)
    numerator = 0
    denominator = 0
    remaining = hours
    for start in starts:
        _validate_start(start, hours, block_hours)
        consumed = min(block_hours, remaining)
        end = start + consumed
        numerator += value_prefix[end] - value_prefix[start]
        denominator += valid_prefix[end] - valid_prefix[start]
        if multiplicity_delta is not None:
            multiplicity_delta[start] += 1
            multiplicity_delta[end] -= 1
        remaining -= consumed
        if remaining == 0:
            break
    if remaining:
        raise ValueError("block starts do not cover the nominal grid")
    return numerator, denominator


def _multiset_digest(delta: Sequence[int]) -> str:
    digest = hashlib.sha256()
    multiplicity = 0
    for index, change in enumerate(delta[:-1]):
        multiplicity += change
        if multiplicity:
            digest.update(f"{index}:{multiplicity}\n".encode("ascii"))
    return digest.hexdigest()
