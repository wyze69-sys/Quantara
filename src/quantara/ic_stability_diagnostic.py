"""Deterministic read-side diagnostics for per-fold direction IC stability."""

from __future__ import annotations

import json
import random
import statistics
from decimal import Decimal, localcontext
from enum import StrEnum
from pathlib import Path

SIDECAR_SCHEMA = "quantara.ic_stability_sidecar/v1"
FOLD_COUNT = 117
RANDOM_SEED = 20260829
Q18 = Decimal("0.000000000000000001")
ZERO = Decimal(0)


class GateVerdict(StrEnum):
    PROCEED = "PROCEED"
    PROCEED_WITH_CAVEAT = "PROCEED_WITH_CAVEAT"
    STOP_PUBLISH_NEGATIVE = "STOP_PUBLISH_NEGATIVE"


def _q18(value: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 50
        return value.quantize(Q18)


def _validated_ics(ics: list[Decimal]) -> list[Decimal]:
    if len(ics) != FOLD_COUNT:
        raise ValueError(f"IC diagnostic requires exactly {FOLD_COUNT} folds")
    if any(not isinstance(ic, Decimal) or not ic.is_finite() for ic in ics):
        raise ValueError("per-fold ICs must be finite Decimal values")
    return list(ics)


def _mean(values: list[Decimal]) -> Decimal:
    return sum(values, ZERO) / Decimal(len(values))


def _percentile(values: list[Decimal], probability: Decimal) -> Decimal:
    ordered = sorted(values)
    position = Decimal(len(ordered) - 1) * probability
    lower_index = int(position)
    fraction = position - Decimal(lower_index)
    if fraction == ZERO:
        return ordered[lower_index]
    return ordered[lower_index] + (
        ordered[lower_index + 1] - ordered[lower_index]
    ) * fraction


def load_per_fold_ics(sidecar_path: Path) -> list[Decimal]:
    payload = json.loads(Path(sidecar_path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != SIDECAR_SCHEMA:
        raise ValueError(f"sidecar schema_version must be {SIDECAR_SCHEMA}")
    records = payload.get("records")
    if not isinstance(records, list) or len(records) != FOLD_COUNT:
        raise ValueError(f"sidecar must contain exactly {FOLD_COUNT} records")

    ics: list[Decimal] = []
    for expected_index, record in enumerate(records):
        if not isinstance(record, dict) or record.get("fold_index") != expected_index:
            raise ValueError("sidecar records must preserve fold order")
        raw_ic = record.get("direction_ic")
        if not isinstance(raw_ic, str):
            raise ValueError("sidecar direction_ic values must be Decimal strings")
        try:
            ic = Decimal(raw_ic)
        except Exception as exc:
            raise ValueError("sidecar direction_ic value is invalid") from exc
        if not ic.is_finite():
            raise ValueError("sidecar direction_ic values must be finite")
        ics.append(ic)
    return _validated_ics(ics)


def summarize_per_fold(ics: list[Decimal]) -> dict:
    values = _validated_ics(ics)
    with localcontext() as context:
        context.prec = 50
        ordered_indices = sorted(range(FOLD_COUNT), key=lambda index: values[index])
        worst_indices = sorted(ordered_indices[:10])
        best_indices = sorted(ordered_indices[-10:])

        def fold_values(indices: list[int]) -> list[dict]:
            return [
                {"fold_index": index, "direction_ic": _q18(values[index])}
                for index in indices
            ]

        time_series = [
            {
                "fold_index": index,
                "direction_ic": _q18(ic),
                "quarter": f"2024-Q{min(index // 30, 3) + 1}",
            }
            for index, ic in enumerate(values)
        ]
        return {
            "mean": _q18(_mean(values)),
            "median": _q18(statistics.median(values)),
            "stdev": _q18(statistics.stdev(values)),
            "p25": _q18(_percentile(values, Decimal("0.25"))),
            "p75": _q18(_percentile(values, Decimal("0.75"))),
            "min": _q18(min(values)),
            "max": _q18(max(values)),
            "count_positive": sum(ic > ZERO for ic in values),
            "count_above_0_10": sum(ic > Decimal("0.10") for ic in values),
            "best_10": fold_values(best_indices),
            "worst_10": fold_values(worst_indices),
            "time_series": time_series,
        }


def bootstrap_mean_ci(
    ics: list[Decimal], n_resamples: int = 10_000, ci: float = 0.95
) -> tuple[Decimal, Decimal]:
    values = _validated_ics(ics)
    if n_resamples <= 0:
        raise ValueError("n_resamples must be positive")
    ci_decimal = Decimal(str(ci))
    if not ZERO < ci_decimal < Decimal(1):
        raise ValueError("ci must be between 0 and 1")

    randomizer = random.Random(RANDOM_SEED)
    with localcontext() as context:
        context.prec = 50
        resampled_means = [
            _mean(
                [
                    values[randomizer.randrange(FOLD_COUNT)]
                    for _ in range(FOLD_COUNT)
                ]
            )
            for _ in range(n_resamples)
        ]
        tail = (Decimal(1) - ci_decimal) / Decimal(2)
        return (
            _q18(_percentile(resampled_means, tail)),
            _q18(_percentile(resampled_means, Decimal(1) - tail)),
        )


def permutation_test(
    ics: list[Decimal], n_permutations: int = 10_000
) -> Decimal:
    values = _validated_ics(ics)
    if n_permutations <= 0:
        raise ValueError("n_permutations must be positive")

    randomizer = random.Random(RANDOM_SEED)
    with localcontext() as context:
        context.prec = 50
        observed = abs(_mean(values))
        extreme_count = 0
        for _ in range(n_permutations):
            permuted_mean = _mean(
                [
                    ic if randomizer.random() < 0.5 else -ic
                    for ic in values
                ]
            )
            extreme_count += abs(permuted_mean) >= observed
        return _q18(Decimal(extreme_count) / Decimal(n_permutations))


def evaluate_ic_stability_gate(
    ics: list[Decimal],
) -> tuple[GateVerdict, str]:
    summary = summarize_per_fold(ics)
    lower, upper = bootstrap_mean_ci(ics)
    permutation_p = permutation_test(ics)
    stdev = summary["stdev"]
    ci_includes_zero = lower <= ZERO <= upper

    if (
        stdev > Decimal("0.20")
        or ci_includes_zero
        or permutation_p > Decimal("0.05")
    ):
        verdict = GateVerdict.STOP_PUBLISH_NEGATIVE
    elif stdev < Decimal("0.10"):
        verdict = GateVerdict.PROCEED
    else:
        verdict = GateVerdict.PROCEED_WITH_CAVEAT

    reason = (
        f"per_fold_sd={stdev} ci=({lower},{upper}) "
        f"permutation_p={permutation_p}"
    )
    return verdict, reason
