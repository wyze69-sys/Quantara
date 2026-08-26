"""Validation-folds quality evaluator tests (plan Task 5).

Covers design §11 PASS-only policy:
- PASS state on clean walk-forward folds and stats
- Deterministic quality_identity
- Failing fixture per invariant:
  - Coverage partition failure
  - Fold count mismatch
  - Leakage invariant violation
  - Structural-null count mismatch
  - Sign distribution sum inconsistency
  - Returns bounds violation
  - Non-monotonic time bounds
"""

from __future__ import annotations

from decimal import Decimal

from quantara.fold_stats import FoldStats, compute_fold_stats
from quantara.folds import Fold, FoldPartition, build_walkforward_folds
from quantara.validation_quality import (
    QUALITY_POLICY_VERSION,
    evaluate_validation_quality,
)


def _make_clean_parent_rows(n: int = 744) -> list[tuple]:
    rows = []
    base_time = 1704067200000
    for i in range(n):
        t = base_time + i * 3600_000
        # Head feature nulls
        f_ret = None if i < 1 else Decimal("0.0005")
        f_roc = None if i < 60 else Decimal("0.012")
        f_rvol = None if i < 20 else Decimal("0.007")
        f_volratio = None if i < 19 else Decimal("1.05")

        # Tail label nulls
        if i >= n - 24:
            l_fwdret = None
            l_fwddir = None
        else:
            l_fwdret = Decimal("0.0015")
            l_fwddir = 1
        rows.append((t, f_ret, f_roc, f_rvol, f_volratio, l_fwdret, l_fwddir))
    return rows


def _build_clean_partition_and_stats(n: int = 744) -> tuple[FoldPartition, list[FoldStats]]:
    rows = _make_clean_parent_rows(n)
    partition = build_walkforward_folds(n)
    stats_list = [
        compute_fold_stats(rows, fold.test_range, total_parent_rows=n)
        for fold in partition.folds
    ]
    return partition, stats_list


def test_clean_validation_quality_passes() -> None:
    """Standard N=744 partition passes all 7 quality gates."""
    partition, stats_list = _build_clean_partition_and_stats(744)
    report = evaluate_validation_quality(partition, stats_list, expected_parent_rows=744)

    assert report.state == "PASS"
    assert report.failing_checks() == []
    assert len(report.findings) == 7
    for finding in report.findings:
        assert finding.outcome == "pass"

    ident = report.identity()
    assert isinstance(ident, str) and len(ident) > 0
    assert ident == report.identity()  # deterministic


def test_failing_fixture_coverage_partition() -> None:
    """Tampering with coverage counts causes validation_coverage_partition to fail."""
    partition, stats_list = _build_clean_partition_and_stats(744)
    bad_coverage = {
        "total_rows": 744,
        "role_counts": {
            "TRAIN": 10,  # Must be 0
            "EMBARGO": 0,
            "TEST": 374,
            "EXCLUDED": 360,
        },
    }
    tampered_partition = FoldPartition(
        parent_rows=744,
        excluded_head_rows=360,
        folds=partition.folds,
        coverage=bad_coverage,
    )
    report = evaluate_validation_quality(
        tampered_partition, stats_list, expected_parent_rows=744
    )
    assert report.state == "FAIL"
    assert "validation_coverage_partition" in report.failing_checks()


def test_failing_fixture_fold_count() -> None:
    """Mismatch between partition folds and stats list causes validation_fold_count to fail."""
    partition, stats_list = _build_clean_partition_and_stats(744)
    report = evaluate_validation_quality(
        partition, stats_list[:-1], expected_parent_rows=744
    )
    assert report.state == "FAIL"
    assert "validation_fold_count" in report.failing_checks()


def test_failing_fixture_leakage_invariants() -> None:
    """A fold with broken embargo causes validation_fold_leakage_invariants to fail."""
    partition, stats_list = _build_clean_partition_and_stats(744)
    tampered_folds = list(partition.folds)
    # Tamper fold 0: embargo width 10 instead of 24
    tampered_folds[0] = Fold(
        fold_id=0,
        train_range=(0, 350),  # embargo 10
        embargo_range=(350, 360),
        test_range=(360, 432),
    )
    tampered_partition = FoldPartition(
        parent_rows=744,
        excluded_head_rows=360,
        folds=tampered_folds,
        coverage=partition.coverage,
    )
    report = evaluate_validation_quality(
        tampered_partition, stats_list, expected_parent_rows=744
    )
    assert report.state == "FAIL"
    assert "validation_fold_leakage_invariants" in report.failing_checks()


