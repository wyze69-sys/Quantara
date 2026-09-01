from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
V1_SPEC_PATH = REPO_ROOT / "docs/superpowers/specs/2026-08-31-quantara-protocol-v1.md"
V1_YAML_PATH = REPO_ROOT / "configs/protocols/quantara-protocol-v1.yaml"
V1_FIXTURE_PATH = REPO_ROOT / "tests/fixtures/protocol_v1_expected.json"
V11_SPEC_PATH = REPO_ROOT / "docs/superpowers/specs/2026-09-01-quantara-protocol-v1_1.md"
V11_YAML_PATH = REPO_ROOT / "configs/protocols/quantara-protocol-v1_1.yaml"

PREDECESSOR_SHA256 = "91457d3f1497abfd4e20cf4624768a5d9e9ba4b4478008fb4c7f65c17d90c65a"
UNASSIGNED_V11_HASH = "NOT_YET_ASSIGNED_PENDING_PACKET_C5"
V1_TOP_LEVEL_KEYS = (
    "protocol_id",
    "protocol_status",
    "frozen_date",
    "planning_baseline",
    "research_question",
    "inventory",
    "canonical_lane_immutability",
    "canonical_record_fields",
    "exclusions",
    "target",
    "realized_volatility",
    "feature_formulas",
    "feature_window_completeness",
    "dislocation_roles",
    "model_ladder",
    "model_mandates",
    "cross_quote_dislocation_policy",
    "logistic_constants",
    "search_and_calibration_restrictions",
    "point_in_time",
    "missing_and_duplicate_policy",
    "validation",
    "success_gate",
    "optional_family_retention",
    "sealed_2025",
    "audit_reference_hash_basis",
    "audit_references",
)
HEX_64_RE = re.compile(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")
FROZEN_HASH_POSITION_RE = re.compile(
    r"(?im)^.*frozen(?:_semantic)?(?:\s+|_)sha-?256.*$"
)


def _load_yaml(path: Path) -> dict[str, object]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _load_v11() -> dict[str, object]:
    return _load_yaml(V11_YAML_PATH)


def _assert_no_float(node: object, path: str = "$") -> None:
    assert not isinstance(node, float), f"float is forbidden at {path}"
    if isinstance(node, dict):
        for key, value in node.items():
            _assert_no_float(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _assert_no_float(value, f"{path}[{index}]")


def test_frozen_v1_artifacts_exist_and_semantic_identity_is_unchanged() -> None:
    assert V1_SPEC_PATH.is_file()
    assert V1_YAML_PATH.is_file()
    assert V1_FIXTURE_PATH.is_file()

    fixture = json.loads(V1_FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["semantic_sha256"] == PREDECESSOR_SHA256

    document = _load_yaml(V1_YAML_PATH)
    assert set(V1_TOP_LEVEL_KEYS) <= set(document)
    projected = {key: document[key] for key in V1_TOP_LEVEL_KEYS}
    canonical = json.dumps(
        projected,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == PREDECESSOR_SHA256


def test_v11_draft_is_fail_closed_and_unloadable_by_frozen_v1_loader() -> None:
    from quantara.protocol import ProtocolValidationError, load_protocol

    with pytest.raises(ProtocolValidationError):
        load_protocol(V11_YAML_PATH)


def test_v11_draft_identity_status_and_hash_state() -> None:
    document = _load_v11()
    assert document["protocol_id"] == "quantara-protocol-v1_1"
    assert document["protocol_status"] == "DRAFT_UNFROZEN_SUCCESSOR"
    assert document["supersedes"] == "quantara-protocol-v1"
    assert document["predecessor_semantic_sha256"] == PREDECESSOR_SHA256
    assert document["frozen_semantic_sha256"] == UNASSIGNED_V11_HASH
    assert document["scoring_permission"] == "NONE_UNTIL_FROZEN"

    spec_text = V11_SPEC_PATH.read_text(encoding="utf-8")
    yaml_text = V11_YAML_PATH.read_text(encoding="utf-8")
    all_hash_tokens = HEX_64_RE.findall(spec_text + "\n" + yaml_text)
    assert set(all_hash_tokens) <= {PREDECESSOR_SHA256}
    for line in FROZEN_HASH_POSITION_RE.findall(spec_text + "\n" + yaml_text):
        assert HEX_64_RE.search(line) is None, (
            f"draft frozen-hash position contains a digest: {line}"
        )


def test_v11_time_semantics_are_explicit_and_boundary_ordering_is_causal() -> None:
    document = _load_v11()
    point_in_time = document["point_in_time"]
    assert point_in_time["boundary_event_time"] == "F = T"
    assert point_in_time["nominal_eligibility_ts"] == "T + 1 ms"
    assert point_in_time["prediction_ts"] == "T + 2 ms"
    assert point_in_time["join_inequality"] == "eligibility_ts < prediction_ts"
    assert point_in_time["kline_eligibility_ts"] == "C + 1 ms"
    assert point_in_time["funding_eligibility_ts"] == "F + 1 ms"
    assert point_in_time["oi_eligibility_ts"] == "O + 5 minutes"
    assert point_in_time["kraken_eligibility_ts"] == "K + 1 hour"
    assert document["feature_formulas"]["funding_24h_sum"] == (
        "sum settled rates with T-24h < settlement_ts <= T"
    )

    boundary_ms = 0
    eligibility_ms = boundary_ms + 1
    v11_prediction_ms = boundary_ms + 2
    v1_prediction_ms = boundary_ms + 1
    assert eligibility_ms < v11_prediction_ms
    assert not eligibility_ms < v1_prediction_ms


def test_v11_quantile_contract_is_nearest_rank_without_rounding() -> None:
    quantile = _load_v11()["target"]["quantile"]
    assert quantile["ordering"] == "Z_(1) <= ... <= Z_(N)"
    assert quantile["rank"] == "j = ceil(0.80 * N)"
    assert quantile["selection"] == "k = Z_(j)"
    assert quantile["label"] == "Y_t = 1[Z_t > k]"
    assert quantile["decimal_precision"] == 50
    assert quantile["decimal_rounding"] == "ROUND_HALF_EVEN"
    assert quantile["interpolation"] == "FORBIDDEN"
    assert quantile["threshold_rounding"] == "FORBIDDEN"
    assert quantile["canonical_threshold_representation"] == "full Decimal string"

    sample_size = 6
    assert math.ceil(0.80 * sample_size) == 5


@pytest.mark.parametrize(
    ("test_start", "expected_last_origin", "expected_last_label_close"),
    (
        (
            datetime(2022, 1, 1, tzinfo=UTC),
            datetime(2021, 12, 31, tzinfo=UTC),
            datetime(2021, 12, 31, 23, 59, 59, 999000, tzinfo=UTC),
        ),
        (
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2024, 12, 31, tzinfo=UTC),
            datetime(2024, 12, 31, 23, 59, 59, 999000, tzinfo=UTC),
        ),
    ),
)
def test_v11_exact_purge_arithmetic(
    test_start: datetime,
    expected_last_origin: datetime,
    expected_last_label_close: datetime,
) -> None:
    purge = _load_v11()["validation"]["purge"]
    assert purge["training_origin_eligibility"] == "O + 24h <= S"
    assert purge["last_eligible_training_origin"] == "S - 24h"
    assert purge["first_test_origin"] == "S"

    last_origin = test_start - timedelta(hours=24)
    last_label_close = last_origin + timedelta(hours=24) - timedelta(milliseconds=1)
    assert last_origin == expected_last_origin
    assert last_label_close == expected_last_label_close
    if test_start.year == 2025:
        rejected_cutoff = datetime(2024, 12, 30, 23, tzinfo=UTC)
        assert last_origin != rejected_cutoff


def test_v11_yaml_has_no_floats_duplicate_top_level_keys_or_missing_deferred_packets() -> None:
    yaml_text = V11_YAML_PATH.read_text(encoding="utf-8")
    document = _load_v11()
    _assert_no_float(document)

    root = yaml.compose(yaml_text, Loader=yaml.SafeLoader)
    assert isinstance(root, yaml.MappingNode)
    keys = [key_node.value for key_node, _ in root.value]
    assert len(keys) == len(set(keys)), "duplicate top-level YAML mapping key"

    deferred = document["deferred_change_set"]
    assert set(deferred) == {"C2", "C3", "C4", "C5"}
    assert deferred["C2"]["owner_packet"] == "C2"
    assert deferred["C2"]["status"] == "IMPLEMENTED_PACKET_C2"
    assert deferred["C3"]["owner_packet"] == "C3"
    assert deferred["C3"]["status"] == "IMPLEMENTED_PACKET_C3"
    assert deferred["C4"] == {
        "owner_packet": "C4",
        "status": "IMPLEMENTED_PACKET_C4",
    }
    assert deferred["C5"] == {"owner_packet": "C5", "status": "DEFERRED"}


def test_v11_estimator_and_optional_family_are_bound_by_packet_c3() -> None:
    document = _load_v11()
    binding = document["estimator_binding"]
    assert binding["implementation"] == "src/quantara/training_metrics_logistic.py"
    assert binding["entry_point"] == "fit_logistic_irls"
    assert binding["model_l2_lambda"] == "1"
    assert binding["maximum_updates"] == 50
    assert binding["eta_clamp"] == "24"
    assert binding["probability_clamp"] == "0.000000000001"

    assert document["fail_closed_causes"] == [
        "single_class_training_outcome",
        "constant_train_feature",
        "zero_pivot",
        "non_convergence",
        "binary_float_input",
        "calibration_single_class_outcome",
        "calibration_degenerate_logit",
    ]
    calibration = document["calibration"]
    assert calibration["lambda"] == "0"
    assert set(calibration["back_transform"]) == {"slope", "intercept"}
    assert len(calibration["failure_conditions"]) == 6

    m2k = document["model_ladder"]["M2K"]
    assert m2k["base"] == "M2"
    assert m2k["adds"] == [
        "kraken_ret_1h",
        "kraken_rv_24h",
        "binance_kraken_ret_divergence_1h",
        "binance_kraken_cross_quote_log_ratio",
    ]

    optional = document["optional_family_retention"]
    assert optional["holm_test_count"] == 3
    assert optional["successor_repair_status"] == "IMPLEMENTED_PACKET_C3"
    assert optional["compute_all_three_before_deciding"] is True

    assert document["success_gate"]["criteria"] == [
        {
            "id": 1,
            "rule": "pooled BSS_B2 >= 0.02",
            "threshold": "0.02",
        },
        {
            "id": 2,
            "rule": (
                "bootstrap 95% lower bound for BS_B2 - BS_candidate is greater "
                "than zero"
            ),
        },
        {
            "id": 3,
            "rule": "positive Brier improvement in at least two validation years",
            "min_years": 2,
        },
        {
            "id": 4,
            "rule": "no year has BSS_B2 < -0.02",
            "threshold": "-0.02",
        },
        {
            "id": 5,
            "rule": "pooled absolute probability bias is at most 0.02",
            "threshold": "0.02",
        },
        {
            "id": 6,
            "rule": "pooled calibration slope is between 0.8 and 1.2",
            "lower": "0.8",
            "upper": "1.2",
        },
        {
            "id": 7,
            "rule": "yearly absolute probability bias is at most 0.04",
            "threshold": "0.04",
        },
    ]


def test_v11_bootstrap_b4_contract_is_frozen_by_packet_c2() -> None:
    bootstrap = _load_v11()["validation"]["bootstrap"]
    assert bootstrap["block_hours"] == 168
    assert bootstrap["resamples"] == 20000
    assert bootstrap["circularity"] == "non_circular"
    assert bootstrap["eligible_start_range"] == "0 ... H_y - L"
    assert bootstrap["blocks_per_year"] == "n_blocks_y = ceil(H_y / L)"
    assert bootstrap["interval"]["method"] == (
        "raw-bootstrap percentile nearest-rank without interpolation"
    )
    assert bootstrap["interval"]["rank_formula"] == "j(q) = ceil(q * B)"
    assert bootstrap["p_value"]["null_centering"] == (
        "d0_t = d_t - D_obs on paired-valid hours; nulls stay null"
    )
    assert bootstrap["p_value"]["formula"] == (
        "p = (1 + count(D0*_b >= D_obs)) / (B + 1)"
    )
    assert bootstrap["fail_closed"]["observed_year"] == (
        "fewer than 168 paired-valid observations in any required year"
    )
    assert bootstrap["fail_closed"]["replicate_year"] == (
        "no paired-valid observation in any required year for a replicate"
    )
    assert bootstrap["successor_repair_status"] == "IMPLEMENTED_PACKET_C2"
    assert bootstrap["supersedes_v1_inference"] is True


def test_v11_spec_records_intentional_lineage_and_future_experiment_boundary() -> None:
    spec_text = V11_SPEC_PATH.read_text(encoding="utf-8")
    assert "2026-08-24" in spec_text
    assert "LightGBM" in spec_text
    assert "earlier recommendation" in spec_text
    assert "separately preregistered successor experiment" in spec_text
    assert "no scoring of any period" in spec_text
    assert "no 2025 access" in spec_text


def test_v11_c4_contract_literals_and_terminal_states_are_exact() -> None:
    document = _load_v11()
    assert len(document) == 46
    assert document["protocol_status"] == "DRAFT_UNFROZEN_SUCCESSOR"
    assert document["frozen_semantic_sha256"] == UNASSIGNED_V11_HASH

    resolution = document["oi_timestamp_resolution"]
    assert resolution["oi_timestamp_role"] == "UNRESOLVED_CONSERVATIVE"
    assert resolution["oi_provider_field"] == "create_time"
    assert resolution["oi_eligibility_ts"] == "O + 5 minutes"
    assert resolution["semantic_claim_permitted"] is False
    assert resolution["kraken_timestamp_role"] == "DOCUMENTED_INTERVAL_START"
    assert resolution["kraken_eligibility_ts"] == "K + 1 hour"

    final_refit = document["final_refit"]
    assert final_refit["retained_candidate"] == "frozen C3 retention graph result"
    assert final_refit["paired_comparator"] == "B2"
    assert final_refit["refit_train_start"] == "2020-09-01 00:00:00.000 UTC"
    assert final_refit["refit_origin_rule"] == "O + 24h <= 2025-01-01 00:00:00.000 UTC"
    assert final_refit["refit_last_origin"] == "2024-12-31 00:00:00.000 UTC"
    assert final_refit["refit_last_label_close"] == "2024-12-31 23:59:59.999 UTC"
    assert final_refit["nominal_origin_count"] == 37969
    assert final_refit["excluded_tail_count"] == 23
    assert final_refit["failure"]["state"] == "FINAL_FIT_FAILURE"

    buffer_contract = document["target_endpoint_buffer_2026"]
    assert buffer_contract["state"] == "SEALED"
    assert buffer_contract["role"] == "target_only"
    assert buffer_contract["permitted_series"] == ["btcusdt_perp_ohlcv"]
    assert buffer_contract["origin_count_supported"] == 8760
    assert buffer_contract["buffer_dependent_origins"] == 23
    assert buffer_contract["required_1h_bar_count"] == 23
    assert buffer_contract["required_1m_row_count"] == 1380
    assert buffer_contract["buffer_end_inclusive_ms"] == 1767308399999
    assert buffer_contract["refused_bar_open_ms"] == 1767308400000
    sealed = document["sealed_2025"]
    assert buffer_contract["allowed_pre_gate_checks"] == sealed["allowed_pre_gate_checks"]
    assert buffer_contract["forbidden_operations"] == sealed["forbidden_operations"]

    gate = document["replication_gate_2025"]
    assert [criterion["id"] for criterion in gate["criteria"]] == [1, 2, 3, 4, 5]
    assert [criterion["threshold"] for criterion in gate["criteria"]] == [
        "0.02",
        "> 0",
        "0.02",
        "frozen C3 defaults",
        "true",
    ]
    assert gate["outcome_on_failure"] == "DID_NOT_REPLICATE"
    assert gate["run_count_permitted"] == 1
    assert gate["bootstrap_geometry"]["H_2025"] == 8760
    assert gate["bootstrap_geometry"]["block_hours"] == 168
    assert gate["bootstrap_geometry"]["n_blocks"] == 53
    assert gate["bootstrap_geometry"]["concatenated_hours"] == 8904
    assert gate["bootstrap_geometry"]["eligible_block_starts"] == "0 .. 8592"
    assert gate["bootstrap_geometry"]["distinct_eligible_starts"] == 8593
    assert gate["bootstrap_geometry"]["ci_rank_lower_at_b_20000"] == 500
    assert gate["bootstrap_geometry"]["ci_rank_upper_at_b_20000"] == 19500
    assert gate["comparison_id"]["seeds_2025"] == {
        "M2": 13432793617478683004,
        "M2K": 17576365771105646995,
        "M3": 15946086953525544617,
        "M4": 3803725181447297110,
    }
    calibration_reuse = gate["calibration_reuse"]
    assert calibration_reuse["lambda"] == "0"
    assert calibration_reuse["probability_clamp_lower"] == "0.000000000001"
    assert calibration_reuse["probability_clamp_upper"] == "0.999999999999"
    assert calibration_reuse["slope"] == "calibration_slope = beta_z / sd_x"
    assert calibration_reuse["intercept"] == (
        "calibration_intercept = beta_0 - beta_z * mu_x / sd_x"
    )
    assert calibration_reuse["slope_band_source"] == (
        "estimator_c3.calibration_slope_passes defaults"
    )
    assert calibration_reuse["failure_condition_count"] == 6
    assert gate["coverage_reporting"]["minimum_coverage_threshold"] == "NONE_BY_DESIGN"

    sealed = document["sealed_2025"]
    assert sealed["successor_buffer_and_replication_rule"] == "IMPLEMENTED_PACKET_C4"
    assert sealed["buffer_contract"] == "target_endpoint_buffer_2026"
    assert sealed["replication_contract"] == "replication_gate_2025"
    assert document["outcome_states"] == [
        "FINAL_FIT_FAILURE",
        "REPLICATED",
        "DID_NOT_REPLICATE",
    ]


def test_v11_c4_spec_status_is_implemented_while_c5_stays_deferred() -> None:
    spec_text = V11_SPEC_PATH.read_text(encoding="utf-8")
    assert (
        "| Timestamp, refit, buffer, and replication contract | `IMPLEMENTED` | C4 |" in spec_text
    )
    assert "| Coverage and final freeze | `DEFERRED` | C5 |" in spec_text
