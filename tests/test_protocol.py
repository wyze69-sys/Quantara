"""Tests for the fail-closed Protocol-v1 loader and semantic hash."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from quantara.protocol import (
    FROZEN_SEMANTIC_SHA256,
    ProtocolValidationError,
    canonical_semantic_json,
    load_protocol,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = REPO_ROOT / "configs" / "protocols" / "quantara-protocol-v1.yaml"
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "protocol_v1_expected.json"
EXPECTED_HASH = "91457d3f1497abfd4e20cf4624768a5d9e9ba4b4478008fb4c7f65c17d90c65a"


@pytest.fixture(scope="module")
def frozen_document() -> dict[str, object]:
    value = yaml.safe_load(PROTOCOL_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_yaml(tmp_path: Path, value: object, *, sort_keys: bool = False) -> Path:
    path = tmp_path / "protocol.yaml"
    path.write_text(yaml.safe_dump(value, sort_keys=sort_keys), encoding="utf-8")
    return path


def _mapping_paths(value: object, path: tuple[object, ...] = ()) -> list[tuple[object, ...]]:
    paths: list[tuple[object, ...]] = []
    if isinstance(value, dict):
        paths.append(path)
        for key, child in value.items():
            paths.extend(_mapping_paths(child, (*path, key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            paths.extend(_mapping_paths(child, (*path, index)))
    return paths


def _at_path(value: object, path: tuple[object, ...]) -> object:
    current = value
    for component in path:
        current = current[component]  # type: ignore[index]
    return current


def test_loads_frozen_protocol_and_matches_independent_hash() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    protocol = load_protocol(PROTOCOL_PATH)

    assert FROZEN_SEMANTIC_SHA256 == EXPECTED_HASH
    assert protocol.semantic_sha256 == EXPECTED_HASH
    assert protocol.semantic_sha256 == fixture["semantic_sha256"]
    assert protocol.to_dict() == fixture["expected_semantic"]
    assert json.loads(protocol.canonical_json) == fixture["expected_semantic"]


def test_yaml_key_order_and_formatting_do_not_change_hash(
    tmp_path: Path, frozen_document: dict[str, object]
) -> None:
    reordered = dict(reversed(list(frozen_document.items())))
    path = tmp_path / "reformatted.yaml"
    path.write_text(
        "# formatting and mapping order are not semantic\n"
        + yaml.safe_dump(reordered, sort_keys=True, width=60),
        encoding="utf-8",
    )

    assert path.read_bytes() != PROTOCOL_PATH.read_bytes()
    assert load_protocol(path).semantic_sha256 == EXPECTED_HASH


def test_unknown_keys_are_rejected_at_every_mapping_level(
    tmp_path: Path, frozen_document: dict[str, object]
) -> None:
    paths = _mapping_paths(frozen_document)
    assert len(paths) > 20

    for index, mapping_path in enumerate(paths):
        mutated = copy.deepcopy(frozen_document)
        mapping = _at_path(mutated, mapping_path)
        assert isinstance(mapping, dict)
        mapping[f"unknown_key_{index}"] = "not frozen"
        with pytest.raises(ProtocolValidationError, match="frozen Protocol v1"):
            load_protocol(_write_yaml(tmp_path, mutated))


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("inventory", 0, "series_id"), "unfrozen_series"),
        (("target", "r24"), "different formula"),
        (("feature_formulas", "funding_24h_sum"), "different formula"),
        (("validation", "outer_folds", 0, "train_end"), "2021-12-30"),
        (("validation", "primary_metric", 0), "different metric"),
        (("success_gate", "criteria", 0, "threshold"), "0.03"),
        (("optional_family_retention", "order", 0), "unfrozen_family"),
        (("validation", "bootstrap", "rng_seed"), 7),
        (("sealed_2025", "state"), "OPEN"),
        (("logistic_constants", "max_iterations"), 51),
    ],
)
def test_every_frozen_scientific_choice_is_exact(
    tmp_path: Path,
    frozen_document: dict[str, object],
    path: tuple[object, ...],
    replacement: object,
) -> None:
    mutated = copy.deepcopy(frozen_document)
    parent = _at_path(mutated, path[:-1])
    parent[path[-1]] = replacement  # type: ignore[index]

    with pytest.raises(ProtocolValidationError, match="frozen Protocol v1"):
        load_protocol(_write_yaml(tmp_path, mutated))


def test_duplicate_feature_names_are_rejected(
    tmp_path: Path, frozen_document: dict[str, object]
) -> None:
    mutated = copy.deepcopy(frozen_document)
    adds = mutated["model_ladder"]["M1"]["adds"]  # type: ignore[index]
    adds.append(adds[0])

    with pytest.raises(ProtocolValidationError, match="duplicate feature name"):
        load_protocol(_write_yaml(tmp_path, mutated))


def test_duplicate_yaml_mapping_keys_are_rejected(tmp_path: Path) -> None:
    text = PROTOCOL_PATH.read_text(encoding="utf-8")
    text = text.replace(
        "feature_formulas:\n",
        "feature_formulas:\n  funding_24h_sum: duplicate\n",
        1,
    )
    path = tmp_path / "duplicate-key.yaml"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ProtocolValidationError, match="duplicate mapping key"):
        load_protocol(path)


def test_floats_are_rejected_from_hash_semantics(
    tmp_path: Path, frozen_document: dict[str, object]
) -> None:
    mutated = copy.deepcopy(frozen_document)
    mutated["success_gate"]["criteria"][0]["threshold"] = 0.02  # type: ignore[index]

    with pytest.raises(ProtocolValidationError, match="float"):
        load_protocol(_write_yaml(tmp_path, mutated))
    with pytest.raises(ProtocolValidationError, match="float"):
        canonical_semantic_json({"threshold": 0.02})


def test_decimal_thresholds_remain_exact_strings() -> None:
    protocol = load_protocol(PROTOCOL_PATH)
    semantic = protocol.to_dict()

    constants = semantic["logistic_constants"]
    assert constants["l2_penalty_lambda"] == "1"
    assert constants["convergence_tolerance"] == "0.000000000001"
    assert constants["probability_clamp"] == "0.000000000001"
    assert semantic["validation"]["bootstrap"]["interval"] == "0.95"
    criteria = semantic["success_gate"]["criteria"]
    decimal_values = [
        value
        for criterion in criteria
        for key, value in criterion.items()
        if key in {"threshold", "lower", "upper"}
    ]
    assert decimal_values == ["0.02", "-0.02", "0.02", "0.8", "1.2", "0.04"]
    assert all(isinstance(value, str) for value in decimal_values)


def test_returned_semantics_cannot_mutate_protocol_identity() -> None:
    protocol = load_protocol(PROTOCOL_PATH)
    mutable_copy = protocol.to_dict()
    mutable_copy["sealed_2025"]["state"] = "OPEN"

    assert protocol.semantic_sha256 == EXPECTED_HASH
    assert protocol.to_dict()["sealed_2025"]["state"] == "SEALED"
