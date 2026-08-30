from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from quantara.phase_auc_diagnostic import (
    PREREG,
    Bar,
    PhaseAucError,
    auc,
    bootstrap_lower_bound,
    compute_statistic,
    evaluate_phase_auc_gate,
    load_frozen_predictions,
    phase_aucs,
    pooled_auc,
    within_fold_mean_auc,
)


# --------------------------------------------------------------------- helpers
def _brute_force_auc(scores: list[float], labels: list[int]) -> float | None:
    positives = [s for s, label in zip(scores, labels, strict=True) if label == 1]
    negatives = [s for s, label in zip(scores, labels, strict=True) if label == 0]
    if not positives or not negatives:
        return None
    total = 0.0
    for high in positives:
        for low in negatives:
            total += 1.0 if high > low else (0.5 if high == low else 0.0)
    return total / (len(positives) * len(negatives))


def _write_sidecar(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"records": records}), encoding="utf-8")


def _prediction(row_index: int, probability: str, direction: int) -> dict:
    return {
        "row_index": row_index,
        "probability": probability,
        "direction": direction,
        "label": 1 if direction == 1 else 0,
    }


# ------------------------------------------------------------------- AUC tests
def test_auc_matches_brute_force_on_tie_heavy_random_cases() -> None:
    randomizer = random.Random(20260830)
    for _ in range(200):
        size = randomizer.randrange(4, 40)
        scores = [randomizer.randrange(0, 5) / 4.0 for _ in range(size)]
        labels = [randomizer.randrange(2) for _ in range(size)]
        assert auc(scores, labels) == _brute_force_auc(scores, labels)


@pytest.mark.parametrize(
    ("scores", "labels", "expected"),
    [
        ([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1], 1.0),
        ([0.9, 0.8, 0.2, 0.1], [0, 0, 1, 1], 0.0),
        ([0.5, 0.5, 0.5, 0.5], [0, 1, 0, 1], 0.5),
    ],
)
def test_auc_boundary_cases(scores, labels, expected) -> None:
    assert auc(scores, labels) == expected


def test_auc_is_undefined_for_single_class() -> None:
    assert auc([0.1, 0.2], [1, 1]) is None
    assert auc([0.1, 0.2], [0, 0]) is None


def test_auc_rejects_mismatched_lengths() -> None:
    with pytest.raises(PhaseAucError):
        auc([0.1, 0.2], [1])


# ------------------------------------------------------------------ load tests
def test_load_excludes_flat_direction_not_zero_label(tmp_path: Path) -> None:
    """label==0 means "down or flat"; only direction==0 is genuinely flat."""
    target = tmp_path / "per_fold_flat.json"
    _write_sidecar(
        target,
        [
            {
                "fold_index": 0,
                "predictions": [
                    _prediction(0, "0.60", 1),
                    _prediction(1, "0.40", -1),  # label 0, but NOT flat
                    _prediction(2, "0.50", 0),  # genuinely flat -> excluded
                ],
            }
        ],
    )

    bars, flat_excluded, fold_count = load_frozen_predictions(target)

    assert flat_excluded == 1
    assert fold_count == 1
    assert [bar.row_index for bar in bars] == [0, 1]
    assert [bar.label for bar in bars] == [1, 0]


def test_load_assigns_phase_by_row_index_modulo(tmp_path: Path) -> None:
    target = tmp_path / "per_fold_phase.json"
    rows = [0, 1, 23, 24, 25, 48]
    _write_sidecar(
        target,
        [
            {
                "fold_index": 0,
                "predictions": [
                    _prediction(row, "0.50", 1 if index % 2 == 0 else -1)
                    for index, row in enumerate(rows)
                ],
            }
        ],
    )

    bars, _, _ = load_frozen_predictions(target)

    assert [bar.phase for bar in bars] == [0, 1, 23, 0, 1, 0]


def test_load_rejects_label_direction_disagreement(tmp_path: Path) -> None:
    target = tmp_path / "per_fold_bad.json"
    _write_sidecar(
        target,
        [
            {
                "fold_index": 0,
                "predictions": [
                    {
                        "row_index": 0,
                        "probability": "0.60",
                        "direction": 1,
                        "label": 0,
                    }
                ],
            }
        ],
    )

    with pytest.raises(PhaseAucError, match="disagrees"):
        load_frozen_predictions(target)


def test_load_rejects_duplicate_row_index(tmp_path: Path) -> None:
    target = tmp_path / "per_fold_dup.json"
    _write_sidecar(
        target,
        [
            {
                "fold_index": 0,
                "predictions": [_prediction(5, "0.60", 1)],
            },
            {
                "fold_index": 1,
                "predictions": [_prediction(5, "0.40", -1)],
            },
        ],
    )

    with pytest.raises(PhaseAucError, match="duplicate row_index"):
        load_frozen_predictions(target)


# ------------------------------------------------------------ statistic tests
def _bars_with_auc(target_auc: float, phase_count: int = PREREG.n_phases) -> list[Bar]:
    """Build bars where every phase has a known AUC of 1.0 or 0.0."""
    bars: list[Bar] = []
    row = 0
    for _ in range(4):
        for phase in range(phase_count):
            up_prob = 0.9 if target_auc == 1.0 else 0.1
            down_prob = 0.1 if target_auc == 1.0 else 0.9
            bars.append(Bar(row, phase, up_prob, 1, 0))
            bars.append(Bar(row + 1, phase, down_prob, 0, 0))
            row += 2
    return bars


