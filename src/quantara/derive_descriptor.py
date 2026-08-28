"""Derived-dataset descriptor loading/validation (data slice 002).

Strict loader for ``quantara.derived-dataset-descriptor/v1`` descriptors:
unknown keys are rejected, identity fields must equal the referenced base
descriptor's approved values exactly, intervals are restricted to the slice
whitelist {1h, 1d} (anything else is a stable ``unsupported_timeframe``), the
period must equal the base period exactly and be exactly divisible by the
timeframe, and the transformation block is shape-checked. Expected row counts
are derived purely by calendar math, never embedded (design §5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from quantara.descriptor import DatasetDescriptor, load_descriptor
from quantara.errors import INVALID_DESCRIPTOR, QuantaraError
from quantara.hashing import descriptor_hash
from quantara.jcs import canonicalize

__all__ = [
    "DERIVED_SCHEMA",
    "SUPPORTED_TIMEFRAMES",
    "TRANSFORMATION_NAME",
    "TRANSFORMATION_VERSION",
    "DerivedDatasetDescriptor",
    "DerivedDescriptorError",
    "UnsupportedTimeframe",
    "load_derived_descriptor",
]

DERIVED_SCHEMA = "quantara.derived-dataset-descriptor/v1"
TRANSFORMATION_NAME = "multi_timeframe_aggregation"
TRANSFORMATION_VERSION = "1"

# design §3.1 / §5: exactly these timeframes are in scope.
SUPPORTED_TIMEFRAMES: dict[str, int] = {
    "1h": 3_600_000,
    "1d": 86_400_000,
}


class DerivedDescriptorError(QuantaraError):
    error_id = INVALID_DESCRIPTOR


class UnsupportedTimeframe(DerivedDescriptorError):
    error_id = "unsupported_timeframe"


IDENTITY_FIELDS = (
    "provider",
    "market_type",
    "instrument_id",
    "provider_symbol",
    "base_asset",
    "quote_asset",
    "settlement_asset",
    "contract_type",
    "dataset_type",
)

DERIVED_KEYS = frozenset(
    {
        "schema",
        "dataset_id",
        *IDENTITY_FIELDS,
        "interval",
        "base_dataset_id",
        "base_descriptor",
        "period",
        "transformation",
        "schema_version",
        "timestamp_semantics",
        "quality_policy_version",
        "legal_record",
    }
)

# Slice 010B: optional under policy 1 (forbidden), required under policy 2.
DERIVED_OPTIONAL_KEYS = frozenset({"quality_approval"})


def _reject(detail: str) -> None:
    raise DerivedDescriptorError(detail)


def _parse_utc(text: object, field_name: str) -> datetime:
    if not isinstance(text, str):
        _reject(f"{field_name} must be a UTC timestamp string")
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise DerivedDescriptorError(
            f"{field_name} is not an approved UTC calendar timestamp: {text!r}"
        ) from exc


@dataclass(frozen=True)
class DerivedDatasetDescriptor:
    schema: str
    dataset_id: str
    provider: str
    market_type: str
    instrument_id: str
    provider_symbol: str
    base_asset: str
    quote_asset: str
    settlement_asset: str
    contract_type: str
    dataset_type: str
    interval: str
    timeframe_ms: int
    start_utc: datetime
    end_utc: datetime
    base_dataset_id: str
    base_descriptor_path: str
    base_descriptor: DatasetDescriptor = field(compare=False)
    transformation: dict[str, str]
    schema_version: str
    timestamp_semantics: str
    quality_policy_version: str
    legal_record: str
    quality_approval: str | None = None

    @property
    def expected_row_count(self) -> int:
        """Calendar math only: (end − start) // timeframe_ms, via exact
        timedelta integer division (no binary-float intermediates)."""
        length_ms = (self.end_utc - self.start_utc) // timedelta(milliseconds=1)
        return length_ms // self.timeframe_ms

    def identity_tuple(self) -> tuple[str, ...]:
        """Ten canonical-row identity strings in schema order."""
        return (
            self.provider,
            self.market_type,
            self.instrument_id,
            self.provider_symbol,
            self.base_asset,
            self.quote_asset,
            self.settlement_asset,
            self.contract_type,
            self.interval,
            self.schema_version,
        )

    def canonical_semantics(self) -> str:
        """JCS of validated semantics; formatting/key-order independent.

        Includes the transformation block and the resolved base binding so any
        change to parent binding or aggregation version changes identity.
        """
        semantics: dict[str, Any] = {
            "schema": self.schema,
            "dataset_id": self.dataset_id,
            **{name: getattr(self, name) for name in IDENTITY_FIELDS},
            "interval": self.interval,
            "period": {
                "start": self.start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": self.end_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            "transformation": dict(self.transformation),
            "schema_version": self.schema_version,
            "timestamp_semantics": self.timestamp_semantics,
            "quality_policy_version": self.quality_policy_version,
            "legal_record": self.legal_record,
            "base_binding": {
                "dataset_id": self.base_dataset_id,
                "descriptor_path": self.base_descriptor_path,
                "descriptor_sha256": descriptor_hash(
                    self.base_descriptor.canonical_semantics()
                ),
            },
        }
        if self.quality_approval is not None:
            semantics["quality_approval"] = self.quality_approval
        return canonicalize(semantics)


def _resolve_base_descriptor(path_text: str, descriptor_path: Path) -> Path:
    candidate = Path(path_text)
    if candidate.is_absolute():
        return candidate
    walker = descriptor_path.resolve().parent
    resolved = walker / candidate
    while not resolved.exists() and walker != walker.parent:
        walker = walker.parent
        resolved = walker / candidate
    if not resolved.exists():
        _reject(f"referenced base descriptor not found: {path_text}")
    return resolved


def load_derived_descriptor(path: Path | str) -> DerivedDatasetDescriptor:
    descriptor_path = Path(path)
    document = yaml.safe_load(descriptor_path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        _reject("derived descriptor must be a YAML mapping")
    unknown = set(document) - DERIVED_KEYS - DERIVED_OPTIONAL_KEYS
    if unknown:
        _reject(f"unknown derived-descriptor keys: {sorted(unknown)}")
    missing = DERIVED_KEYS - set(document)
    if missing:
        _reject(f"missing derived-descriptor keys: {sorted(missing)}")
    if document["schema"] != DERIVED_SCHEMA:
        _reject(f"schema must equal {DERIVED_SCHEMA!r}")

    interval = document["interval"]
    if interval not in SUPPORTED_TIMEFRAMES:
        raise UnsupportedTimeframe(
            f"interval {interval!r} is outside this slice's whitelist "
            f"{sorted(SUPPORTED_TIMEFRAMES)}; generalization is forbidden"
        )
    timeframe_ms = SUPPORTED_TIMEFRAMES[interval]

    base_path = _resolve_base_descriptor(document["base_descriptor"], descriptor_path)
    base = load_descriptor(base_path)

    for name in IDENTITY_FIELDS:
        if document[name] != getattr(base, name):
            _reject(
                f"identity field {name} must equal the base descriptor's "
                f"approved value {getattr(base, name)!r}, got {document[name]!r}"
            )
    for name in ("timestamp_semantics", "legal_record"):
        if str(document[name]) != getattr(base, name):
            _reject(f"{name} must equal the base descriptor's value")
    # Slice 010B policy combination rule (mirrors the base-descriptor rule
    # from 010A T2): "2" is accepted only with quality_approval; "1" only
    # without it. Any other version is rejected outright.
    quality_policy_version = str(document["quality_policy_version"])
    has_approval = "quality_approval" in document
    if quality_policy_version == "1":
        if has_approval:
            _reject(
                "quality_policy_version '1' derived descriptors must not "
                "specify quality_approval"
            )
        quality_approval = None
    elif quality_policy_version == "2":
        if not has_approval:
            _reject(
                "quality_policy_version '2' derived descriptors require a "
                "quality_approval record path"
            )
        quality_approval = document["quality_approval"]
        if not isinstance(quality_approval, str) or not quality_approval:
            _reject("quality_approval must be a non-empty path string")
        from quantara.quality_approval import validate_approval_path

        try:
            validate_approval_path(quality_approval)
        except QuantaraError as exc:
            _reject(f"invalid quality_approval path: {exc}")
    else:
        _reject(
            f"quality_policy_version must be '1' or '2', got "
            f"{quality_policy_version!r}"
        )

    period = document["period"]
    if not isinstance(period, dict) or set(period) != {"start", "end"}:
        _reject("period must be a mapping with exactly start/end")
    start = _parse_utc(period["start"], "period.start")
    end = _parse_utc(period["end"], "period.end")

    # Misaligned configurations are rejected before any comparison against
    # compute-affecting state, per design §5 validation order.
    length_ms = (end - start) // timedelta(milliseconds=1)
    if length_ms <= 0 or length_ms % timeframe_ms != 0:
        _reject(
            f"period length {length_ms} ms must divide evenly by the "
            f"{timeframe_ms} ms timeframe with zero remainder"
        )

    if (start, end) != (base.start_utc, base.end_utc):
        _reject("period must equal the base descriptor's period exactly")

    if document["schema_version"] != f"binance_usdm_kline_{interval}_v1":
        _reject(
            f"schema_version must equal binance_usdm_kline_{interval}_v1, "
            f"got {document['schema_version']!r}"
        )

    base_dataset_id = document["base_dataset_id"]
    if base_dataset_id != base.dataset_id:
        _reject(
            f"base_dataset_id must reference the loaded base descriptor's "
            f"dataset_id {base.dataset_id!r}, got {base_dataset_id!r}"
        )

    transformation = document["transformation"]
    if (
        not isinstance(transformation, dict)
        or set(transformation) != {"name", "version"}
        or transformation["name"] != TRANSFORMATION_NAME
        or str(transformation["version"]) != TRANSFORMATION_VERSION
    ):
        _reject(
            f"transformation must be exactly {{name: {TRANSFORMATION_NAME!r}, "
            f"version: {TRANSFORMATION_VERSION!r}}}"
        )

    return DerivedDatasetDescriptor(
        schema=document["schema"],
        dataset_id=document["dataset_id"],
        **{name: document[name] for name in IDENTITY_FIELDS},
        interval=interval,
        timeframe_ms=timeframe_ms,
        start_utc=start,
        end_utc=end,
        base_dataset_id=base_dataset_id,
        base_descriptor_path=str(document["base_descriptor"]),
        base_descriptor=base,
        transformation={
            "name": transformation["name"],
            "version": str(transformation["version"]),
        },
        schema_version=document["schema_version"],
        timestamp_semantics=document["timestamp_semantics"],
        quality_policy_version=str(document["quality_policy_version"]),
        legal_record=document["legal_record"],
        quality_approval=quality_approval,
    )
