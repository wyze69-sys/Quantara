from __future__ import annotations

import inspect
import json
import math
from dataclasses import fields, replace
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest
import yaml

from quantara.aggregation import IncompleteGroup, aggregate_timeframe
from quantara.bootstrap_b4 import (
    BootstrapB4InferenceError,
    bootstrap_b4,
    derive_stream_seed,
    nominal_hours,
)
from quantara.canonical import CanonicalRow
from quantara.estimator_c3 import calibration_slope_passes
from quantara.replication_c4 import (
    BUFFER_BAR_COUNT,
    BUFFER_END_INCLUSIVE_MS,
    BUFFER_FIRST_BAR_OPEN_MS,
    BUFFER_FIRST_MINUTE_OPEN_MS,
    BUFFER_LAST_BAR_OPEN_MS,
    BUFFER_LAST_MINUTE_OPEN_MS,
    BUFFER_MINUTE_COUNT,
    BUFFER_REFUSED_BAR_OPEN_MS,
    FINAL_FIT_FAILURE,
    FIRST_2025_ORIGIN_MS,
    HOUR_MS,
    KRAKEN_TIMESTAMP_ROLE,
    LABEL_HORIZON_MS,
    LAST_2025_ORIGIN_MS,
    MINUTE_MS,
    OI_ELIGIBILITY_OFFSET_MS,
    OI_TIMESTAMP_ROLE,
    ORIGIN_COUNT_2025,
    REFIT_EXCLUDED_TAIL_COUNT,
    REFIT_LAST_ORIGIN_MS,
    REFIT_NOMINAL_ORIGIN_COUNT,
    REFIT_TRAIN_START_MS,
    REPLICATION_COMPARISON_IDS,
    REPLICATION_CRITERIA,
    SEAL_BOUNDARY_MS,
    ReplicationDecision,
    ReplicationEvidence,
    buffer_bar_opens,
    buffer_dependent_origins,
    buffer_minute_opens,
    enumerate_2025_origins,
    enumerate_refit_origins,
    evaluate_replication_gate,
    is_buffer_minute_in_scope,
    is_refit_eligible_origin,
    label_close_ms,
    latest_eligible_oi_open_ms,
    replication_comparison_id,
    replication_stream_seed,
    requires_2026_buffer,
    truncate_buffer_minutes,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = REPO_ROOT / "tests/fixtures/replication_c4_golden.json"
V11_SPEC_PATH = REPO_ROOT / "docs/superpowers/specs/2026-09-01-quantara-protocol-v1_1.md"
V11_YAML_PATH = REPO_ROOT / "configs/protocols/quantara-protocol-v1_1.yaml"
MODULE_PATH = REPO_ROOT / "src/quantara/replication_c4.py"


def _fixture() -> dict[str, object]:
    value = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _criterion_values(decision: ReplicationDecision) -> dict[str, bool]:
    return {criterion: getattr(decision, criterion) for criterion in REPLICATION_CRITERIA}


def _synthetic_minute(open_ms: int) -> CanonicalRow:
    price = Decimal("1")
    return CanonicalRow(
        identity=("synthetic",) * 10,
        open_time_ms=open_ms,
        close_time_ms=open_ms + MINUTE_MS - 1,
        nominal_available_ms=open_ms + MINUTE_MS,
        open=price,
        high=price,
        low=price,
        close=price,
        base_asset_volume=price,
        quote_asset_volume=price,
        trade_count=1,
        taker_buy_base_volume=price,
        taker_buy_quote_volume=price,
        source_ignore="0",
    )


def test_g1_g2_calendar_2025_and_buffer_geometry_matches_golden() -> None:
    golden = _fixture()["buffer_geometry"]
    origins = enumerate_2025_origins()
    assert len(origins) == ORIGIN_COUNT_2025 == golden["origin_count_2025"] == 8760
    assert origins[0] == FIRST_2025_ORIGIN_MS == golden["first_origin_ms"]
    assert origins[-1] == LAST_2025_ORIGIN_MS == golden["last_origin_ms"]
    assert all(
        current - previous == HOUR_MS
        for previous, current in zip(origins, origins[1:], strict=False)
    )
    assert len(origins) == nominal_hours(2025)
    assert (
        label_close_ms(LAST_2025_ORIGIN_MS)
        == golden["last_label_close_ms"]
        == BUFFER_END_INCLUSIVE_MS
    )

    dependent = buffer_dependent_origins()
    assert len(dependent) == 23 == golden["buffer_dependent_origin_count"]
    assert dependent[0] == golden["first_buffer_dependent_origin_ms"] == 1767142800000
    assert dependent[-1] == LAST_2025_ORIGIN_MS
    assert dependent == tuple(origin for origin in origins if requires_2026_buffer(origin))
    assert all(
        label_close_ms(origin) < BUFFER_FIRST_BAR_OPEN_MS
        for origin in origins
        if not requires_2026_buffer(origin)
    )

    bar_opens = buffer_bar_opens()
    assert len(bar_opens) == BUFFER_BAR_COUNT == golden["required_1h_bar_count"] == 23
    assert bar_opens[0] == BUFFER_FIRST_BAR_OPEN_MS == golden["first_1h_bar_open_ms"]
    assert bar_opens[-1] == BUFFER_LAST_BAR_OPEN_MS == golden["last_1h_bar_open_ms"]
    assert BUFFER_REFUSED_BAR_OPEN_MS == golden["refused_1h_bar_open_ms"]
    assert BUFFER_REFUSED_BAR_OPEN_MS not in bar_opens


def test_g3_target_only_is_derived_from_frozen_ordering() -> None:
    prediction_ts = LAST_2025_ORIGIN_MS + 2
    greatest_eligible_ts = prediction_ts - 1
    assert greatest_eligible_ts == LAST_2025_ORIGIN_MS + 1
    assert greatest_eligible_ts < BUFFER_FIRST_BAR_OPEN_MS


def test_g4_g5_minute_geometry_real_aggregation_and_truncation() -> None:
    golden = _fixture()["buffer_geometry"]
    minute_opens = buffer_minute_opens()
    assert len(minute_opens) == BUFFER_MINUTE_COUNT == golden["required_1m_row_count"] == 1380
    assert minute_opens[0] == BUFFER_FIRST_MINUTE_OPEN_MS == golden["first_1m_open_ms"]
    assert minute_opens[-1] == BUFFER_LAST_MINUTE_OPEN_MS == golden["last_1m_open_ms"]

    buckets: dict[int, list[int]] = {}
    for open_ms in minute_opens:
        buckets.setdefault(open_ms - (open_ms % HOUR_MS), []).append(open_ms)
    assert len(buckets) == 23
    assert {len(bucket) for bucket in buckets.values()} == {60}

    minutes = tuple(_synthetic_minute(open_ms) for open_ms in minute_opens)
    bars = aggregate_timeframe(minutes, ("synthetic-1h",) * 10, HOUR_MS)
    assert len(bars) == 23
    assert all(bar.close_time_ms == bar.open_time_ms + HOUR_MS - 1 for bar in bars)
    assert all(bar.nominal_available_ms == bar.open_time_ms + HOUR_MS for bar in bars)
    with pytest.raises(IncompleteGroup):
        aggregate_timeframe(minutes[:-1], ("synthetic-1h",) * 10, HOUR_MS)

    full_day = list(
        range(BUFFER_FIRST_MINUTE_OPEN_MS, BUFFER_FIRST_MINUTE_OPEN_MS + 24 * HOUR_MS, MINUTE_MS)
    )
    original_day = full_day.copy()
    kept_day, discarded_day = truncate_buffer_minutes(full_day)
    assert full_day == original_day
    assert len(kept_day) == 1380
    assert discarded_day == 60

    full_month = tuple(
        range(
            BUFFER_FIRST_MINUTE_OPEN_MS, BUFFER_FIRST_MINUTE_OPEN_MS + 31 * 24 * HOUR_MS, MINUTE_MS
        )
    )
    kept_month, discarded_month = truncate_buffer_minutes(full_month)
    assert len(kept_month) == 1380
    assert discarded_month == 43260
    assert is_buffer_minute_in_scope(BUFFER_FIRST_MINUTE_OPEN_MS)
    assert is_buffer_minute_in_scope(BUFFER_LAST_MINUTE_OPEN_MS)
    assert not is_buffer_minute_in_scope(BUFFER_REFUSED_BAR_OPEN_MS)


def test_g6_final_refit_sample_uses_the_exact_purge_boundary() -> None:
    golden = _fixture()["refit_geometry"]
    origins = enumerate_refit_origins()
    assert len(origins) == REFIT_NOMINAL_ORIGIN_COUNT == golden["nominal_origin_count"] == 37969
    assert origins[0] == REFIT_TRAIN_START_MS == golden["first_origin_ms"]
    assert origins[-1] == REFIT_LAST_ORIGIN_MS == golden["last_origin_ms"]
    assert all(origin + LABEL_HORIZON_MS <= SEAL_BOUNDARY_MS for origin in origins)
    assert is_refit_eligible_origin(REFIT_LAST_ORIGIN_MS)
    assert not is_refit_eligible_origin(1735606800000)
    naive_count = len(tuple(range(REFIT_TRAIN_START_MS, SEAL_BOUNDARY_MS, HOUR_MS)))
    assert naive_count == golden["naive_origin_count"] == 37992
    assert (
        naive_count - len(origins)
        == REFIT_EXCLUDED_TAIL_COUNT
        == golden["excluded_tail_count"]
        == 23
    )
    assert origins[-1] != 1735599600000


def test_g7_oi_eligibility_is_conservative_and_kraken_asymmetry_survives() -> None:
    for boundary_ms in (0, HOUR_MS, LAST_2025_ORIGIN_MS):
        latest = latest_eligible_oi_open_ms(boundary_ms)
        assert latest == boundary_ms - OI_ELIGIBILITY_OFFSET_MS
        assert latest + OI_ELIGIBILITY_OFFSET_MS < boundary_ms + 2
        assert boundary_ms + OI_ELIGIBILITY_OFFSET_MS >= boundary_ms + 2

    assert OI_TIMESTAMP_ROLE == "UNRESOLVED_CONSERVATIVE"
    assert KRAKEN_TIMESTAMP_ROLE == "DOCUMENTED_INTERVAL_START"
    document = yaml.safe_load(V11_YAML_PATH.read_text(encoding="utf-8"))
    oi_clause = document["point_in_time"]["oi_eligibility"]
    kraken_clause = document["point_in_time"]["kraken_eligibility"]
    assert "interval-start" not in oi_clause.lower()
    assert "interval-start" in kraken_clause.lower()

    spec_text = V11_SPEC_PATH.read_text(encoding="utf-8")
    oi_bullet = next(
        line for line in spec_text.splitlines() if line.startswith("- For five-minute OI")
    )
    oi_bullet_index = spec_text.splitlines().index(oi_bullet)
    oi_clause_text = " ".join(spec_text.splitlines()[oi_bullet_index : oi_bullet_index + 2])
    assert "interval-start" not in oi_clause_text.lower()
    assert "For Kraken hourly OHLCVT with interval-start" in spec_text


def test_g8_comparison_ids_seeds_and_single_year_bootstrap_match_golden() -> None:
    golden = _fixture()
    comparison_fixture = golden["comparison_ids"]
    assert set(REPLICATION_COMPARISON_IDS) == {"M2", "M2K", "M3", "M4"}
    for model, expected in comparison_fixture.items():
        comparison_id = replication_comparison_id(model)
        assert comparison_id == REPLICATION_COMPARISON_IDS[model] == expected["comparison_id"]
        assert replication_stream_seed(model) == derive_stream_seed(comparison_id, 2025)
        assert replication_stream_seed(model) == expected["seed_2025"]

    grid = (Decimal("0.001"), Decimal("0.001"), None) * 2920
    result = bootstrap_b4(
        {2025: grid}, comparison_id=replication_comparison_id("M2"), resamples=200
    )
    geometry = golden["bootstrap_geometry_2025"]
    assert result.observed_mean == Fraction(1, 1000)
    assert result.ci_lower == Fraction(1, 1000)
    assert result.ci_upper == Fraction(1, 1000)
    assert result.p_value == Fraction(1, 201)
    assert (
        f"{result.observed_mean.numerator}/{result.observed_mean.denominator}"
        == geometry["synthetic_observed_mean"]
    )
    assert (
        f"{result.p_value.numerator}/{result.p_value.denominator}"
        == geometry["synthetic_p_value_at_b_200"]
    )

    valid_indices = {index * 52 for index in range(168)}
    minimum_valid_grid = tuple(
        Decimal("0.001") if index in valid_indices else None for index in range(8760)
    )
    assert bootstrap_b4({2025: minimum_valid_grid}, comparison_id="minimum-valid", resamples=1)
    one_short_grid = tuple(
        None if index == 0 else value for index, value in enumerate(minimum_valid_grid)
    )
    with pytest.raises(BootstrapB4InferenceError) as exc_info:
        bootstrap_b4({2025: one_short_grid}, comparison_id="one-short", resamples=1)
    assert exc_info.value.reason == "insufficient_observed_paired_valid"
    assert exc_info.value.year == 2025

    assert math.ceil(8760 / 168) == geometry["n_blocks"] == 53
    assert 53 * 168 == geometry["concatenated_hours"] == 8904
    assert 8760 - 168 == geometry["largest_eligible_block_start"] == 8592
    assert 8760 - 168 + 1 == geometry["distinct_eligible_block_starts"] == 8593
    assert math.ceil(Decimal("0.025") * 20000) == geometry["ci_rank_lower"] == 500
    assert math.ceil(Decimal("0.975") * 20000) == geometry["ci_rank_upper"] == 19500


def test_g9_replication_gate_worked_decisions_and_frozen_slope_binding() -> None:
    golden = _fixture()["worked_decisions"]
    for case in golden.values():
        raw = case["evidence"]
        evidence = ReplicationEvidence(
            bss_b2=Decimal(raw["bss_b2"]),
            ci_lower=Decimal(raw["ci_lower"]),
            probability_bias=Decimal(raw["probability_bias"]),
            calibration_slope=Decimal(raw["calibration_slope"]),
            calibration_defined_and_converged=raw["calibration_defined_and_converged"],
        )
        decision = evaluate_replication_gate(evidence)
        assert _criterion_values(decision) == case["criteria"]
        assert decision.outcome == case["outcome"]

    defaults = inspect.signature(calibration_slope_passes).parameters
    lower = defaults["lower"].default
    upper = defaults["upper"].default
    assert isinstance(lower, Decimal) and isinstance(upper, Decimal)
    base = ReplicationEvidence(Decimal("0.02"), Decimal("0.001"), Decimal("0"), Decimal("1"), True)
    assert evaluate_replication_gate(
        replace(base, calibration_slope=lower)
    ).calibration_slope_in_frozen_band
    assert evaluate_replication_gate(
        replace(base, calibration_slope=upper)
    ).calibration_slope_in_frozen_band
    assert not evaluate_replication_gate(
        replace(base, calibration_slope=lower - Decimal("0.001"))
    ).calibration_slope_in_frozen_band
    assert not evaluate_replication_gate(
        replace(base, calibration_slope=upper + Decimal("0.001"))
    ).calibration_slope_in_frozen_band


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    (
        ("bss_b2", Decimal("0.019")),
        ("ci_lower", Decimal("0")),
        ("probability_bias", Decimal("0.021")),
        ("calibration_slope", Decimal("0.799")),
        ("calibration_defined_and_converged", False),
    ),
)
def test_g9_each_criterion_fails_individually(field_name: str, bad_value: object) -> None:
    evidence = ReplicationEvidence(
        Decimal("0.02"), Decimal("0.001"), Decimal("0"), Decimal("1"), True
    )
    decision = evaluate_replication_gate(replace(evidence, **{field_name: bad_value}))
    assert decision.outcome == "DID_NOT_REPLICATE"
    values = _criterion_values(decision)
    assert (
        values[
            field_name
            if field_name == "calibration_defined_and_converged"
            else {
                "bss_b2": "bss_b2_at_least_0_02",
                "ci_lower": "ci_lower_above_zero",
                "probability_bias": "absolute_probability_bias_at_most_0_02",
                "calibration_slope": "calibration_slope_in_frozen_band",
            }[field_name]
        ]
        is False
    )
    assert sum(values.values()) == 4


