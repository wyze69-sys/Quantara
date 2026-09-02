"""Fail-closed frozen loader, guard, and coverage contract for Protocol v1.1."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

from quantara.bootstrap_b4 import nominal_hours, render_fraction_18
from quantara.protocol import (
    ProtocolValidationError,
    _reject_duplicate_features,
    _reject_duplicate_series,
    _UniqueKeySafeLoader,
    _validate_hash_value,
    canonical_semantic_json,
)

V11_UNASSIGNED_HASH = "NOT_YET_ASSIGNED_PENDING_PACKET_C5"
V11_FROZEN_SEMANTIC_SHA256 = (
    "12dd3445365fdaa9e35cdcf93cae3e79a88b6b4d72d3d703b921359d1e917a9b"
)
V11_FROZEN_STATUS = "FROZEN_BEFORE_2022_2024_SCORING"
V11_SCORING_PERMISSION = (
    "AUTHORIZED_2022_2024_AFTER_THRESHOLD_FIXTURE_2025_REMAINS_SEALED"
)
V11_HASH_EXCLUDED_KEYS = ("frozen_semantic_sha256",)
V11_IN_SCOPE_KEY_COUNT = 48
V11_TOTAL_KEY_COUNT = 49
EXCLUSION_REASONS = (
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
_V11_PRE_GATE_OPERATIONS = frozenset(
    {
        "file_inventory",
        "cryptographic_hashes",
        "parser_compatibility",
        "expected_boundaries",
        "mechanical_corruption",
    }
)
_V11_GATE_ARTIFACT_KEYS = frozenset({"payload", "mac"})
_V11_GATE_PAYLOAD_KEYS = frozenset(
    {
        "artifact_type",
        "schema_version",
        "protocol_sha256",
        "operation",
        "criteria",
    }
)
_V11_GATE_CRITERION_IDS = frozenset(str(index) for index in range(1, 8))
_V11_GATE_ARTIFACT_TYPE = "quantara-protocol-v1_1-gate-result"
_V11_GATE_HMAC_KEY_ENV = "QUANTARA_PROTOCOL_V1_1_GATE_HMAC_KEY"


class ProtocolV11DraftError(ValueError):
    """Raised when a document violates the frozen Protocol v1.1 contract."""


class ProtocolV11GuardError(PermissionError):
    """Raised when a frozen Protocol v1.1 operation is not authorized."""


@dataclass(frozen=True, slots=True)
class ProtocolV11:
    """Validated frozen identity containing canonical text and its semantic digest."""

    source: Path
    canonical_projection_json: str
    semantic_sha256: str
    _canonical_document_json: str = field(repr=False)

    def to_dict(self) -> dict[str, Any]:
        """Return a detached copy, matching the frozen v1 loader's copy boundary."""
        value = json.loads(self._canonical_document_json)
        if not isinstance(value, dict):
            raise ProtocolV11DraftError("validated Protocol v1.1 root is not a mapping")
        return value


@dataclass(frozen=True, slots=True)
class YearCoverage:
    """One exact packet-C5a coverage report for a year or pooled period."""

    candidate_eligible_rows: int
    candidate_eligible_percentage: str
    exclusion_reasons: Mapping[str, int]
    longest_missing_run: int


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """Per-year and pooled packet-C5a coverage reporting contract."""

    per_year: Mapping[int, YearCoverage]
    pooled: YearCoverage


def hash_scope_projection(document: Mapping[str, object]) -> dict[str, object]:
    """Apply the frozen every-key-except-own-hash semantic projection clause."""
    if not isinstance(document, Mapping):
        raise ProtocolV11DraftError("Protocol v1.1 document must be a mapping")
    try:
        _validate_hash_value(dict(document))
    except ProtocolValidationError as exc:
        raise ProtocolV11DraftError(str(exc)) from exc

    if len(document) != V11_TOTAL_KEY_COUNT:
        raise ProtocolV11DraftError(
            f"Protocol v1.1 must contain exactly {V11_TOTAL_KEY_COUNT} top-level keys"
        )
    if set(V11_HASH_EXCLUDED_KEYS) - set(document):
        raise ProtocolV11DraftError("Protocol v1.1 own-hash field is missing")

    projection = {
        key: value for key, value in document.items() if key not in V11_HASH_EXCLUDED_KEYS
    }
    if len(projection) != V11_IN_SCOPE_KEY_COUNT:
        raise ProtocolV11DraftError(
            f"Protocol v1.1 projection must contain {V11_IN_SCOPE_KEY_COUNT} keys"
        )

    scope = document.get("semantic_hash_scope")
    if not isinstance(scope, Mapping):
        raise ProtocolV11DraftError("semantic_hash_scope must be a mapping")
    if scope.get("excluded_keys") != list(V11_HASH_EXCLUDED_KEYS):
        raise ProtocolV11DraftError("semantic_hash_scope excluded_keys does not match code")
    if scope.get("total_key_count") != V11_TOTAL_KEY_COUNT:
        raise ProtocolV11DraftError("semantic_hash_scope total_key_count does not match document")
    if scope.get("in_scope_key_count") != V11_IN_SCOPE_KEY_COUNT:
        raise ProtocolV11DraftError(
            "semantic_hash_scope in_scope_key_count does not match document"
        )

    return json.loads(canonical_semantic_json(projection))


