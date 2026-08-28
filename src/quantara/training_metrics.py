"""Exact-Decimal ridge training and honest walk-forward metrics."""

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
TARGET_INDEX = 5
DIRECTION_INDEX = 6
FEATURE_NAMES = ("f_ret_1", "f_roc_60", "f_rvol_20", "f_volratio_20")
METRICS = ("pearson_ic", "directional_accuracy", "mse")
BASELINES = ("majority_class_train_window", "sign_f_ret_1")


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
    size = len(vector)
    augmented = [list(matrix[i]) + [vector[i]] for i in range(size)]
    for column in range(size):
        pivot_row = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if augmented[pivot_row][column].is_zero():
            raise MetricDomainError("zero pivot in ridge solver")
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
                augmented[row][j] = _sub(
                    augmented[row][j], _mul(factor, augmented[column][j])
                )
    return [augmented[row][size] for row in range(size)]


def fit_ridge_matrix(
    feature_rows: Sequence[Sequence[object]],
    targets: Sequence[object],
    ridge_lambda: Decimal = Decimal("1"),
) -> dict[str, object]:
    """Standardize a matrix and solve its centered ridge normal equations."""
    if len(feature_rows) != len(targets) or len(feature_rows) < 2:
        raise MetricDomainError("ridge matrix requires matching rows and at least two samples")
    width = len(feature_rows[0])
    if width == 0 or any(len(row) != width for row in feature_rows):
        raise MetricDomainError("ridge feature matrix must be non-empty and rectangular")
    x = [
        [_validate_numeric(value, f"feature[{j}]") for j, value in enumerate(row)]
        for row in feature_rows
    ]
    y = [_validate_numeric(value, "target") for value in targets]
    lam = _validate_numeric(ridge_lambda, "ridge_lambda")
    means = [_mean([row[j] for row in x]) for j in range(width)]
    stds: list[Decimal] = []
    for j in range(width):
        variance = _mean([_mul(_sub(row[j], means[j]), _sub(row[j], means[j])) for row in x])
        std = _sqrt(variance)
        if std.is_zero():
            raise MetricDomainError(f"zero train-window standard deviation for feature[{j}]")
        stds.append(std)
    z = [[_div(_sub(row[j], means[j]), stds[j]) for j in range(width)] for row in x]
    intercept = _mean(y)
    centered_y = [_sub(value, intercept) for value in y]
    normal = [[Decimal(0) for _ in range(width)] for _ in range(width)]
    rhs = [Decimal(0) for _ in range(width)]
    for j in range(width):
        rhs[j] = _sum([_mul(row[j], value) for row, value in zip(z, centered_y, strict=True)])
        for k in range(width):
            normal[j][k] = _sum([_mul(row[j], row[k]) for row in z])
        normal[j][j] = _add(normal[j][j], lam)
    coefficients = _solve(normal, rhs)
    return {
        "means": means,
        "stds": stds,
        "coefficients": coefficients,
        "intercept": intercept,
    }


def _pearson(pairs: Sequence[tuple[Decimal, Decimal]]) -> Decimal:
    if len(pairs) < 2:
        raise MetricDomainError(f"fewer than two prediction pairs: {len(pairs)}")
    mean_x = _mean([pair[0] for pair in pairs])
    mean_y = _mean([pair[1] for pair in pairs])
    dx = [_sub(pair[0], mean_x) for pair in pairs]
    dy = [_sub(pair[1], mean_y) for pair in pairs]
    numerator = _sum([_mul(a, b) for a, b in zip(dx, dy, strict=True)])
    sx = _sum([_mul(value, value) for value in dx])
    sy = _sum([_mul(value, value) for value in dy])
    if sx.is_zero() or sy.is_zero():
        raise MetricDomainError("zero prediction or target variance prevents pearson_ic")
    result = _div(numerator, _sqrt(_mul(sx, sy)))
    if result < Decimal(-1) or result > Decimal(1):
        raise MetricDomainError(f"pearson_ic out of bounds: {result}")
    return result


def _sign(value: Decimal) -> int:
    return 1 if value > 0 else (-1 if value < 0 else 0)


def _accuracy(predicted: Sequence[int], actual: Sequence[int]) -> Decimal:
    if not predicted or len(predicted) != len(actual):
        raise MetricDomainError("directional accuracy requires matching non-empty inputs")
    correct = sum(1 for left, right in zip(predicted, actual, strict=True) if left == right)
    return _div(Decimal(correct), Decimal(len(actual)))


