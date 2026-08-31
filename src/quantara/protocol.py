"""Fail-closed loader and semantic identity for frozen Quantara Protocol v1.

The YAML document is accepted only when its complete, canonicalized semantics
match the independently frozen Protocol-v1 SHA-256. Mapping order, comments,
and YAML formatting are intentionally outside that identity.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

FROZEN_SEMANTIC_SHA256 = "91457d3f1497abfd4e20cf4624768a5d9e9ba4b4478008fb4c7f65c17d90c65a"


class ProtocolValidationError(ValueError):
    """Raised when a document is not exactly the frozen Protocol v1."""


class ProtocolGuardError(PermissionError):
    """Raised when a protocol-bound operation is not authorized."""


_PRE_GATE_OPERATIONS = frozenset(
    {
        "file_inventory",
        "cryptographic_hashes",
        "parser_compatibility",
        "expected_boundaries",
        "mechanical_corruption",
    }
)
_GATE_ARTIFACT_KEYS = frozenset({"payload", "mac"})
_GATE_PAYLOAD_KEYS = frozenset(
    {
        "artifact_type",
        "schema_version",
        "protocol_sha256",
        "operation",
        "criteria",
    }
)
_GATE_CRITERION_IDS = frozenset(str(index) for index in range(1, 8))
_GATE_ARTIFACT_TYPE = "quantara-protocol-v1-gate-result"
_GATE_HMAC_KEY_ENV = "QUANTARA_PROTOCOL_V1_GATE_HMAC_KEY"


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """Safe YAML loader that refuses lossy duplicate mapping keys."""


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    loader.flatten_mapping(node)
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise ProtocolValidationError("unhashable YAML mapping key") from exc
        if duplicate:
            raise ProtocolValidationError(f"duplicate mapping key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _validate_hash_value(value: object, path: str = "$") -> None:
    """Allow only deterministic JSON values, explicitly excluding floats."""
    if isinstance(value, float):
        raise ProtocolValidationError(f"float is forbidden in protocol hash semantics at {path}")
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_hash_value(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ProtocolValidationError(
                    f"protocol mapping key must be a string at {path}: {key!r}"
                )
            _validate_hash_value(item, f"{path}.{key}")
        return
    raise ProtocolValidationError(
        f"unsupported value type in protocol hash semantics at {path}: {type(value).__name__}"
    )


def canonical_semantic_json(semantic: object) -> str:
    """Render deterministic JSON after enforcing Decimal-safe value types."""
    _validate_hash_value(semantic)
    return json.dumps(semantic, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def semantic_sha256(semantic: object) -> str:
    """Return the SHA-256 of canonical Protocol-v1 semantic JSON."""
    canonical = canonical_semantic_json(semantic)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Construct a JSON object while rejecting duplicate names."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolGuardError(f"duplicate gate artifact key: {key!r}")
        result[key] = value
    return result


def _canonical_gate_payload(payload: dict[str, object]) -> bytes:
    """Return the deterministic bytes covered by the external MAC key."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _load_gate_authentication_key() -> bytes:
    """Load the independent local trust root from process configuration."""
    encoded_key = os.environ.get(_GATE_HMAC_KEY_ENV)
    if encoded_key is None:
        raise ProtocolGuardError(
            f"score_2025 requires {_GATE_HMAC_KEY_ENV} to be configured"
        )
    if len(encoded_key) != 64:
        raise ProtocolGuardError(
            f"{_GATE_HMAC_KEY_ENV} must contain exactly 32 bytes as hexadecimal"
        )
    try:
        authentication_key = bytes.fromhex(encoded_key)
    except ValueError as exc:
        raise ProtocolGuardError(
            f"{_GATE_HMAC_KEY_ENV} is not valid hexadecimal"
        ) from exc
    if len(authentication_key) != 32:
        raise ProtocolGuardError(
            f"{_GATE_HMAC_KEY_ENV} must decode to exactly 32 bytes"
        )
    return authentication_key


def _verify_gate_result_artifact(
    artifact: object,
    authentication_key: object,
    protocol_hash: str,
) -> None:
    """Verify a strict, hash-bound all-pass result from immutable artifact bytes."""
    if not isinstance(artifact, bytes):
        raise ProtocolGuardError(
            "gate result must be an immutable bytes snapshot, not a path or mutable buffer"
        )
    if not isinstance(authentication_key, bytes) or len(authentication_key) < 32:
        raise ProtocolGuardError(
            "authentication key must be external immutable bytes of at least 32 bytes"
        )

    try:
        envelope = json.loads(
            artifact.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
        )
    except ProtocolGuardError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolGuardError("gate result is not canonicalizable UTF-8 JSON") from exc

    if not isinstance(envelope, dict) or set(envelope) != _GATE_ARTIFACT_KEYS:
        raise ProtocolGuardError("gate result envelope has missing or unknown keys")
    payload = envelope["payload"]
    mac_hex = envelope["mac"]
    if not isinstance(payload, dict) or set(payload) != _GATE_PAYLOAD_KEYS:
        raise ProtocolGuardError("gate result payload has missing or unknown keys")
    if not isinstance(mac_hex, str) or len(mac_hex) != 64:
        raise ProtocolGuardError("gate result MAC must be a SHA-256 hexadecimal string")
    try:
        supplied_mac = bytes.fromhex(mac_hex)
    except ValueError as exc:
        raise ProtocolGuardError("gate result MAC is not hexadecimal") from exc
    if len(supplied_mac) != hashlib.sha256().digest_size:
        raise ProtocolGuardError("gate result MAC has the wrong length")

    expected_mac = hmac.digest(
        authentication_key,
        _canonical_gate_payload(payload),
        "sha256",
    )
    if not hmac.compare_digest(expected_mac, supplied_mac):
        raise ProtocolGuardError("gate result MAC authentication failed")

    if payload["artifact_type"] != _GATE_ARTIFACT_TYPE:
        raise ProtocolGuardError("unsupported gate result artifact type")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise ProtocolGuardError("unsupported gate result schema version")
    if payload["protocol_sha256"] != protocol_hash:
        raise ProtocolGuardError("gate result is stale or bound to a different protocol")
    if payload["operation"] != "score_2025":
        raise ProtocolGuardError("gate result is not bound to score_2025")

    criteria = payload["criteria"]
    if not isinstance(criteria, dict) or set(criteria) != _GATE_CRITERION_IDS:
        raise ProtocolGuardError("gate result must contain exactly all Protocol v1 criteria")
    if any(type(value) is not bool or not value for value in criteria.values()):
        raise ProtocolGuardError("every Protocol v1 criterion must be boolean true")


