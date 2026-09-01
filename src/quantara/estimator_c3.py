"""Protocol v1.1 C3 estimator binding and optional-family decision contract.

This layer wraps the byte-frozen exact-Decimal estimator in
``quantara.training_metrics_logistic``.  It adds protocol guards and decision
machinery without changing or reimplementing logistic IRLS.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

from quantara.training_metrics_logistic import (
    DECIMAL_CONTEXT,
    MetricDomainError,
    clamp_mu,
    fit_logistic_irls,
)

FAIL_CLOSED_CAUSES = (
    "single_class_training_outcome",
    "constant_train_feature",
    "zero_pivot",
    "non_convergence",
    "binary_float_input",
    "calibration_single_class_outcome",
    "calibration_degenerate_logit",
)

HYPOTHESIS_ORDER = ("H_ETH", "H_K_M2", "H_K_M3")
COMPARISON_IDS = {
    "H_ETH": "H_ETH|M3_vs_M2",
    "H_K_M2": "H_K_M2|M2K_vs_M2",
    "H_K_M3": "H_K_M3|M4_vs_M3",
}
RESULT_CLASS = "selection_evidence"


class EstimatorC3Failure(MetricDomainError):
    """Named fail-closed C3 comparison failure."""

    error_id = "estimator_c3_failure"

    def __init__(
        self,
        cause: str,
        *,
        diagnostics: Mapping[str, object] | None = None,
    ) -> None:
        if cause not in FAIL_CLOSED_CAUSES:
            raise ValueError(f"unknown C3 fail-closed cause: {cause}")
        self.cause = cause
        self.diagnostics = dict(diagnostics or {})
        super().__init__(cause)


@dataclass(frozen=True)
class CalibrationFit:
    beta_z: Decimal
    mu_x: Decimal
    sd_x: Decimal
    beta_0: Decimal
    slope: Decimal
    intercept: Decimal
    converged_iterations: int
    eta_clamp_count: int
    mu_clamp_count: int
    probability_clamp_count: int

    @classmethod
    def synthetic(
        cls,
        *,
        beta_z: Decimal,
        sd_x: Decimal,
        slope: Decimal,
    ) -> CalibrationFit:
        """Build an explicit synthetic gate probe without running a fit."""
        return cls(
            beta_z=beta_z,
            mu_x=Decimal(0),
            sd_x=sd_x,
            beta_0=Decimal(0),
            slope=slope,
            intercept=Decimal(0),
            converged_iterations=1,
            eta_clamp_count=0,
            mu_clamp_count=0,
            probability_clamp_count=0,
        )


@dataclass(frozen=True)
class HolmStep:
    rank: int
    hypothesis: str
    p_value: Fraction
    threshold: Fraction
    rejected: bool


@dataclass(frozen=True)
class HolmResult:
    p_values: dict[str, Fraction]
    steps: tuple[HolmStep, ...]
    rejections: dict[str, bool]


@dataclass(frozen=True)
class HypothesisEvidence:
    hypothesis: str
    comparison_id: str
    p_value: Fraction
    relative_brier_improvement: Decimal
    ci_lower: Decimal
    improved_years: int
    worst_year_improvement: Decimal
    m3b_diagnostic_improvement: Decimal | None = None


@dataclass(frozen=True)
class HypothesisDecision:
    hypothesis: str
    comparison_id: str
    p_value: Fraction
    criteria: dict[str, bool]
    passes: bool
    result_class: str = RESULT_CLASS


@dataclass(frozen=True)
class OptionalFamilyResult:
    holm: HolmResult
    decisions: dict[str, HypothesisDecision]
    retained_model: str
    unlocks_2025: bool = False
    requires_seven_criterion_success_gate: bool = True


def _require_both_classes(labels: Sequence[object], cause: str) -> None:
    classes: set[int] = set()
    for label in labels:
        if isinstance(label, float):
            raise EstimatorC3Failure("binary_float_input")
        if isinstance(label, bool) or not isinstance(label, int) or label not in (0, 1):
            raise MetricDomainError(f"logistic label must be int 0 or 1, got {label!r}")
        classes.add(label)
    if classes != {0, 1}:
        raise EstimatorC3Failure(cause)


def _mapped_fit(
    feature_rows: Sequence[Sequence[object]],
    labels: Sequence[object],
    *,
    ridge_lambda: Decimal,
) -> dict[str, object]:
    try:
        return fit_logistic_irls(
            feature_rows,
            labels,
            ridge_lambda=ridge_lambda,
        )
    except MetricDomainError as error:
        message = str(error)
        if "binary float input" in message:
            raise EstimatorC3Failure("binary_float_input") from error
        if "zero train-window standard deviation" in message:
            raise EstimatorC3Failure("constant_train_feature") from error
        if "zero pivot" in message:
            raise EstimatorC3Failure("zero_pivot") from error
        if "irls_did_not_converge" in message:
            raise EstimatorC3Failure("non_convergence") from error
        raise


def fit_candidate(
    feature_rows: Sequence[Sequence[object]],
    labels: Sequence[object],
) -> dict[str, object]:
    """Fit one candidate through the frozen solver after the C3 class guard."""
    return fit_bound_logistic(feature_rows, labels, ridge_lambda=Decimal("1"))


def fit_bound_logistic(
    feature_rows: Sequence[Sequence[object]],
    labels: Sequence[object],
    *,
    ridge_lambda: Decimal,
) -> dict[str, object]:
    """Apply the C3 guard and failure mapping around one frozen solver call."""
    _require_both_classes(labels, "single_class_training_outcome")
    return _mapped_fit(feature_rows, labels, ridge_lambda=ridge_lambda)


def _probability(value: object) -> Decimal:
    if isinstance(value, bool):
        raise MetricDomainError(f"boolean probability is forbidden: {value!r}")
    if isinstance(value, float):
        raise EstimatorC3Failure("binary_float_input")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as error:
        raise MetricDomainError(f"malformed probability: {value!r}") from error
    if not result.is_finite() or result < 0 or result > 1:
        raise MetricDomainError(f"probability must be finite and in [0, 1]: {value!r}")
    return result


def fit_calibration(
    probabilities: Sequence[object],
    labels: Sequence[object],
) -> CalibrationFit:
    """Fit unpenalized calibration on clamped logit probabilities."""
    if len(probabilities) != len(labels) or len(probabilities) < 2:
        raise MetricDomainError(
            "calibration fit requires matching probabilities and at least two samples"
        )
    _require_both_classes(labels, "calibration_single_class_outcome")

    logits: list[Decimal] = []
    probability_clamp_count = 0
    for raw_probability in probabilities:
        probability, clamped = clamp_mu(_probability(raw_probability))
        probability_clamp_count += int(clamped)
        odds = DECIMAL_CONTEXT.divide(
            probability,
            DECIMAL_CONTEXT.subtract(Decimal(1), probability),
        )
        logits.append(DECIMAL_CONTEXT.ln(odds))

    fit = _mapped_fit(
        [[value] for value in logits],
        labels,
        ridge_lambda=Decimal(0),
    )
    eta_clamp_count = int(fit["eta_clamp_count"])
    if eta_clamp_count > 0:
        raise EstimatorC3Failure(
            "calibration_degenerate_logit",
            diagnostics={"eta_clamp_count": eta_clamp_count},
        )

    beta_0 = fit["intercept"]
    coefficients = fit["coefficients"]
    means = fit["means"]
    stds = fit["stds"]
    if not (
        isinstance(beta_0, Decimal)
        and isinstance(coefficients, list)
        and isinstance(means, list)
        and isinstance(stds, list)
        and len(coefficients) == len(means) == len(stds) == 1
        and isinstance(coefficients[0], Decimal)
        and isinstance(means[0], Decimal)
        and isinstance(stds[0], Decimal)
    ):
        raise MetricDomainError("frozen calibration fit returned an invalid shape")
    beta_z = coefficients[0]
    mu_x = means[0]
    sd_x = stds[0]
    slope = DECIMAL_CONTEXT.divide(beta_z, sd_x)
    intercept = DECIMAL_CONTEXT.subtract(
        beta_0,
        DECIMAL_CONTEXT.divide(
            DECIMAL_CONTEXT.multiply(beta_z, mu_x),
            sd_x,
        ),
    )
    return CalibrationFit(
        beta_z=beta_z,
        mu_x=mu_x,
        sd_x=sd_x,
        beta_0=beta_0,
        slope=slope,
        intercept=intercept,
        converged_iterations=int(fit["converged_iterations"]),
        eta_clamp_count=eta_clamp_count,
        mu_clamp_count=int(fit["mu_clamp_count"]),
        probability_clamp_count=probability_clamp_count,
    )


def calibration_slope_passes(
    fit: CalibrationFit,
    *,
    lower: Decimal = Decimal("0.8"),
    upper: Decimal = Decimal("1.2"),
) -> bool:
    """Apply the success band to the back-transformed raw-logit slope."""
    if isinstance(lower, float) or isinstance(upper, float):
        raise EstimatorC3Failure("binary_float_input")
    return lower <= fit.slope <= upper


def holm_step_down(p_values: Mapping[str, Fraction]) -> HolmResult:
    """Ordinary exact-Fraction Holm over the three frozen hypotheses."""
    if set(p_values) != set(HYPOTHESIS_ORDER):
        raise ValueError(f"Holm requires exactly {HYPOTHESIS_ORDER!r}")
    copied: dict[str, Fraction] = {}
    for hypothesis in HYPOTHESIS_ORDER:
        p_value = p_values[hypothesis]
        if not isinstance(p_value, Fraction):
            raise TypeError("Holm p-values must be fractions.Fraction")
        if p_value < 0 or p_value > 1:
            raise ValueError(f"Holm p-value outside [0, 1] for {hypothesis}")
        copied[hypothesis] = p_value

    tie_rank = {hypothesis: index for index, hypothesis in enumerate(HYPOTHESIS_ORDER)}
    ordered = sorted(
        copied.items(),
        key=lambda item: (item[1], tie_rank[item[0]]),
    )
    active = True
    steps: list[HolmStep] = []
    rejections = {hypothesis: False for hypothesis in HYPOTHESIS_ORDER}
    alpha = Fraction(1, 20)
    family_size = len(HYPOTHESIS_ORDER)
    for rank, (hypothesis, p_value) in enumerate(ordered, start=1):
        threshold = alpha / (family_size - rank + 1)
        rejected = active and p_value <= threshold
        if not rejected:
            active = False
        rejections[hypothesis] = rejected
        steps.append(
            HolmStep(
                rank=rank,
                hypothesis=hypothesis,
                p_value=p_value,
                threshold=threshold,
                rejected=rejected,
            )
        )
    return HolmResult(
        p_values=copied,
        steps=tuple(steps),
        rejections=rejections,
    )


def _require_decimal(value: Decimal, name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be decimal.Decimal")


def evaluate_hypothesis_gate(
    evidence: HypothesisEvidence,
    *,
    holm_rejected: bool,
) -> HypothesisDecision:
    """Evaluate the five frozen, conjunctive retention criteria once."""
    _require_decimal(
        evidence.relative_brier_improvement,
        "relative_brier_improvement",
    )
    _require_decimal(evidence.ci_lower, "ci_lower")
    _require_decimal(evidence.worst_year_improvement, "worst_year_improvement")
    if not isinstance(evidence.improved_years, int) or isinstance(
        evidence.improved_years, bool
    ):
        raise TypeError("improved_years must be an int")
    criteria = {
        "pooled_relative_brier_improvement_at_least_0_01": (
            evidence.relative_brier_improvement >= Decimal("0.01")
        ),
        "ci_lower_bound_above_zero": evidence.ci_lower > 0,
        "holm_rejected": holm_rejected,
        "at_least_two_validation_years_improve": evidence.improved_years >= 2,
        "no_validation_year_worse_than_minus_0_02": (
            evidence.worst_year_improvement >= Decimal("-0.02")
        ),
    }
    return HypothesisDecision(
        hypothesis=evidence.hypothesis,
        comparison_id=evidence.comparison_id,
        p_value=evidence.p_value,
        criteria=criteria,
        passes=all(criteria.values()),
    )


def evaluate_optional_family(
    evidence: Mapping[str, HypothesisEvidence],
) -> OptionalFamilyResult:
    """Compute all three decisions, then apply the frozen retention graph."""
    if set(evidence) != set(HYPOTHESIS_ORDER):
        raise ValueError(f"optional family requires exactly {HYPOTHESIS_ORDER!r}")
    copied: dict[str, HypothesisEvidence] = {}
    p_values: dict[str, Fraction] = {}
    for hypothesis in HYPOTHESIS_ORDER:
        item = evidence[hypothesis]
        if item.hypothesis != hypothesis:
            raise ValueError(f"hypothesis key mismatch for {hypothesis}")
        if item.comparison_id != COMPARISON_IDS[hypothesis]:
            raise ValueError(f"comparison_id mismatch for {hypothesis}")
        copied[hypothesis] = item
        p_values[hypothesis] = item.p_value

    holm = holm_step_down(p_values)
    decisions = {
        hypothesis: evaluate_hypothesis_gate(
            copied[hypothesis],
            holm_rejected=holm.rejections[hypothesis],
        )
        for hypothesis in HYPOTHESIS_ORDER
    }
    if decisions["H_ETH"].passes:
        retained_model = "M4" if decisions["H_K_M3"].passes else "M3"
    else:
        retained_model = "M2K" if decisions["H_K_M2"].passes else "M2"
    return OptionalFamilyResult(
        holm=holm,
        decisions=decisions,
        retained_model=retained_model,
    )
