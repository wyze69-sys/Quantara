"""Adversarial freeze and sealed-2025 guard tests for Protocol v1."""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from quantara.protocol import (
    FROZEN_SEMANTIC_SHA256,
    ProtocolGuardError,
    ProtocolValidationError,
    guard_protocol_operation,
    load_protocol,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = REPO_ROOT / "configs" / "protocols" / "quantara-protocol-v1.yaml"
AUTHENTICATION_KEY = bytes(range(32))
ALL_CRITERIA = {str(index): True for index in range(1, 8)}


@pytest.fixture(scope="module")
def frozen_document() -> dict[str, object]:
    value = yaml.safe_load(PROTOCOL_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _at_path(value: object, path: tuple[object, ...]) -> object:
    current = value
    for component in path:
        current = current[component]  # type: ignore[index]
    return current


def _write_yaml(tmp_path: Path, value: object) -> Path:
    path = tmp_path / "mutated-protocol.yaml"
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    return path


def _guarded_data_access(protocol_path: Path, access_data: Callable[[], None]) -> None:
    protocol = load_protocol(protocol_path)
    guard_protocol_operation(protocol.semantic_sha256, "file_inventory")
    access_data()


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("target", "threshold"), "k = empirical Q75(Z_t)"),
        (("optional_family_retention", "order", 0), "liquidations_block"),
        (("inventory", 7, "venue"), "coinbase"),
        (("validation", "outer_folds", 1, "train_end"), "2022-12-30"),
        (("validation", "bootstrap", "resamples"), 1999),
        (("success_gate", "criteria", 0, "threshold"), "0.01"),
        (("model_mandates", "m3b_role"), "ETH OI may alter the retained candidate"),
        (
            ("dislocation_roles", "primary_futures_dislocation_feature"),
            "btc_mark_price_1m",
        ),
        (("sealed_2025", "state"), "OPEN"),
    ],
    ids=[
        "target-threshold",
        "feature-family",
        "venue",
        "fold-date",
        "bootstrap-size",
        "success-gate",
        "eth-oi-role",
        "native-premium-role",
        "2025-state",
    ],
)
def test_scientific_mutations_fail_before_data_access(
    tmp_path: Path,
    frozen_document: dict[str, object],
    path: tuple[object, ...],
    replacement: object,
) -> None:
    mutated = copy.deepcopy(frozen_document)
    parent = _at_path(mutated, path[:-1])
    parent[path[-1]] = replacement  # type: ignore[index]
    accesses: list[str] = []

    with pytest.raises(ProtocolValidationError, match="frozen Protocol v1"):
        _guarded_data_access(_write_yaml(tmp_path, mutated), lambda: accesses.append("read"))

    assert accesses == []


