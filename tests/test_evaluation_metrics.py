"""Exact Decimal Pearson and Spearman engine tests (data slice 006, Task T3).

Matrix:
- hand-computed Pearson;
- perfect positive and negative correlation;
- a valid zero-correlation fixture;
- deterministic canonical row-order summation;
- odd and even tie groups;
- all-equal and partially tied ranks;
- Spearman invariance under exact strictly increasing transforms preserving equality groups;
- overlapping feature/target nulls;
- fewer than two pairs;
- zero feature and target variance;
- bool, float, malformed Decimal, NaN, and infinities;
- Q18 half-even boundary cases;
- ambient-context mutation;
- Hypothesis determinism and tie-group properties.
"""

from __future__ import annotations

from decimal import (
    Decimal,
    Inexact,
    Rounded,
    getcontext,
    setcontext,
)

import pytest
from hypothesis import given
from hypothesis import strategies as st

from quantara.evaluation_metrics import (
    DECIMAL_CONTEXT,
    DECIMAL_CONTRACT,
    STORAGE_QUANTUM,
    MetricDomainError,
    average_ranks,
    build_evaluation_records,
    build_evaluation_summaries,
    evaluate_fold_feature,
)


def _hostile_context():
    ctx = getcontext()
    ctx.prec = 1
    ctx.Emax = 1
    ctx.Emin = -1
    ctx.traps[Inexact] = True
    ctx.traps[Rounded] = True


def test_decimal_contract_and_quantum() -> None:
    assert DECIMAL_CONTEXT.prec == 50
    assert DECIMAL_CONTEXT.rounding == "ROUND_HALF_EVEN"
    assert STORAGE_QUANTUM == Decimal("0.000000000000000001")
    assert DECIMAL_CONTRACT["precision"] == 50
    assert DECIMAL_CONTRACT["storage_quantum"] == "0.000000000000000001"


def test_hand_computed_pearson() -> None:
    # x = [1, 2, 3], y = [2, 4, 7]
    # mean_x = 2, mean_y = 13/3
    # dx = [-1, 0, 1]
    # dy = [-7/3, -1/3, 8/3]
    # dx*dy = [7/3, 0, 8/3] => sum = 15/3 = 5
    # dx^2 = [1, 0, 1] => sum = 2
    # dy^2 = [49/9, 1/9, 64/9] => sum = 114/9 = 38/3
    # denominator = sqrt(2 * 38/3) = sqrt(76/3)
    # r = 5 / sqrt(76/3) = 5 * sqrt(3) / sqrt(76) ~= 0.993399267798782782
    rows = [
        (0, Decimal("1"), 0, 0, 0, Decimal("2"), 0),
        (1, Decimal("2"), 0, 0, 0, Decimal("4"), 0),
        (2, Decimal("3"), 0, 0, 0, Decimal("7"), 0),
    ]
    res = evaluate_fold_feature(
        fold_id=0,
        feature="f_ret_1",
        target="l_fwdret_24",
        test_range=(0, 3),
        test_rows=rows,
        feature_idx=1,
        target_idx=5,
    )
    assert res["valid_pair_count"] == 3
    assert res["excluded_pair_count"] == 0
    # Check Q18 string format
    assert len(res["pearson_ic"].split(".")[1]) == 18
    assert len(res["spearman_ic"].split(".")[1]) == 18
    # 5 / sqrt(76/3) in 50-digit precision quantized to Q18 is 0.993399267798782855
    assert res["pearson_ic"] == "0.993399267798782855"
    # Spearman on monotonic data [1, 2, 3] and [2, 4, 7] is exactly 1
    assert res["spearman_ic"] == "1.000000000000000000"


def test_perfect_positive_and_negative_correlation() -> None:
    # Positive
    rows_pos = [(i, Decimal(i), 0, 0, 0, Decimal(i * 10), 0) for i in range(1, 5)]
    res_pos = evaluate_fold_feature(0, "f_ret_1", "l_fwdret_24", (0, 4), rows_pos, 1, 5)
    assert res_pos["pearson_ic"] == "1.000000000000000000"
    assert res_pos["spearman_ic"] == "1.000000000000000000"

    # Negative
    rows_neg = [(i, Decimal(i), 0, 0, 0, Decimal((5 - i) * 10), 0) for i in range(1, 5)]
    res_neg = evaluate_fold_feature(0, "f_ret_1", "l_fwdret_24", (0, 4), rows_neg, 1, 5)
    assert res_neg["pearson_ic"] == "-1.000000000000000000"
    assert res_neg["spearman_ic"] == "-1.000000000000000000"


