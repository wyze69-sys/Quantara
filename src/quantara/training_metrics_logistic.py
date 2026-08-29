"""Exact-Decimal logistic IRLS probability head with pre-registered kill criteria.

Slice 012. This module is additive: ``quantara.training_metrics`` (the frozen
slice 011 ridge module) is not imported for arithmetic and is not mutated. The
DECIMAL_CONTEXT discipline, the Q18 storage quantum, and the Gauss-elimination
solver pattern are reimplemented locally so the ridge path stays byte-frozen.

Zero binary floats: every numeric value is ``decimal.Decimal`` and every
operation goes through ``DECIMAL_CONTEXT``.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import (
    ROUND_HALF_EVEN,
    Clamped,
    Context,
    Decimal,
    DivisionByZero,
    FloatOperation,
    Inexact,
    InvalidOperation,
    Overflow,
    Rounded,
    Subnormal,
    Underflow,
)

from quantara.errors import QuantaraError

DECIMAL_CONTEXT = Context(
    prec=50,
    rounding=ROUND_HALF_EVEN,
    Emin=-999999,
    Emax=999999,
    capitals=1,
    clamp=0,
    traps=[InvalidOperation, DivisionByZero, Overflow],
)
for _signal in (Inexact, Rounded, Subnormal, Underflow, Clamped, FloatOperation):
    DECIMAL_CONTEXT.traps[_signal] = False

STORAGE_QUANTUM = Decimal("0.000000000000000001")
DECIMAL_CONTRACT: dict[str, object] = {
    "precision": 50,
    "rounding": "ROUND_HALF_EVEN",
    "emin": -999999,
    "emax": 999999,
    "capitals": 1,
    "clamp": 0,
    "enabled_traps": ["InvalidOperation", "DivisionByZero", "Overflow"],
    "storage_quantum": "0.000000000000000001",
}

FEATURE_INDICES = (1, 2, 3, 4)
RETURN_INDEX = 5
DIRECTION_INDEX = 6
FEATURE_NAMES = ("f_ret_1", "f_roc_60", "f_rvol_20", "f_volratio_20")
METRICS = ("directional_accuracy", "log_loss", "brier", "direction_ic", "pearson_ic")
BASELINES = ("majority_class_train_window", "sign_f_ret_1", "climatology_p")
BASELINE_METRICS: dict[str, tuple[str, ...]] = {
    "majority_class_train_window": ("directional_accuracy",),
    "sign_f_ret_1": ("directional_accuracy",),
    "climatology_p": ("directional_accuracy", "log_loss", "brier"),
}

# Frozen IRLS parameters (descriptor-pinned; no search permitted).
RIDGE_LAMBDA = Decimal("1")
MAX_ITERATIONS = 50
TOLERANCE = Decimal("0.000000000001")
ETA_CLAMP = Decimal("24")
MU_CLAMP = Decimal("0.000000000001")
MINIMUM_USABLE_TRAIN_ROWS = 200

MODEL_PARAMETERS: dict[str, object] = {
    "family": "logistic_irls",
    "lambda": "1",
    "max_iterations": 50,
    "tolerance": "0.000000000001",
    "eta_clamp": "24",
    "mu_clamp": "0.000000000001",
    "solver": "gauss_elimination_partial_pivot",
}

# Pre-registered kill criteria (plan section 4). Frozen before any model run;
# post-hoc renegotiation is prohibited.
KILL_CRITERIA: dict[str, str] = {
    "directional_accuracy_min": "0.534900284900284900",
    "direction_ic_min": "0.020000000000000000",
    "log_loss_max": "0.762500000000000000",
    "brier_max": "0.250000000000000000",
}
KILL_RESULT_KEYS = (
    "k1_directional_accuracy",
    "k2_direction_ic",
    "k3_log_loss",
    "k4_brier",
)


class MetricDomainError(QuantaraError):
    error_id = "metric_domain_error"


def _add(a: Decimal, b: Decimal) -> Decimal:
    return DECIMAL_CONTEXT.add(a, b)


def _sub(a: Decimal, b: Decimal) -> Decimal:
    return DECIMAL_CONTEXT.subtract(a, b)


def _mul(a: Decimal, b: Decimal) -> Decimal:
    return DECIMAL_CONTEXT.multiply(a, b)


def _div(a: Decimal, b: Decimal) -> Decimal:
    return DECIMAL_CONTEXT.divide(a, b)


def _sqrt(a: Decimal) -> Decimal:
    return DECIMAL_CONTEXT.sqrt(a)


def _exp(a: Decimal) -> Decimal:
    return DECIMAL_CONTEXT.exp(a)


def _ln(a: Decimal) -> Decimal:
    if a <= 0:
        raise MetricDomainError(f"logarithm domain error for {a}")
    return DECIMAL_CONTEXT.ln(a)


_Q18_ZERO = DECIMAL_CONTEXT.quantize(Decimal(0), STORAGE_QUANTUM)


def quantize_q18(value: Decimal) -> Decimal:
    result = DECIMAL_CONTEXT.quantize(value, STORAGE_QUANTUM)
    return _Q18_ZERO if result.is_zero() else result


def _q18(value: Decimal) -> str:
    return format(quantize_q18(value), "f")


def _validate_numeric(value: object, name: str) -> Decimal:
    if isinstance(value, bool):
        raise MetricDomainError(f"boolean input not permitted for {name}: {value!r}")
    if isinstance(value, float):
        raise MetricDomainError(f"binary float input not permitted for {name}: {value!r}")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:
        raise MetricDomainError(f"malformed numeric input for {name}: {value!r}") from exc
    if result.is_nan() or result.is_infinite():
        raise MetricDomainError(f"non-finite numeric input for {name}: {value!r}")
    return result


def _validate_label(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value not in (0, 1):
        raise MetricDomainError(f"logistic label must be int 0 or 1, got {value!r}")
    return value


def _sum(values: Sequence[Decimal]) -> Decimal:
    total = Decimal(0)
    for value in values:
        total = _add(total, value)
    return total


def _mean(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise MetricDomainError("cannot compute mean of empty values")
    return _div(_sum(values), Decimal(len(values)))


def _solve(matrix: Sequence[Sequence[Decimal]], vector: Sequence[Decimal]) -> list[Decimal]:
    """Gauss elimination with partial pivoting (local reimplementation)."""
    size = len(vector)
    augmented = [list(matrix[i]) + [vector[i]] for i in range(size)]
    for column in range(size):
        pivot_row = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if augmented[pivot_row][column].is_zero():
            raise MetricDomainError("zero pivot in logistic ridge solver")
        if pivot_row != column:
            augmented[column], augmented[pivot_row] = augmented[pivot_row], augmented[column]
        pivot = augmented[column][column]
        for j in range(column, size + 1):
            augmented[column][j] = _div(augmented[column][j], pivot)
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            for j in range(column, size + 1):
                augmented[row][j] = _sub(augmented[row][j], _mul(factor, augmented[column][j]))
    return [augmented[row][size] for row in range(size)]


def clamp_eta(value: Decimal, limit: Decimal = ETA_CLAMP) -> tuple[Decimal, bool]:
    """Clamp the linear predictor to [-limit, +limit]; report whether it bit."""
    if value > limit:
        return limit, True
    if value < -limit:
        return -limit, True
    return value, False


def clamp_mu(value: Decimal, limit: Decimal = MU_CLAMP) -> tuple[Decimal, bool]:
    """Separation guard: clamp a probability to [limit, 1 - limit]."""
    high = _sub(Decimal(1), limit)
    if value < limit:
        return limit, True
    if value > high:
        return high, True
    return value, False


def logistic_sigmoid(eta: Decimal) -> Decimal:
    """mu = 1 / (1 + exp(-eta)) in exact-decimal arithmetic."""
    return _div(Decimal(1), _add(Decimal(1), _exp(-eta)))


def _standardization(
    feature_rows: Sequence[Sequence[object]],
) -> tuple[list[list[Decimal]], list[Decimal], list[Decimal]]:
    width = len(feature_rows[0])
    if width == 0 or any(len(row) != width for row in feature_rows):
        raise MetricDomainError("logistic feature matrix must be non-empty and rectangular")
    x = [
        [_validate_numeric(value, f"feature[{j}]") for j, value in enumerate(row)]
        for row in feature_rows
    ]
    means = [_mean([row[j] for row in x]) for j in range(width)]
    stds: list[Decimal] = []
    for j in range(width):
        variance = _mean([_mul(_sub(row[j], means[j]), _sub(row[j], means[j])) for row in x])
        std = _sqrt(variance)
        if std.is_zero():
            raise MetricDomainError(f"zero train-window standard deviation for feature[{j}]")
        stds.append(std)
    z = [[_div(_sub(row[j], means[j]), stds[j]) for j in range(width)] for row in x]
    return z, means, stds


def fit_logistic_irls(
    feature_rows: Sequence[Sequence[object]],
    labels: Sequence[object],
    ridge_lambda: Decimal = RIDGE_LAMBDA,
    max_iterations: int = MAX_ITERATIONS,
    tolerance: Decimal = TOLERANCE,
) -> dict[str, object]:
    """Fit a ridge-penalised logistic regression by exact-decimal IRLS.

    The intercept is unpenalised; ``ridge_lambda`` is applied to the four
    coefficients only. Returns standardization statistics, the fitted
    parameters, the iteration count, and the clamp hit counts.
    """
    if len(feature_rows) != len(labels) or len(feature_rows) < 2:
        raise MetricDomainError("logistic fit requires matching rows and at least two samples")
    z, means, stds = _standardization(feature_rows)
    y = [Decimal(_validate_label(value)) for value in labels]
    lam = _validate_numeric(ridge_lambda, "ridge_lambda")
    if not isinstance(max_iterations, int) or isinstance(max_iterations, bool):
        raise MetricDomainError(f"max_iterations must be an int, got {max_iterations!r}")
    if max_iterations < 1:
        raise MetricDomainError(f"max_iterations must be positive, got {max_iterations}")
    tol = _validate_numeric(tolerance, "tolerance")

    width = len(z[0])
    size = width + 1
    design = [[Decimal(1), *row] for row in z]
    beta = [Decimal(0) for _ in range(size)]
    eta_clamp_count = 0
    mu_clamp_count = 0
    for iteration in range(1, max_iterations + 1):
        eta: list[Decimal] = []
        for row in design:
            raw = _sum([_mul(row[k], beta[k]) for k in range(size)])
            value, clamped = clamp_eta(raw)
            if clamped:
                eta_clamp_count += 1
            eta.append(value)
        mu: list[Decimal] = []
        for value in eta:
            probability, clamped = clamp_mu(logistic_sigmoid(value))
            if clamped:
                mu_clamp_count += 1
            mu.append(probability)
        weights = [_mul(value, _sub(Decimal(1), value)) for value in mu]
        working = [
            _add(eta[i], _div(_sub(y[i], mu[i]), weights[i])) for i in range(len(design))
        ]
        normal = [[Decimal(0) for _ in range(size)] for _ in range(size)]
        rhs = [Decimal(0) for _ in range(size)]
        for a in range(size):
            rhs[a] = _sum(
                [
                    _mul(_mul(design[i][a], weights[i]), working[i])
                    for i in range(len(design))
                ]
            )
            for b in range(size):
                normal[a][b] = _sum(
                    [
                        _mul(_mul(design[i][a], weights[i]), design[i][b])
                        for i in range(len(design))
                    ]
                )
        for k in range(1, size):
            normal[k][k] = _add(normal[k][k], lam)
        updated = _solve(normal, rhs)
        converged = all(abs(_sub(updated[k], beta[k])) < tol for k in range(size))
        beta = updated
        if converged:
            return {
                "means": means,
                "stds": stds,
                "intercept": beta[0],
                "coefficients": beta[1:],
                "converged_iterations": iteration,
                "eta_clamp_count": eta_clamp_count,
                "mu_clamp_count": mu_clamp_count,
            }
    raise MetricDomainError(
        f"irls_did_not_converge within {max_iterations} iterations"
    )


def predict_probability(
    fit: dict[str, object], features: Sequence[object]
) -> tuple[Decimal, bool]:
    """Q18-quantized up-probability for one row under a fitted fold model."""
    means = fit["means"]
    stds = fit["stds"]
    coefficients = fit["coefficients"]
    if len(features) != len(means):
        raise MetricDomainError("prediction feature width does not match the fitted model")
    eta = fit["intercept"]
    for j, value in enumerate(features):
        numeric = _validate_numeric(value, FEATURE_NAMES[j] if j < len(FEATURE_NAMES) else str(j))
        standardized = _div(_sub(numeric, means[j]), stds[j])
        eta = _add(eta, _mul(coefficients[j], standardized))
    clamped_eta, clamped = clamp_eta(eta)
    return quantize_q18(logistic_sigmoid(clamped_eta)), clamped


def log_loss(probabilities: Sequence[Decimal], labels: Sequence[object]) -> Decimal:
    """-mean( ln p for y=1, ln(1-p) for y=0 ), p clamped inside the log."""
    if not probabilities or len(probabilities) != len(labels):
        raise MetricDomainError("log_loss requires matching non-empty inputs")
    terms: list[Decimal] = []
    for probability, label in zip(probabilities, labels, strict=True):
        value = _validate_numeric(probability, "probability")
        guarded, _ = clamp_mu(value)
        if _validate_label(label) == 1:
            terms.append(_ln(guarded))
        else:
            terms.append(_ln(_sub(Decimal(1), guarded)))
    return -_mean(terms)


def brier(probabilities: Sequence[Decimal], labels: Sequence[object]) -> Decimal:
    """mean (p - y)^2."""
    if not probabilities or len(probabilities) != len(labels):
        raise MetricDomainError("brier requires matching non-empty inputs")
    terms: list[Decimal] = []
    for probability, label in zip(probabilities, labels, strict=True):
        value = _validate_numeric(probability, "probability")
        error = _sub(value, Decimal(_validate_label(label)))
        terms.append(_mul(error, error))
    return _mean(terms)


def _pearson(pairs: Sequence[tuple[Decimal, Decimal]], name: str) -> Decimal:
    if len(pairs) < 2:
        raise MetricDomainError(f"fewer than two prediction pairs for {name}: {len(pairs)}")
    mean_x = _mean([pair[0] for pair in pairs])
    mean_y = _mean([pair[1] for pair in pairs])
    dx = [_sub(pair[0], mean_x) for pair in pairs]
    dy = [_sub(pair[1], mean_y) for pair in pairs]
    numerator = _sum([_mul(a, b) for a, b in zip(dx, dy, strict=True)])
    sx = _sum([_mul(value, value) for value in dx])
    sy = _sum([_mul(value, value) for value in dy])
    if sx.is_zero() or sy.is_zero():
        raise MetricDomainError(f"zero variance prevents {name}")
    result = _div(numerator, _sqrt(_mul(sx, sy)))
    if result < Decimal(-1) or result > Decimal(1):
        raise MetricDomainError(f"{name} out of bounds: {result}")
    return result


def direction_ic(probabilities: Sequence[Decimal], labels: Sequence[object]) -> Decimal:
    """Pearson IC of the predicted up-probability against the binary label."""
    pairs = [
        (
            _validate_numeric(probability, "probability"),
            Decimal(_validate_label(label)),
        )
        for probability, label in zip(probabilities, labels, strict=True)
    ]
    return _pearson(pairs, "direction_ic")


def climatology_probability(up_count: int, down_count: int) -> Decimal:
    """Train-window up-rate as a Q18 constant probability baseline."""
    for name, value in (("up_count", up_count), ("down_count", down_count)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise MetricDomainError(f"climatology {name} must be a non-negative int: {value!r}")
    total = up_count + down_count
    if total == 0:
        raise MetricDomainError("climatology baseline requires at least one labeled train row")
    return quantize_q18(_div(Decimal(up_count), Decimal(total)))


def _sign(value: Decimal) -> int:
    return 1 if value > 0 else (-1 if value < 0 else 0)


def _accuracy(predicted: Sequence[int], actual: Sequence[int]) -> Decimal:
    if not predicted or len(predicted) != len(actual):
        raise MetricDomainError("directional accuracy requires matching non-empty inputs")
    correct = sum(1 for left, right in zip(predicted, actual, strict=True) if left == right)
    return _div(Decimal(correct), Decimal(len(actual)))


def build_logistic_training_records(
    validation_folds: Sequence[dict], research_rows: Sequence[Sequence]
) -> list[dict]:
    """Per-fold logistic IRLS fit, prediction, metrics, and causal baselines."""
    records: list[dict] = []
    for fold in validation_folds:
        train_start, train_end = fold["train_range"]
        test_start, test_end = fold["test_range"]
        train_rows = research_rows[train_start:train_end]

        usable = []
        zero_train_label_count = 0
        train_directions: list[int] = []
        for row in train_rows:
            direction = row[DIRECTION_INDEX]
            if direction is not None:
                if direction not in (-1, 0, 1):
                    raise MetricDomainError("train direction labels must be -1, 0, or 1")
                train_directions.append(direction)
                if direction == 0:
                    zero_train_label_count += 1
            if direction in (None, 0):
                continue
            if any(row[index] is None for index in FEATURE_INDICES):
                continue
            usable.append(row)
        if len(usable) < MINIMUM_USABLE_TRAIN_ROWS:
            raise MetricDomainError(
                f"fold {fold['fold_id']} requires at least "
                f"{MINIMUM_USABLE_TRAIN_ROWS} usable train rows; got {len(usable)}"
            )
        matrix = [[row[index] for index in FEATURE_INDICES] for row in usable]
        train_labels = [1 if row[DIRECTION_INDEX] == 1 else 0 for row in usable]
        first = fit_logistic_irls(matrix, train_labels)
        second = fit_logistic_irls(matrix, train_labels)
        if first != second:
            raise MetricDomainError(f"fold {fold['fold_id']} IRLS solve is non-deterministic")

        up_count = sum(value == 1 for value in train_directions)
        down_count = sum(value == -1 for value in train_directions)
        majority_direction = 1 if up_count >= down_count else -1
        climatology_p = climatology_probability(up_count, down_count)
        climatology_direction = 1 if climatology_p >= Decimal("0.5") else -1

        predictions: list[dict] = []
        probabilities: list[Decimal] = []
        scored_labels: list[int] = []
        predicted_directions: list[int] = []
        actual_directions: list[int] = []
        sign_ret_directions: list[int] = []
        return_pairs: list[tuple[Decimal, Decimal]] = []
        feature_null_count = 0
        return_null_count = 0
        direction_null_count = 0
        zero_label_count = 0
        predict_eta_clamp_count = 0
        for row_index in range(test_start, test_end):
            row = research_rows[row_index]
            has_feature_null = any(row[index] is None for index in FEATURE_INDICES)
            if has_feature_null:
                feature_null_count += 1
            if row[RETURN_INDEX] is None:
                return_null_count += 1
            direction = row[DIRECTION_INDEX]
            if direction is None:
                direction_null_count += 1
            elif direction not in (-1, 0, 1):
                raise MetricDomainError("test direction labels must be -1, 0, or 1")
            elif direction == 0:
                zero_label_count += 1
            if (
                has_feature_null
                or row[RETURN_INDEX] is None
                or direction is None
                or direction == 0
            ):
                continue
            features = [row[index] for index in FEATURE_INDICES]
            probability, clamped = predict_probability(first, features)
            if clamped:
                predict_eta_clamp_count += 1
            label = 1 if direction == 1 else 0
            predicted_direction = 1 if probability >= Decimal("0.5") else -1
            forward_return = _validate_numeric(row[RETURN_INDEX], "l_fwdret_24")
            probabilities.append(probability)
            scored_labels.append(label)
            predicted_directions.append(predicted_direction)
            actual_directions.append(direction)
            sign_ret_directions.append(
                _sign(_validate_numeric(row[FEATURE_INDICES[0]], FEATURE_NAMES[0]))
            )
            return_pairs.append((probability, forward_return))
            predictions.append(
                {
                    "row_index": row_index,
                    "probability": _q18(probability),
                    "label": label,
                    "direction": direction,
                    "predicted_direction": predicted_direction,
                    "target": _q18(forward_return),
                }
            )

        predicted_count = len(predictions)
        record = {
            "fold_id": fold["fold_id"],
            "train_range": list(fold["train_range"]),
            "embargo_range": list(fold["embargo_range"]),
            "test_range": list(fold["test_range"]),
            "train_row_count": len(train_rows),
            "usable_train_count": len(usable),
            "excluded_train_count": len(train_rows) - len(usable),
            "zero_train_label_count": zero_train_label_count,
            "test_row_count": test_end - test_start,
            "predicted_count": predicted_count,
            "excluded_test_count": (test_end - test_start) - predicted_count,
            "feature_null_count": feature_null_count,
            "target_null_count": return_null_count,
            "direction_null_count": direction_null_count,
            "zero_label_count": zero_label_count,
            "feature_means": {
                name: _q18(first["means"][i]) for i, name in enumerate(FEATURE_NAMES)
            },
            "feature_stds": {
                name: _q18(first["stds"][i]) for i, name in enumerate(FEATURE_NAMES)
            },
            "coefficients": {
                name: _q18(first["coefficients"][i]) for i, name in enumerate(FEATURE_NAMES)
            },
            "intercept": _q18(first["intercept"]),
            "converged_iterations": first["converged_iterations"],
            "eta_clamp_count": first["eta_clamp_count"],
            "mu_clamp_count": first["mu_clamp_count"],
            "predict_eta_clamp_count": predict_eta_clamp_count,
            "solver_deterministic": True,
            "directional_accuracy": _q18(_accuracy(predicted_directions, actual_directions)),
            "log_loss": _q18(log_loss(probabilities, scored_labels)),
            "brier": _q18(brier(probabilities, scored_labels)),
            "direction_ic": _q18(direction_ic(probabilities, scored_labels)),
            "pearson_ic": _q18(_pearson(return_pairs, "pearson_ic")),
            "predictions": predictions,
            "baselines": {
                "majority_class_train_window": {
                    "directional_accuracy": _q18(
                        _accuracy([majority_direction] * predicted_count, actual_directions)
                    ),
                    "predicted_direction": majority_direction,
                    "train_up_count": up_count,
                    "train_down_count": down_count,
                    "train_zero_count": zero_train_label_count,
                },
                "sign_f_ret_1": {
                    "directional_accuracy": _q18(
                        _accuracy(sign_ret_directions, actual_directions)
                    )
                },
                "climatology_p": {
                    "probability": _q18(climatology_p),
                    "predicted_direction": climatology_direction,
                    "directional_accuracy": _q18(
                        _accuracy([climatology_direction] * predicted_count, actual_directions)
                    ),
                    "log_loss": _q18(
                        log_loss([climatology_p] * predicted_count, scored_labels)
                    ),
                    "brier": _q18(brier([climatology_p] * predicted_count, scored_labels)),
                },
            },
        }
        records.append(record)
    return records


def _summary(values: Sequence[Decimal], total_count: int) -> dict:
    ordered = sorted(values)
    count = len(ordered)
    if count == 0:
        raise MetricDomainError("cannot summarize zero folds")
    if count % 2:
        median = ordered[count // 2]
    else:
        median = _div(_add(ordered[count // 2 - 1], ordered[count // 2]), Decimal(2))
    return {
        "equal_weight_mean": _q18(_mean(values)),
        "median": _q18(median),
        "minimum": _q18(ordered[0]),
        "maximum": _q18(ordered[-1]),
        "positive_fold_count": sum(value > 0 for value in values),
        "negative_fold_count": sum(value < 0 for value in values),
        "zero_fold_count": sum(value == 0 for value in values),
        "fold_count": count,
        "total_predicted_count": total_count,
    }


def build_logistic_training_summaries(records: Sequence[dict]) -> tuple[list[dict], dict]:
    total = sum(record["predicted_count"] for record in records)
    summaries = []
    for metric in METRICS:
        values = [Decimal(record[metric]) for record in records]
        summaries.append({"metric": metric, **_summary(values, total)})
    baselines: dict[str, dict] = {}
    for baseline in BASELINES:
        baselines[baseline] = {
            metric: _summary(
                [Decimal(record["baselines"][baseline][metric]) for record in records],
                total,
            )
            for metric in BASELINE_METRICS[baseline]
        }
    return summaries, baselines


def _summary_mean(summaries: Sequence[dict], metric: str) -> str:
    for item in summaries:
        if item.get("metric") == metric:
            value = item.get("equal_weight_mean")
            if not isinstance(value, str):
                raise MetricDomainError(f"summary {metric} equal_weight_mean is not a string")
            return value
    raise MetricDomainError(f"summary block missing metric {metric}")


def _baseline_mean(baselines: dict, baseline: str, metric: str) -> str:
    try:
        value = baselines[baseline][metric]["equal_weight_mean"]
    except (KeyError, TypeError) as exc:
        raise MetricDomainError(
            f"baseline summary missing {baseline}.{metric}"
        ) from exc
    if not isinstance(value, str):
        raise MetricDomainError(f"baseline {baseline}.{metric} mean is not a string")
    return value


def evaluate_kill_criteria(
    summaries: Sequence[dict],
    baselines: dict,
    constants: dict[str, str] | None = None,
) -> dict:
    """Pure kill-criteria evaluation over published summaries only.

    Consumes summary and baseline-summary blocks — never test rows — so the
    decision cannot see prediction-level data. ``constants`` defaults to the
    pre-registered module constants; a caller may pass the descriptor's pinned
    block (the same values) so the artifact and the descriptor agree by
    construction. The thresholds are never derived from observed values.
    """
    pinned = dict(KILL_CRITERIA if constants is None else constants)
    if set(pinned) != set(KILL_CRITERIA):
        raise MetricDomainError(f"kill-criteria constants must be {sorted(KILL_CRITERIA)}")
    observed = {
        "directional_accuracy_mean": _summary_mean(summaries, "directional_accuracy"),
        "direction_ic_mean": _summary_mean(summaries, "direction_ic"),
        "log_loss_mean": _summary_mean(summaries, "log_loss"),
        "brier_mean": _summary_mean(summaries, "brier"),
        "pearson_ic_mean": _summary_mean(summaries, "pearson_ic"),
    }
    for baseline in BASELINES:
        for metric in BASELINE_METRICS[baseline]:
            observed[f"{baseline}_{metric}_mean"] = _baseline_mean(baselines, baseline, metric)
    results = {
        "k1_directional_accuracy": Decimal(observed["directional_accuracy_mean"])
        >= Decimal(pinned["directional_accuracy_min"]),
        "k2_direction_ic": Decimal(observed["direction_ic_mean"])
        >= Decimal(pinned["direction_ic_min"]),
        "k3_log_loss": Decimal(observed["log_loss_mean"]) <= Decimal(pinned["log_loss_max"]),
        "k4_brier": Decimal(observed["brier_mean"]) <= Decimal(pinned["brier_max"]),
    }
    return {
        "constants": pinned,
        "observed": observed,
        "results": {key: bool(results[key]) for key in KILL_RESULT_KEYS},
        "all_passed": all(bool(results[key]) for key in KILL_RESULT_KEYS),
    }
