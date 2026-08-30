"""Phase-partitioned AUC diagnostic for 24h-direction discrimination.

Read-side only. Consumes frozen per-fold sidecars; refits nothing.

Pre-registered in ``docs/research/015c-phase-auc-prereg.md`` (committed at
``c42fa5e``, strictly before any statistic was computed). Every constant in
:data:`PREREG` is frozen by that document and must not be tuned.

Why phase partitioning
----------------------
``l_fwddir_24[t] = sign(close[t+24] - close[t])``, so consecutive bars share 23
of 24 hours of label window. Partitioning test bars by ``row_index % 24`` yields
24 phases whose within-phase observations sit exactly 24 bars apart, making their
label windows adjacent and non-overlapping. This removes the overlap by
construction rather than correcting for it afterwards.

AUC rather than IC because 012 optimises a binary target and AUC measures
discrimination without requiring calibrated probabilities -- which is the
property still in question after 015b found the probabilities themselves lose to
a constant 0.500 forecast.
"""

from __future__ import annotations

import json
import math
import random
import statistics
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

__all__ = [
    "PREREG",
    "PhaseAucResult",
    "auc",
    "load_frozen_predictions",
    "phase_aucs",
    "compute_statistic",
    "bootstrap_lower_bound",
    "evaluate_phase_auc_gate",
    "within_fold_mean_auc",
    "pooled_auc",
]


# --------------------------------------------------------------------- config
@dataclass(frozen=True)
class _Prereg:
    """Constants frozen by the 015c pre-registration. Do not tune."""

    n_phases: int = 24
    block_bars: int = 168  # 7 days; exceeds 24h label + 60h feature lookback
    n_bootstrap: int = 10_000
    seed: int = 20260830
    confidence: float = 0.95
    min_year_auc: Decimal = Decimal("0.50")


PREREG = _Prereg()


class PhaseAucError(ValueError):
    """Raised when frozen inputs violate a pre-registered assumption."""


