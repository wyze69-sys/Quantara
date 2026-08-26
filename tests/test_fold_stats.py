"""Per-fold test-segment statistics tests (plan Task 4).

Covers design §6 statistics and design §5.5 causality:
- Exact row count and epoch-ms time bounds
- Per-column null counts vs structural expectations
- Sign distribution summing exactly to non-null label count
- Exact Decimal mean, min, max rendered via render_decimal_18
- Invariant §5.5: strict causality (mutating rows outside test segment
  leaves fold statistics bit-identical).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from quantara.fold_stats import (
    NULLABLE_COLUMNS,
    compute_fold_stats,
)


def _make_row(
    idx: int,
    open_time_base: int = 1704067200000,
    ret: str | None = "0.001",
    dir_val: int | None = 1,
    is_feature_null: bool = False,
) -> tuple:
    time_ms = open_time_base + idx * 3600_000
    f_ret = None if is_feature_null else Decimal("0.0005")
    f_roc = None if is_feature_null else Decimal("0.015")
    f_rvol = None if is_feature_null else Decimal("0.008")
    f_volratio = None if is_feature_null else Decimal("1.2")
    l_fwdret = Decimal(ret) if ret is not None else None
    l_fwddir = dir_val
    return (time_ms, f_ret, f_roc, f_rvol, f_volratio, l_fwdret, l_fwddir)


def test_fold_stats_basic_computation() -> None:
    """Computes correct counts, times, nulls, sign distribution, and stats."""
    n = 744
    rows = [_make_row(i) for i in range(n)]

    # Fold 0: [360, 432)
    stats = compute_fold_stats(rows, (360, 432), total_parent_rows=n)

    assert stats.row_count == 72
    assert stats.open_time_ms_first == 1704067200000 + 360 * 3600_000
    assert stats.open_time_ms_last == 1704067200000 + 431 * 3600_000

    # In fold 0, no nulls are expected for any column
    for col in NULLABLE_COLUMNS:
        assert stats.null_counts[col] == 0
        assert stats.expected_null_counts[col] == 0

    # Sign distribution
    assert stats.sign_distribution == {"-1": 0, "0": 0, "1": 72}
    total_labels = sum(stats.sign_distribution.values())
    assert total_labels == stats.row_count - stats.null_counts["l_fwddir_24"]

    # Returns stats
    assert stats.fwdret_mean == "0.001000000000000000"
    assert stats.fwdret_min == "0.001000000000000000"
    assert stats.fwdret_max == "0.001000000000000000"


def test_fold_stats_final_fold_with_structural_nulls() -> None:
    """Final fold [648, 744) has 24 tail label nulls."""
    n = 744
    rows = []
    for i in range(n):
        if i >= n - 24:
            rows.append(_make_row(i, ret=None, dir_val=None))
        else:
            rows.append(_make_row(i, ret="-0.002", dir_val=-1))

    # Fold 4: [648, 744) (96 rows)
    stats = compute_fold_stats(rows, (648, 744), total_parent_rows=n)

    assert stats.row_count == 96
    # Features have 0 nulls
    for col in ("f_ret_1", "f_roc_60", "f_rvol_20", "f_volratio_20"):
        assert stats.null_counts[col] == 0
        assert stats.expected_null_counts[col] == 0

    # Labels have exactly 24 nulls
    assert stats.null_counts["l_fwdret_24"] == 24
    assert stats.expected_null_counts["l_fwdret_24"] == 24
    assert stats.null_counts["l_fwddir_24"] == 24
    assert stats.expected_null_counts["l_fwddir_24"] == 24

    # Non-null labels: 96 - 24 = 72
    assert stats.sign_distribution == {"-1": 72, "0": 0, "1": 0}
    assert (
        sum(stats.sign_distribution.values())
        == stats.row_count - stats.null_counts["l_fwddir_24"]
    )

    # Returns mean/min/max over 72 valid rows
    assert stats.fwdret_mean == "-0.002000000000000000"
    assert stats.fwdret_min == "-0.002000000000000000"
    assert stats.fwdret_max == "-0.002000000000000000"


def test_fold_stats_varying_signs_and_values() -> None:
    """Sign distribution counts -1, 0, +1 correctly with exact decimal mean."""
    rows = []
    # 3 rows with different directions and returns
    rows.append(_make_row(0, ret="-0.01", dir_val=-1))
    rows.append(_make_row(1, ret="0.00", dir_val=0))
    rows.append(_make_row(2, ret="0.02", dir_val=1))

    stats = compute_fold_stats(rows, (0, 3), total_parent_rows=3)
    assert stats.sign_distribution == {"-1": 1, "0": 1, "1": 1}
    assert stats.fwdret_min == "-0.010000000000000000"
    assert stats.fwdret_max == "0.020000000000000000"
    # Mean (-0.01 + 0.00 + 0.02) / 3 = 0.01 / 3 = 0.003333333333333333...
    assert stats.fwdret_mean == "0.003333333333333333"


def test_property_5_5_statistic_causality() -> None:
    """Mutating rows outside a fold's test segment leaves stats bit-identical."""
    n = 744
    target_range = (432, 504)  # Fold 1

    # Baseline rows
    rows_clean = [_make_row(i, ret="0.001", dir_val=1) for i in range(n)]
    stats_baseline = compute_fold_stats(rows_clean, target_range, total_parent_rows=n)

    # Mutate rows in [0, 360) (excluded head)
    rows_mutated_head = list(rows_clean)
    for i in range(0, 100):
        rows_mutated_head[i] = _make_row(i, ret="999.0", dir_val=-1)
    stats_after_head_mutation = compute_fold_stats(
        rows_mutated_head, target_range, total_parent_rows=n
    )
    assert stats_after_head_mutation.to_dict() == stats_baseline.to_dict()

    # Mutate rows in [360, 432) (fold 0 test segment)
    rows_mutated_prev = list(rows_clean)
    for i in range(360, 432):
        rows_mutated_prev[i] = _make_row(i, ret="-888.0", dir_val=0)
    stats_after_prev_mutation = compute_fold_stats(
        rows_mutated_prev, target_range, total_parent_rows=n
    )
    assert stats_after_prev_mutation.to_dict() == stats_baseline.to_dict()

    # Mutate rows in [504, 744) (future test segments)
    rows_mutated_future = list(rows_clean)
    for i in range(504, 744):
        rows_mutated_future[i] = _make_row(i, ret="777.0", dir_val=1)
    stats_after_future_mutation = compute_fold_stats(
        rows_mutated_future, target_range, total_parent_rows=n
    )
    assert stats_after_future_mutation.to_dict() == stats_baseline.to_dict()


def test_empty_test_segment_raises() -> None:
    rows = [_make_row(0)]
    with pytest.raises(ValueError, match="empty"):
        compute_fold_stats(rows, (1, 1))
