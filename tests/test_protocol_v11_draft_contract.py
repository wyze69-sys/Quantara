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
    for packet, item in deferred.items():
        assert item["owner_packet"] == packet
        assert item["status"] == "DEFERRED"


def test_v11_spec_records_intentional_lineage_and_future_experiment_boundary() -> None:
    spec_text = V11_SPEC_PATH.read_text(encoding="utf-8")
    assert "2026-08-24" in spec_text
    assert "LightGBM" in spec_text
    assert "earlier recommendation" in spec_text
    assert "separately preregistered successor experiment" in spec_text
    assert "no scoring of any period" in spec_text
    assert "no 2025 access" in spec_text