def load_protocol_v11(path: str | Path) -> ProtocolV11:
    """Load UTF-8 Protocol v1.1 only when its frozen semantic identity matches."""
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ProtocolV11DraftError(f"cannot read protocol as UTF-8: {source}") from exc

    try:
        document = yaml.load(text, Loader=_UniqueKeySafeLoader)
    except ProtocolValidationError as exc:
        raise ProtocolV11DraftError(str(exc)) from exc
    except yaml.YAMLError as exc:
        raise ProtocolV11DraftError(f"invalid protocol YAML: {source}") from exc

    if not isinstance(document, dict):
        raise ProtocolV11DraftError("protocol root must be a mapping")
    try:
        _validate_hash_value(document)
        _reject_duplicate_series(document)
        _reject_duplicate_features(document)
    except ProtocolValidationError as exc:
        raise ProtocolV11DraftError(str(exc)) from exc

    expected_state = {
        "frozen_semantic_sha256": V11_FROZEN_SEMANTIC_SHA256,
        "protocol_status": V11_FROZEN_STATUS,
        "scoring_permission": V11_SCORING_PERMISSION,
    }
    for key, expected in expected_state.items():
        if document.get(key) != expected:
            raise ProtocolV11DraftError(
                f"frozen Protocol v1.1 requires {key} to equal {expected!r}"
            )

    sealed = document.get("sealed_2025")
    if not isinstance(sealed, Mapping):
        raise ProtocolV11DraftError("sealed_2025 must be a mapping")
    pre_gate_checks = sealed.get("allowed_pre_gate_checks")
    if not isinstance(pre_gate_checks, list) or set(pre_gate_checks) != (
        _V11_PRE_GATE_OPERATIONS
    ):
        raise ProtocolV11DraftError(
            "sealed_2025 allowed_pre_gate_checks does not match the frozen guard"
        )
    success_gate = document.get("success_gate")
    if not isinstance(success_gate, Mapping):
        raise ProtocolV11DraftError("success_gate must be a mapping")
    criteria = success_gate.get("criteria")
    if not isinstance(criteria, list) or {
        str(criterion.get("id"))
        for criterion in criteria
        if isinstance(criterion, Mapping)
    } != _V11_GATE_CRITERION_IDS:
        raise ProtocolV11DraftError(
            "success_gate criteria does not match the seven-criterion frozen guard"
        )

    projection = hash_scope_projection(document)
    canonical_projection = canonical_semantic_json(projection)
    digest = hashlib.sha256(canonical_projection.encode("utf-8")).hexdigest()
    if digest != V11_FROZEN_SEMANTIC_SHA256:
        raise ProtocolV11DraftError(
            "Protocol v1.1 semantic SHA-256 mismatch: "
            f"expected {V11_FROZEN_SEMANTIC_SHA256}, got {digest}"
        )
    canonical_document = canonical_semantic_json(document)
    return ProtocolV11(
        source=source,
        canonical_projection_json=canonical_projection,
        semantic_sha256=digest,
        _canonical_document_json=canonical_document,
    )


def _unique_v11_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolV11GuardError(f"duplicate gate artifact key: {key!r}")
        result[key] = value
    return result


