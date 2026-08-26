"""Anchored walk-forward fold partitioning engine (data slice 004).

Pure partition and boundary engines per design §4 and §5:
- Deterministic anchored walk-forward partitions
- Label-horizon embargo gaps
- Excluded head warmup region
- Remainder-merge into final fold
- Formal leakage invariants: disjoint completeness, exact embargo width,
  label-horizon forward safety, and boundary determinism.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantara.validation_descriptor import UndersizedParentDataset

__all__ = [
    "DEFAULT_EMBARGO",
    "DEFAULT_MIN_TRAIN_SIZE",
    "DEFAULT_TEST_SIZE",
    "Fold",
    "FoldPartition",
    "build_walkforward_folds",
    "compute_test_ranges",
]

DEFAULT_TEST_SIZE = 72
DEFAULT_MIN_TRAIN_SIZE = 336
DEFAULT_EMBARGO = 24


@dataclass(frozen=True)
class Fold:
    """One anchored walk-forward fold boundary specification."""

    fold_id: int
    train_range: tuple[int, int] | None
    embargo_range: tuple[int, int] | None
    test_range: tuple[int, int]

    def to_dict(self) -> dict:
        return {
            "fold_id": self.fold_id,
            "train_range": list(self.train_range) if self.train_range else None,
            "embargo_range": list(self.embargo_range) if self.embargo_range else None,
            "test_range": list(self.test_range),
        }


@dataclass(frozen=True)
class FoldPartition:
    """Complete collection of walk-forward folds and coverage partition."""

    parent_rows: int
    excluded_head_rows: int
    folds: list[Fold]
    coverage: dict

    def to_dict(self) -> dict:
        return {
            "parent_rows": self.parent_rows,
            "excluded_head_rows": self.excluded_head_rows,
            "folds": [f.to_dict() for f in self.folds],
            "coverage": self.coverage,
        }


def compute_test_ranges(
    n_rows: int,
    test_size: int,
    first_test_start: int,
) -> list[tuple[int, int]]:
    """Compute consecutive test ranges starting at first_test_start.

    The final partial block (< test_size) merges into the last fold's
    test segment (design §4).
    """
    test_rows = n_rows - first_test_start
    if test_rows < test_size:
        return []

    ranges: list[tuple[int, int]] = []
    current = first_test_start
    while current + test_size <= n_rows:
        next_start = current + test_size
        if n_rows - next_start < test_size:
            ranges.append((current, n_rows))
            break
        ranges.append((current, next_start))
        current = next_start

    return ranges


def build_walkforward_folds(
    n_rows: int,
    test_size: int = DEFAULT_TEST_SIZE,
    min_train_size: int = DEFAULT_MIN_TRAIN_SIZE,
    embargo: int = DEFAULT_EMBARGO,
) -> FoldPartition:
    """Build deterministic walk-forward folds per design §4.

    Rejects parents with n_rows < min_train_size + embargo + test_size
    as ``UndersizedParentDataset``.
    """
    min_required = min_train_size + embargo + test_size
    if n_rows < min_required:
        raise UndersizedParentDataset(
            f"parent dataset provides {n_rows} rows; the validation folds "
            f"require at least min_train_size + embargo + test_size = "
            f"{min_required} rows ({n_rows} < {min_required})"
        )

    first_test_start = min_train_size + embargo
    test_ranges = compute_test_ranges(n_rows, test_size, first_test_start)

    folds: list[Fold] = []
    for fold_id, (test_start, test_end) in enumerate(test_ranges):
        train_end = test_start - embargo
        if train_end >= min_train_size:
            train_range: tuple[int, int] | None = (0, train_end)
            embargo_range: tuple[int, int] | None = (train_end, test_start)
        else:
            train_range = None
            embargo_range = None

        folds.append(
            Fold(
                fold_id=fold_id,
                train_range=train_range,
                embargo_range=embargo_range,
                test_range=(test_start, test_end),
            )
        )

    total_test_rows = sum(f.test_range[1] - f.test_range[0] for f in folds)
    # Truthful dataset-level aggregates only. Under anchored expanding trains,
    # per-row TRAIN/EMBARGO counts are undefined (rows belong to several folds'
    # trains), so no per-row role partition is published; train/embargo extents
    # live in each fold, and rows outside every test segment are captured by
    # excluded_head_rows (= parent_rows - test_rows).
    coverage = {
        "total_rows": n_rows,
        "fold_count": len(folds),
        "test_rows": total_test_rows,
    }

    return FoldPartition(
        parent_rows=n_rows,
        excluded_head_rows=first_test_start,
        folds=folds,
        coverage=coverage,
    )