@pytest.mark.parametrize("bias", (Decimal("-0.02"), Decimal("0.02")))
def test_g9_probability_bias_boundaries_are_inclusive(bias: Decimal) -> None:
    evidence = ReplicationEvidence(Decimal("0.02"), Decimal("0.001"), bias, Decimal("1"), True)
    assert evaluate_replication_gate(evidence).absolute_probability_bias_at_most_0_02


@pytest.mark.parametrize(
    "field_name", ("bss_b2", "ci_lower", "probability_bias", "calibration_slope")
)
def test_g9_binary_float_inputs_are_rejected(field_name: str) -> None:
    evidence = ReplicationEvidence(
        Decimal("0.02"), Decimal("0.001"), Decimal("0"), Decimal("1"), True
    )
    contaminated = replace(evidence, **{field_name: 0.02})
    with pytest.raises(TypeError):
        evaluate_replication_gate(contaminated)


def test_g9_criterion_inventory_rejections_and_outcome_separation() -> None:
    assert REPLICATION_CRITERIA == (
        "bss_b2_at_least_0_02",
        "ci_lower_above_zero",
        "absolute_probability_bias_at_most_0_02",
        "calibration_slope_in_frozen_band",
        "calibration_defined_and_converged",
    )
    assert len(REPLICATION_CRITERIA) == 5
    assert all("year" not in criterion for criterion in REPLICATION_CRITERIA)
    assert tuple(field.name for field in fields(ReplicationDecision)) == (
        *REPLICATION_CRITERIA,
        "outcome",
    )

    source = MODULE_PATH.read_text(encoding="utf-8")
    for rejected in ("0.015", "0.03", "0.75", "1.25", "0.04", "0.98"):
        assert rejected not in source

    decision = evaluate_replication_gate(
        ReplicationEvidence(Decimal("0.02"), Decimal("0.001"), Decimal("0"), Decimal("1"), True)
    )
    assert decision.outcome == "REPLICATED"
    assert decision.outcome != FINAL_FIT_FAILURE
    outcome_states = yaml.safe_load(V11_YAML_PATH.read_text(encoding="utf-8"))["outcome_states"]
    assert outcome_states == ["FINAL_FIT_FAILURE", "REPLICATED", "DID_NOT_REPLICATE"]
