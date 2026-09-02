"""Fail-closed draft loader and coverage contract for Protocol v1.1 packet C5a.

This module deliberately canonicalizes the declared semantic projection without
computing a digest. Protocol v1.1 remains unfrozen until packet C5.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from types import MappingProxyType
from typing import Any, NoReturn

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


class ProtocolV11DraftError(ValueError):
    """Raised when a document violates the packet-C5a draft contract."""


class ProtocolV11GuardError(PermissionError):
    """Raised because the unfrozen v1.1 draft authorizes no operation."""


@dataclass(frozen=True, slots=True)
class ProtocolV11:
    """Validated draft identity containing canonical text but deliberately no digest."""

    source: Path
    canonical_projection_json: str
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
    """Apply the packet-C5a every-key-except-own-hash projection rule."""
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
    """Load the UTF-8 Protocol v1.1 draft under the packet-C5a fail-closed rules."""
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
        "frozen_semantic_sha256": V11_UNASSIGNED_HASH,
        "protocol_status": "DRAFT_UNFROZEN_SUCCESSOR",
        "scoring_permission": "NONE_UNTIL_FROZEN",
    }
    for key, expected in expected_state.items():
        if document.get(key) != expected:
            raise ProtocolV11DraftError(
                f"Protocol v1.1 draft requires {key} to remain {expected!r}"
            )

    projection = hash_scope_projection(document)
    canonical_projection = canonical_semantic_json(projection)
    canonical_document = canonical_semantic_json(document)
    return ProtocolV11(
        source=source,
        canonical_projection_json=canonical_projection,
        _canonical_document_json=canonical_document,
    )


def guard_protocol_v11_operation(operation: str) -> NoReturn:
    """Refuse every operation under packet C5a because v1.1 is still unfrozen."""
    raise ProtocolV11GuardError(
        f"Protocol v1.1 operation {operation!r} is forbidden while "
        f"frozen_semantic_sha256 is {V11_UNASSIGNED_HASH}"
    )


def longest_missing_run(flags: Sequence[bool]) -> int:
    """Measure packet-C5a ineligible runs on one nominal yearly grid."""
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
    """Compute exact packet-C5a coverage using frozen B4 grid and rendering helpers."""
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
