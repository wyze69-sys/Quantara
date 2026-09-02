from __future__ import annotations

import copy
import inspect
import re
from pathlib import Path

import pytest
import yaml

from quantara.bootstrap_b4 import nominal_hours
from quantara.protocol import FROZEN_SEMANTIC_SHA256, ProtocolValidationError, load_protocol
from quantara.protocol_v11 import (
    EXCLUSION_REASONS,
    V11_FROZEN_SEMANTIC_SHA256,
    V11_FROZEN_STATUS,
    V11_HASH_EXCLUDED_KEYS,
    V11_IN_SCOPE_KEY_COUNT,
    V11_TOTAL_KEY_COUNT,
    ProtocolV11DraftError,
    ProtocolV11GuardError,
    coverage_report,
    guard_protocol_v11_operation,
    hash_scope_projection,
    load_protocol_v11,
    longest_missing_run,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
V1_YAML_PATH = REPO_ROOT / "configs/protocols/quantara-protocol-v1.yaml"
V11_YAML_PATH = REPO_ROOT / "configs/protocols/quantara-protocol-v1_1.yaml"
MODULE_PATH = REPO_ROOT / "src/quantara/protocol_v11.py"
HEX_64_RE = re.compile(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")

EXPECTED_EXCLUSION_REASONS = (
    "missing_native_interval",
    "incomplete_feature_window",
    "funding_cadence_incomplete",
    "oi_snapshot_gap",
    "invalid_label_endpoint",
    "buffer_bar_missing",
    "pre_archive_period",
    "eth_oi_pre_2021_12_01",
    "same_key_conflict",
)


def _load_v11_document() -> dict[str, object]:
    document = yaml.safe_load(V11_YAML_PATH.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _write_document(tmp_path: Path, document: dict[str, object]) -> Path:
    path = tmp_path / "protocol-v1_1.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _reasons_for(flags: list[bool], reason: str = "missing_native_interval") -> list[str | None]:
    return [None if eligible else reason for eligible in flags]


def test_hash_scope_is_self_checking_against_post_edit_document() -> None:
    document = _load_v11_document()
    scope = document["semantic_hash_scope"]

    assert len(document) == 49 == V11_TOTAL_KEY_COUNT
    assert V11_HASH_EXCLUDED_KEYS == ("frozen_semantic_sha256",)
    assert len(document) - len(V11_HASH_EXCLUDED_KEYS) == 48 == V11_IN_SCOPE_KEY_COUNT
    assert scope["excluded_keys"] == list(V11_HASH_EXCLUDED_KEYS)
    assert scope["total_key_count"] == len(document)
    assert scope["in_scope_key_count"] == len(document) - len(V11_HASH_EXCLUDED_KEYS)


def test_hash_scope_projection_omits_only_own_hash_and_preserves_every_other_value() -> None:
    document = _load_v11_document()
    projected = hash_scope_projection(document)

    assert set(document) - set(projected) == set(V11_HASH_EXCLUDED_KEYS)
    assert set(projected) == set(document) - set(V11_HASH_EXCLUDED_KEYS)
    for key, value in projected.items():
        assert value == document[key]


def test_canonical_projection_is_independent_of_top_level_yaml_order(tmp_path: Path) -> None:
    document = _load_v11_document()
    reversed_document = dict(reversed(tuple(document.items())))
    reordered_path = _write_document(tmp_path, reversed_document)

    original = load_protocol_v11(V11_YAML_PATH)
    reordered = load_protocol_v11(reordered_path)
    assert original.canonical_projection_json == reordered.canonical_projection_json


def test_frozen_loader_exposes_exactly_the_frozen_digest_literal() -> None:
    import quantara.protocol_v11 as module

    protocol = load_protocol_v11(V11_YAML_PATH)
    assert protocol.semantic_sha256 == V11_FROZEN_SEMANTIC_SHA256
    assert V11_FROZEN_SEMANTIC_SHA256 in MODULE_PATH.read_text(encoding="utf-8")
    digest_literals = {
        value
        for value in vars(module).values()
        if isinstance(value, str) and HEX_64_RE.fullmatch(value)
    }
    assert digest_literals == {V11_FROZEN_SEMANTIC_SHA256}


def test_to_dict_returns_a_detached_copy_of_the_validated_document() -> None:
    protocol = load_protocol_v11(V11_YAML_PATH)
    first = protocol.to_dict()
    first["protocol_status"] = "MUTATED_BY_CALLER"

    assert protocol.to_dict()["protocol_status"] == V11_FROZEN_STATUS


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("frozen_semantic_sha256", "a" * 64),
        ("protocol_status", "FROZEN"),
        ("scoring_permission", "ALLOWED"),
    ),
)
def test_frozen_state_tampering_is_rejected(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    document = _load_v11_document()
    document[field] = value

    with pytest.raises(ProtocolV11DraftError):
        load_protocol_v11(_write_document(tmp_path, document))


def test_duplicate_top_level_key_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate-top.yaml"
    path.write_text(
        V11_YAML_PATH.read_text(encoding="utf-8") + "\nprotocol_id: duplicate\n",
        encoding="utf-8",
    )
    with pytest.raises(ProtocolV11DraftError, match="duplicate mapping key"):
        load_protocol_v11(path)


def test_duplicate_nested_key_is_rejected(tmp_path: Path) -> None:
    text = V11_YAML_PATH.read_text(encoding="utf-8")
    needle = "semantic_hash_scope:\n"
    path = tmp_path / "duplicate-nested.yaml"
    path.write_text(
        text.replace(needle, needle + "  basis: duplicate\n", 1),
        encoding="utf-8",
    )
    with pytest.raises(ProtocolV11DraftError, match="duplicate mapping key"):
        load_protocol_v11(path)


def test_float_and_non_string_mapping_key_are_rejected(tmp_path: Path) -> None:
    float_path = tmp_path / "float.yaml"
    float_path.write_text(
        V11_YAML_PATH.read_text(encoding="utf-8") + "\nextra_float: 1.5\n",
        encoding="utf-8",
    )
    with pytest.raises(ProtocolV11DraftError, match="float is forbidden"):
        load_protocol_v11(float_path)

    key_path = tmp_path / "non-string-key.yaml"
    key_path.write_text(
        V11_YAML_PATH.read_text(encoding="utf-8") + "\n1: invalid-key\n",
        encoding="utf-8",
    )
    with pytest.raises(ProtocolV11DraftError, match="mapping key must be a string"):
        load_protocol_v11(key_path)


def test_duplicate_series_and_ladder_feature_are_rejected(tmp_path: Path) -> None:
    document = _load_v11_document()
    duplicate_series = copy.deepcopy(document)
    duplicate_series["inventory"].append(copy.deepcopy(duplicate_series["inventory"][0]))
    with pytest.raises(ProtocolV11DraftError, match="duplicate inventory series_id"):
        load_protocol_v11(_write_document(tmp_path, duplicate_series))

    duplicate_feature = copy.deepcopy(document)
    additions = duplicate_feature["model_ladder"]["M2"]["adds"]
    additions.append(additions[0])
    with pytest.raises(ProtocolV11DraftError, match="duplicate feature name"):
        load_protocol_v11(_write_document(tmp_path, duplicate_feature))


def test_frozen_guard_allows_pre_gate_checks_and_refuses_uncredentialed_scoring() -> None:
    for operation in (
        "file_inventory",
        "cryptographic_hashes",
        "parser_compatibility",
        "expected_boundaries",
        "mechanical_corruption",
    ):
        assert guard_protocol_v11_operation(
            V11_FROZEN_SEMANTIC_SHA256, operation
        ) is None
    with pytest.raises(ProtocolV11GuardError):
        guard_protocol_v11_operation(V11_FROZEN_SEMANTIC_SHA256, "score_2025")
    with pytest.raises(ProtocolV11GuardError):
        guard_protocol_v11_operation(V11_FROZEN_SEMANTIC_SHA256, "unknown_operation")


def test_v1_loader_remains_isolated_from_v11() -> None:
    with pytest.raises(ProtocolValidationError):
        load_protocol(V11_YAML_PATH)
    assert load_protocol(V1_YAML_PATH).semantic_sha256 == FROZEN_SEMANTIC_SHA256


@pytest.mark.parametrize(
    ("flags", "expected"),
    (
        ([True, True, True], 0),
        ([False, False, False], 3),
        ([False, False, True, True], 2),
        ([True, True, False, False], 2),
        ([True, False, False, False, True], 3),
        ([False, False, True, False, False], 2),
    ),
)
def test_longest_missing_run_edges(flags: list[bool], expected: int) -> None:
    assert longest_missing_run(flags) == expected


def test_coverage_grid_length_and_boolean_input_are_fail_closed() -> None:
    with pytest.raises(ValueError, match="nominal_hours"):
        coverage_report({2024: [True] * 8760})
    assert nominal_hours(2024) == 8784
    invalid = [True] * nominal_hours(2023)
    invalid[-1] = 1.0
    with pytest.raises((TypeError, ValueError), match="float|boolean"):
        coverage_report({2023: invalid})


def test_coverage_exact_percentages_and_zero_exclusion_case() -> None:
    full = [True] * nominal_hours(2023)
    report = coverage_report({2023: full})
    year = report.per_year[2023]

    assert year.candidate_eligible_rows == 8760
    assert year.candidate_eligible_percentage == "100.000000000000000000"
    assert year.exclusion_reasons == {reason: 0 for reason in EXCLUSION_REASONS}
    assert year.longest_missing_run == 0
    assert report.pooled == year

    partial = [True] * 8737 + [False] * 23
    partial_report = coverage_report(
        {2023: partial},
        exclusions_by_year={2023: _reasons_for(partial)},
    )
    assert partial_report.per_year[2023].candidate_eligible_percentage == (
        "99.737442922374429224"
    )


def test_coverage_all_ineligible_counts_and_run_length() -> None:
    flags = [False] * nominal_hours(2023)
    report = coverage_report(
        {2023: flags},
        exclusions_by_year={2023: _reasons_for(flags, "invalid_label_endpoint")},
    )
    year = report.per_year[2023]
    assert year.candidate_eligible_rows == 0
    assert year.candidate_eligible_percentage == "0.000000000000000000"
    assert year.exclusion_reasons["invalid_label_endpoint"] == 8760
    assert sum(year.exclusion_reasons.values()) == 8760
    assert year.longest_missing_run == 8760


def test_pooled_coverage_uses_pooled_counts_and_never_spans_year_boundary() -> None:
    first = [True] * nominal_hours(2023)
    first[-2:] = [False, False]
    second = [True] * nominal_hours(2024)
    second[:3] = [False, False, False]
    report = coverage_report(
        {2023: first, 2024: second},
        exclusions_by_year={
            2023: _reasons_for(first),
            2024: _reasons_for(second),
        },
    )

    assert report.pooled.candidate_eligible_rows == 8760 + 8784 - 5
    assert report.pooled.candidate_eligible_percentage not in {
        report.per_year[2023].candidate_eligible_percentage,
        report.per_year[2024].candidate_eligible_percentage,
    }
    assert report.pooled.longest_missing_run == 3
    assert sum(report.pooled.exclusion_reasons.values()) == 5


def test_exclusions_must_be_closed_complete_and_non_float() -> None:
    flags = [True] * nominal_hours(2023)
    flags[0] = False
    with pytest.raises(ValueError, match="unknown exclusion reason"):
        coverage_report(
            {2023: flags},
            exclusions_by_year={2023: ["unknown_reason"] + [None] * (len(flags) - 1)},
        )
    with pytest.raises(ValueError, match="requires exactly one exclusion reason"):
        coverage_report({2023: flags})
    with pytest.raises((TypeError, ValueError), match="float|string"):
        coverage_report(
            {2023: flags},
            exclusions_by_year={2023: [1.0] + [None] * (len(flags) - 1)},
        )


def test_exclusion_vocabulary_is_exact_ordered_and_traceable() -> None:
    document = _load_v11_document()
    entries = document["exclusion_reason_vocabulary"]["reasons"]
    assert EXCLUSION_REASONS == EXPECTED_EXCLUSION_REASONS
    assert tuple(entry["reason"] for entry in entries) == EXCLUSION_REASONS
    for entry in entries:
        assert entry["source_clause"].split(".", 1)[0] in document


def test_loader_and_coverage_module_are_pure_and_use_only_synthetic_grids() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "configs/datasets" not in source
    assert "glob(" not in source
    assert "numpy" not in source
    assert "urllib" not in source
    assert "requests" not in source
    assert inspect.isfunction(coverage_report)
