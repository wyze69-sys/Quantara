from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, ROUND_HALF_EVEN, Decimal, localcontext
from fractions import Fraction
from pathlib import Path

import pytest
import yaml

from quantara.bootstrap_b4 import (
    BootstrapB4InferenceError,
    SplitMix64,
    aggregate_from_starts,
    bootstrap_b4,
    derive_stream_seed,
    materialize_resampled_indices,
    nearest_rank_interval,
    nominal_hours,
    pooled_observed_mean,
    pooled_resample_from_starts,
    render_fraction_18,
    sample_block_starts,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_PATH = REPO_ROOT / "tests/fixtures/bootstrap_b4_golden.json"
V11_SPEC_PATH = (
    REPO_ROOT / "docs/superpowers/specs/2026-09-01-quantara-protocol-v1_1.md"
)
V11_YAML_PATH = REPO_ROOT / "configs/protocols/quantara-protocol-v1_1.yaml"


def _synthetic_grid(year: int) -> list[int | None]:
    """Generate documented synthetic scaled loss differences without real data."""
    return [
        None
        if index % 29 in {0, 1}
        else (((index * 17 + year) % 41) - 18) * 10**15
        for index in range(nominal_hours(year))
    ]


def _golden_record() -> dict[str, object]:
    comparison_id = "synthetic-candidate-vs-comparator"
    result = bootstrap_b4(
        {2022: _synthetic_grid(2022), 2024: _synthetic_grid(2024)},
        comparison_id=comparison_id,
        resamples=200,
    )
    return {
        "schema_version": 1,
        "comparison_id": comparison_id,
        "resamples": 200,
        "synthetic_generator": (
            "null iff index mod 29 is 0 or 1; otherwise "
            "(((index * 17 + year) mod 41) - 18) * 10^15 scaled units"
        ),
        "derived_seeds": {
            str(year): result.derived_seeds[year] for year in sorted(result.derived_seeds)
        },
        "resampled_index_multiset_sha256": {
            str(year): result.index_multiset_sha256[year]
            for year in sorted(result.index_multiset_sha256)
        },
        "observed_mean": render_fraction_18(result.observed_mean),
        "ci_lower": render_fraction_18(result.ci_lower),
        "ci_upper": render_fraction_18(result.ci_upper),
        "p_value": f"{result.p_value.numerator}/{result.p_value.denominator}",
    }


def test_splitmix64_golden_sequence_and_reproducibility() -> None:
    expected = (
        16294208416658607535,
        7960286522194355700,
        487617019471545679,
        17909611376780542444,
        1961750202426094747,
    )
    first = SplitMix64(0)
    second = SplitMix64(0)
    assert tuple(first.next_u64() for _ in expected) == expected
    assert tuple(second.next_u64() for _ in expected) == expected


def test_stream_derivation_is_frozen_and_comparison_specific() -> None:
    assert derive_stream_seed("candidate-vs-b2", 2022) == 8789920857805351394
    assert derive_stream_seed("candidate-vs-b2", 2022) == derive_stream_seed(
        "candidate-vs-b2", 2022
    )
    assert derive_stream_seed("candidate-vs-b2", 2022) != derive_stream_seed(
        "candidate-vs-b2", 2023
    )
    assert derive_stream_seed("candidate-vs-b2", 2022) != derive_stream_seed(
        "other-vs-b2", 2022
    )
    same_first = SplitMix64(derive_stream_seed("candidate-vs-b2", 2022))
    same_second = SplitMix64(derive_stream_seed("candidate-vs-b2", 2022))
    different_year = SplitMix64(derive_stream_seed("candidate-vs-b2", 2023))
    different_comparison = SplitMix64(derive_stream_seed("other-vs-b2", 2022))
    same_sequence = tuple(same_first.next_u64() for _ in range(4))
    assert tuple(same_second.next_u64() for _ in range(4)) == same_sequence
    assert tuple(different_year.next_u64() for _ in range(4)) != same_sequence
    assert tuple(different_comparison.next_u64() for _ in range(4)) != same_sequence


def test_below_uses_the_frozen_rejection_limit() -> None:
    bound = 10
    limit = 2**64 - (2**64 % bound)
    assert limit == 18446744073709551610

    class ScriptedSplitMix64(SplitMix64):
        def __init__(self, values: Iterator[int]) -> None:
            self._values = values

        def next_u64(self) -> int:
            return next(self._values)

    rng = ScriptedSplitMix64(iter((2**64 - 1, 7)))
    assert rng.below(bound) == 7
    ordinary = SplitMix64(123)
    assert all(0 <= ordinary.below(bound) < bound for _ in range(1000))


@pytest.mark.parametrize(
    ("year", "hours", "eligible_starts"),
    (
        (2020, 8784, 8617),
        (2021, 8760, 8593),
        (2022, 8760, 8593),
        (2023, 8760, 8593),
        (2024, 8784, 8617),
        (2025, 8760, 8593),
    ),
)
def test_calendar_geometry_is_derived(
    year: int, hours: int, eligible_starts: int
) -> None:
    derived_hours = (
        datetime(year + 1, 1, 1, tzinfo=UTC)
        - datetime(year, 1, 1, tzinfo=UTC)
    ) // timedelta(hours=1)
    assert derived_hours == hours
    assert nominal_hours(year) == hours
    assert (hours + 168 - 1) // 168 == 53
    assert hours - 168 + 1 == eligible_starts


@pytest.mark.parametrize("year", (2022, 2024))
def test_sampled_blocks_are_non_circular_and_truncated_to_nominal_year(year: int) -> None:
    hours = nominal_hours(year)
    starts = sample_block_starts(SplitMix64(99), hours, block_hours=168)
    indices = materialize_resampled_indices(starts, hours, block_hours=168)
    assert len(starts) == 53
    assert all(0 <= start <= hours - 168 for start in starts)
    assert 53 * 168 == 8904
    assert len(indices) == hours
    assert min(indices) >= 0
    assert max(indices) < hours


def test_truncation_and_incremental_consumption_are_identical() -> None:
    hours = nominal_hours(2022)
    values = [None if index % 13 == 0 else index - 4000 for index in range(hours)]
    starts = sample_block_starts(SplitMix64(987654321), hours, block_hours=168)

    untruncated = [
        index
        for start in starts
        for index in range(start, start + 168)
    ]
    assert len(untruncated) == 8904
    concatenated = untruncated[:hours]
    incremental: list[int] = []
    remaining = hours
    for start in starts:
        consumed = min(168, remaining)
        incremental.extend(range(start, start + consumed))
        remaining -= consumed
        if remaining == 0:
            break

    assert concatenated == incremental
    assert materialize_resampled_indices(starts, hours, 168) == tuple(incremental)
    numerator, denominator = aggregate_from_starts(values, starts, 168)
    assert numerator == sum(values[index] for index in incremental if values[index] is not None)
    assert denominator == sum(values[index] is not None for index in incremental)


def test_observed_statistic_is_an_exact_pooled_fraction_and_nulls_are_not_imputed() -> None:
    assert pooled_observed_mean({2001: [1, None, 3, 0]}) == Fraction(4, 3)

    complete = pooled_observed_mean({2001: [1, 0, 2]})
    with_null = pooled_observed_mean({2001: [1, None, 2]})
    assert complete == Fraction(3, 3)
    assert with_null == Fraction(3, 2)


def test_pooling_uses_valid_observation_count_not_year_count_or_nominal_hours() -> None:
    grids = {2001: [2, 2], 2002: [0] * 8}
    pooled = pooled_observed_mean(grids)
    mean_of_year_means = (Fraction(2, 1) + Fraction(0, 1)) / 2
    assert pooled == Fraction(2, 5)
    assert pooled != mean_of_year_means


def test_nearest_rank_interval_uses_one_indexed_ranks_without_interpolation() -> None:
    replicates = tuple(Fraction(value, 1) for value in range(1, 201))
    lower, upper = nearest_rank_interval(replicates)
    assert (200 + 40 - 1) // 40 == 5
    assert (39 * 200 + 40 - 1) // 40 == 195
    assert lower == Fraction(5, 1)
    assert upper == Fraction(195, 1)


def test_null_centred_identity_and_p_value_formulations_agree_exactly() -> None:
    grids = {2022: _synthetic_grid(2022)}
    result = bootstrap_b4(grids, comparison_id="identity-check", resamples=200)
    null_replicates = tuple(
        replicate - result.observed_mean for replicate in result.replicate_means
    )
    assert all(
        centred == raw - result.observed_mean
        for centred, raw in zip(null_replicates, result.replicate_means, strict=True)
    )
    null_count = sum(value >= result.observed_mean for value in null_replicates)
    doubled_count = sum(
        value >= 2 * result.observed_mean for value in result.replicate_means
    )
    assert null_count == doubled_count
    assert result.p_value == Fraction(1 + null_count, 201)
    assert result.p_value >= Fraction(1, 201)


def test_p_value_minimum_and_symmetric_noise_behaviour() -> None:
    positive = bootstrap_b4(
        {2022: [1] * nominal_hours(2022)},
        comparison_id="positive-constant",
        resamples=200,
    )
    assert positive.p_value == Fraction(1, 201)

    symmetric = bootstrap_b4(
        {2022: [1 if index % 2 == 0 else -1 for index in range(nominal_hours(2022))]},
        comparison_id="symmetric-noise",
        resamples=200,
    )
    assert symmetric.observed_mean == 0
    assert symmetric.p_value > Fraction(1, 201)


def test_decimal_inputs_are_exact_and_non_quantum_values_are_rejected() -> None:
    grid = [Decimal("0.000000000000000001")] * nominal_hours(2022)
    result = bootstrap_b4({2022: grid}, comparison_id="decimal-input", resamples=2)
    assert result.observed_mean == Fraction(1, 10**18)
    with pytest.raises(ValueError, match="1e-18"):
        bootstrap_b4(
            {2022: [Decimal("0.0000000000000000001")] * nominal_hours(2022)},
            comparison_id="invalid-decimal-input",
            resamples=2,
        )
    assert render_fraction_18(Fraction(-1, 10**30)) == "0.000000000000000000"


def test_observed_year_with_167_valid_values_fails_closed() -> None:
    values: list[int | None] = [1] * 167
    values.extend([None] * (nominal_hours(2022) - len(values)))
    with pytest.raises(BootstrapB4InferenceError) as captured:
        bootstrap_b4({2022: values}, comparison_id="too-sparse", resamples=2)
    assert captured.value.year == 2022
    assert captured.value.replicate_index is None
    assert captured.value.reason == "insufficient_observed_paired_valid"


def test_replicate_with_empty_required_year_fails_closed_even_when_pool_is_positive() -> None:
    sparse: list[int | None] = [1] * 168
    sparse.extend([None] * (nominal_hours(2023) - len(sparse)))
    dense = [1] * nominal_hours(2022)
    starts = {
        2022: [0] * 53,
        2023: [168] * 53,
    }
    with pytest.raises(BootstrapB4InferenceError) as captured:
        pooled_resample_from_starts(
            {2022: dense, 2023: sparse},
            starts,
            block_hours=168,
            replicate_index=7,
        )
    assert captured.value.year == 2023
    assert captured.value.replicate_index == 7
    assert captured.value.reason == "empty_resampled_required_year"


def test_monte_carlo_justification_literals_and_protocol_artifacts_match() -> None:
    with localcontext() as context:
        context.prec = 50
        p = Decimal("0.05") / Decimal(3)
        z = Decimal("1.96")
        quantum = Decimal("0.000000000000000001")
        half_2000 = (z * (p * (1 - p) / Decimal(2000)).sqrt()).quantize(
            quantum, rounding=ROUND_HALF_EVEN
        )
        half_20000 = (z * (p * (1 - p) / Decimal(20000)).sqrt()).quantize(
            quantum, rounding=ROUND_HALF_EVEN
        )
        minimum_exact = z * z * p * (1 - p) / (Decimal("0.002") ** 2)
        minimum_integer = minimum_exact.to_integral_value(rounding=ROUND_CEILING)

    assert format(half_2000, "f") == "0.005610684252190438"
    assert format(half_20000, "f") == "0.001774254146896035"
    assert minimum_exact == Decimal("15739.888888888888888888888888888888888888888888889")
    assert minimum_integer == Decimal(15740)

    document = yaml.safe_load(V11_YAML_PATH.read_text(encoding="utf-8"))
    bootstrap = document["validation"]["bootstrap"]
    monte_carlo = bootstrap["monte_carlo_justification"]
    assert monte_carlo["half_width_b_2000"] == format(half_2000, "f")
    assert monte_carlo["half_width_b_20000"] == format(half_20000, "f")
    assert monte_carlo["minimum_resamples_exact"].startswith("15739.888")
    assert monte_carlo["minimum_resamples_ceiling"] == 15740

    spec_text = V11_SPEC_PATH.read_text(encoding="utf-8")
    for literal in (
        "0.005610684252190438",
        "0.001774254146896035",
        "15740",
    ):
        assert literal in spec_text


def test_v11_yaml_has_no_duplicate_mapping_keys_at_any_depth() -> None:
    root = yaml.compose(V11_YAML_PATH.read_text(encoding="utf-8"), Loader=yaml.SafeLoader)

    def assert_unique(node: yaml.Node, path: str) -> None:
        if isinstance(node, yaml.MappingNode):
            keys: set[str] = set()
            for key_node, value_node in node.value:
                key = key_node.value
                assert key not in keys, f"duplicate YAML key at {path}.{key}"
                keys.add(key)
                assert_unique(value_node, f"{path}.{key}")
        elif isinstance(node, yaml.SequenceNode):
            for index, child in enumerate(node.value):
                assert_unique(child, f"{path}[{index}]")

    assert root is not None
    assert_unique(root, "$")


def test_golden_fixture_pins_reduced_end_to_end_run() -> None:
    expected = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert _golden_record() == expected


def test_determinism_and_comparison_id_stream_separation() -> None:
    grids = {2022: _synthetic_grid(2022), 2024: _synthetic_grid(2024)}
    first = bootstrap_b4(grids, comparison_id="same", resamples=20)
    second = bootstrap_b4(grids, comparison_id="same", resamples=20)
    changed = bootstrap_b4(grids, comparison_id="changed", resamples=20)
    assert first == second
    assert first.replicate_means != changed.replicate_means


def test_full_20000_resample_path_finishes_inside_budget() -> None:
    started = time.perf_counter()
    result = bootstrap_b4(
        {2022: [1] * nominal_hours(2022)},
        comparison_id="full-budget-check",
        resamples=20000,
    )
    elapsed = time.perf_counter() - started
    assert len(result.replicate_means) == 20000
    assert result.ci_lower == Fraction(1, 10**18)
    assert result.ci_upper == Fraction(1, 10**18)
    assert elapsed < 60.0, f"full B=20000 path took {elapsed:.3f}s"


def test_derived_seed_matches_independent_sha256_construction() -> None:
    payload = "quantara-protocol-v1_1|bootstrap-b4|candidate-vs-b2|2022"
    expected = int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big")
    assert expected == 8789920857805351394
    assert derive_stream_seed("candidate-vs-b2", 2022) == expected
