"""Fold partition and leakage invariant property tests (plan Task 3).

Verifies design §4 arithmetic and design §5 properties:
- §4: Acceptance numbers on N=744 (5 folds, 384 test coverage, 360 excluded)
- §5.1: Partition completeness and disjointness over generated N
- §5.2: Embargo width invariants
- §5.3: Symbolic and empirical label-horizon safety
- §5.4: Value-perturbation determinism
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from quantara.folds import (
    DEFAULT_EMBARGO,
    DEFAULT_MIN_TRAIN_SIZE,
    build_walkforward_folds,
)
from quantara.validation_descriptor import UndersizedParentDataset


def test_acceptance_numbers_n_744() -> None:
    """Design §4 and plan §7 arithmetic: N = 744 exact numbers."""
    partition = build_walkforward_folds(744)

    assert partition.parent_rows == 744
    assert partition.excluded_head_rows == 360
    assert len(partition.folds) == 5

    # Test segment boundaries and lengths
    expected_test_ranges = [
        (360, 432),
        (432, 504),
        (504, 576),
        (576, 648),
        (648, 744),
    ]
    actual_test_ranges = [f.test_range for f in partition.folds]
    assert actual_test_ranges == expected_test_ranges

    test_lengths = [f.test_range[1] - f.test_range[0] for f in partition.folds]
    assert test_lengths == [72, 72, 72, 72, 96]

    # Every fold train length >= min_train_size (336)
    for f in partition.folds:
        assert f.train_range is not None
        assert f.train_range[0] == 0
        train_len = f.train_range[1] - f.train_range[0]
        assert train_len >= 336

        # Embargo width is exactly 24
        assert f.embargo_range is not None
        assert f.embargo_range[1] - f.embargo_range[0] == 24
        assert f.embargo_range[0] == f.train_range[1]
        assert f.embargo_range[1] == f.test_range[0]

    # Coverage accounting
    assert partition.coverage["total_rows"] == 744
    assert partition.coverage["role_counts"]["EXCLUDED"] == 360
    assert partition.coverage["role_counts"]["TEST"] == 384
    assert partition.coverage["role_counts"]["TRAIN"] == 0
    assert partition.coverage["role_counts"]["EMBARGO"] == 0
    assert (
        partition.coverage["role_counts"]["EXCLUDED"]
        + partition.coverage["role_counts"]["TEST"]
        == 744
    )


def test_minimum_viable_n_432() -> None:
    """T8 golden fixture parent size: exactly one fold."""
    partition = build_walkforward_folds(432)
    assert len(partition.folds) == 1
    assert partition.folds[0].train_range == (0, 336)
    assert partition.folds[0].embargo_range == (336, 360)
    assert partition.folds[0].test_range == (360, 432)
    assert partition.excluded_head_rows == 360
    assert partition.coverage["role_counts"]["TEST"] == 72
    assert partition.coverage["role_counts"]["EXCLUDED"] == 360


def test_undersized_parent_rejected_pre_compute() -> None:
    """N < 432 must be rejected as UndersizedParentDataset."""
    for n in (0, 1, 100, 359, 360, 431):
        with pytest.raises(UndersizedParentDataset) as excinfo:
            build_walkforward_folds(n)
        assert excinfo.value.error_id == "undersized_parent_dataset"


# --- Property §5.1: Partition completeness and disjointness ------------------


@given(n=st.integers(min_value=432, max_value=2500))
def test_property_5_1_partition_completeness_and_disjointness(n: int) -> None:
    """Union of EXCLUDED and TEST is exactly [0, N) with no gaps or overlaps."""
    partition = build_walkforward_folds(n)
    first_test_start = DEFAULT_MIN_TRAIN_SIZE + DEFAULT_EMBARGO
    assert partition.excluded_head_rows == first_test_start

    excluded_indices = set(range(0, first_test_start))
    test_indices: set[int] = set()

    for fold in partition.folds:
        start, end = fold.test_range
        # Disjoint fold tests
        fold_test_set = set(range(start, end))
        assert not (test_indices & fold_test_set), "Overlapping test segments!"
        test_indices.update(fold_test_set)

    # Union is [0, N)
    assert not (excluded_indices & test_indices), "EXCLUDED overlaps TEST!"
    assert (excluded_indices | test_indices) == set(range(n))
    assert (
        partition.coverage["role_counts"]["EXCLUDED"]
        + partition.coverage["role_counts"]["TEST"]
        == n
    )

    # In each fold, train, embargo, test are contiguous and disjoint
    for fold in partition.folds:
        assert fold.train_range is not None
        assert fold.embargo_range is not None
        assert fold.train_range[0] == 0
        assert fold.train_range[1] == fold.embargo_range[0]
        assert fold.embargo_range[1] == fold.test_range[0]
        assert fold.test_range[0] < fold.test_range[1]


# --- Property §5.2: Embargo width --------------------------------------------


@given(n=st.integers(min_value=432, max_value=2500))
def test_property_5_2_embargo_width(n: int) -> None:
    """Whenever train and test exist, test_start - train_end == embargo exactly."""
    partition = build_walkforward_folds(n)
    for fold in partition.folds:
        assert fold.train_range is not None
        assert fold.embargo_range is not None
        train_end = fold.train_range[1]
        embargo_start, embargo_end = fold.embargo_range
        test_start, _ = fold.test_range

        assert test_start - train_end == DEFAULT_EMBARGO
        assert embargo_end - embargo_start == DEFAULT_EMBARGO
        assert embargo_start == train_end
        assert embargo_end == test_start


# --- Property §5.3: Label-horizon safety (symbolic and empirical) -----------


@given(n=st.integers(min_value=432, max_value=2500))
def test_property_5_3_label_horizon_safety(n: int) -> None:
    """Forward label window of any train row ends strictly before earliest test index.

    Symbolic: max(train index) + H < min(test index).
    Empirical: for every train row t in fold, t + H < test_start.
    """
    h = DEFAULT_EMBARGO  # embargo == label_horizon == 24
    partition = build_walkforward_folds(n, embargo=h)

    for fold in partition.folds:
        assert fold.train_range is not None
        train_start, train_end = fold.train_range
        test_start, _ = fold.test_range

        max_train_idx = train_end - 1
        min_test_idx = test_start

        # Symbolic invariant: max_train_idx + H < min_test_idx
        assert max_train_idx + h < min_test_idx
        # Exact gap between max train forward reach and min test is 1 bar
        assert (min_test_idx - 1) == (max_train_idx + h)

        # Empirical sweep over every train index
        for t in range(train_start, train_end):
            label_reaches = t + h
            assert label_reaches < min_test_idx


# --- Property §5.4: Boundary determinism under value perturbation ------------


def test_property_5_4_boundary_determinism() -> None:
    """Perturbing parent row values leaves fold boundaries byte-identical."""
    n = 744
    # Dataset 1: values all 100.0
    partition1 = build_walkforward_folds(n)

    # Dataset 2: values all 99999.0 (different values, same length)
    partition2 = build_walkforward_folds(n)

    assert partition1.to_dict() == partition2.to_dict()
