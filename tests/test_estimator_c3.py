from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Mapping
from decimal import Decimal, DivisionByZero, localcontext
from fractions import Fraction
from pathlib import Path

import pytest
import yaml

import quantara.estimator_c3 as estimator_c3
from quantara.bootstrap_b4 import SplitMix64, derive_stream_seed
from quantara.estimator_c3 import (
    COMPARISON_IDS,
    HYPOTHESIS_ORDER,
    CalibrationFit,
    EstimatorC3Failure,
    HypothesisEvidence,
    calibration_slope_passes,
    evaluate_optional_family,
    fit_bound_logistic,
    fit_calibration,
    fit_candidate,
    holm_step_down,
)
from quantara.training_metrics_logistic import (
    DECIMAL_CONTEXT,
    ETA_CLAMP,
    MAX_ITERATIONS,
    MU_CLAMP,
    RIDGE_LAMBDA,
    STORAGE_QUANTUM,
    TOLERANCE,
    _standardization,
    clamp_mu,
    fit_logistic_irls,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
V11_YAML_PATH = REPO_ROOT / "configs/protocols/quantara-protocol-v1_1.yaml"
V11_SPEC_PATH = (
    REPO_ROOT / "docs/superpowers/specs/2026-09-01-quantara-protocol-v1_1.md"
)
FROZEN_ESTIMATOR_PATH = REPO_ROOT / "src/quantara/training_metrics_logistic.py"
GOLDEN_PATH = REPO_ROOT / "tests/fixtures/estimator_c3_golden.json"
PACKET_PARENT = "7abce82"

KRAKEN_COLUMNS = [
    "kraken_ret_1h",
    "kraken_rv_24h",
    "binance_kraken_ret_divergence_1h",
    "binance_kraken_cross_quote_log_ratio",
]
EXPECTED_WIDTHS = {
    "B1": 1,
    "B2": 3,
    "M1": 6,
    "M2": 7,
    "M2K": 11,
    "M3": 12,
    "M3b": 13,
    "M4": 16,
}


def _load_v11() -> dict[str, object]:
    value = yaml.safe_load(V11_YAML_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _assert_no_float(node: object) -> None:
    assert not isinstance(node, float)
    if isinstance(node, dict):
        for value in node.values():
            _assert_no_float(value)
    elif isinstance(node, list):
        for value in node:
            _assert_no_float(value)


def _model_columns(
    ladder: Mapping[str, Mapping[str, object]], model: str
) -> list[str]:
    entry = ladder[model]
    base = entry["base"]
    inherited = [] if base is None else _model_columns(ladder, str(base))
    return [*inherited, *[str(item) for item in entry["adds"]]]


def _well_posed_rows(width: int) -> tuple[list[list[Decimal]], list[int]]:
    rows = [
        [
            Decimal(((index + 1) * (column + 3) + index * index) % (19 + column))
            + Decimal(column + 1) / Decimal("100")
            for column in range(width)
        ]
        for index in range(80)
    ]
    labels = [1 if index % 7 in (0, 1, 2) else 0 for index in range(80)]
    return rows, labels


def _direct_raw_logistic_fit(
    x_values: list[Decimal], labels: list[int]
) -> tuple[Decimal, Decimal]:
    """Independent raw-scale two-parameter Newton fit for the F3 oracle."""
    beta_0 = Decimal(0)
    beta_1 = Decimal(0)
    with localcontext(DECIMAL_CONTEXT) as context:
        for _ in range(50):
            h00 = Decimal(0)
            h01 = Decimal(0)
            h11 = Decimal(0)
            score_0 = Decimal(0)
            score_1 = Decimal(0)
            for x_value, label in zip(x_values, labels, strict=True):
                eta = context.add(beta_0, context.multiply(beta_1, x_value))
                mu = context.divide(
                    Decimal(1), context.add(Decimal(1), context.exp(-eta))
                )
                weight = context.multiply(mu, context.subtract(Decimal(1), mu))
                residual = context.subtract(Decimal(label), mu)
                h00 = context.add(h00, weight)
                h01 = context.add(h01, context.multiply(weight, x_value))
                h11 = context.add(
                    h11,
                    context.multiply(weight, context.multiply(x_value, x_value)),
                )
                score_0 = context.add(score_0, residual)
                score_1 = context.add(
                    score_1, context.multiply(residual, x_value)
                )
            determinant = context.subtract(
                context.multiply(h00, h11), context.multiply(h01, h01)
            )
            delta_0 = context.divide(
                context.subtract(
                    context.multiply(score_0, h11),
                    context.multiply(score_1, h01),
                ),
                determinant,
            )
            delta_1 = context.divide(
                context.subtract(
                    context.multiply(h00, score_1),
                    context.multiply(h01, score_0),
                ),
                determinant,
            )
            updated_0 = context.add(beta_0, delta_0)
            updated_1 = context.add(beta_1, delta_1)
            converged = (
                abs(context.subtract(updated_0, beta_0)) < Decimal("1E-12")
                and abs(context.subtract(updated_1, beta_1)) < Decimal("1E-12")
            )
            beta_0, beta_1 = updated_0, updated_1
            if converged:
                return beta_0, beta_1
    raise AssertionError("independent raw-scale fit did not converge")


def _calibration_fixture() -> tuple[list[Decimal], list[int]]:
    probabilities = [Decimal(index) / Decimal(20) for index in range(2, 19)]
    labels = [0, 0, 1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1, 1, 1]
    return probabilities, labels


def _f3_calibration_fixture() -> tuple[list[Decimal], list[int]]:
    raw_logits = [Decimal(value) for value in (-2, -1, 1, 2)] * 4
    labels = [0, 1, 0, 1, 1, 0, 1, 0, 0, 1, 1, 0, 1, 0, 0, 1]
    with localcontext(DECIMAL_CONTEXT) as context:
        probabilities = [
            context.divide(
                Decimal(1), context.add(Decimal(1), context.exp(-value))
            )
            for value in raw_logits
        ]
    return probabilities, labels


def _passing_evidence(
    hypothesis: str,
    *,
    p_value: Fraction = Fraction(1, 1000),
    relative_improvement: Decimal = Decimal("0.02"),
    ci_lower: Decimal = Decimal("0.001"),
    improved_years: int = 2,
    worst_year_improvement: Decimal = Decimal("-0.01"),
    m3b_diagnostic_improvement: Decimal | None = None,
) -> HypothesisEvidence:
    return HypothesisEvidence(
        hypothesis=hypothesis,
        comparison_id=COMPARISON_IDS[hypothesis],
        p_value=p_value,
        relative_brier_improvement=relative_improvement,
        ci_lower=ci_lower,
        improved_years=improved_years,
        worst_year_improvement=worst_year_improvement,
        m3b_diagnostic_improvement=m3b_diagnostic_improvement,
    )


def _decision_inputs(
    *, eth: bool, kraken_m2: bool, kraken_m3: bool
) -> dict[str, HypothesisEvidence]:
    inputs = {
        hypothesis: _passing_evidence(hypothesis) for hypothesis in HYPOTHESIS_ORDER
    }
    pass_flags = {
        "H_ETH": eth,
        "H_K_M2": kraken_m2,
        "H_K_M3": kraken_m3,
    }
    for hypothesis, passes in pass_flags.items():
        if not passes:
            inputs[hypothesis] = _passing_evidence(
                hypothesis, relative_improvement=Decimal("0.009")
            )
    return inputs


def _golden_document() -> dict[str, object]:
    """Regenerate the golden solely from documented deterministic synthetic inputs."""
    bootstrap_resamples = 200
    p_values: dict[str, Fraction] = {}
    seeds: dict[str, int] = {}
    evidence: dict[str, HypothesisEvidence] = {}
    for hypothesis in HYPOTHESIS_ORDER:
        comparison_id = COMPARISON_IDS[hypothesis]
        seed = derive_stream_seed(comparison_id, 2024)
        seeds[hypothesis] = seed
        exceedances = SplitMix64(seed).below(3)
        p_value = Fraction(1 + exceedances, bootstrap_resamples + 1)
        p_values[hypothesis] = p_value
        evidence[hypothesis] = _passing_evidence(hypothesis, p_value=p_value)

    family = evaluate_optional_family(evidence)
    probabilities, labels = _calibration_fixture()
    calibration = fit_calibration(probabilities, labels)
    return {
        "generator": {
            "description": (
                "SplitMix64(derive_stream_seed(comparison_id, 2024)).below(3) "
                "sets the synthetic exceedance count"
            ),
            "bootstrap_resamples": bootstrap_resamples,
        },
        "hypotheses": {
            hypothesis: {
                "comparison_id": COMPARISON_IDS[hypothesis],
                "c2_seed_2024": seeds[hypothesis],
                "p_value": (
                    f"{p_values[hypothesis].numerator}/"
                    f"{p_values[hypothesis].denominator}"
                ),
                "criteria": family.decisions[hypothesis].criteria,
                "result_class": family.decisions[hypothesis].result_class,
            }
            for hypothesis in HYPOTHESIS_ORDER
        },
        "holm_steps": [
            {
                "rank": step.rank,
                "hypothesis": step.hypothesis,
                "p_value": f"{step.p_value.numerator}/{step.p_value.denominator}",
                "threshold": f"{step.threshold.numerator}/{step.threshold.denominator}",
                "rejected": step.rejected,
            }
            for step in family.holm.steps
        ],
        "retained_model": family.retained_model,
        "unlocks_2025": family.unlocks_2025,
        "calibration": {
            "beta_z": format(calibration.beta_z.quantize(STORAGE_QUANTUM), "f"),
            "mu_x": format(calibration.mu_x.quantize(STORAGE_QUANTUM), "f"),
            "sd_x": format(calibration.sd_x.quantize(STORAGE_QUANTUM), "f"),
            "beta_0": format(calibration.beta_0.quantize(STORAGE_QUANTUM), "f"),
            "slope": format(calibration.slope.quantize(STORAGE_QUANTUM), "f"),
            "intercept": format(
                calibration.intercept.quantize(STORAGE_QUANTUM), "f"
            ),
        },
        "result_class": "selection_evidence",
    }


def test_yaml_binding_matches_frozen_estimator_constants() -> None:
    binding = _load_v11()["estimator_binding"]
    assert binding == {
        "implementation": "src/quantara/training_metrics_logistic.py",
        "entry_point": "fit_logistic_irls",
        "decimal_precision": 50,
        "rounding": "ROUND_HALF_EVEN",
        "storage_quantum": "0.000000000000000001",
        "standardization": "train-window z-score, population denominator n",
        "initial_coefficients": "all zero",
        "model_l2_lambda": "1",
        "intercept": "unpenalized",
        "convergence": (
            "every abs(beta_new - beta_old) < 0.000000000001"
        ),
        "maximum_updates": 50,
        "linear_solver": "Gaussian elimination with partial pivoting",
        "pivot_failure": "exact-zero pivot, fail closed",
        "constant_train_feature": "exact-zero train std, fail closed",
        "non_convergence": "fail closed",
        "binary_float_inputs": "forbidden",
        "eta_clamp": "24",
        "probability_clamp": "0.000000000001",
    }
    assert RIDGE_LAMBDA == Decimal("1")
    assert MAX_ITERATIONS == 50
    assert TOLERANCE == Decimal("0.000000000001")
    assert ETA_CLAMP == Decimal("24")
    assert MU_CLAMP == Decimal("0.000000000001")
    assert DECIMAL_CONTEXT.prec == 50
    assert DECIMAL_CONTEXT.rounding == "ROUND_HALF_EVEN"
    assert STORAGE_QUANTUM == Decimal("1e-18")


def test_frozen_estimator_is_byte_identical_to_packet_parent() -> None:
    current = subprocess.run(
        [
            "git",
            "hash-object",
            "--path=src/quantara/training_metrics_logistic.py",
            "src/quantara/training_metrics_logistic.py",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    expected = subprocess.run(
        [
            "git",
            "rev-parse",
            f"{PACKET_PARENT}:src/quantara/training_metrics_logistic.py",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert FROZEN_ESTIMATOR_PATH.is_file()
    assert current == expected


def test_all_ladder_widths_fit_and_match_recursive_yaml_columns() -> None:
    document = _load_v11()
    ladder = document["model_ladder"]
    assert document["ladder_widths"] == EXPECTED_WIDTHS
    for model, expected_width in EXPECTED_WIDTHS.items():
        assert len(_model_columns(ladder, model)) == expected_width
        rows, labels = _well_posed_rows(expected_width)
        result = fit_candidate(rows, labels)
        assert result["converged_iterations"] <= 5


@pytest.mark.parametrize("label", [0, 1])
def test_c3_guard_rejects_single_class_training_outcome(label: int) -> None:
    with pytest.raises(EstimatorC3Failure) as error:
        fit_candidate([[Decimal(index)] for index in range(60)], [label] * 60)
    assert error.value.cause == "single_class_training_outcome"


def test_frozen_solver_still_converges_on_all_ones_without_c3_guard() -> None:
    result = fit_logistic_irls(
        [[Decimal(index)] for index in range(60)],
        [1] * 60,
    )
    assert result["intercept"] == Decimal(
        "25.000000000037751345442790977516449695475234067772"
    )
    assert result["eta_clamp_count"] == 120


def test_mixed_training_outcome_with_one_minority_example_passes_guard() -> None:
    labels = [0, *([1] * 59)]
    result = fit_candidate([[Decimal(index)] for index in range(60)], labels)
    assert result["converged_iterations"] <= 50


def test_exact_constant_feature_maps_to_constant_train_feature() -> None:
    with pytest.raises(EstimatorC3Failure) as error:
        fit_candidate([[Decimal("0.5")] for _ in range(60)], [0, 1] * 30)
    assert error.value.cause == "constant_train_feature"


def test_fifty_digit_repeated_value_passes_std_then_maps_zero_pivot() -> None:
    value = Decimal(
        "0.60229735249715581406505578465265846420638254804033"
    )
    rows = [[value] for _ in range(60)]
    _, _, stds = _standardization(rows)
    assert stds == [Decimal("2.5E-49")]
    with pytest.raises(EstimatorC3Failure) as error:
        fit_bound_logistic(
            rows,
            [0, 1] * 30,
            ridge_lambda=Decimal(0),
        )
    assert error.value.cause == "zero_pivot"


def test_c3_has_no_rejected_pivot_or_condition_tolerance() -> None:
    source = (REPO_ROOT / "src/quantara/estimator_c3.py").read_text(encoding="utf-8")
    assert "1e-40" not in source
    assert "1E-40" not in source
    assert "condition_number" not in source
    assert "condition-number" not in source


def test_calibration_back_transform_matches_independent_raw_fit() -> None:
    probabilities, labels = _f3_calibration_fixture()
    result = fit_calibration(probabilities, labels)
    with localcontext(DECIMAL_CONTEXT) as context:
        x_values = [
            context.ln(context.divide(value, context.subtract(Decimal(1), value)))
            for value in probabilities
        ]
    direct_intercept, direct_slope = _direct_raw_logistic_fit(x_values, labels)
    assert abs(result.slope - direct_slope) <= Decimal("1E-45")
    assert abs(result.intercept - direct_intercept) <= Decimal("1E-45")
    assert result.slope.quantize(STORAGE_QUANTUM) == direct_slope.quantize(
        STORAGE_QUANTUM
    )
    assert result.intercept.quantize(STORAGE_QUANTUM) == direct_intercept.quantize(
        STORAGE_QUANTUM
    )


def test_probability_endpoints_require_the_frozen_clamp() -> None:
    assert clamp_mu(Decimal(0)) == (Decimal("1E-12"), True)
    assert clamp_mu(Decimal(1)) == (Decimal("0.999999999999"), True)
    with localcontext(DECIMAL_CONTEXT) as context:
        unclamped_zero = context.ln(
            context.divide(Decimal(0), context.subtract(Decimal(1), Decimal(0)))
        )
        assert unclamped_zero == Decimal("-Infinity")
        with pytest.raises(DivisionByZero):
            context.ln(
                context.divide(
                    Decimal(1), context.subtract(Decimal(1), Decimal(1))
                )
            )
    result = fit_calibration(
        [Decimal(0), Decimal("0.2"), Decimal("0.8"), Decimal(1)],
        [0, 1, 0, 1],
    )
    assert result.probability_clamp_count == 2


def test_single_class_calibration_fails_closed() -> None:
    with pytest.raises(EstimatorC3Failure) as error:
        fit_calibration([Decimal("0.2"), Decimal("0.8")], [1, 1])
    assert error.value.cause == "calibration_single_class_outcome"


def test_zero_variance_calibration_logit_fails_closed() -> None:
    with pytest.raises(EstimatorC3Failure) as error:
        fit_calibration([Decimal("0.5")] * 4, [0, 1, 0, 1])
    assert error.value.cause in {"constant_train_feature", "zero_pivot"}


def test_separated_calibration_fails_by_eta_clamp_not_nonconvergence() -> None:
    logits = [Decimal(index - 10) for index in range(20)]
    logits = [value if value != 0 else Decimal("0.5") for value in logits]
    with localcontext(DECIMAL_CONTEXT) as context:
        probabilities = [
            context.divide(Decimal(1), context.add(Decimal(1), context.exp(-value)))
            for value in logits
        ]
    labels = [0 if value < 0 else 1 for value in logits]
    direct = fit_logistic_irls(
        [[value] for value in logits], labels, ridge_lambda=Decimal(0)
    )
    assert direct["converged_iterations"] == 25
    assert direct["eta_clamp_count"] > 0
    assert direct["mu_clamp_count"] == 0
    with pytest.raises(EstimatorC3Failure) as error:
        fit_calibration(probabilities, labels)
    assert error.value.cause == "calibration_degenerate_logit"
    assert error.value.diagnostics["eta_clamp_count"] > 0


@pytest.mark.parametrize(
    ("fit", "expected"),
    (
        (
            CalibrationFit.synthetic(
                beta_z=Decimal("1"),
                sd_x=Decimal("0.5"),
                slope=Decimal("2"),
            ),
            False,
        ),
        (
            CalibrationFit.synthetic(
                beta_z=Decimal("2"),
                sd_x=Decimal("2"),
                slope=Decimal("1"),
            ),
            True,
        ),
    ),
)
def test_calibration_gate_uses_raw_logit_slope(
    fit: CalibrationFit, expected: bool
) -> None:
    assert calibration_slope_passes(fit) is expected


def test_holm_thresholds_are_exact_fractions() -> None:
    result = holm_step_down(
        {
            "H_ETH": Fraction(1, 1000),
            "H_K_M2": Fraction(1, 500),
            "H_K_M3": Fraction(1, 250),
        }
    )
    assert [step.threshold for step in result.steps] == [
        Fraction(1, 60),
        Fraction(1, 40),
        Fraction(1, 20),
    ]


def test_holm_step_assignment_follows_sorted_p_values_not_model_name() -> None:
    first = holm_step_down(
        {
            "H_ETH": Fraction(3, 1000),
            "H_K_M2": Fraction(1, 1000),
            "H_K_M3": Fraction(2, 1000),
        }
    )
    second = holm_step_down(
        {
            "H_ETH": Fraction(1, 1000),
            "H_K_M2": Fraction(3, 1000),
            "H_K_M3": Fraction(2, 1000),
        }
    )
    assert first.steps[0].hypothesis == "H_K_M2"
    assert second.steps[0].hypothesis == "H_ETH"


def test_holm_stops_after_first_failure() -> None:
    result = holm_step_down(
        {
            "H_ETH": Fraction(1, 100),
            "H_K_M2": Fraction(1, 30),
            "H_K_M3": Fraction(1, 25),
        }
    )
    assert [step.rejected for step in result.steps] == [True, False, False]


def test_holm_first_step_is_attainable_at_twenty_thousand_resamples() -> None:
    assert Fraction(1, 20001) <= Fraction(1, 60)
    assert Fraction(333, 20001) == Fraction(111, 6667)
    assert Fraction(333, 20001) <= Fraction(1, 60)
    assert Fraction(334, 20001) > Fraction(1, 60)
    boundary = max(
        count
        for count in range(20001)
        if Fraction(1 + count, 20001) <= Fraction(1, 60)
    )
    assert boundary == 332


def test_holm_result_carries_all_three_even_when_graph_uses_two() -> None:
    result = evaluate_optional_family(
        _decision_inputs(eth=True, kraken_m2=False, kraken_m3=True)
    )
    assert set(result.holm.p_values) == set(HYPOTHESIS_ORDER)
    assert set(result.decisions) == set(HYPOTHESIS_ORDER)
    assert result.retained_model == "M4"


def test_holm_rejects_binary_float_p_values() -> None:
    with pytest.raises(TypeError):
        holm_step_down(
            {
                "H_ETH": 0.001,
                "H_K_M2": Fraction(1, 500),
                "H_K_M3": Fraction(1, 250),
            }
        )


def test_comparison_ids_and_c2_stream_seeds_are_distinct() -> None:
    assert COMPARISON_IDS == {
        "H_ETH": "H_ETH|M3_vs_M2",
        "H_K_M2": "H_K_M2|M2K_vs_M2",
        "H_K_M3": "H_K_M3|M4_vs_M3",
    }
    seeds = {
        derive_stream_seed(comparison_id, 2024)
        for comparison_id in COMPARISON_IDS.values()
    }
    assert len(seeds) == 3


@pytest.mark.parametrize(
    ("eth", "kraken_m2", "kraken_m3", "expected"),
    (
        (True, True, True, "M4"),
        (True, True, False, "M3"),
        (False, True, True, "M2K"),
        (False, False, True, "M2"),
    ),
)
def test_frozen_retention_graph(
    eth: bool, kraken_m2: bool, kraken_m3: bool, expected: str
) -> None:
    result = evaluate_optional_family(
        _decision_inputs(eth=eth, kraken_m2=kraken_m2, kraken_m3=kraken_m3)
    )
    assert result.retained_model == expected


@pytest.mark.parametrize(
    "failed_field",
    (
        "relative_brier_improvement",
        "ci_lower",
        "holm",
        "improved_years",
        "worst_year_improvement",
    ),
)
def test_each_optional_criterion_failed_alone_blocks_retention(
    failed_field: str,
) -> None:
    inputs = _decision_inputs(eth=True, kraken_m2=True, kraken_m3=True)
    kwargs: dict[str, object] = {}
    if failed_field == "relative_brier_improvement":
        kwargs["relative_improvement"] = Decimal("0.009")
    elif failed_field == "ci_lower":
        kwargs["ci_lower"] = Decimal(0)
    elif failed_field == "holm":
        kwargs["p_value"] = Fraction(1, 2)
    elif failed_field == "improved_years":
        kwargs["improved_years"] = 1
    else:
        kwargs["worst_year_improvement"] = Decimal("-0.021")
    inputs["H_ETH"] = _passing_evidence("H_ETH", **kwargs)
    result = evaluate_optional_family(inputs)
    assert result.decisions["H_ETH"].passes is False
    assert result.retained_model != "M3"
    assert result.retained_model != "M4"


def test_m3b_never_becomes_retained_even_with_largest_improvement() -> None:
    inputs = _decision_inputs(eth=True, kraken_m2=True, kraken_m3=True)
    inputs["H_ETH"] = _passing_evidence(
        "H_ETH", m3b_diagnostic_improvement=Decimal("999")
    )
    result = evaluate_optional_family(inputs)
    assert result.retained_model == "M4"
    assert result.retained_model != "M3b"


def test_retention_is_pure_and_evaluates_each_hypothesis_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _decision_inputs(eth=False, kraken_m2=False, kraken_m3=True)
    snapshot = dict(inputs)
    calls: list[str] = []
    original = estimator_c3.evaluate_hypothesis_gate

    def counting_gate(
        evidence: HypothesisEvidence, *, holm_rejected: bool
    ) -> object:
        calls.append(evidence.hypothesis)
        return original(evidence, holm_rejected=holm_rejected)

    monkeypatch.setattr(estimator_c3, "evaluate_hypothesis_gate", counting_gate)
    first = evaluate_optional_family(inputs)
    assert calls == list(HYPOTHESIS_ORDER)
    assert inputs == snapshot
    calls.clear()
    second = evaluate_optional_family(inputs)
    assert calls == list(HYPOTHESIS_ORDER)
    assert first == second


def test_retention_never_unlocks_2025_without_success_gate() -> None:
    result = evaluate_optional_family(
        _decision_inputs(eth=True, kraken_m2=True, kraken_m3=True)
    )
    assert result.unlocks_2025 is False
    assert result.requires_seven_criterion_success_gate is True


def test_yaml_selection_evidence_and_primary_m2_roles() -> None:
    document = _load_v11()
    optional = document["optional_family_retention"]
    assert optional["optional_block_2022_2024_result_class"] == "selection_evidence"
    assert optional["independent_replication_source"] == "sealed 2025 only"
    assert document["model_mandates"]["mandatory_primary_candidate"] == "M2"
    assert "selection_evidence" not in str(
        document["model_mandates"]["mandatory_rule"]
    )


def test_every_optional_result_is_labelled_selection_evidence() -> None:
    result = evaluate_optional_family(
        _decision_inputs(eth=True, kraken_m2=True, kraken_m3=True)
    )
    assert {
        decision.result_class for decision in result.decisions.values()
    } == {"selection_evidence"}


def test_spec_uses_required_selection_claim_wording_without_false_replication() -> None:
    spec = V11_SPEC_PATH.read_text(encoding="utf-8")
    required = "selected on 2022–2024 development evidence"
    assert required in spec
    optional_sentences = re.findall(
        r"[^.\n]*optional[^.\n]*2022[–-]2024[^.\n]*\.", spec, re.IGNORECASE
    )
    assert optional_sentences
    assert all("replicated" not in sentence.lower() for sentence in optional_sentences)


def test_v11_yaml_c3_contract_and_no_float_path() -> None:
    document = _load_v11()
    _assert_no_float(document)
    assert document["fail_closed_causes"] == [
        "single_class_training_outcome",
        "constant_train_feature",
        "zero_pivot",
        "non_convergence",
        "binary_float_input",
        "calibration_single_class_outcome",
        "calibration_degenerate_logit",
    ]
    assert document["calibration"]["lambda"] == "0"
    optional = document["optional_family_retention"]
    assert optional["holm_test_count"] == 3
    assert optional["successor_repair_status"] == "IMPLEMENTED_PACKET_C3"
    assert optional["compute_all_three_before_deciding"] is True
    assert optional["holm_step_thresholds"] == ["1/60", "1/40", "1/20"]
    assert optional["tie_order"] == ["H_ETH", "H_K_M2", "H_K_M3"]
    assert optional["min_attainable_p"] == "1/20001"
    assert optional["max_exceedance_count_clearing_first_step"] == 332
    assert optional["p_at_332"] == "111/6667"
    assert optional["p_at_333"] == "334/20001"
    assert document["model_ladder"]["M2K"] == {
        "base": "M2",
        "adds": KRAKEN_COLUMNS,
        "definition": "M2 plus frozen four-column Kraken block",
    }


def test_golden_synthetic_optional_family_contract() -> None:
    expected = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert _golden_document() == expected
