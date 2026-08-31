"""Fail-closed loader and semantic identity for frozen Quantara Protocol v1.

The YAML document is accepted only when its complete, canonicalized semantics
match the independently frozen Protocol-v1 SHA-256. Mapping order, comments,
and YAML formatting are intentionally outside that identity.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

FROZEN_SEMANTIC_SHA256 = "91457d3f1497abfd4e20cf4624768a5d9e9ba4b4478008fb4c7f65c17d90c65a"


class ProtocolValidationError(ValueError):
    """Raised when a document is not exactly the frozen Protocol v1."""


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