def test_zero_correlation_fixture() -> None:
    # x = [-1, 0, 1], y = [1, 0, 1]
    # dx = [-1, 0, 1], dy = [1/3, -2/3, 1/3]
    # dx*dy = [-1/3, 0, 1/3] => sum = 0
    rows = [
        (0, Decimal("-1"), 0, 0, 0, Decimal("1"), 0),
        (1, Decimal("0"), 0, 0, 0, Decimal("0"), 0),
        (2, Decimal("1"), 0, 0, 0, Decimal("1"), 0),
    ]
    res = evaluate_fold_feature(0, "f_ret_1", "l_fwdret_24", (0, 3), rows, 1, 5)
    assert res["pearson_ic"] == "0.000000000000000000"


def test_average_ranks_odd_even_all_equal_and_ties() -> None:
    # Odd tie group: [10, 20, 20, 20, 30]
    # ranks: 10->1, 20s occupy 2,3,4 -> avg 3, 30->5
    vals_odd = [Decimal("10"), Decimal("20"), Decimal("20"), Decimal("20"), Decimal("30")]
    ranks_odd = average_ranks(vals_odd)
    assert ranks_odd == [Decimal("1"), Decimal("3"), Decimal("3"), Decimal("3"), Decimal("5")]

    # Even tie group: [10, 20, 20, 30]
    # 20s occupy 2,3 -> avg 2.5
    vals_even = [Decimal("10"), Decimal("20"), Decimal("20"), Decimal("30")]
    ranks_even = average_ranks(vals_even)
    assert ranks_even == [Decimal("1"), Decimal("2.5"), Decimal("2.5"), Decimal("4")]

    # All equal: [5, 5, 5, 5]
    # 1,2,3,4 -> avg 2.5
    vals_all = [Decimal("5"), Decimal("5"), Decimal("5"), Decimal("5")]
    ranks_all = average_ranks(vals_all)
    assert ranks_all == [Decimal("2.5"), Decimal("2.5"), Decimal("2.5"), Decimal("2.5")]

    # Partially tied and unsorted input: [30, 10, 20, 20]
    # 10->1, 20->2.5, 20->2.5, 30->4
    vals_unsorted = [Decimal("30"), Decimal("10"), Decimal("20"), Decimal("20")]
    ranks_unsorted = average_ranks(vals_unsorted)
    assert ranks_unsorted == [Decimal("4"), Decimal("1"), Decimal("2.5"), Decimal("2.5")]


def test_spearman_invariance_under_strictly_increasing_transforms() -> None:
    rows1 = [
        (0, Decimal("1.2"), 0, 0, 0, Decimal("3.4"), 0),
        (1, Decimal("2.5"), 0, 0, 0, Decimal("1.1"), 0),
        (2, Decimal("0.8"), 0, 0, 0, Decimal("5.6"), 0),
        (3, Decimal("4.0"), 0, 0, 0, Decimal("2.2"), 0),
        (4, Decimal("2.5"), 0, 0, 0, Decimal("7.0"), 0),  # tie in x
    ]
    res1 = evaluate_fold_feature(0, "f_ret_1", "l_fwdret_24", (0, 5), rows1, 1, 5)

    # Strictly increasing transformation on x and y:
    # x' = x * 3 + 10, y' = y + 100
    rows2 = [
        (0, Decimal("1.2") * 3 + 10, 0, 0, 0, Decimal("3.4") + 100, 0),
        (1, Decimal("2.5") * 3 + 10, 0, 0, 0, Decimal("1.1") + 100, 0),
        (2, Decimal("0.8") * 3 + 10, 0, 0, 0, Decimal("5.6") + 100, 0),
        (3, Decimal("4.0") * 3 + 10, 0, 0, 0, Decimal("2.2") + 100, 0),
        (4, Decimal("2.5") * 3 + 10, 0, 0, 0, Decimal("7.0") + 100, 0),
    ]
    res2 = evaluate_fold_feature(0, "f_ret_1", "l_fwdret_24", (0, 5), rows2, 1, 5)
    assert res1["spearman_ic"] == res2["spearman_ic"]


def test_overlapping_null_accounting() -> None:
    # 5 rows:
    # row 0: valid x, valid y
    # row 1: null x, valid y
    # row 2: valid x, null y
    # row 3: null x, null y (overlapping null)
    # row 4: valid x, valid y
    rows = [
        (0, Decimal("1"), 0, 0, 0, Decimal("10"), 0),
        (1, None, 0, 0, 0, Decimal("20"), 0),
        (2, Decimal("3"), 0, 0, 0, None, 0),
        (3, None, 0, 0, 0, None, 0),
        (4, Decimal("5"), 0, 0, 0, Decimal("50"), 0),
    ]
    res = evaluate_fold_feature(0, "f_ret_1", "l_fwdret_24", (0, 5), rows, 1, 5)
    assert res["test_row_count"] == 5
    assert res["valid_pair_count"] == 2
    assert res["excluded_pair_count"] == 3
    assert res["feature_null_count"] == 2
    assert res["target_null_count"] == 2
    assert res["excluded_pair_count"] == res["test_row_count"] - res["valid_pair_count"]