def _signed_artifact(
    *,
    protocol_hash: str = FROZEN_SEMANTIC_SHA256,
    operation: str = "score_2025",
    criteria: object = ALL_CRITERIA,
    key: bytes = AUTHENTICATION_KEY,
) -> bytes:
    payload = {
        "artifact_type": "quantara-protocol-v1-gate-result",
        "schema_version": 1,
        "protocol_sha256": protocol_hash,
        "operation": operation,
        "criteria": criteria,
    }
    canonical_payload = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    mac = hmac.new(key, canonical_payload, hashlib.sha256).hexdigest()
    return json.dumps(
        {"payload": payload, "mac": mac},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


@pytest.mark.parametrize(
    "operation",
    [
        "file_inventory",
        "cryptographic_hashes",
        "parser_compatibility",
        "expected_boundaries",
        "mechanical_corruption",
    ],
)
def test_pre_gate_operations_are_allowed_for_frozen_hash(operation: str) -> None:
    guard_protocol_operation(FROZEN_SEMANTIC_SHA256, operation)


def test_score_2025_requires_authenticated_hash_bound_all_pass_artifact() -> None:
    guard_protocol_operation(
        FROZEN_SEMANTIC_SHA256,
        "score_2025",
        gate_result_artifact=_signed_artifact(),
        authentication_key=AUTHENTICATION_KEY,
    )


@pytest.mark.parametrize(
    ("protocol_hash", "operation"),
    [
        ("0" * 64, "file_inventory"),
        (FROZEN_SEMANTIC_SHA256[:-1], "file_inventory"),
        (FROZEN_SEMANTIC_SHA256, "labels"),
        (FROZEN_SEMANTIC_SHA256, "model_scores"),
        (FROZEN_SEMANTIC_SHA256, "unknown_operation"),
        (FROZEN_SEMANTIC_SHA256, 2025),
    ],
)
def test_wrong_hash_malformed_types_and_unsupported_operations_are_rejected(
    protocol_hash: object, operation: object
) -> None:
    with pytest.raises(ProtocolGuardError):
        guard_protocol_operation(protocol_hash, operation)  # type: ignore[arg-type]


def test_score_2025_fails_closed_without_external_authentication_material() -> None:
    artifact = _signed_artifact()
    for kwargs in (
        {},
        {"gate_result_artifact": artifact},
        {"authentication_key": AUTHENTICATION_KEY},
    ):
        with pytest.raises(ProtocolGuardError):
            guard_protocol_operation(
                FROZEN_SEMANTIC_SHA256, "score_2025", **kwargs  # type: ignore[arg-type]
            )


@pytest.mark.parametrize(
    "criteria",
    [
        {str(index): True for index in range(1, 7)},
        {**ALL_CRITERIA, "8": True},
        {**ALL_CRITERIA, "2": False},
        {**ALL_CRITERIA, "2": 1},
        [True] * 7,
    ],
    ids=["missing", "unknown", "false", "non-boolean", "wrong-type"],
)
def test_score_2025_rejects_incomplete_or_nonpassing_criteria(criteria: object) -> None:
    with pytest.raises(ProtocolGuardError):
        guard_protocol_operation(
            FROZEN_SEMANTIC_SHA256,
            "score_2025",
            gate_result_artifact=_signed_artifact(criteria=criteria),
            authentication_key=AUTHENTICATION_KEY,
        )


@pytest.mark.parametrize(
    "artifact",
    [
        b"not json",
        b"[]",
        b'{"payload":{},"mac":"00","unknown":true}',
        b'{"payload":{},"payload":{},"mac":"00"}',
        b'{"payload":{},"mac":7}',
    ],
    ids=["invalid-json", "wrong-root", "unknown-key", "duplicate-key", "wrong-mac-type"],
)
def test_malformed_artifacts_are_rejected(artifact: bytes) -> None:
    with pytest.raises(ProtocolGuardError):
        guard_protocol_operation(
            FROZEN_SEMANTIC_SHA256,
            "score_2025",
            gate_result_artifact=artifact,
            authentication_key=AUTHENTICATION_KEY,
        )


def test_unknown_payload_keys_are_rejected() -> None:
    envelope = json.loads(_signed_artifact())
    envelope["payload"]["self_authenticating_key"] = AUTHENTICATION_KEY.hex()
    artifact = json.dumps(envelope, separators=(",", ":")).encode("utf-8")

    with pytest.raises(ProtocolGuardError):
        guard_protocol_operation(
            FROZEN_SEMANTIC_SHA256,
            "score_2025",
            gate_result_artifact=artifact,
            authentication_key=AUTHENTICATION_KEY,
        )


@pytest.mark.parametrize(
    "artifact",
    [
        _signed_artifact(protocol_hash="0" * 64),
        _signed_artifact(operation="file_inventory"),
    ],
    ids=["stale-protocol-hash", "wrong-operation"],
)
def test_artifact_is_bound_to_frozen_hash_and_score_operation(artifact: bytes) -> None:
    with pytest.raises(ProtocolGuardError):
        guard_protocol_operation(
            FROZEN_SEMANTIC_SHA256,
            "score_2025",
            gate_result_artifact=artifact,
            authentication_key=AUTHENTICATION_KEY,
        )


def test_invalid_mac_and_artifact_supplied_key_cannot_authenticate() -> None:
    forged_key = b"x" * 32
    forged_artifact = _signed_artifact(key=forged_key)

    with pytest.raises(ProtocolGuardError):
        guard_protocol_operation(
            FROZEN_SEMANTIC_SHA256,
            "score_2025",
            gate_result_artifact=forged_artifact,
            authentication_key=AUTHENTICATION_KEY,
        )


def test_artifact_must_be_immutable_bytes_snapshot_not_a_path(tmp_path: Path) -> None:
    path = tmp_path / "gate-result.json"
    path.write_bytes(_signed_artifact())

    for ambiguous_input in (path, str(path), bytearray(path.read_bytes())):
        with pytest.raises(ProtocolGuardError, match="immutable bytes snapshot"):
            guard_protocol_operation(
                FROZEN_SEMANTIC_SHA256,
                "score_2025",
                gate_result_artifact=ambiguous_input,  # type: ignore[arg-type]
                authentication_key=AUTHENTICATION_KEY,
            )


@pytest.mark.parametrize("key", [b"short", bytearray(AUTHENTICATION_KEY), "secret"])
def test_authentication_key_must_be_external_strong_immutable_bytes(key: object) -> None:
    with pytest.raises(ProtocolGuardError):
        guard_protocol_operation(
            FROZEN_SEMANTIC_SHA256,
            "score_2025",
            gate_result_artifact=_signed_artifact(),
            authentication_key=key,  # type: ignore[arg-type]
        )
