"""Exact-Decimal ridge walk-forward metric tests for slice 011."""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext

import pytest

from quantara.training_metrics import (
    MetricDomainError,
    build_training_records,
    build_training_summaries,
    fit_ridge_matrix,
    quantize_q18,
)


def _independent_two_feature_expected(
    x: list[list[Decimal]], y: list[Decimal]
) -> tuple[list[Decimal], Decimal]:
    """Independent Decimal 2x2 normal-equation oracle embedded in the test."""
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        n = Decimal(len(x))
        means = [sum(row[j] for row in x) / n for j in range(2)]
        stds = [
            (sum((row[j] - means[j]) ** 2 for row in x) / n).sqrt()
            for j in range(2)
        ]
        z = [[(row[j] - means[j]) / stds[j] for j in range(2)] for row in x]
        y_mean = sum(y) / n
        yc = [value - y_mean for value in y]
        a = sum(row[0] * row[0] for row in z) + Decimal(1)
        b = sum(row[0] * row[1] for row in z)
        d = sum(row[1] * row[1] for row in z) + Decimal(1)
        c0 = sum(row[0] * value for row, value in zip(z, yc, strict=True))
        c1 = sum(row[1] * value for row, value in zip(z, yc, strict=True))
        determinant = a * d - b * b
        return [(c0 * d - b * c1) / determinant, (a * c1 - b * c0) / determinant], y_mean


def test_hand_computed_two_feature_ridge_and_determinism() -> None:
    x = [
        [Decimal("1"), Decimal("2")],
        [Decimal("2"), Decimal("1")],
        [Decimal("3"), Decimal("5")],
        [Decimal("5"), Decimal("4")],
    ]
    y = [Decimal("1"), Decimal("2"), Decimal("4"), Decimal("8")]
    expected_w, expected_b = _independent_two_feature_expected(x, y)
    first = fit_ridge_matrix(x, y)
    second = fit_ridge_matrix(x, y)
    assert first == second
    assert [quantize_q18(value) for value in first["coefficients"]] == [
        quantize_q18(value) for value in expected_w
    ]
    assert first["intercept"] == expected_b
    assert first["means"] == [Decimal("2.75"), Decimal("3")]


def test_zero_std_and_float_inputs_rejected() -> None:
    with pytest.raises(MetricDomainError, match="standard deviation"):
        fit_ridge_matrix(
            [[Decimal("1"), Decimal("2")], [Decimal("1"), Decimal("3")]],
            [Decimal("1"), Decimal("2")],
        )
    with pytest.raises(MetricDomainError, match="binary float"):
        fit_ridge_matrix(
            [[Decimal("1"), 2.0], [Decimal("2"), Decimal("3")]],
            [Decimal("1"), Decimal("2")],
        )


def _rows(count: int = 220) -> list[tuple]:
    rows = []
    for i in range(count + 4):
        d = Decimal(i)
        target = d / Decimal("100") - Decimal("1")
        direction = 1 if i % 2 == 0 else -1
        rows.append(
            (
                i,
                d + Decimal("1"),
                (d * d) + Decimal("2"),
                Decimal((i % 7) + 1),
                Decimal((i % 11) + 2),
                target,
                direction,
            )
        )
    return rows


def test_fold_training_counts_metrics_and_causal_baseline_tie() -> None:
    rows = _rows()
    folds = [
        {
            "fold_id": 0,
            "train_range": [0, 200],
            "embargo_range": [200, 224],
            "test_range": [224, 224],
        }
    ]
    # Give the fold a four-row test segment while preserving the 24-row embargo.
    rows.extend(_rows(4)[-4:])
    folds[0]["test_range"] = [224, 228]
    records = build_training_records(folds, rows)
    record = records[0]
    assert record["usable_train_count"] == 200
    assert record["predicted_count"] == 4
    assert record["solver_deterministic"] is True
    assert record["baselines"]["majority_class_train_window"]["predicted_direction"] == 1
    assert record["baselines"]["majority_class_train_window"][
        "directional_accuracy"
    ] == "0.500000000000000000"
    assert record["baselines"]["sign_f_ret_1"]["directional_accuracy"] == (
        "0.500000000000000000"
    )
    assert len(record["pearson_ic"].split(".")[1]) == 18
    assert Decimal(record["mse"]) >= 0
    assert Decimal("0") <= Decimal(record["directional_accuracy"]) <= Decimal("1")
    assert len(record["predictions"]) == 4


def test_minimum_train_floor_and_null_accounting() -> None:
    rows = _rows(200)
    rows[0] = tuple([rows[0][0], None, *rows[0][2:]])
    fold = {
        "fold_id": 0,
        "train_range": [0, 200],
        "embargo_range": [200, 224],
        "test_range": [224, 228],
    }
    with pytest.raises(MetricDomainError, match="at least 200"):
        build_training_records([fold], rows + _rows(4)[-4:])


def test_summaries_and_baseline_side_by_side() -> None:
    records = build_training_records(
        [
            {
                "fold_id": 0,
                "train_range": [0, 200],
                "embargo_range": [200, 224],
                "test_range": [224, 228],
            }
        ],
        _rows() + _rows(4)[-4:],
    )
    summaries, baselines = build_training_summaries(records)
    assert [item["metric"] for item in summaries] == [
        "pearson_ic",
        "directional_accuracy",
        "mse",
    ]
    assert set(baselines) == {"majority_class_train_window", "sign_f_ret_1"}