def test_phase_aucs_reports_undefined_cells() -> None:
    bars = [Bar(0, 0, 0.6, 1, 0), Bar(24, 0, 0.4, 0, 0), Bar(1, 1, 0.5, 1, 0)]
    aucs, undefined = phase_aucs(bars)

    assert aucs[0] == 1.0
    assert 1 not in aucs
    assert undefined == PREREG.n_phases - 1


def test_compute_statistic_is_unweighted_mean_excess() -> None:
    perfect = _bars_with_auc(1.0)
    inverted = _bars_with_auc(0.0)

    result = compute_statistic({"2022": perfect, "2023": inverted})

    assert result.cells_used == 2 * PREREG.n_phases
    assert result.cells_undefined == 0
    assert result.statistic == pytest.approx(0.0)
    assert result.year_mean_auc["2022"] == pytest.approx(1.0)
    assert result.year_mean_auc["2023"] == pytest.approx(0.0)


def test_compute_statistic_rejects_year_with_no_defined_cell() -> None:
    with pytest.raises(PhaseAucError, match="no phase"):
        compute_statistic({"2022": [Bar(0, 0, 0.5, 1, 0)]})


# ----------------------------------------------------------- bootstrap + gate
def test_bootstrap_is_deterministic_under_frozen_seed() -> None:
    bars = _bars_with_auc(1.0)
    first, replicates_first = bootstrap_lower_bound({"2022": bars}, n_bootstrap=20)
    second, replicates_second = bootstrap_lower_bound({"2022": bars}, n_bootstrap=20)

    assert first == second
    assert replicates_first == replicates_second


def test_bootstrap_block_length_preserves_phase_composition() -> None:
    """block_bars must be a multiple of n_phases, else phases resample unevenly."""
    assert PREREG.block_bars % PREREG.n_phases == 0


def test_gate_requires_both_conditions() -> None:
    passing = compute_statistic({"2022": _bars_with_auc(1.0)})

    should_continue, reason = evaluate_phase_auc_gate(passing, lower_bound=0.01)
    assert should_continue is True
    assert "lower_bound_positive=True" in reason

    should_continue, _ = evaluate_phase_auc_gate(passing, lower_bound=-0.01)
    assert should_continue is False

    failing = compute_statistic({"2022": _bars_with_auc(0.0)})
    should_continue, _ = evaluate_phase_auc_gate(failing, lower_bound=0.01)
    assert should_continue is False


def test_gate_rejects_when_any_single_year_falls_below_half() -> None:
    mixed = compute_statistic({"2022": _bars_with_auc(1.0), "2023": _bars_with_auc(0.0)})
    should_continue, _ = evaluate_phase_auc_gate(mixed, lower_bound=0.01)
    assert should_continue is False


def test_prereg_constants_are_frozen() -> None:
    """Guards against silent tuning of pre-registered parameters."""
    assert PREREG.n_phases == 24
    assert PREREG.block_bars == 168
    assert PREREG.n_bootstrap == 10_000
    assert PREREG.seed == 20260830
    assert PREREG.confidence == 0.95


# ------------------------------------------------------ geometry comparison
def test_within_fold_mean_auc_averages_per_fold_not_pooled() -> None:
    """Two folds each perfectly separating, but on disjoint score ranges.

    Within-fold AUC is 1.0 for both. Pooled AUC is lower, because fold B's down
    bars outrank fold A's up bars. This is the windowing artifact in miniature.
    """
    bars = [
        Bar(0, 0, 0.20, 1, 0),
        Bar(1, 1, 0.10, 0, 0),
        Bar(2, 2, 0.90, 1, 1),
        Bar(3, 3, 0.80, 0, 1),
    ]

    mean, sd, n_folds = within_fold_mean_auc(bars)

    assert mean == pytest.approx(1.0)
    assert sd == pytest.approx(0.0)
    assert n_folds == 2
    assert pooled_auc(bars) == pytest.approx(0.75)
    assert pooled_auc(bars) < mean


def test_within_fold_skips_single_class_folds() -> None:
    bars = [
        Bar(0, 0, 0.60, 1, 0),
        Bar(1, 1, 0.40, 0, 0),
        Bar(2, 2, 0.90, 1, 1),
        Bar(3, 3, 0.80, 1, 1),  # fold 1 is all-up -> undefined
        Bar(4, 4, 0.30, 1, 2),
        Bar(5, 5, 0.70, 0, 2),
    ]

    _, _, n_folds = within_fold_mean_auc(bars)

    assert n_folds == 2


def test_within_fold_requires_two_defined_folds() -> None:
    with pytest.raises(PhaseAucError, match="at least 2"):
        within_fold_mean_auc([Bar(0, 0, 0.6, 1, 0), Bar(1, 1, 0.4, 0, 0)])


def test_pooled_auc_rejects_single_class() -> None:
    with pytest.raises(PhaseAucError, match="only one class"):
        pooled_auc([Bar(0, 0, 0.6, 1, 0), Bar(1, 1, 0.4, 1, 0)])