def build_training_records(
    validation_folds: Sequence[dict], research_rows: Sequence[Sequence]
) -> list[dict]:
    records: list[dict] = []
    for fold in validation_folds:
        train_start, train_end = fold["train_range"]
        test_start, test_end = fold["test_range"]
        train_rows = research_rows[train_start:train_end]
        usable = [
            row
            for row in train_rows
            if all(row[index] is not None for index in (*FEATURE_INDICES, TARGET_INDEX))
        ]
        if len(usable) < 200:
            raise MetricDomainError(
                f"fold {fold['fold_id']} requires at least 200 usable train rows; got {len(usable)}"
            )
        matrix = [[row[index] for index in FEATURE_INDICES] for row in usable]
        targets = [row[TARGET_INDEX] for row in usable]
        first = fit_ridge_matrix(matrix, targets)
        second = fit_ridge_matrix(matrix, targets)
        if first != second:
            raise MetricDomainError(f"fold {fold['fold_id']} ridge solve is non-deterministic")

        train_directions = [
            row[DIRECTION_INDEX]
            for row in train_rows
            if row[DIRECTION_INDEX] is not None
        ]
        if any(value not in (-1, 0, 1) for value in train_directions):
            raise MetricDomainError("train direction labels must be -1, 0, or 1")
        up_count = sum(value == 1 for value in train_directions)
        down_count = sum(value == -1 for value in train_directions)
        zero_train_count = sum(value == 0 for value in train_directions)
        majority_direction = 1 if up_count >= down_count else -1

        prediction_pairs: list[tuple[Decimal, Decimal]] = []
        predicted_signs: list[int] = []
        actual_signs: list[int] = []
        sign_ret_signs: list[int] = []
        predictions: list[dict] = []
        feature_null_count = target_null_count = direction_null_count = 0
        squared_errors: list[Decimal] = []
        for row_index in range(test_start, test_end):
            row = research_rows[row_index]
            has_feature_null = any(row[index] is None for index in FEATURE_INDICES)
            if has_feature_null:
                feature_null_count += 1
            if row[TARGET_INDEX] is None:
                target_null_count += 1
            if row[DIRECTION_INDEX] is None:
                direction_null_count += 1
            if has_feature_null or row[TARGET_INDEX] is None or row[DIRECTION_INDEX] is None:
                continue
            values = [
                _validate_numeric(row[index], FEATURE_NAMES[j])
                for j, index in enumerate(FEATURE_INDICES)
            ]
            prediction = first["intercept"]
            for j, value in enumerate(values):
                standardized = _div(_sub(value, first["means"][j]), first["stds"][j])
                prediction = _add(prediction, _mul(first["coefficients"][j], standardized))
            stored_prediction = quantize_q18(prediction)
            target = _validate_numeric(row[TARGET_INDEX], "l_fwdret_24")
            actual_direction = row[DIRECTION_INDEX]
            if actual_direction not in (-1, 0, 1):
                raise MetricDomainError("test direction labels must be -1, 0, or 1")
            prediction_pairs.append((stored_prediction, target))
            predicted_signs.append(_sign(stored_prediction))
            actual_signs.append(actual_direction)
            sign_ret_signs.append(_sign(values[0]))
            error = _sub(stored_prediction, target)
            squared_errors.append(_mul(error, error))
            predictions.append(
                {
                    "row_index": row_index,
                    "prediction": _q18(stored_prediction),
                    "target": _q18(target),
                    "direction": actual_direction,
                }
            )
        predicted_count = len(predictions)
        majority_accuracy = _accuracy([majority_direction] * predicted_count, actual_signs)
        record = {
            "fold_id": fold["fold_id"],
            "train_range": list(fold["train_range"]),
            "embargo_range": list(fold["embargo_range"]),
            "test_range": list(fold["test_range"]),
            "train_row_count": len(train_rows),
            "usable_train_count": len(usable),
            "excluded_train_count": len(train_rows) - len(usable),
            "test_row_count": test_end - test_start,
            "predicted_count": predicted_count,
            "excluded_test_count": (test_end - test_start) - predicted_count,
            "feature_null_count": feature_null_count,
            "target_null_count": target_null_count,
            "direction_null_count": direction_null_count,
            "feature_means": {
                name: _q18(first["means"][i])
                for i, name in enumerate(FEATURE_NAMES)
            },
            "feature_stds": {name: _q18(first["stds"][i]) for i, name in enumerate(FEATURE_NAMES)},
            "coefficients": {
                name: _q18(first["coefficients"][i])
                for i, name in enumerate(FEATURE_NAMES)
            },
            "intercept": _q18(first["intercept"]),
            "solver_deterministic": True,
            "pearson_ic": _q18(_pearson(prediction_pairs)),
            "directional_accuracy": _q18(_accuracy(predicted_signs, actual_signs)),
            "mse": _q18(_mean(squared_errors)),
            "zero_prediction_count": sum(value == 0 for value in predicted_signs),
            "zero_label_count": sum(value == 0 for value in actual_signs),
            "predictions": predictions,
            "baselines": {
                "majority_class_train_window": {
                    "directional_accuracy": _q18(majority_accuracy),
                    "predicted_direction": majority_direction,
                    "train_up_count": up_count,
                    "train_down_count": down_count,
                    "train_zero_count": zero_train_count,
                },
                "sign_f_ret_1": {
                    "directional_accuracy": _q18(_accuracy(sign_ret_signs, actual_signs))
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


def build_training_summaries(records: Sequence[dict]) -> tuple[list[dict], dict]:
    total = sum(record["predicted_count"] for record in records)
    summaries = []
    for metric in METRICS:
        values = [Decimal(record[metric]) for record in records]
        summaries.append({"metric": metric, **_summary(values, total)})
    baselines = {}
    for baseline in BASELINES:
        values = [
            Decimal(record["baselines"][baseline]["directional_accuracy"])
            for record in records
        ]
        baselines[baseline] = _summary(values, total)
    return summaries, baselines