# ------------------------------------------------------------------------ AUC
def auc(scores: list[float], labels: list[int]) -> float | None:
    """Mann-Whitney U / (n_pos * n_neg), mid-ranking ties for 0.5 credit.

    Returns ``None`` when only one class is present, since AUC is undefined
    there. Callers must surface undefined cells rather than dropping them.
    """
    n = len(scores)
    if n != len(labels):
        raise PhaseAucError("scores and labels must be the same length")

    order = sorted(range(n), key=lambda i: scores[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        mid_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = mid_rank
        i = j + 1

    n_pos = sum(1 for value in labels if value == 1)
    n_neg = n - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    rank_sum_pos = sum(ranks[i] for i in range(n) if labels[i] == 1)
    return (rank_sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


# ----------------------------------------------------------------------- load
@dataclass(frozen=True)
class Bar:
    row_index: int
    phase: int
    probability: float
    label: int  # 1 = up, 0 = down
    fold_index: int


def load_frozen_predictions(sidecar_path: Path | str) -> tuple[list[Bar], int, int]:
    """Load test-bar predictions from a frozen per-fold sidecar.

    Returns ``(bars, flat_excluded, fold_count)``.

    The sidecar ``label`` field is the *binarised training target*
    (``training_metrics_logistic.py``: ``1 if direction == 1 else 0``), so
    ``label == 0`` means "down or flat", not "flat". The three-way sign lives in
    ``direction``. Flat bars must therefore be detected via ``direction``, and
    this function cross-checks the two fields on every row.
    """
    payload = json.loads(Path(sidecar_path).read_text(encoding="utf-8"))
    records = payload["records"]

    bars: list[Bar] = []
    flat_excluded = 0
    seen: set[int] = set()
    for record in records:
        fold_index = record["fold_index"]
        for prediction in record["predictions"]:
            direction = int(prediction["direction"])
            if direction == 0:
                flat_excluded += 1
                continue
            row_index = int(prediction["row_index"])
            if row_index in seen:
                raise PhaseAucError(f"duplicate row_index {row_index} in sidecar")
            seen.add(row_index)

            label = 1 if direction == 1 else 0
            if label != int(prediction["label"]):
                raise PhaseAucError(
                    f"row {row_index}: direction={direction} disagrees with "
                    f"label={prediction['label']}"
                )
            bars.append(
                Bar(
                    row_index=row_index,
                    phase=row_index % PREREG.n_phases,
                    probability=float(prediction["probability"]),
                    label=label,
                    fold_index=fold_index,
                )
            )

    bars.sort(key=lambda bar: bar.row_index)
    return bars, flat_excluded, len(records)


# ------------------------------------------------------------- the statistic
def phase_aucs(bars: list[Bar]) -> tuple[dict[int, float], int]:
    """AUC per phase. Returns ``(phase -> auc, undefined_cell_count)``."""
    buckets: list[tuple[list[float], list[int]]] = [([], []) for _ in range(PREREG.n_phases)]
    for bar in bars:
        buckets[bar.phase][0].append(bar.probability)
        buckets[bar.phase][1].append(bar.label)

    out: dict[int, float] = {}
    undefined = 0
    for phase in range(PREREG.n_phases):
        scores, labels = buckets[phase]
        value = auc(scores, labels)
        if value is None:
            undefined += 1
        else:
            out[phase] = value
    return out, undefined


@dataclass(frozen=True)
class PhaseAucResult:
    statistic: float  # T = mean(AUC - 0.5) across all cells
    year_mean_auc: dict[str, float]
    cells_used: int
    cells_undefined: int


def compute_statistic(per_year_bars: dict[str, list[Bar]]) -> PhaseAucResult:
    """Pre-registration §4: unweighted mean of ``AUC - 0.5`` over all cells.

    Every phase enters with equal weight. No phase is selected, dropped, or
    reweighted after inspection.
    """
    excesses: list[float] = []
    year_means: dict[str, float] = {}
    undefined = 0
    for year in sorted(per_year_bars):
        aucs, year_undefined = phase_aucs(per_year_bars[year])
        undefined += year_undefined
        if not aucs:
            raise PhaseAucError(f"{year}: no phase produced a defined AUC")
        excesses.extend(value - 0.5 for value in aucs.values())
        year_means[year] = statistics.fmean(aucs.values())

    return PhaseAucResult(
        statistic=statistics.fmean(excesses),
        year_mean_auc=year_means,
        cells_used=len(excesses),
        cells_undefined=undefined,
    )


# ------------------------------------------------- circular moving-block boot
def bootstrap_lower_bound(
    per_year_bars: dict[str, list[Bar]],
    n_bootstrap: int | None = None,
    seed: int | None = None,
) -> tuple[float, list[float]]:
    """Pre-registration §5: paired circular moving-block bootstrap.

    Blocks are ``PREREG.block_bars`` long and drawn circularly. Each bar carries
    ``(phase, probability, label)`` as a unit so the score/label pairing is never
    broken. Because ``block_bars`` is a multiple of ``n_phases``, every block
    contributes equally to all 24 phases and phase composition is preserved.

    Returns ``(one_sided_lower_bound, sorted_replicates)``.
    """
    n_bootstrap = PREREG.n_bootstrap if n_bootstrap is None else n_bootstrap
    seed = PREREG.seed if seed is None else seed
    randomizer = random.Random(seed)

    prepared: dict[str, tuple[list[tuple[int, float, int]], int, int]] = {}
    for year, bars in per_year_bars.items():
        series = [(bar.phase, bar.probability, bar.label) for bar in bars]
        n = len(series)
        prepared[year] = (series, n, math.ceil(n / PREREG.block_bars))

    replicates: list[float] = []
    for _ in range(n_bootstrap):
        excesses: list[float] = []
        for year in sorted(prepared):
            series, n, n_blocks = prepared[year]
            buckets: list[tuple[list[float], list[int]]] = [
                ([], []) for _ in range(PREREG.n_phases)
            ]
            for _ in range(n_blocks):
                start = randomizer.randrange(n)
                for offset in range(PREREG.block_bars):
                    phase, probability, label = series[(start + offset) % n]
                    buckets[phase][0].append(probability)
                    buckets[phase][1].append(label)
            for phase in range(PREREG.n_phases):
                scores, labels = buckets[phase]
                value = auc(scores, labels)
                if value is not None:
                    excesses.append(value - 0.5)
        replicates.append(statistics.fmean(excesses))

    replicates.sort()
    index = int((1.0 - PREREG.confidence) * len(replicates))
    return replicates[index], replicates


# ---------------------------------------------------------------- frozen gate
def evaluate_phase_auc_gate(result: PhaseAucResult, lower_bound: float) -> tuple[bool, str]:
    """Pre-registration §6. Both conditions must hold to continue.

    Returns ``(should_continue, reason)``. A ``False`` verdict terminates the
    OHLCV-only 24h-direction line; §7 forbids reversing it on the secondary
    mature-fold cut.
    """
    lower_bound_positive = lower_bound > 0.0
    min_year = min(result.year_mean_auc.values())
    years_pass = Decimal(str(min_year)) >= PREREG.min_year_auc

    reason = (
        f"lower_bound={lower_bound:+.18f} "
        f"lower_bound_positive={lower_bound_positive} "
        f"min_year_mean_auc={min_year:.18f} years_pass={years_pass}"
    )
    return (lower_bound_positive and years_pass), reason


# ------------------------------------------------- geometry comparison (§6)
def within_fold_mean_auc(bars: list[Bar]) -> tuple[float, float, int]:
    """Mean and SD of per-fold AUC over 72-bar folds.

    This is the artifact-prone geometry 015b measured in. Returns
    ``(mean, sample_sd, n_defined_folds)``. Folds whose AUC is undefined are
    excluded from the mean and not counted.
    """
    buckets: dict[int, tuple[list[float], list[int]]] = {}
    for bar in bars:
        scores, labels = buckets.setdefault(bar.fold_index, ([], []))
        scores.append(bar.probability)
        labels.append(bar.label)

    values = [
        value for scores, labels in buckets.values() if (value := auc(scores, labels)) is not None
    ]
    if len(values) < 2:
        raise PhaseAucError("need at least 2 defined folds to report mean and SD")
    return statistics.fmean(values), statistics.stdev(values), len(values)


def pooled_auc(bars: list[Bar]) -> float:
    """Single AUC over every bar in the year, with no windowing.

    Label overlap is still present here, but the 72-bar window is gone. Comparing
    this against :func:`within_fold_mean_auc` and the phase-partitioned mean
    separates the windowing artifact from the overlap artifact (015c §6).
    """
    value = auc([bar.probability for bar in bars], [bar.label for bar in bars])
    if value is None:
        raise PhaseAucError("pooled AUC undefined: only one class present")
    return value
