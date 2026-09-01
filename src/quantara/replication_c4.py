"""Protocol v1.1 C4 timestamp, refit, buffer, and replication binding.

The module contains only exact integer and ``Decimal`` contract arithmetic. It
delegates stream derivation to the frozen C2 bootstrap and binds calibration
limits to the frozen C3 helper defaults.
"""

from __future__ import annotations

import inspect
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from quantara import bootstrap_b4, estimator_c3

HOUR_MS = 3_600_000
MINUTE_MS = 60_000
LABEL_HORIZON_MS = 86_400_000
SEAL_BOUNDARY_MS = 1_735_689_600_000
FIRST_2025_ORIGIN_MS = 1_735_689_600_000
LAST_2025_ORIGIN_MS = 1_767_222_000_000
ORIGIN_COUNT_2025 = 8_760
BUFFER_FIRST_BAR_OPEN_MS = 1_767_225_600_000
BUFFER_LAST_BAR_OPEN_MS = 1_767_304_800_000
BUFFER_END_INCLUSIVE_MS = 1_767_308_399_999
BUFFER_REFUSED_BAR_OPEN_MS = 1_767_308_400_000
BUFFER_BAR_COUNT = 23
BUFFER_FIRST_MINUTE_OPEN_MS = 1_767_225_600_000
BUFFER_LAST_MINUTE_OPEN_MS = 1_767_308_340_000
BUFFER_MINUTE_COUNT = 1_380
REFIT_TRAIN_START_MS = 1_598_918_400_000
REFIT_LAST_ORIGIN_MS = 1_735_603_200_000
REFIT_NOMINAL_ORIGIN_COUNT = 37_969
REFIT_EXCLUDED_TAIL_COUNT = 23
OI_ELIGIBILITY_OFFSET_MS = 300_000
OI_TIMESTAMP_ROLE = "UNRESOLVED_CONSERVATIVE"
KRAKEN_TIMESTAMP_ROLE = "DOCUMENTED_INTERVAL_START"
FINAL_FIT_FAILURE = "FINAL_FIT_FAILURE"

REPLICATION_CRITERIA = (
    "bss_b2_at_least_0_02",
    "ci_lower_above_zero",
    "absolute_probability_bias_at_most_0_02",
    "calibration_slope_in_frozen_band",
    "calibration_defined_and_converged",
)
REPLICATION_COMPARISON_IDS = {
    model: f"REPLICATION_2025|{model}_vs_B2" for model in ("M2", "M2K", "M3", "M4")
}

_CALIBRATION_PARAMETERS = inspect.signature(estimator_c3.calibration_slope_passes).parameters
_CALIBRATION_SLOPE_LOWER = _CALIBRATION_PARAMETERS["lower"].default
_CALIBRATION_SLOPE_UPPER = _CALIBRATION_PARAMETERS["upper"].default


@dataclass(frozen=True)
class ReplicationEvidence:
    """Exact one-year evidence supplied to the five-criterion gate."""

    bss_b2: Decimal
    ci_lower: Decimal
    probability_bias: Decimal
    calibration_slope: Decimal
    calibration_defined_and_converged: bool


@dataclass(frozen=True)
class ReplicationDecision:
    """Named criterion decisions and the terminal replication outcome."""

    bss_b2_at_least_0_02: bool
    ci_lower_above_zero: bool
    absolute_probability_bias_at_most_0_02: bool
    calibration_slope_in_frozen_band: bool
    calibration_defined_and_converged: bool
    outcome: str


def enumerate_2025_origins() -> tuple[int, ...]:
    """Return the complete calendar-2025 hourly origin grid."""

    origins = tuple(FIRST_2025_ORIGIN_MS + index * HOUR_MS for index in range(ORIGIN_COUNT_2025))
    if len(origins) != bootstrap_b4.nominal_hours(2025):
        raise AssertionError("calendar-2025 origin count disagrees with frozen C2")
    if origins[-1] != LAST_2025_ORIGIN_MS:
        raise AssertionError("calendar-2025 final origin disagrees with frozen boundary")
    return origins


def label_close_ms(origin_ms: int) -> int:
    """Return the exact close time of an origin's 24-hour label endpoint."""

    return origin_ms + LABEL_HORIZON_MS - 1


def requires_2026_buffer(origin_ms: int) -> bool:
    """Return whether the origin's label endpoint reaches the sealed buffer."""

    return label_close_ms(origin_ms) >= BUFFER_FIRST_BAR_OPEN_MS


def buffer_dependent_origins() -> tuple[int, ...]:
    """Return the 23 calendar-2025 origins whose labels depend on the buffer."""

    return tuple(origin for origin in enumerate_2025_origins() if requires_2026_buffer(origin))


def buffer_bar_opens() -> tuple[int, ...]:
    """Return the exact authorized 2026 target-only hourly bar opens."""

    return tuple(BUFFER_FIRST_BAR_OPEN_MS + index * HOUR_MS for index in range(BUFFER_BAR_COUNT))


def buffer_minute_opens() -> tuple[int, ...]:
    """Return the exact authorized 2026 target-only minute opens."""

    return tuple(
        BUFFER_FIRST_MINUTE_OPEN_MS + index * MINUTE_MS for index in range(BUFFER_MINUTE_COUNT)
    )


def is_buffer_minute_in_scope(open_ms: int) -> bool:
    """Apply the inclusive post-parse, pre-aggregation minute boundary."""

    return BUFFER_FIRST_MINUTE_OPEN_MS <= open_ms <= BUFFER_LAST_MINUTE_OPEN_MS