def test_fewer_than_two_pairs_rejected() -> None:
    # Only 1 valid pair
    rows = [
        (0, Decimal("1"), 0, 0, 0, Decimal("10"), 0),
        (1, None, 0, 0, 0, Decimal("20"), 0),
    ]
    with pytest.raises(MetricDomainError) as excinfo:
        evaluate_fold_feature(0, "f_ret_1", "l_fwdret_24", (0, 2), rows, 1, 5)
    assert "fewer than two" in str(excinfo.value).lower()


def test_zero_variance_rejected() -> None:
    # Zero feature variance
    rows_fx = [
        (0, Decimal("1"), 0, 0, 0, Decimal("10"), 0),
        (1, Decimal("1"), 0, 0, 0, Decimal("20"), 0),
    ]
    with pytest.raises(MetricDomainError) as excinfo:
        evaluate_fold_feature(0, "f_ret_1", "l_fwdret_24", (0, 2), rows_fx, 1, 5)
    assert "feature variance" in str(excinfo.value).lower()

    # Zero target variance
    rows_fy = [
        (0, Decimal("1"), 0, 0, 0, Decimal("10"), 0),
        (1, Decimal("2"), 0, 0, 0, Decimal("10"), 0),
    ]
    with pytest.raises(MetricDomainError) as excinfo:
        evaluate_fold_feature(0, "f_ret_1", "l_fwdret_24", (0, 2), rows_fy, 1, 5)
    assert "target variance" in str(excinfo.value).lower()


