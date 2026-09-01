"""Exact-Decimal logistic IRLS metric and kill-criteria tests for slice 012."""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext

import pytest

from quantara.training_metrics_logistic import (
    ETA_CLAMP,
    KILL_CRITERIA,
    MU_CLAMP,
    MetricDomainError,
    brier,
    build_logistic_training_records,
    build_logistic_training_summaries,
    clamp_eta,
    clamp_mu,
    climatology_probability,
    direction_ic,
    direction_ic_with_definition,
    evaluate_criterion_outcomes,
    evaluate_kill_criteria,
    fit_logistic_irls,
    log_loss,
    logistic_sigmoid,
    predict_probability,
    quantize_q18,
    return_ic_with_definition,
)

_ORACLE_CONTEXT = Context(prec=50, rounding=ROUND_HALF_EVEN)


def _cramer3(matrix: list[list[Decimal]], vector: list[Decimal]) -> list[Decimal]:
    """Independent 3x3 solve by Cramer's rule (not Gauss elimination)."""

    def det(m: list[list[Decimal]]) -> Decimal:
        return (
            m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
            - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
        )

    base = det(matrix)
    solution = []
    for column in range(3):
        replaced = [
            [vector[row] if index == column else matrix[row][index] for index in range(3)]
            for row in range(3)
        ]
        solution.append(det(replaced) / base)
    return solution


def _independent_two_feature_irls(
    x: list[list[Decimal]], y: list[int]
) -> tuple[list[Decimal], int]:
    """Independent Decimal IRLS oracle for a two-feature logistic fit."""
    with localcontext(_ORACLE_CONTEXT):
        n = Decimal(len(x))
        means = [sum(row[j] for row in x) / n for j in range(2)]
        stds = [(sum((row[j] - means[j]) ** 2 for row in x) / n).sqrt() for j in range(2)]
        design = [
            [Decimal(1)] + [(row[j] - means[j]) / stds[j] for j in range(2)] for row in x
        ]
        labels = [Decimal(value) for value in y]
        low = Decimal("0.000000000001")
        high = Decimal(1) - low
        beta = [Decimal(0), Decimal(0), Decimal(0)]
        for iteration in range(1, 51):
            eta = []
            for row in design:
                value = sum(row[k] * beta[k] for k in range(3))
                if value > Decimal(24):
                    value = Decimal(24)
                elif value < Decimal(-24):
                    value = Decimal(-24)
                eta.append(value)
            mu = []
            for value in eta:
                probability = Decimal(1) / (Decimal(1) + (-value).exp())
                if probability < low:
                    probability = low
                elif probability > high:
                    probability = high
                mu.append(probability)
            weights = [value * (Decimal(1) - value) for value in mu]
            working = [eta[i] + (labels[i] - mu[i]) / weights[i] for i in range(len(design))]
            normal = [
                [
                    sum(design[i][a] * weights[i] * design[i][b] for i in range(len(design)))
                    for b in range(3)
                ]
                for a in range(3)
            ]
            for k in (1, 2):
                normal[k][k] += Decimal(1)
            rhs = [
                sum(design[i][a] * weights[i] * working[i] for i in range(len(design)))
                for a in range(3)
            ]
            updated = _cramer3(normal, rhs)
            converged = all(
                abs(updated[k] - beta[k]) < Decimal("0.000000000001") for k in range(3)
            )
            beta = updated
            if converged:
                return beta, iteration
        raise AssertionError("oracle did not converge")


_TWO_FEATURE_X = [
    [Decimal("1"), Decimal("2")],
    [Decimal("2"), Decimal("1")],
    [Decimal("3"), Decimal("5")],
    [Decimal("5"), Decimal("4")],
    [Decimal("6"), Decimal("9")],
    [Decimal("8"), Decimal("7")],
    [Decimal("9"), Decimal("3")],
    [Decimal("11"), Decimal("6")],
]
_TWO_FEATURE_Y = [0, 1, 0, 1, 1, 0, 1, 1]


def test_hand_computed_two_feature_irls_matches_independent_oracle() -> None:
    expected_beta, expected_iterations = _independent_two_feature_irls(
        _TWO_FEATURE_X, _TWO_FEATURE_Y
    )
    fit = fit_logistic_irls(_TWO_FEATURE_X, _TWO_FEATURE_Y)
    assert fit["converged_iterations"] == expected_iterations
    assert quantize_q18(fit["intercept"]) == quantize_q18(expected_beta[0])
    assert [quantize_q18(value) for value in fit["coefficients"]] == [
        quantize_q18(value) for value in expected_beta[1:]
    ]
    assert fit["means"] == [Decimal("5.625"), Decimal("4.625")]