def test_failing_fixture_structural_nulls() -> None:
    """An unexpected null in a feature causes validation_structural_nulls to fail."""
    partition, stats_list = _build_clean_partition_and_stats(744)
    tampered_stats = list(stats_list)
    # Inject 1 unexpected null into f_ret_1 in fold 0
    bad_nulls = dict(tampered_stats[0].null_counts, f_ret_1=1)
    tampered_stats[0] = FoldStats(
        row_count=tampered_stats[0].row_count,
        open_time_ms_first=tampered_stats[0].open_time_ms_first,
        open_time_ms_last=tampered_stats[0].open_time_ms_last,
        null_counts=bad_nulls,
        expected_null_counts=tampered_stats[0].expected_null_counts,
        sign_distribution=tampered_stats[0].sign_distribution,
        fwdret_mean=tampered_stats[0].fwdret_mean,
        fwdret_min=tampered_stats[0].fwdret_min,
        fwdret_max=tampered_stats[0].fwdret_max,
    )
    report = evaluate_validation_quality(
        partition, tampered_stats, expected_parent_rows=744
    )
    assert report.state == "FAIL"
    assert "validation_structural_nulls" in report.failing_checks()


def test_failing_fixture_sign_distribution_sum() -> None:
    """Sign counts not summing to non-null labels causes
    validation_sign_distribution_sum to fail.
    """
    partition, stats_list = _build_clean_partition_and_stats(744)
    tampered_stats = list(stats_list)
    bad_signs = {"-1": 10, "0": 0, "1": 10}  # sum = 20 != 72
    tampered_stats[0] = FoldStats(
        row_count=tampered_stats[0].row_count,
        open_time_ms_first=tampered_stats[0].open_time_ms_first,
        open_time_ms_last=tampered_stats[0].open_time_ms_last,
        null_counts=tampered_stats[0].null_counts,
        expected_null_counts=tampered_stats[0].expected_null_counts,
        sign_distribution=bad_signs,
        fwdret_mean=tampered_stats[0].fwdret_mean,
        fwdret_min=tampered_stats[0].fwdret_min,
        fwdret_max=tampered_stats[0].fwdret_max,
    )
    report = evaluate_validation_quality(
        partition, tampered_stats, expected_parent_rows=744
    )
    assert report.state == "FAIL"
    assert "validation_sign_distribution_sum" in report.failing_checks()


def test_failing_fixture_returns_bounds() -> None:
    """fwdret_min > fwdret_max causes validation_returns_bounds to fail."""
    partition, stats_list = _build_clean_partition_and_stats(744)
    tampered_stats = list(stats_list)
    tampered_stats[0] = FoldStats(
        row_count=tampered_stats[0].row_count,
        open_time_ms_first=tampered_stats[0].open_time_ms_first,
        open_time_ms_last=tampered_stats[0].open_time_ms_last,
        null_counts=tampered_stats[0].null_counts,
        expected_null_counts=tampered_stats[0].expected_null_counts,
        sign_distribution=tampered_stats[0].sign_distribution,
        fwdret_mean="0.001000000000000000",
        fwdret_min="0.050000000000000000",  # min > max
        fwdret_max="0.010000000000000000",
    )
    report = evaluate_validation_quality(
        partition, tampered_stats, expected_parent_rows=744
    )
    assert report.state == "FAIL"
    assert "validation_returns_bounds" in report.failing_checks()


def test_failing_fixture_time_bounds() -> None:
    """Non-monotonic timestamps cause validation_time_bounds to fail."""
    partition, stats_list = _build_clean_partition_and_stats(744)
    tampered_stats = list(stats_list)
    # Invert first and last in fold 0
    tampered_stats[0] = FoldStats(
        row_count=tampered_stats[0].row_count,
        open_time_ms_first=tampered_stats[0].open_time_ms_last,
        open_time_ms_last=tampered_stats[0].open_time_ms_first,
        null_counts=tampered_stats[0].null_counts,
        expected_null_counts=tampered_stats[0].expected_null_counts,
        sign_distribution=tampered_stats[0].sign_distribution,
        fwdret_mean=tampered_stats[0].fwdret_mean,
        fwdret_min=tampered_stats[0].fwdret_min,
        fwdret_max=tampered_stats[0].fwdret_max,
    )
    report = evaluate_validation_quality(
        partition, tampered_stats, expected_parent_rows=744
    )
    assert report.state == "FAIL"
    assert "validation_time_bounds" in report.failing_checks()


def test_quality_policy_version_label() -> None:
    assert QUALITY_POLICY_VERSION == "1"
