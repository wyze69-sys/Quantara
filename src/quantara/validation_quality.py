"""Validation-folds quality evaluation (data slice 004).

Evaluates walk-forward fold partitions and descriptive statistics against
strict PASS-only invariants (design §11):
- Coverage partition completeness and disjointness (§5.1)
- Leakage invariants: embargo width, train length, label-horizon safety (§5.2, §5.3)
- Structural-null exact equality (actual == expected for every segment and column, §6)
- Sign distribution sum consistency (§6)
- Returns bounds and exact Decimal representations (§6)
- Monotonic open-time bounds across segments
- Deterministic quality_identity
Policy v1: exactly PASS publishes; any failure blocks publication.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from quantara.fold_stats import NULLABLE_COLUMNS, FoldStats
from quantara.folds import FoldPartition
from quantara.hashing import quality_identity

__all__ = [
    "Finding",
    "QUALITY_POLICY_VERSION",
    "ValidationQualityReport",
    "evaluate_validation_quality",
]

QUALITY_POLICY_VERSION = "1"


@dataclass(frozen=True)
class Finding:
    check_id: str
    outcome: str  # "pass" | "fail"
    severity: str  # "hard"
    count: int
    evidence: dict


class ValidationQualityReport:
    """Outcome of validation-folds quality evaluation."""

    def __init__(self, findings: list[Finding]) -> None:
        self.findings = findings
        self.state = "FAIL" if any(f.outcome != "pass" for f in findings) else "PASS"

    def failing_checks(self) -> list[str]:
        return [f.check_id for f in self.findings if f.outcome != "pass"]

    def identity(self) -> str:
        """Deterministic JCS identity; operational timestamps excluded."""
        return quality_identity(
            [
                {
                    "check_id": f.check_id,
                    "count": f.count,
                    "evidence": f.evidence,
                    "outcome": f.outcome,
                    "severity": f.severity,
                }
                for f in self.findings
            ]
        )


def evaluate_validation_quality(
    partition: FoldPartition,
    fold_stats_list: Sequence[FoldStats],
    expected_parent_rows: int,
    min_train_size: int = 336,
    embargo: int = 24,
) -> ValidationQualityReport:
    """Evaluate walk-forward folds and statistics against PASS-only quality gates."""
    findings: list[Finding] = []

    def record(check_id: str, ok: bool, count: int = 0, **evidence) -> None:
        findings.append(
            Finding(
                check_id=check_id,
                outcome="pass" if ok else "fail",
                severity="hard",
                count=count,
                evidence=evidence,
            )
        )

    # 1. Coverage partition (truthful aggregates; design amendment 2026-08-26)
    cov_total = partition.coverage.get("total_rows")
    test_cov = partition.coverage.get("test_rows")
    fold_count_cov = partition.coverage.get("fold_count")
    excl = partition.excluded_head_rows

    total_matches = (
        partition.parent_rows == expected_parent_rows
        and cov_total == expected_parent_rows
    )
    role_sum_matches = excl + (test_cov or 0) == expected_parent_rows
    coverage_keys_valid = (
        fold_count_cov == len(partition.folds)
        and "role_counts" not in partition.coverage
    )

    # Disjointness of test segments
    segments_disjoint = True
    test_indices: set[int] = set()
    for f in partition.folds:
        start, end = f.test_range
        cur_set = set(range(start, end))
        if test_indices & cur_set:
            segments_disjoint = False
            break
        test_indices.update(cur_set)

    cov_ok = (
        total_matches
        and role_sum_matches
        and coverage_keys_valid
        and segments_disjoint
        and (len(test_indices) == test_cov)
    )
    record(
        "validation_coverage_partition",
        cov_ok,
        count=0 if cov_ok else 1,
        expected_parent_rows=expected_parent_rows,
        partition_rows=partition.parent_rows,
        coverage=partition.coverage,
        excluded_head_rows=excl,
        segments_disjoint=segments_disjoint,
    )

    # 2. Fold count
    fold_count = len(partition.folds)
    stats_count = len(fold_stats_list)
    count_ok = fold_count > 0 and fold_count == stats_count
    record(
        "validation_fold_count",
        count_ok,
        count=0 if count_ok else 1,
        fold_count=fold_count,
        stats_count=stats_count,
    )

    # 3. Leakage invariants per fold
    leakage_failures = 0
    for fold in partition.folds:
        if fold.train_range is None or fold.embargo_range is None:
            leakage_failures += 1
            continue
        train_len = fold.train_range[1] - fold.train_range[0]
        if train_len < min_train_size:
            leakage_failures += 1
            continue
        if fold.test_range[0] - fold.train_range[1] != embargo:
            leakage_failures += 1
            continue
        if fold.embargo_range != (fold.train_range[1], fold.test_range[0]):
            leakage_failures += 1
            continue
        # Symbolic safety: max(train index) + embargo < min(test index)
        max_train_idx = fold.train_range[1] - 1
        if max_train_idx + embargo >= fold.test_range[0]:
            leakage_failures += 1
            continue

    leakage_ok = (leakage_failures == 0)
    record(
        "validation_fold_leakage_invariants",
        leakage_ok,
        count=leakage_failures,
        min_train_size=min_train_size,
        embargo=embargo,
    )

    # 4. Structural nulls exact equality
    null_failures = 0
    for stats in fold_stats_list:
        for col in NULLABLE_COLUMNS:
            actual = stats.null_counts.get(col)
            expected = stats.expected_null_counts.get(col)
            if actual != expected:
                null_failures += 1
    nulls_ok = (null_failures == 0)
    record(
        "validation_structural_nulls",
        nulls_ok,
        count=null_failures,
    )

    # 5. Sign distribution sum consistency
    sign_failures = 0
    for stats in fold_stats_list:
        total_signs = sum(stats.sign_distribution.values())
        expected_signs = stats.row_count - stats.null_counts["l_fwddir_24"]
        if total_signs != expected_signs:
            sign_failures += 1
    sign_ok = (sign_failures == 0)
    record(
        "validation_sign_distribution_sum",
        sign_ok,
        count=sign_failures,
    )

    # 6. Returns bounds
    returns_failures = 0
    for stats in fold_stats_list:
        if stats.fwdret_mean is not None:
            try:
                mean_val = Decimal(stats.fwdret_mean)
                min_val = Decimal(stats.fwdret_min)  # type: ignore[arg-type]
                max_val = Decimal(stats.fwdret_max)  # type: ignore[arg-type]
                if not (min_val <= mean_val <= max_val):
                    returns_failures += 1
            except Exception:
                returns_failures += 1
    returns_ok = (returns_failures == 0)
    record(
        "validation_returns_bounds",
        returns_ok,
        count=returns_failures,
    )

    # 7. Monotonic open-time bounds across segments
    time_failures = 0
    for f_idx, stats in enumerate(fold_stats_list):
        if stats.open_time_ms_first > stats.open_time_ms_last:
            time_failures += 1
        if f_idx > 0:
            prev_stats = fold_stats_list[f_idx - 1]
            if stats.open_time_ms_first <= prev_stats.open_time_ms_last:
                time_failures += 1
    time_ok = (time_failures == 0)
    record(
        "validation_time_bounds",
        time_ok,
        count=time_failures,
    )

    return ValidationQualityReport(findings)