def test_irls_double_solve_is_exactly_deterministic() -> None:
    first = fit_logistic_irls(_TWO_FEATURE_X, _TWO_FEATURE_Y)
    second = fit_logistic_irls(_TWO_FEATURE_X, _TWO_FEATURE_Y)
    assert first == second


def test_eta_and_mu_clamp_behaviour() -> None:
    assert clamp_eta(Decimal("30")) == (ETA_CLAMP, True)
    assert clamp_eta(Decimal("-30")) == (-ETA_CLAMP, True)
    assert clamp_eta(Decimal("1.5")) == (Decimal("1.5"), False)
    assert clamp_eta(ETA_CLAMP) == (ETA_CLAMP, False)
    assert clamp_mu(Decimal("0")) == (MU_CLAMP, True)
    assert clamp_mu(Decimal("1")) == (Decimal(1) - MU_CLAMP, True)
    assert clamp_mu(Decimal("0.25")) == (Decimal("0.25"), False)


def test_sigmoid_at_the_eta_clamp_stays_inside_the_separation_guard() -> None:
    assert logistic_sigmoid(Decimal(0)) == Decimal("0.5")
    high = logistic_sigmoid(ETA_CLAMP)
    low = logistic_sigmoid(-ETA_CLAMP)
    assert low < Decimal("0.5") < high < Decimal(1)
    # The eta clamp keeps mu strictly inside the separation guard, so the mu
    # clamp is a defensive redundancy rather than a reachable branch.
    assert clamp_mu(high) == (high, False)
    assert clamp_mu(low) == (low, False)


def test_zero_std_float_and_label_domain_rejected() -> None:
    with pytest.raises(MetricDomainError, match="standard deviation"):
        fit_logistic_irls([[Decimal("1"), Decimal("2")], [Decimal("1"), Decimal("3")]], [0, 1])
    with pytest.raises(MetricDomainError, match="binary float"):
        fit_logistic_irls([[Decimal("1"), 2.0], [Decimal("2"), Decimal("3")]], [0, 1])
    with pytest.raises(MetricDomainError, match="label"):
        fit_logistic_irls([[Decimal("1"), Decimal("2")], [Decimal("2"), Decimal("3")]], [0, -1])
    with pytest.raises(MetricDomainError, match="label"):
        fit_logistic_irls(
            [[Decimal("1"), Decimal("2")], [Decimal("2"), Decimal("3")]], [False, True]
        )


def test_non_convergence_is_a_loud_domain_error() -> None:
    with pytest.raises(MetricDomainError, match="irls_did_not_converge"):
        fit_logistic_irls(_TWO_FEATURE_X, _TWO_FEATURE_Y, max_iterations=1)


def _ln(value: str) -> Decimal:
    with localcontext(_ORACLE_CONTEXT):
        return Decimal(value).ln()


def test_log_loss_and_brier_against_hand_values() -> None:
    half = [Decimal("0.5"), Decimal("0.5")]
    assert quantize_q18(log_loss(half, [1, 0])) == quantize_q18(-_ln("0.5"))
    assert brier(half, [1, 0]) == Decimal("0.25")
    assert quantize_q18(log_loss([Decimal("1"), Decimal("0")], [1, 0])) == quantize_q18(
        -_ln(str(Decimal(1) - MU_CLAMP))
    )
    # A zero probability on a positive label is clamped, not a division by zero.
    assert log_loss([Decimal("0")], [1]) == -_ln("0.000000000001")
    assert brier([Decimal("0.25")], [1]) == Decimal("0.5625")


def test_direction_ic_and_climatology_probability() -> None:
    probabilities = [Decimal("0.1"), Decimal("0.4"), Decimal("0.6"), Decimal("0.9")]
    assert direction_ic(probabilities, [0, 0, 1, 1]) > Decimal("0.85")
    assert direction_ic(probabilities, [1, 1, 0, 0]) < Decimal("-0.85")
    assert climatology_probability(3, 1) == Decimal("0.750000000000000000")
    assert climatology_probability(4706, 4051) == quantize_q18(Decimal(4706) / Decimal(8757))
    with pytest.raises(MetricDomainError, match="climatology"):
        climatology_probability(0, 0)


