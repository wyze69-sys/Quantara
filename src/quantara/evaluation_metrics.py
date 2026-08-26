"""Deterministic Decimal Pearson and Spearman correlation engine (data slice 006).

Implements exact Decimal IC computation over out-of-sample test folds:
- Dedicated decimal.Context: prec 50, ROUND_HALF_EVEN, Emin/Emax ±999999, traps for
  InvalidOperation, DivisionByZero, Overflow;
- Independent null accounting (feature_null, target_null, valid, excluded);
- Deterministic average ranks with 1-based positions and exact tie-group means;
- Single ROUND_HALF_EVEN Q18 quantization at storage boundary;
- Pre- and post-quantization [-1, 1] bounds checks;
- Zero feature/target variance and <2 pairs loud rejection;
- Cross-fold summary statistics computed from stored Q18 values.
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

__all__ = [
    "DECIMAL_CONTEXT",
    "DECIMAL_CONTRACT",
    "STORAGE_QUANTUM",
    "MetricDomainError",
    "average_ranks",
    "build_evaluation_records",
    "build_evaluation_summaries",
    "evaluate_fold_feature",
]

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
STORAGE_QUANTUM = Decimal("0.000000000000000001")

FEATURE_COLUMN_INDICES: dict[str, int] = {
    "f_ret_1": 1,
    "f_roc_60": 2,
    "f_rvol_20": 3,
    "f_volratio_20": 4,
}
TARGET_COLUMN_INDEX = 5


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


def _quantize_q18(a: Decimal) -> Decimal:
    res = DECIMAL_CONTEXT.quantize(a, STORAGE_QUANTUM)
    if res.is_zero():
        return Decimal("0").quantize(STORAGE_QUANTUM)
    return res


def _format_q18(a: Decimal) -> str:
    return format(a, "f")


def _validate_numeric(val: object, name: str) -> Decimal:
    if isinstance(val, bool):
        raise MetricDomainError(f"boolean input not permitted for {name}: {val!r}")
    if isinstance(val, float):
        raise MetricDomainError(f"binary float input not permitted for {name}: {val!r}")
    try:
        dec = val if isinstance(val, Decimal) else Decimal(str(val))
    except Exception as exc:
        raise MetricDomainError(f"malformed numeric input for {name}: {val!r}") from exc
    if dec.is_nan() or dec.is_infinite():
        raise MetricDomainError(f"non-finite numeric input for {name}: {val!r}")
    return dec


def average_ranks(values: Sequence[Decimal]) -> list[Decimal]:
    """Deterministic average ranks with 1-based positions and exact tie-group means."""
    if not values:
        return []
    n = len(values)
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks: list[Decimal] = [Decimal(0)] * n

    start = 0
    while start < n:
        end = start
        val = indexed[start][1]
        while end + 1 < n and indexed[end + 1][1] == val:
            end += 1
        start_pos = Decimal(start + 1)
        end_pos = Decimal(end + 1)
        rank_mean = _div(_add(start_pos, end_pos), Decimal(2))
        for i in range(start, end + 1):
            orig_idx = indexed[i][0]
            ranks[orig_idx] = rank_mean
        start = end + 1

    return ranks


def _compute_pearson(valid_pairs: Sequence[tuple[Decimal, Decimal]]) -> str:
    n = Decimal(len(valid_pairs))
    if len(valid_pairs) < 2:
        raise MetricDomainError(f"fewer than two valid pairs: {len(valid_pairs)}")

    sum_x = Decimal(0)
    sum_y = Decimal(0)
    for x, y in valid_pairs:
        sum_x = _add(sum_x, x)
        sum_y = _add(sum_y, y)
    mean_x = _div(sum_x, n)
    mean_y = _div(sum_y, n)

    numerator = Decimal(0)
    sum_sq_x = Decimal(0)
    sum_sq_y = Decimal(0)
    for x, y in valid_pairs:
        dx = _sub(x, mean_x)
        dy = _sub(y, mean_y)
        numerator = _add(numerator, _mul(dx, dy))
        sum_sq_x = _add(sum_sq_x, _mul(dx, dx))
        sum_sq_y = _add(sum_sq_y, _mul(dy, dy))

    if sum_sq_x.is_zero():
        raise MetricDomainError("zero feature variance prevents metric computation")
    if sum_sq_y.is_zero():
        raise MetricDomainError("zero target variance prevents metric computation")

    denom_sq = _mul(sum_sq_x, sum_sq_y)
    denominator = _sqrt(denom_sq)
    pearson_raw = _div(numerator, denominator)

    one = Decimal(1)
    minus_one = Decimal(-1)
    if pearson_raw < minus_one or pearson_raw > one:
        raise MetricDomainError(
            f"pearson_ic out of [-1, 1] bounds before quantization: {pearson_raw}"
        )

    pearson_q18 = _quantize_q18(pearson_raw)
    if pearson_q18 < minus_one or pearson_q18 > one:
        raise MetricDomainError(
            f"pearson_ic out of [-1, 1] bounds after quantization: {pearson_q18}"
        )

    return _format_q18(pearson_q18)


def _compute_spearman(valid_pairs: Sequence[tuple[Decimal, Decimal]]) -> str:
    x_ranks = average_ranks([p[0] for p in valid_pairs])
    y_ranks = average_ranks([p[1] for p in valid_pairs])
    rank_pairs = list(zip(x_ranks, y_ranks, strict=True))
    return _compute_pearson(rank_pairs)


def evaluate_fold_feature(
    fold_id: int,
    feature: str,
    target: str,
    test_range: Sequence[int],
    test_rows: Sequence[Sequence],
    feature_idx: int = 1,
    target_idx: int = 5,
) -> dict:
    """Evaluate one fold-feature pair and return its deterministic record."""
    test_row_count = len(test_rows)
    feature_null_count = 0
    target_null_count = 0
    valid_pairs: list[tuple[Decimal, Decimal]] = []

    for row in test_rows:
        val_x = row[feature_idx]
        val_y = row[target_idx]
        x_is_null = val_x is None
        y_is_null = val_y is None
        if x_is_null:
            feature_null_count += 1
        if y_is_null:
            target_null_count += 1
        if not x_is_null and not y_is_null:
            dec_x = _validate_numeric(val_x, feature)
            dec_y = _validate_numeric(val_y, target)
            valid_pairs.append((dec_x, dec_y))

    valid_pair_count = len(valid_pairs)
    excluded_pair_count = test_row_count - valid_pair_count

    pearson_str = _compute_pearson(valid_pairs)
    spearman_str = _compute_spearman(valid_pairs)

    return {
        "fold_id": fold_id,
        "feature": feature,
        "target": target,
        "test_range": list(test_range),
        "test_row_count": test_row_count,
        "valid_pair_count": valid_pair_count,
        "excluded_pair_count": excluded_pair_count,
        "feature_null_count": feature_null_count,
        "target_null_count": target_null_count,
        "pearson_ic": pearson_str,
        "spearman_ic": spearman_str,
    }


def build_evaluation_records(
    validation_folds: Sequence[dict],
    research_rows: Sequence[Sequence],
    features: Sequence[str] = ("f_ret_1", "f_roc_60", "f_rvol_20", "f_volratio_20"),
    target: str = "l_fwdret_24",
) -> list[dict]:
    """Build all fold-feature records in fold-major, feature-major order."""
    records: list[dict] = []
    for fold in validation_folds:
        test_start, test_end = fold["test_range"]
        fold_rows = research_rows[test_start:test_end]
        for feature in features:
            f_idx = FEATURE_COLUMN_INDICES[feature]
            rec = evaluate_fold_feature(
                fold_id=fold["fold_id"],
                feature=feature,
                target=target,
                test_range=fold["test_range"],
                test_rows=fold_rows,
                feature_idx=f_idx,
                target_idx=TARGET_COLUMN_INDEX,
            )
            records.append(rec)
    return records


def build_evaluation_summaries(
    records: Sequence[dict],
    features: Sequence[str] = ("f_ret_1", "f_roc_60", "f_rvol_20", "f_volratio_20"),
    metrics: Sequence[str] = ("pearson_ic", "spearman_ic"),
) -> list[dict]:
    """Build cross-fold summary objects in feature-major, metric-major order."""
    summaries: list[dict] = []
    zero = Decimal(0)
    for feature in features:
        feature_records = [r for r in records if r["feature"] == feature]
        if not feature_records:
            raise MetricDomainError(f"no records found for feature {feature!r}")
        total_valid_pair_count = sum(r["valid_pair_count"] for r in feature_records)
        fold_count = len(feature_records)

        for metric in metrics:
            metric_vals = [Decimal(r[metric]) for r in feature_records]
            pos_count = sum(1 for v in metric_vals if v > zero)
            neg_count = sum(1 for v in metric_vals if v < zero)
            zero_count = sum(1 for v in metric_vals if v == zero)

            minimum = min(metric_vals)
            maximum = max(metric_vals)

            sorted_vals = sorted(metric_vals)
            n_vals = len(sorted_vals)
            if n_vals % 2 == 1:
                median = sorted_vals[n_vals // 2]
            else:
                mid = n_vals // 2
                mid_sum = _add(sorted_vals[mid - 1], sorted_vals[mid])
                median = _quantize_q18(_div(mid_sum, Decimal(2)))

            sum_all = Decimal(0)
            for v in metric_vals:
                sum_all = _add(sum_all, v)
            mean_raw = _div(sum_all, Decimal(fold_count))
            equal_weight_mean = _quantize_q18(mean_raw)

            summaries.append(
                {
                    "feature": feature,
                    "metric": metric,
                    "fold_count": fold_count,
                    "total_valid_pair_count": total_valid_pair_count,
                    "positive_fold_count": pos_count,
                    "negative_fold_count": neg_count,
                    "zero_fold_count": zero_count,
                    "minimum": _format_q18(minimum),
                    "maximum": _format_q18(maximum),
                    "median": _format_q18(median),
                    "equal_weight_mean": _format_q18(equal_weight_mean),
                }
            )
    return summaries