def truncate_buffer_minutes(
    open_ms_seq: Sequence[int],
) -> tuple[tuple[int, ...], int]:
    """Copy and truncate minute opens, returning kept rows and discard count."""

    copied = tuple(open_ms_seq)
    kept = tuple(open_ms for open_ms in copied if is_buffer_minute_in_scope(open_ms))
    return kept, len(copied) - len(kept)


def enumerate_refit_origins() -> tuple[int, ...]:
    """Return nominal hourly origins satisfying the final purge inequality."""

    origins = tuple(range(REFIT_TRAIN_START_MS, REFIT_LAST_ORIGIN_MS + HOUR_MS, HOUR_MS))
    if len(origins) != REFIT_NOMINAL_ORIGIN_COUNT:
        raise AssertionError("final-refit nominal count disagrees with frozen boundary")
    return origins


def is_refit_eligible_origin(origin_ms: int) -> bool:
    """Apply the exact final-refit range, cadence, and purge boundary."""

    return (
        REFIT_TRAIN_START_MS <= origin_ms <= REFIT_LAST_ORIGIN_MS
        and (origin_ms - REFIT_TRAIN_START_MS) % HOUR_MS == 0
        and origin_ms + LABEL_HORIZON_MS <= SEAL_BOUNDARY_MS
    )


def latest_eligible_oi_open_ms(boundary_ms: int) -> int:
    """Return the latest conservative five-minute provider timestamp at T."""

    return boundary_ms - OI_ELIGIBILITY_OFFSET_MS


def replication_comparison_id(model: str) -> str:
    """Return the frozen 2025 paired-B2 comparison identifier."""

    try:
        return REPLICATION_COMPARISON_IDS[model]
    except KeyError as error:
        raise ValueError(f"unsupported replication model: {model!r}") from error


def replication_stream_seed(model: str) -> int:
    """Delegate the model's 2025 seed to the frozen C2 derivation."""

    return bootstrap_b4.derive_stream_seed(replication_comparison_id(model), 2025)


def _require_decimal(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be decimal.Decimal")


def evaluate_replication_gate(evidence: ReplicationEvidence) -> ReplicationDecision:
    """Evaluate the exact five-condition one-year replication gate once."""

    if not isinstance(evidence, ReplicationEvidence):
        raise TypeError("evidence must be ReplicationEvidence")
    for field_name in ("bss_b2", "ci_lower", "probability_bias", "calibration_slope"):
        _require_decimal(getattr(evidence, field_name), field_name)
    if not isinstance(evidence.calibration_defined_and_converged, bool):
        raise TypeError("calibration_defined_and_converged must be bool")

    criteria = {
        "bss_b2_at_least_0_02": evidence.bss_b2 >= Decimal("0.02"),
        "ci_lower_above_zero": evidence.ci_lower > Decimal(0),
        "absolute_probability_bias_at_most_0_02": (
            abs(evidence.probability_bias) <= Decimal("0.02")
        ),
        "calibration_slope_in_frozen_band": (
            _CALIBRATION_SLOPE_LOWER <= evidence.calibration_slope <= _CALIBRATION_SLOPE_UPPER
        ),
        "calibration_defined_and_converged": (evidence.calibration_defined_and_converged),
    }
    outcome = "REPLICATED" if all(criteria.values()) else "DID_NOT_REPLICATE"
    return ReplicationDecision(**criteria, outcome=outcome)


__all__ = [
    "BUFFER_BAR_COUNT",
    "BUFFER_END_INCLUSIVE_MS",
    "BUFFER_FIRST_BAR_OPEN_MS",
    "BUFFER_FIRST_MINUTE_OPEN_MS",
    "BUFFER_LAST_BAR_OPEN_MS",
    "BUFFER_LAST_MINUTE_OPEN_MS",
    "BUFFER_MINUTE_COUNT",
    "BUFFER_REFUSED_BAR_OPEN_MS",
    "FINAL_FIT_FAILURE",
    "FIRST_2025_ORIGIN_MS",
    "HOUR_MS",
    "KRAKEN_TIMESTAMP_ROLE",
    "LABEL_HORIZON_MS",
    "LAST_2025_ORIGIN_MS",
    "MINUTE_MS",
    "OI_ELIGIBILITY_OFFSET_MS",
    "OI_TIMESTAMP_ROLE",
    "ORIGIN_COUNT_2025",
    "REFIT_EXCLUDED_TAIL_COUNT",
    "REFIT_LAST_ORIGIN_MS",
    "REFIT_NOMINAL_ORIGIN_COUNT",
    "REFIT_TRAIN_START_MS",
    "REPLICATION_COMPARISON_IDS",
    "REPLICATION_CRITERIA",
    "SEAL_BOUNDARY_MS",
    "ReplicationDecision",
    "ReplicationEvidence",
    "buffer_bar_opens",
    "buffer_dependent_origins",
    "buffer_minute_opens",
    "enumerate_2025_origins",
    "enumerate_refit_origins",
    "evaluate_replication_gate",
    "is_buffer_minute_in_scope",
    "is_refit_eligible_origin",
    "label_close_ms",
    "latest_eligible_oi_open_ms",
    "replication_comparison_id",
    "replication_stream_seed",
    "requires_2026_buffer",
    "truncate_buffer_minutes",
]