def test_single_class_fold_ic_is_zero_and_flagged_undefined() -> None:
    probabilities = [Decimal("0.2"), Decimal("0.4"), Decimal("0.7")]
    # All-one-class labels: correlation is mathematically undefined.
    with pytest.raises(MetricDomainError, match="zero variance"):
        direction_ic(probabilities, [0, 0, 0])
    value, defined = direction_ic_with_definition(probabilities, [0, 0, 0])
    assert defined is False
    assert value == Decimal("0.000000000000000000")
    value, defined = direction_ic_with_definition(probabilities, [0, 1, 1])
    assert defined is True
    assert value == direction_ic(probabilities, [0, 1, 1])

    constant = [(Decimal("0.5"), Decimal("0.1")), (Decimal("0.5"), Decimal("0.2"))]
    value, defined = return_ic_with_definition(constant)
    assert (value, defined) == (Decimal("0.000000000000000000"), False)
    varying = [(Decimal("0.4"), Decimal("0.1")), (Decimal("0.6"), Decimal("0.2"))]
    value, defined = return_ic_with_definition(varying)
    assert defined is True
    assert value == Decimal(1)


def _kill_inputs(
    accuracy: str,
    ic: str,
    loss: str,
    score: str,
    majority_accuracy: str = "0.500000000000000000",
) -> tuple[list[dict], dict]:
    summaries = [
        {"metric": "directional_accuracy", "equal_weight_mean": accuracy},
        {"metric": "log_loss", "equal_weight_mean": loss},
        {"metric": "brier", "equal_weight_mean": score},
        {"metric": "direction_ic", "equal_weight_mean": ic},
        {"metric": "pearson_ic", "equal_weight_mean": "0.000000000000000000"},
    ]
    baselines = {
        "majority_class_train_window": {
            "directional_accuracy": {"equal_weight_mean": majority_accuracy}
        },
        "sign_f_ret_1": {
            "directional_accuracy": {"equal_weight_mean": "0.500000000000000000"}
        },
        "climatology_p": {
            "directional_accuracy": {"equal_weight_mean": "0.500000000000000000"},
            "log_loss": {"equal_weight_mean": "0.693147180559945309"},
            "brier": {"equal_weight_mean": "0.250000000000000000"},
        },
    }
    return summaries, baselines


def _kill_block(accuracy: str, ic: str, loss: str, score: str) -> dict:
    summaries, baselines = _kill_inputs(accuracy, ic, loss, score)
    return evaluate_kill_criteria(summaries, baselines)


def test_independent_outcomes_keep_k1_pass_when_another_criterion_fails() -> None:
    summaries, baselines = _kill_inputs(
        accuracy="0.518584146160487831",
        ic="-0.036035220107766154",
        loss="0.703652372374689632",
        score="0.254166614144309991",
        majority_accuracy="0.507449088689223463",
    )

    # The immutable historical gate used 2024's fixed K1 threshold and therefore
    # remains reproducible, but it is not the cross-year criterion report.
    historical = evaluate_kill_criteria(summaries, baselines)
    assert historical["results"]["k1_directional_accuracy"] is False

    outcomes = evaluate_criterion_outcomes(summaries, baselines)
    assert outcomes["results"] == {
        "k1_directional_accuracy": True,
        "k2_direction_ic": False,
        "k3_log_loss": True,
        "k4_brier": False,
    }
    assert outcomes["all_passed"] is False
    assert outcomes["references"]["k1_directional_accuracy"] == {
        "kind": "same_sample_majority_class_train_window",
        "value": "0.507449088689223463",
    }