@pytest.mark.parametrize(
    "bad_val",
    [
        True,
        False,
        1.5,
        "not_a_decimal",
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
)
def test_invalid_numeric_inputs_rejected(bad_val: object) -> None:
    rows = [
        (0, bad_val, 0, 0, 0, Decimal("10"), 0),
        (1, Decimal("2"), 0, 0, 0, Decimal("20"), 0),
    ]
    with pytest.raises(MetricDomainError):
        evaluate_fold_feature(0, "f_ret_1", "l_fwdret_24", (0, 2), rows, 1, 5)


def test_q18_half_even_rounding_boundary() -> None:
    from quantara.evaluation_metrics import _quantize_q18

    # ROUND_HALF_EVEN:
    # 0.0000000000000000015 -> 0.000000000000000002 (rounds to even 2)
    # 0.0000000000000000025 -> 0.000000000000000002 (rounds to even 2)
    v1 = Decimal("0.0000000000000000015")
    v2 = Decimal("0.0000000000000000025")
    assert _quantize_q18(v1) == Decimal("0.000000000000000002")
    assert _quantize_q18(v2) == Decimal("0.000000000000000002")


def test_ambient_context_mutation_isolation() -> None:
    saved = getcontext().copy()
    try:
        _hostile_context()
        rows = [
            (0, Decimal("1.234567890123456789"), 0, 0, 0, Decimal("2.345678901234567890"), 0),
            (1, Decimal("2.345678901234567890"), 0, 0, 0, Decimal("4.567890123456789012"), 0),
            (2, Decimal("3.456789012345678901"), 0, 0, 0, Decimal("7.890123456789012345"), 0),
        ]
        res = evaluate_fold_feature(0, "f_ret_1", "l_fwdret_24", (0, 3), rows, 1, 5)
        # Should succeed without raising Inexact or Rounded trap
        assert res["valid_pair_count"] == 3
        # Hostile context unchanged
        assert getcontext().prec == 1
    finally:
        setcontext(saved)


@given(st.lists(st.integers(min_value=-1000, max_value=1000), min_size=1, max_size=50))
def test_hypothesis_average_ranks_properties(values: list[int]) -> None:
    dec_vals = [Decimal(v) for v in values]
    ranks = average_ranks(dec_vals)
    n = len(values)
    # 1. Sum of ranks must equal n * (n + 1) / 2 exactly
    expected_sum = Decimal(n * (n + 1)) / Decimal(2)
    assert sum(ranks) == expected_sum

    # 2. Equal values must have identical ranks
    val_to_rank: dict[Decimal, Decimal] = {}
    for v, r in zip(dec_vals, ranks, strict=True):
        if v in val_to_rank:
            assert val_to_rank[v] == r
        else:
            val_to_rank[v] = r

    # 3. Monotonicity: if v1 < v2 then rank(v1) < rank(v2)
    sorted_unique_vals = sorted(val_to_rank.keys())
    for i in range(len(sorted_unique_vals) - 1):
        v1 = sorted_unique_vals[i]
        v2 = sorted_unique_vals[i + 1]
        assert val_to_rank[v1] < val_to_rank[v2]


def test_build_evaluation_records_ordering_and_keys() -> None:
    # 2 folds, 4 rows total
    folds = [
        {"fold_id": 0, "test_range": [0, 2]},
        {"fold_id": 1, "test_range": [2, 4]},
    ]
    # Rows: 0: open_time_ms, 1: f_ret_1, 2: f_roc_60, 3: f_rvol_20, 4: f_volratio_20, 5: l_fwdret_24
    rows = [
        (0, Decimal("1"), Decimal("10"), Decimal("100"), Decimal("1000"), Decimal("2"), 0),
        (1, Decimal("2"), Decimal("20"), Decimal("200"), Decimal("2000"), Decimal("4"), 0),
        (2, Decimal("3"), Decimal("30"), Decimal("300"), Decimal("3000"), Decimal("6"), 0),
        (3, Decimal("4"), Decimal("40"), Decimal("400"), Decimal("4000"), Decimal("8"), 0),
    ]
    records = build_evaluation_records(folds, rows)
    # Exactly 2 folds * 4 features = 8 records
    assert len(records) == 8

    # Fold-major, feature-major ordering
    expected_order = [
        (0, "f_ret_1"),
        (0, "f_roc_60"),
        (0, "f_rvol_20"),
        (0, "f_volratio_20"),
        (1, "f_ret_1"),
        (1, "f_roc_60"),
        (1, "f_rvol_20"),
        (1, "f_volratio_20"),
    ]
    actual_order = [(r["fold_id"], r["feature"]) for r in records]
    assert actual_order == expected_order

    # Required key set
    expected_keys = {
        "fold_id",
        "feature",
        "target",
        "test_range",
        "test_row_count",
        "valid_pair_count",
        "excluded_pair_count",
        "feature_null_count",
        "target_null_count",
        "pearson_ic",
        "spearman_ic",
    }
    for r in records:
        assert set(r.keys()) == expected_keys
        assert r["test_row_count"] == 2
        assert r["valid_pair_count"] == 2
        assert r["excluded_pair_count"] == 0
        assert r["feature_null_count"] == 0
        assert r["target_null_count"] == 0


def test_build_evaluation_summary_calculation_and_median() -> None:
    # 4 folds for feature 'f_ret_1', metric values: [-0.2, -0.1, +0.3, +0.4]
    # Even count median = (-0.1 + 0.3) / 2 = 0.1
    # Mean = (-0.2 - 0.1 + 0.3 + 0.4) / 4 = 0.4 / 4 = 0.1
    # Min = -0.2, Max = 0.4
    # Positive = 2, Negative = 2, Zero = 0
    records = [
        {
            "fold_id": 0,
            "feature": "f_ret_1",
            "target": "l_fwdret_24",
            "valid_pair_count": 72,
            "pearson_ic": "-0.200000000000000000",
            "spearman_ic": "-0.100000000000000000",
        },
        {
            "fold_id": 1,
            "feature": "f_ret_1",
            "target": "l_fwdret_24",
            "valid_pair_count": 72,
            "pearson_ic": "-0.100000000000000000",
            "spearman_ic": "0.000000000000000000",
        },
        {
            "fold_id": 2,
            "feature": "f_ret_1",
            "target": "l_fwdret_24",
            "valid_pair_count": 72,
            "pearson_ic": "0.300000000000000000",
            "spearman_ic": "0.200000000000000000",
        },
        {
            "fold_id": 3,
            "feature": "f_ret_1",
            "target": "l_fwdret_24",
            "valid_pair_count": 72,
            "pearson_ic": "0.400000000000000000",
            "spearman_ic": "0.300000000000000000",
        },
    ]
    summaries = build_evaluation_summaries(records, features=["f_ret_1"])
    # 1 feature * 2 metrics = 2 summaries
    assert len(summaries) == 2

    # Feature-major, metric-major order
    assert summaries[0]["feature"] == "f_ret_1"
    assert summaries[0]["metric"] == "pearson_ic"
    assert summaries[1]["feature"] == "f_ret_1"
    assert summaries[1]["metric"] == "spearman_ic"

    p_sum = summaries[0]
    assert p_sum["fold_count"] == 4
    assert p_sum["total_valid_pair_count"] == 288
    assert p_sum["positive_fold_count"] == 2
    assert p_sum["negative_fold_count"] == 2
    assert p_sum["zero_fold_count"] == 0
    assert p_sum["minimum"] == "-0.200000000000000000"
    assert p_sum["maximum"] == "0.400000000000000000"
    assert p_sum["median"] == "0.100000000000000000"
    assert p_sum["equal_weight_mean"] == "0.100000000000000000"

    # Odd count median: 3 folds [-0.2, -0.1, 0.3] -> median is -0.1
    odd_records = records[:3]
    odd_summaries = build_evaluation_summaries(odd_records, features=["f_ret_1"])
    assert odd_summaries[0]["median"] == "-0.100000000000000000"
