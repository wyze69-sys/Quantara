from __future__ import annotations

import bisect
import copy
import hashlib
import hmac
import json
import os
import re
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from quantara.protocol import (
    FROZEN_SEMANTIC_SHA256,
    ProtocolGuardError,
    canonical_semantic_json,
    guard_protocol_operation,
)
from quantara.protocol_v11 import (
    V11_FROZEN_SEMANTIC_SHA256,
    V11_HASH_EXCLUDED_KEYS,
    V11_IN_SCOPE_KEY_COUNT,
    V11_TOTAL_KEY_COUNT,
    V11_UNASSIGNED_HASH,
    ProtocolV11DraftError,
    ProtocolV11GuardError,
    guard_protocol_v11_operation,
    hash_scope_projection,
    load_protocol_v11,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
V1_FIXTURE_PATH = REPO_ROOT / "tests/fixtures/protocol_v1_expected.json"
V11_FIXTURE_PATH = REPO_ROOT / "tests/fixtures/protocol_v1_1_expected.json"
V11_YAML_PATH = REPO_ROOT / "configs/protocols/quantara-protocol-v1_1.yaml"
V11_SPEC_PATH = (
    REPO_ROOT / "docs/superpowers/specs/2026-09-01-quantara-protocol-v1_1.md"
)
V11_MODULE_PATH = REPO_ROOT / "src/quantara/protocol_v11.py"
EXPECTED_V11_SEMANTIC_SHA256 = (
    "12dd3445365fdaa9e35cdcf93cae3e79a88b6b4d72d3d703b921359d1e917a9b"
)
EXPECTED_V11_SPEC_SHA256 = (
    "b3ace74814d5619c91650c4a56fd4eb1f27e12d7e98ddb895da653248395a7ab"
)
PRE_EDIT_V11_SPEC_SHA256 = (
    "4c72d2e672d7f46ef9af8b7fb30d3263d6b0a5cb0e52216256aaefb7965ef150"
)
V1_ARTIFACT_TYPE = "quantara-protocol-v1-gate-result"
V11_ARTIFACT_TYPE = "quantara-protocol-v1_1-gate-result"
V1_HMAC_ENV = "QUANTARA_PROTOCOL_V1_GATE_HMAC_KEY"
V11_HMAC_ENV = "QUANTARA_PROTOCOL_V1_1_GATE_HMAC_KEY"
SYNTHETIC_KEY_HEX = "23" * 32
INHERITED_KEYS = (
    "audit_reference_hash_basis",
    "canonical_lane_immutability",
    "canonical_record_fields",
    "cross_quote_dislocation_policy",
    "dislocation_roles",
    "feature_formulas",
    "feature_window_completeness",
    "inventory",
    "logistic_constants",
    "missing_and_duplicate_policy",
    "model_mandates",
    "planning_baseline",
    "realized_volatility",
    "research_question",
    "search_and_calibration_restrictions",
    "success_gate",
)
AUDIT_DIGESTS = {
    "a7_report": "379a70250630f1e914618eda33131f6d396535126cbedbde7955a4216e7b2f72",
    "a7_sidecar": "3b3b6ea81b3e1d91a9c10140333b2e01ab39929ff9022d0573878defd043ff58",
    "a8_report": "548ad0c2c6d766f49d5bb41de0fa1fecd0e928ec8939d253db5a1d31e55a9919",
    "a8_sidecar": "08f972fcbc9776d5a6cdc028a2d7523d24355887b204dddc2277a540c22a2c52",
    "a9_report": "225793a4723c1f55345084fe0a5be5c68273181798ce96ba61ac3283adaf5fb5",
    "a9_sidecar": "808c1a17c0b710187c36254c31992d2b645cc2533b7fec4b4c0d05b7d42f7c14",
    "a10_report": "61881d940dca4810293b487cb172427fc5c18d1936724ba28939eabc4a88e9ee",
    "a10_sidecar": "621c5781df4d94810dbfc2fa61f9a78767f6b735ed9d42c421d2cfc5e10cfe86",
}


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _load_document() -> dict[str, object]:
    value = yaml.safe_load(V11_YAML_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_document(tmp_path: Path, document: dict[str, object]) -> Path:
    path = tmp_path / "protocol-v1_1.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _normalized_sha256(path: Path) -> str:
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _artifact(
    artifact_type: str,
    protocol_sha256: str,
    criteria: dict[str, object],
    key_hex: str = SYNTHETIC_KEY_HEX,
) -> bytes:
    payload = {
        "artifact_type": artifact_type,
        "schema_version": 1,
        "protocol_sha256": protocol_sha256,
        "operation": "score_2025",
        "criteria": criteria,
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    envelope = {
        "payload": payload,
        "mac": hmac.digest(bytes.fromhex(key_hex), canonical, "sha256").hex(),
    }
    return json.dumps(
        envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _mutate_top_level(value: object) -> object:
    if isinstance(value, str):
        return value + "__C5_TAMPER__"
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, list):
        return [*copy.deepcopy(value), "__C5_TAMPER__"]
    if isinstance(value, dict):
        changed = copy.deepcopy(value)
        changed["__c5_tamper__"] = "changed"
        return changed
    raise AssertionError(f"unsupported top-level mutation type: {type(value).__name__}")


def _resolve_strictly_before(
    rows: list[tuple[datetime, str]], prediction_ts: datetime
) -> str | None:
    timestamps = [timestamp for timestamp, _ in rows]
    index = bisect.bisect_left(timestamps, prediction_ts) - 1
    return None if index < 0 else rows[index][1]


def _parent_document() -> dict[str, object]:
    result = subprocess.run(
        [
            "git",
            "show",
            "c2e1a8d:configs/protocols/quantara-protocol-v1_1.yaml",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    value = yaml.safe_load(result.stdout)
    assert isinstance(value, dict)
    return value


def test_frozen_digest_is_identical_in_every_recorded_location() -> None:
    fixture = _load_json(V11_FIXTURE_PATH)
    document = _load_document()
    module_text = V11_MODULE_PATH.read_text(encoding="utf-8")
    spec_text = V11_SPEC_PATH.read_text(encoding="utf-8")
    digest = EXPECTED_V11_SEMANTIC_SHA256

    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert digest != V11_UNASSIGNED_HASH
    assert fixture["semantic_sha256"] == digest
    assert document["frozen_semantic_sha256"] == digest
    assert V11_FROZEN_SEMANTIC_SHA256 == digest
    assert digest in module_text
    assert spec_text.count(digest) >= 2


def test_fixture_expected_semantic_hashes_to_the_frozen_digest() -> None:
    fixture = _load_json(V11_FIXTURE_PATH)
    canonical = json.dumps(
        fixture["expected_semantic"],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == (
        EXPECTED_V11_SEMANTIC_SHA256
    )
    assert len(canonical.encode("utf-8")) == 42566


def test_yaml_projection_hashes_to_the_frozen_digest() -> None:
    projection = hash_scope_projection(_load_document())
    canonical = canonical_semantic_json(projection)
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == (
        EXPECTED_V11_SEMANTIC_SHA256
    )


def test_fixture_and_yaml_projection_are_equal_key_by_key() -> None:
    expected = _load_json(V11_FIXTURE_PATH)["expected_semantic"]
    actual = hash_scope_projection(_load_document())
    assert isinstance(expected, dict)
    for key in sorted(set(expected) | set(actual)):
        assert expected.get(key) == actual.get(key), f"first differing key: {key}"


def test_fixture_declares_the_48_in_scope_keys_in_sorted_order() -> None:
    fixture = _load_json(V11_FIXTURE_PATH)
    expected = fixture["expected_semantic"]
    keys = fixture["expected_top_level_keys"]
    assert isinstance(expected, dict)
    assert keys == sorted(expected) == sorted(keys)
    assert len(keys) == 48


def test_frozen_loader_returns_the_frozen_digest() -> None:
    protocol = load_protocol_v11(V11_YAML_PATH)
    assert protocol.semantic_sha256 == EXPECTED_V11_SEMANTIC_SHA256


@pytest.mark.parametrize(
    "key", _load_json(V11_FIXTURE_PATH)["expected_top_level_keys"]
)
def test_frozen_loader_rejects_every_single_key_mutation(
    tmp_path: Path, key: str
) -> None:
    document = _load_document()
    document[key] = _mutate_top_level(document[key])
    with pytest.raises(ProtocolV11DraftError):
        load_protocol_v11(_write_document(tmp_path, document))


def test_frozen_loader_rejects_the_unassigned_sentinel(tmp_path: Path) -> None:
    document = _load_document()
    document["frozen_semantic_sha256"] = V11_UNASSIGNED_HASH
    with pytest.raises(ProtocolV11DraftError):
        load_protocol_v11(_write_document(tmp_path, document))


def test_frozen_loader_rejects_a_wrong_but_well_formed_digest(tmp_path: Path) -> None:
    document = _load_document()
    document["frozen_semantic_sha256"] = "a" * 64
    with pytest.raises(ProtocolV11DraftError):
        load_protocol_v11(_write_document(tmp_path, document))


@pytest.mark.parametrize(
    ("field", "value"),
    (("protocol_status", "DRAFT_UNFROZEN_SUCCESSOR"), ("scoring_permission", "NONE_UNTIL_FROZEN")),
)
def test_frozen_loader_rejects_draft_status_or_draft_scoring_permission(
    tmp_path: Path, field: str, value: str
) -> None:
    document = _load_document()
    document[field] = value
    with pytest.raises(ProtocolV11DraftError):
        load_protocol_v11(_write_document(tmp_path, document))


def test_frozen_loader_rejects_nested_audit_reference_digest_tampering(
    tmp_path: Path,
) -> None:
    document = _load_document()
    document["audit_references"]["a7_report"]["sha256"] = "b" * 64
    with pytest.raises(ProtocolV11DraftError):
        load_protocol_v11(_write_document(tmp_path, document))


def test_out_of_scope_key_edit_does_not_change_the_digest() -> None:
    document = _load_document()
    original = hash_scope_projection(document)
    document["frozen_semantic_sha256"] = "c" * 64
    edited = hash_scope_projection(document)
    assert canonical_semantic_json(original) == canonical_semantic_json(edited)


def test_appending_a_future_row_does_not_change_any_earlier_feature() -> None:
    base = datetime(2024, 3, 1, tzinfo=UTC)
    rows = [(base + timedelta(hours=i), f"v{i}") for i in range(4)]
    for offset in range(1, 5):
        prediction_ts = base + timedelta(hours=offset)
        before = _resolve_strictly_before(rows, prediction_ts)
        future = rows + [(prediction_ts + timedelta(minutes=1), "future")]
        assert _resolve_strictly_before(future, prediction_ts) == before


def test_backward_as_of_join_never_selects_an_equal_or_later_eligibility_ts() -> None:
    prediction_ts = datetime(2024, 3, 1, tzinfo=UTC)
    rows = [
        (prediction_ts - timedelta(milliseconds=1), "earlier"),
        (prediction_ts, "equal"),
        (prediction_ts + timedelta(milliseconds=1), "later"),
    ]
    assert _resolve_strictly_before(rows, prediction_ts) == "earlier"


def test_forbidden_join_modes_are_closed_and_asserted() -> None:
    assert _load_document()["point_in_time"]["forbidden"] == [
        "nearest_joins",
        "forward_joins",
        "unfinished_bars",
        "future_revisions",
        "same_timestamp_equality",
    ]


@pytest.mark.parametrize(
    ("source", "event_offset", "eligibility_offset", "after_boundary"),
    (
        ("kline", timedelta(milliseconds=-1), timedelta(milliseconds=1), False),
        ("funding", timedelta(0), timedelta(milliseconds=1), True),
        ("oi", timedelta(minutes=-5), timedelta(minutes=5), False),
        ("kraken", timedelta(hours=-1), timedelta(hours=1), False),
    ),
)
def test_every_source_boundary_offset_is_arithmetically_correct(
    source: str,
    event_offset: timedelta,
    eligibility_offset: timedelta,
    after_boundary: bool,
) -> None:
    boundary = datetime(2024, 3, 1, tzinfo=UTC)
    prediction_ts = boundary + timedelta(milliseconds=2)
    eligibility_ts = boundary + event_offset + eligibility_offset
    assert eligibility_ts < prediction_ts, source
    assert (eligibility_ts > boundary) is after_boundary


def test_funding_same_boundary_is_eligible_and_others_are_already_eligible() -> None:
    boundary = datetime(2024, 3, 1, tzinfo=UTC)
    funding = boundary + timedelta(milliseconds=1)
    others = [boundary, boundary, boundary]
    assert funding > boundary
    assert all(value <= boundary for value in others)
    assert funding < boundary + timedelta(milliseconds=2)


def test_v1_gate_artifact_cannot_authorize_v11_and_v11_artifact_cannot_authorize_v1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(V1_HMAC_ENV, SYNTHETIC_KEY_HEX)
    monkeypatch.setenv(V11_HMAC_ENV, SYNTHETIC_KEY_HEX)
    criteria = {str(index): True for index in range(1, 8)}
    with pytest.raises(ProtocolV11GuardError):
        guard_protocol_v11_operation(
            EXPECTED_V11_SEMANTIC_SHA256,
            "score_2025",
            gate_result_artifact=_artifact(
                V1_ARTIFACT_TYPE, EXPECTED_V11_SEMANTIC_SHA256, criteria
            ),
        )
    with pytest.raises(ProtocolGuardError):
        guard_protocol_operation(
            FROZEN_SEMANTIC_SHA256,
            "score_2025",
            gate_result_artifact=_artifact(
                V11_ARTIFACT_TYPE, FROZEN_SEMANTIC_SHA256, criteria
            ),
        )


def test_pre_gate_operations_match_the_document_and_reject_artifacts() -> None:
    operations = _load_document()["sealed_2025"]["allowed_pre_gate_checks"]
    assert operations == [
        "file_inventory",
        "cryptographic_hashes",
        "parser_compatibility",
        "expected_boundaries",
        "mechanical_corruption",
    ]
    for operation in operations:
        assert guard_protocol_v11_operation(
            EXPECTED_V11_SEMANTIC_SHA256, operation
        ) is None
        with pytest.raises(ProtocolV11GuardError):
            guard_protocol_v11_operation(
                EXPECTED_V11_SEMANTIC_SHA256,
                operation,
                gate_result_artifact=b"credential",
            )


def test_score_2025_requires_a_valid_hmac_artifact_and_seven_true_criteria(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(V11_HMAC_ENV, SYNTHETIC_KEY_HEX)
    criteria = {str(index): True for index in range(1, 8)}
    artifact = _artifact(V11_ARTIFACT_TYPE, EXPECTED_V11_SEMANTIC_SHA256, criteria)
    assert guard_protocol_v11_operation(
        EXPECTED_V11_SEMANTIC_SHA256,
        "score_2025",
        gate_result_artifact=artifact,
    ) is None


def test_score_2025_rejects_five_criteria_wrong_type_bad_mac_and_missing_env_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seven = {str(index): True for index in range(1, 8)}
    monkeypatch.setenv(V11_HMAC_ENV, SYNTHETIC_KEY_HEX)
    bad_artifacts = [
        _artifact(
            V11_ARTIFACT_TYPE,
            EXPECTED_V11_SEMANTIC_SHA256,
            {str(index): True for index in range(1, 6)},
        ),
        _artifact(
            V11_ARTIFACT_TYPE,
            EXPECTED_V11_SEMANTIC_SHA256,
            {**seven, "7": 1},
        ),
        _artifact(V11_ARTIFACT_TYPE, EXPECTED_V11_SEMANTIC_SHA256, seven)[:-1]
        + b"0",
    ]
    for artifact in bad_artifacts:
        with pytest.raises(ProtocolV11GuardError):
            guard_protocol_v11_operation(
                EXPECTED_V11_SEMANTIC_SHA256,
                "score_2025",
                gate_result_artifact=artifact,
            )
    monkeypatch.delenv(V11_HMAC_ENV)
    with pytest.raises(ProtocolV11GuardError, match=V11_HMAC_ENV):
        guard_protocol_v11_operation(
            EXPECTED_V11_SEMANTIC_SHA256,
            "score_2025",
            gate_result_artifact=_artifact(
                V11_ARTIFACT_TYPE, EXPECTED_V11_SEMANTIC_SHA256, seven
            ),
        )


def test_the_three_previously_untested_labels_are_pinned() -> None:
    document = _load_document()
    assert document["target"]["quantile"]["fixture_status"] == (
        "REQUIRED_BEFORE_2022_2024_SCORING"
    )
    assert document["target"]["quantile"]["fixture_owner_packet"] == "STAGE_2"
    assert document["validation"]["bootstrap"]["monte_carlo_justification"][
        "holm_threshold_context"
    ] == "IMPLEMENTED_PACKET_C3"


def test_quantile_holds_thirteen_keys_with_ten_method_keys_byte_identical() -> None:
    current = _load_document()["target"]["quantile"]
    parent = _parent_document()["target"]["quantile"]
    method_keys = (
        "ordering",
        "rank",
        "selection",
        "label",
        "decimal_precision",
        "decimal_rounding",
        "interpolation",
        "threshold_rounding",
        "canonical_threshold_representation",
        "tie_break",
    )
    assert len(current) == 13
    for key in method_keys:
        assert current[key] == parent[key]


def test_top_level_counts_and_scope_clause_remain_48_of_49() -> None:
    document = _load_document()
    scope = document["semantic_hash_scope"]
    assert len(document) == V11_TOTAL_KEY_COUNT == 49
    assert V11_HASH_EXCLUDED_KEYS == ("frozen_semantic_sha256",)
    assert len(hash_scope_projection(document)) == V11_IN_SCOPE_KEY_COUNT == 48
    assert scope["total_key_count"] == len(document)
    assert scope["in_scope_key_count"] == len(document) - len(V11_HASH_EXCLUDED_KEYS)


def test_sealed_2025_is_byte_identical_to_the_parent_commit() -> None:
    assert canonical_semantic_json(_load_document()["sealed_2025"]) == (
        canonical_semantic_json(_parent_document()["sealed_2025"])
    )
    assert _load_document()["sealed_2025"]["scoring_permission"] == (
        "FORBIDDEN_UNTIL_GATE_PASS_AND_PROTOCOL_FREEZE"
    )


def test_deferred_change_set_is_complete_with_c5_implemented() -> None:
    deferred = _load_document()["deferred_change_set"]
    assert set(deferred) == {"C2", "C3", "C4", "C5a", "C5"}
    assert deferred["C5"] == {"owner_packet": "C5", "status": "IMPLEMENTED_PACKET_C5"}


def test_exclusions_and_standing_rejections_survive_the_freeze() -> None:
    document = _load_document()
    assert set(document["exclusions"]) == {"forbidden_families", "rules"}
    assert document["standing_rejections"] == {
        "signed_return_replacement": "REJECTED",
        "sigma_denominator_floor": "REJECTED",
        "arbitrary_98_percent_coverage_cutoff": "REJECTED",
        "new_feature_search": "REJECTED",
    }


def test_fixture_inherits_exactly_the_sixteen_frozen_v1_values() -> None:
    v1 = _load_json(V1_FIXTURE_PATH)["expected_semantic"]
    v11 = _load_json(V11_FIXTURE_PATH)["expected_semantic"]
    assert isinstance(v1, dict) and isinstance(v11, dict)
    assert len(INHERITED_KEYS) == 16
    for key in INHERITED_KEYS:
        assert v11[key] == v1[key]


def test_replication_seeds_are_derived_by_the_frozen_c2_rule() -> None:
    seeds = _load_document()["replication_gate_2025"]["comparison_id"]["seeds_2025"]
    for model in ("M2", "M2K", "M3", "M4"):
        comparison_id = f"REPLICATION_2025|{model}_vs_B2"
        payload = f"quantara-protocol-v1_1|bootstrap-b4|{comparison_id}|2025"
        derived = int.from_bytes(
            hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big"
        )
        assert seeds[model] == derived


def test_audit_reference_digests_match_normalized_live_files() -> None:
    references = _load_document()["audit_references"]
    assert set(references) == set(AUDIT_DIGESTS)
    for name, expected in AUDIT_DIGESTS.items():
        assert references[name]["sha256"] == expected
        assert _normalized_sha256(REPO_ROOT / references[name]["path"]) == expected


def test_post_edit_spec_digest_is_pinned() -> None:
    assert EXPECTED_V11_SPEC_SHA256 != PRE_EDIT_V11_SPEC_SHA256
    assert _normalized_sha256(V11_SPEC_PATH) == EXPECTED_V11_SPEC_SHA256


def test_no_dependency_network_or_sealed_data_access_is_added() -> None:
    source = V11_MODULE_PATH.read_text(encoding="utf-8")
    assert "numpy" not in source
    assert "requests" not in source
    assert "urllib" not in source
    assert "configs/datasets" not in source
    assert "glob(" not in source
    assert SYNTHETIC_KEY_HEX not in source
    assert V1_HMAC_ENV not in source
    assert V11_HMAC_ENV in source
    assert os.environ.get("__QUANTARA_TEST_SENTINEL__") is None