def test_kill_criteria_boundaries_pass_and_fail_exactly() -> None:
    exact = _kill_block(
        KILL_CRITERIA["directional_accuracy_min"],
        KILL_CRITERIA["direction_ic_min"],
        KILL_CRITERIA["log_loss_max"],
        KILL_CRITERIA["brier_max"],
    )
    assert exact["all_passed"] is True
    assert exact["results"] == {
        "k1_directional_accuracy": True,
        "k2_direction_ic": True,
        "k3_log_loss": True,
        "k4_brier": True,
    }
    assert exact["constants"] == {
        "directional_accuracy_min": "0.534900284900284900",
        "direction_ic_min": "0.020000000000000000",
        "log_loss_max": "0.762500000000000000",
        "brier_max": "0.250000000000000000",
    }

    just_under_k1 = _kill_block(
        "0.534900284900284899",
        KILL_CRITERIA["direction_ic_min"],
        KILL_CRITERIA["log_loss_max"],
        KILL_CRITERIA["brier_max"],
    )
    assert just_under_k1["results"]["k1_directional_accuracy"] is False
    assert just_under_k1["all_passed"] is False

    just_under_k2 = _kill_block(
        KILL_CRITERIA["directional_accuracy_min"],
        "0.019999999999999999",
        KILL_CRITERIA["log_loss_max"],
        KILL_CRITERIA["brier_max"],
    )
    assert just_under_k2["results"] == {
        "k1_directional_accuracy": True,
        "k2_direction_ic": False,
        "k3_log_loss": True,
        "k4_brier": True,
    }

    just_over_k3 = _kill_block(
        KILL_CRITERIA["directional_accuracy_min"],
        KILL_CRITERIA["direction_ic_min"],
        "0.762500000000000001",
        KILL_CRITERIA["brier_max"],
    )
    assert just_over_k3["results"]["k3_log_loss"] is False

    just_over_k4 = _kill_block(
        KILL_CRITERIA["directional_accuracy_min"],
        KILL_CRITERIA["direction_ic_min"],
        KILL_CRITERIA["log_loss_max"],
        "0.250000000000000001",
    )
    assert just_over_k4["results"]["k4_brier"] is False
    assert just_over_k4["observed"]["brier_mean"] == "0.250000000000000001"
    assert just_over_k4["observed"]["climatology_p_log_loss_mean"] == (
        "0.693147180559945309"
    )
    assert just_over_k4["observed"][
        "majority_class_train_window_directional_accuracy_mean"
    ] == "0.500000000000000000"


def _logistic_rows(count: int) -> list[tuple]:
    rows = []
    for index in range(count):
        rows.append(
            (
                1704067200000 + index * 3600000,
                Decimal((index % 17) - 8) / Decimal(10),
                Decimal((index * 7 % 23) - 11),
                Decimal((index % 7) + 1),
                Decimal((index % 11) + 2),
                Decimal((index % 13) - 6) / Decimal(100),
                1 if (index % 5) in (0, 1, 2) else -1,
            )
        )
    return rows


def _fold() -> dict:
    return {
        "fold_id": 0,
        "train_range": [0, 240],
        "embargo_range": [240, 264],
        "test_range": [264, 270],
    }


def _fixture_rows() -> list[tuple]:
    rows = _logistic_rows(270)
    for index in (10, 11):
        rows[index] = (*rows[index][:6], 0)
    rows[264] = (*rows[264][:6], 0)
    rows[265] = (rows[265][0], None, None, None, None, rows[265][5], rows[265][6])
    return rows


def test_fold_records_exclude_zero_and_null_rows_with_causal_baselines() -> None:
    rows = _fixture_rows()
    records = build_logistic_training_records([_fold()], rows)
    record = records[0]
    assert record["train_row_count"] == 240
    assert record["usable_train_count"] == 238
    assert record["excluded_train_count"] == 2
    assert record["zero_train_label_count"] == 2
    assert record["test_row_count"] == 6
    assert record["predicted_count"] == 4
    assert record["excluded_test_count"] == 2
    assert record["zero_label_count"] == 1
    assert record["feature_null_count"] == 1
    assert record["solver_deterministic"] is True
    assert record["converged_iterations"] >= 1
    assert record["mu_clamp_count"] == 0
    assert len(record["predictions"]) == 4
    for prediction in record["predictions"]:
        assert Decimal(0) < Decimal(prediction["probability"]) < Decimal(1)
        assert prediction["label"] in (0, 1)
        assert prediction["direction"] in (-1, 1)
        assert prediction["predicted_direction"] in (-1, 1)
        assert (prediction["label"] == 1) == (prediction["direction"] == 1)

    labels = [row[6] for row in rows[0:240] if row[6] is not None]
    up_count = labels.count(1)
    down_count = labels.count(-1)
    baselines = record["baselines"]
    assert set(baselines) == {
        "majority_class_train_window",
        "sign_f_ret_1",
        "climatology_p",
    }
    assert baselines["majority_class_train_window"]["train_up_count"] == up_count
    assert baselines["majority_class_train_window"]["train_down_count"] == down_count
    assert baselines["majority_class_train_window"]["predicted_direction"] == (
        1 if up_count >= down_count else -1
    )
    assert baselines["climatology_p"]["probability"] == format(
        climatology_probability(up_count, down_count), "f"
    )

    probabilities = [Decimal(item["probability"]) for item in record["predictions"]]
    scored_labels = [item["label"] for item in record["predictions"]]
    assert record["log_loss"] == format(quantize_q18(log_loss(probabilities, scored_labels)), "f")
    assert record["brier"] == format(quantize_q18(brier(probabilities, scored_labels)), "f")
    assert record["direction_ic"] == format(
        quantize_q18(direction_ic(probabilities, scored_labels)), "f"
    )
    assert record["direction_ic_defined"] is True
    assert record["pearson_ic_defined"] is True
    for name in (
        "directional_accuracy",
        "log_loss",
        "brier",
        "direction_ic",
        "pearson_ic",
    ):
        assert len(record[name].split(".")[1]) == 18