def guard_protocol_operation(
    protocol_hash: str,
    operation: str,
    *,
    gate_result_artifact: bytes | None = None,
) -> None:
    """Authorize a frozen-protocol operation, failing closed before data access.

    The five inventory/integrity checks allowed while 2025 is sealed require the
    frozen semantic hash. ``score_2025`` additionally requires an immutable byte
    snapshot of a strict local gate-result artifact authenticated against a trust
    root loaded independently from process configuration. Accepting bytes rather
    than a path removes path resolution and check/use races; the key is deliberately
    absent from the artifact, function arguments, and module source.
    """
    if not isinstance(protocol_hash, str) or protocol_hash != FROZEN_SEMANTIC_SHA256:
        raise ProtocolGuardError("operation requires the frozen Protocol v1 hash")
    if not isinstance(operation, str):
        raise ProtocolGuardError("operation name must be a string")

    if operation in _PRE_GATE_OPERATIONS:
        if gate_result_artifact is not None:
            raise ProtocolGuardError("pre-gate checks do not accept gate credentials")
        return
    if operation != "score_2025":
        raise ProtocolGuardError(f"unsupported Protocol v1 operation: {operation!r}")
    if gate_result_artifact is None:
        raise ProtocolGuardError("score_2025 requires an authenticated gate result")

    _verify_gate_result_artifact(
        gate_result_artifact,
        _load_gate_authentication_key(),
        protocol_hash,
    )


def _reject_duplicate_features(document: dict[str, Any]) -> None:
    ladder = document.get("model_ladder")
    if not isinstance(ladder, dict):
        return
    for model_name, model in ladder.items():
        if not isinstance(model, dict):
            continue
        additions = model.get("adds")
        if not isinstance(additions, list):
            continue
        seen: set[object] = set()
        for feature in additions:
            try:
                duplicate = feature in seen
                seen.add(feature)
            except TypeError as exc:
                raise ProtocolValidationError(
                    f"invalid feature name in model_ladder.{model_name}.adds"
                ) from exc
            if duplicate:
                raise ProtocolValidationError(
                    f"duplicate feature name in model_ladder.{model_name}.adds: {feature!r}"
                )


def _reject_duplicate_series(document: dict[str, Any]) -> None:
    inventory = document.get("inventory")
    if not isinstance(inventory, list):
        return
    seen: set[object] = set()
    for entry in inventory:
        if not isinstance(entry, dict) or "series_id" not in entry:
            continue
        series_id = entry["series_id"]
        try:
            duplicate = series_id in seen
            seen.add(series_id)
        except TypeError as exc:
            raise ProtocolValidationError("invalid inventory series_id") from exc
        if duplicate:
            raise ProtocolValidationError(f"duplicate inventory series_id: {series_id!r}")


@dataclass(frozen=True, slots=True)
class Protocol:
    """Validated immutable identity backed by private canonical JSON bytes."""

    source: Path
    canonical_json: str
    semantic_sha256: str

    def to_dict(self) -> dict[str, Any]:
        """Return a detached copy so callers cannot mutate the validated identity."""
        value = json.loads(self.canonical_json)
        if not isinstance(value, dict):  # Defensive: construction is internal.
            raise ProtocolValidationError("validated protocol root is not a mapping")
        return value


def load_protocol(path: str | Path) -> Protocol:
    """Load *path* only if it is exactly frozen Quantara Protocol v1.

    Validation fails closed: duplicate YAML keys, floats, unsupported values,
    duplicate model features/series, unknown keys at any depth, missing keys,
    and every changed scientific parameter all prevent acceptance. The final
    digest is a stable trust anchor rather than a second editable protocol copy.
    """
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ProtocolValidationError(f"cannot read protocol as UTF-8: {source}") from exc

    try:
        document = yaml.load(text, Loader=_UniqueKeySafeLoader)
    except ProtocolValidationError:
        raise
    except yaml.YAMLError as exc:
        raise ProtocolValidationError(f"invalid protocol YAML: {source}") from exc

    if not isinstance(document, dict):
        raise ProtocolValidationError("protocol root must be a mapping")

    _validate_hash_value(document)
    _reject_duplicate_series(document)
    _reject_duplicate_features(document)
    canonical = canonical_semantic_json(document)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if digest != FROZEN_SEMANTIC_SHA256:
        raise ProtocolValidationError(
            "document does not equal frozen Protocol v1 semantics "
            f"(expected {FROZEN_SEMANTIC_SHA256}, got {digest})"
        )

    return Protocol(source=source, canonical_json=canonical, semantic_sha256=digest)