def _canonical_v11_gate_payload(payload: dict[str, object]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _load_v11_gate_authentication_key() -> bytes:
    encoded_key = os.environ.get(_V11_GATE_HMAC_KEY_ENV)
    if encoded_key is None:
        raise ProtocolV11GuardError(
            f"score_2025 requires {_V11_GATE_HMAC_KEY_ENV} to be configured"
        )
    if len(encoded_key) != 64:
        raise ProtocolV11GuardError(
            f"{_V11_GATE_HMAC_KEY_ENV} must contain exactly 32 bytes as hexadecimal"
        )
    try:
        authentication_key = bytes.fromhex(encoded_key)
    except ValueError as exc:
        raise ProtocolV11GuardError(
            f"{_V11_GATE_HMAC_KEY_ENV} is not valid hexadecimal"
        ) from exc
    if len(authentication_key) != 32:
        raise ProtocolV11GuardError(
            f"{_V11_GATE_HMAC_KEY_ENV} must decode to exactly 32 bytes"
        )
    return authentication_key


def _verify_v11_gate_result_artifact(
    artifact: object,
    authentication_key: object,
    protocol_hash: str,
) -> None:
    if not isinstance(artifact, bytes):
        raise ProtocolV11GuardError(
            "gate result must be an immutable bytes snapshot, not a path or mutable buffer"
        )
    if not isinstance(authentication_key, bytes) or len(authentication_key) != 32:
        raise ProtocolV11GuardError(
            "authentication key must be external immutable bytes of exactly 32 bytes"
        )
    try:
        envelope = json.loads(
            artifact.decode("utf-8"), object_pairs_hook=_unique_v11_json_object
        )
    except ProtocolV11GuardError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolV11GuardError(
            "gate result is not canonicalizable UTF-8 JSON"
        ) from exc
    if not isinstance(envelope, dict) or set(envelope) != _V11_GATE_ARTIFACT_KEYS:
        raise ProtocolV11GuardError("gate result envelope has missing or unknown keys")
    payload = envelope["payload"]
    mac_hex = envelope["mac"]
    if not isinstance(payload, dict) or set(payload) != _V11_GATE_PAYLOAD_KEYS:
        raise ProtocolV11GuardError("gate result payload has missing or unknown keys")
    if not isinstance(mac_hex, str) or re.fullmatch(r"[0-9a-f]{64}", mac_hex) is None:
        raise ProtocolV11GuardError(
            "gate result MAC must be 64 lowercase hexadecimal characters"
        )
    supplied_mac = bytes.fromhex(mac_hex)
    expected_mac = hmac.digest(
        authentication_key,
        _canonical_v11_gate_payload(payload),
        "sha256",
    )
    if not hmac.compare_digest(expected_mac, supplied_mac):
        raise ProtocolV11GuardError("gate result MAC authentication failed")
    if payload["artifact_type"] != _V11_GATE_ARTIFACT_TYPE:
        raise ProtocolV11GuardError("unsupported gate result artifact type")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise ProtocolV11GuardError("unsupported gate result schema version")
    if payload["protocol_sha256"] != protocol_hash:
        raise ProtocolV11GuardError(
            "gate result is stale or bound to a different protocol"
        )
    if payload["operation"] != "score_2025":
        raise ProtocolV11GuardError("gate result is not bound to score_2025")
    criteria = payload["criteria"]
    if not isinstance(criteria, dict) or set(criteria) != _V11_GATE_CRITERION_IDS:
        raise ProtocolV11GuardError(
            "gate result must contain exactly all seven Protocol v1.1 success criteria"
        )
    if any(type(value) is not bool or not value for value in criteria.values()):
        raise ProtocolV11GuardError(
            "every Protocol v1.1 success criterion must be boolean true"
        )


def guard_protocol_v11_operation(
    protocol_hash: str,
    operation: str,
    *,
    gate_result_artifact: bytes | None = None,
) -> None:
    """Authorize only the frozen pre-gate checks or authenticated 2025 scoring."""
    if (
        not isinstance(protocol_hash, str)
        or protocol_hash != V11_FROZEN_SEMANTIC_SHA256
    ):
        raise ProtocolV11GuardError(
            "operation requires the frozen Protocol v1.1 semantic hash"
        )
    if not isinstance(operation, str):
        raise ProtocolV11GuardError("operation name must be a string")
    if operation in _V11_PRE_GATE_OPERATIONS:
        if gate_result_artifact is not None:
            raise ProtocolV11GuardError(
                "pre-gate checks do not accept gate credentials"
            )
        return
    if operation != "score_2025":
        raise ProtocolV11GuardError(
            f"unsupported Protocol v1.1 operation: {operation!r}"
        )
    if gate_result_artifact is None:
        raise ProtocolV11GuardError(
            "score_2025 requires an authenticated gate result"
        )
    _verify_v11_gate_result_artifact(
        gate_result_artifact,
        _load_v11_gate_authentication_key(),
        protocol_hash,
    )


def longest_missing_run(flags: Sequence[bool]) -> int:
    """Measure the frozen coverage clause's ineligible run on one yearly grid."""
    longest = 0
    current = 0
    for flag in flags:
        if type(flag) is not bool:
            kind = "float" if isinstance(flag, float) else type(flag).__name__
            raise TypeError(f"eligibility flags must be boolean; {kind} is forbidden")
        if flag:
            current = 0
        else:
            current += 1
            longest = max(longest, current)
    return longest


def coverage_report(
    eligibility_by_year: Mapping[int, Sequence[bool]],
    *,
    exclusions_by_year: Mapping[int, Sequence[str | None]] | None = None,
) -> CoverageReport:
    """Compute the frozen coverage clause using B4 grid and rendering helpers."""
    if not isinstance(eligibility_by_year, Mapping) or not eligibility_by_year:
        raise ValueError("eligibility_by_year must be a non-empty mapping")
    if exclusions_by_year is not None and not isinstance(exclusions_by_year, Mapping):
        raise TypeError("exclusions_by_year must be a mapping")
    if exclusions_by_year is not None:
        unknown_years = set(exclusions_by_year) - set(eligibility_by_year)
        if unknown_years:
            raise ValueError(f"exclusions supplied for unknown years: {sorted(unknown_years)!r}")

    per_year: dict[int, YearCoverage] = {}
    pooled_eligible = 0
    pooled_positions = 0
    pooled_longest = 0
    pooled_counts = {reason: 0 for reason in EXCLUSION_REASONS}

    for year in sorted(eligibility_by_year):
        flags = eligibility_by_year[year]
        if isinstance(flags, (str, bytes)) or not isinstance(flags, Sequence):
            raise TypeError("each eligibility grid must be a sequence")
        expected_hours = nominal_hours(year)
        if len(flags) != expected_hours:
            raise ValueError(
                f"year {year} grid length must equal nominal_hours({year})={expected_hours}"
            )
        year_longest = longest_missing_run(flags)

        reasons: Sequence[str | None]
        if exclusions_by_year is None or year not in exclusions_by_year:
            reasons = (None,) * expected_hours
        else:
            reasons = exclusions_by_year[year]
            if isinstance(reasons, (str, bytes)) or not isinstance(reasons, Sequence):
                raise TypeError("each exclusion grid must be a sequence")
            if len(reasons) != expected_hours:
                raise ValueError("exclusion grid length must match the nominal eligibility grid")

        year_counts = {reason: 0 for reason in EXCLUSION_REASONS}
        eligible_rows = 0
        for flag, reason in zip(flags, reasons, strict=True):
            if flag:
                eligible_rows += 1
                if reason is not None:
                    raise ValueError("eligible positions cannot carry an exclusion reason")
                continue
            if reason is None:
                raise ValueError("each ineligible position requires exactly one exclusion reason")
            if not isinstance(reason, str):
                kind = "float" if isinstance(reason, float) else type(reason).__name__
                raise TypeError(f"exclusion reason must be a string; {kind} is forbidden")
            if reason not in year_counts:
                raise ValueError(f"unknown exclusion reason: {reason!r}")
            year_counts[reason] += 1

        excluded_rows = expected_hours - eligible_rows
        if sum(year_counts.values()) != excluded_rows:
            raise AssertionError("exclusion reason counts do not equal ineligible rows")
        percentage = render_fraction_18(Fraction(eligible_rows * 100, expected_hours))
        per_year[year] = YearCoverage(
            candidate_eligible_rows=eligible_rows,
            candidate_eligible_percentage=percentage,
            exclusion_reasons=MappingProxyType(year_counts),
            longest_missing_run=year_longest,
        )
        pooled_eligible += eligible_rows
        pooled_positions += expected_hours
        pooled_longest = max(pooled_longest, year_longest)
        for reason, count in year_counts.items():
            pooled_counts[reason] += count

    pooled = YearCoverage(
        candidate_eligible_rows=pooled_eligible,
        candidate_eligible_percentage=render_fraction_18(
            Fraction(pooled_eligible * 100, pooled_positions)
        ),
        exclusion_reasons=MappingProxyType(pooled_counts),
        longest_missing_run=pooled_longest,
    )
    return CoverageReport(per_year=MappingProxyType(per_year), pooled=pooled)