def test_training_uses_only_train_rows_and_predicts_with_the_fold_fit() -> None:
    rows = _fixture_rows()
    record = build_logistic_training_records([_fold()], rows)[0]
    poisoned = list(rows)
    for index in range(266, 270):
        row = poisoned[index]
        poisoned[index] = (
            row[0],
            row[1] + Decimal("1"),
            row[2] + Decimal("1"),
            row[3] + Decimal("1"),
            row[4] + Decimal("1"),
            row[5],
            row[6],
        )
    unchanged = build_logistic_training_records([_fold()], poisoned)[0]
    assert unchanged["coefficients"] == record["coefficients"]
    assert unchanged["intercept"] == record["intercept"]
    assert unchanged["feature_means"] == record["feature_means"]
    assert unchanged["feature_stds"] == record["feature_stds"]
    assert unchanged["predictions"] != record["predictions"]

    usable = [row for row in rows[0:240] if row[6] not in (None, 0)]
    fit = fit_logistic_irls(
        [list(row[1:5]) for row in usable],
        [1 if row[6] == 1 else 0 for row in usable],
    )
    for prediction in record["predictions"]:
        source = rows[prediction["row_index"]]
        probability, _ = predict_probability(fit, list(source[1:5]))
        assert format(probability, "f") == prediction["probability"]


def test_single_class_test_fold_records_zero_ic_instead_of_failing() -> None:
    rows = _fixture_rows()
    # Force every eligible scored row in the fold to the same direction, as
    # 2024 fold 56 genuinely is.
    for index in range(264, 270):
        rows[index] = (*rows[index][:6], -1)
    record = build_logistic_training_records([_fold()], rows)[0]
    assert record["predicted_count"] == 5
    assert record["direction_ic"] == "0.000000000000000000"
    assert record["direction_ic_defined"] is False
    assert record["pearson_ic_defined"] is True
    summaries, _ = build_logistic_training_summaries([record])
    ic_summary = next(item for item in summaries if item["metric"] == "direction_ic")
    assert ic_summary["defined_fold_count"] == 0
    assert ic_summary["equal_weight_mean"] == "0.000000000000000000"


def test_prediction_eta_clamp_is_counted() -> None:
    rows = _fixture_rows()
    rows[266] = (
        rows[266][0],
        Decimal("100000"),
        Decimal("100000"),
        Decimal("100000"),
        Decimal("100000"),
        rows[266][5],
        rows[266][6],
    )
    record = build_logistic_training_records([_fold()], rows)[0]
    assert record["predict_eta_clamp_count"] >= 1


def test_minimum_usable_train_floor_is_enforced() -> None:
    rows = _logistic_rows(270)
    for index in range(0, 45):
        rows[index] = (*rows[index][:6], 0)
    with pytest.raises(MetricDomainError, match="at least 200"):
        build_logistic_training_records([_fold()], rows)


def test_summaries_and_baseline_summaries_cover_every_metric() -> None:
    records = build_logistic_training_records([_fold()], _fixture_rows())
    summaries, baselines = build_logistic_training_summaries(records)
    assert [item["metric"] for item in summaries] == [
        "directional_accuracy",
        "log_loss",
        "brier",
        "direction_ic",
        "pearson_ic",
    ]
    assert all(item["fold_count"] == 1 for item in summaries)
    assert all(item["total_predicted_count"] == 4 for item in summaries)
    assert all(item["defined_fold_count"] == 1 for item in summaries)
    assert set(baselines) == {
        "majority_class_train_window",
        "sign_f_ret_1",
        "climatology_p",
    }
    assert set(baselines["climatology_p"]) == {
        "directional_accuracy",
        "log_loss",
        "brier",
    }
    assert set(baselines["sign_f_ret_1"]) == {"directional_accuracy"}
    assert set(baselines["majority_class_train_window"]) == {"directional_accuracy"}
    block = evaluate_kill_criteria(summaries, baselines)
    assert set(block) == {"constants", "observed", "results", "all_passed"}
    assert block["observed"]["directional_accuracy_mean"] == next(
        item["equal_weight_mean"]
        for item in summaries
        if item["metric"] == "directional_accuracy"
    )
