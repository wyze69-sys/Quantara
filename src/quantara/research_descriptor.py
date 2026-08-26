"""Research-table descriptor loading/validation (data slice 003b).

Strict loader for ``quantara.research-descriptor/v1`` descriptors: unknown
keys are rejected, identity fields must equal the referenced base derived
descriptor's approved values exactly, the period must equal the base period,
the feature set is whitelisted, every parameter must carry its approved value
(any other value is a stable ``unsupported_parameter``, never a silent
generalization), the schema/policy/legal fields are fixed to the approved v2
amendment, and the minimum parent size is derived arithmetically as
``max(windows needing closes) + label_horizon`` and enforced against the
base's expected row count — an undersized base is ``undersized_base_dataset``,
rejected before any compute (design §6).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

from quantara.derive_descriptor import DerivedDatasetDescriptor, load_derived_descriptor
from quantara.errors import INVALID_DESCRIPTOR, QuantaraError
from quantara.jcs import canonicalize

__all__ = [
    "APPROVED_LEGAL_RECORD",
    "APPROVED_PARAMETERS",
    "FEATURE_SET_NAME",
    "FEATURE_SET_VERSION",
    "MINIMUM_PARENT_ROWS",
    "RESEARCH_DATASET_TYPE",
    "RESEARCH_SCHEMA",
    "SCHEMA_VERSION",
    "ResearchDescriptor",
    "ResearchDescriptorError",
    "UndersizedBaseDataset",
    "UnsupportedParameter",
    "load_research_descriptor",
    "minimum_parent_rows",
]

RESEARCH_SCHEMA = "quantara.research-descriptor/v1"
RESEARCH_DATASET_TYPE = "research_table"
FEATURE_SET_NAME = "btcusdt_core_v1"
FEATURE_SET_VERSION = "1"
SCHEMA_VERSION = "quantara_research_featureset_v1"
QUALITY_POLICY_VERSION = "1"
APPROVED_LEGAL_RECORD = "configs/legal/binance-usdm-provider-rights.v2.yaml"

# design §3.2–3.3 / §6: parameters restricted to these exact values.
APPROVED_PARAMETERS: dict[str, int] = {
    "roc_window": 60,
    "vol_window": 20,
    "volume_window": 20,
    "label_horizon": 24,
}

DATASET_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")


class ResearchDescriptorError(QuantaraError):
    error_id = INVALID_DESCRIPTOR


class UnsupportedParameter(ResearchDescriptorError):
    error_id = "unsupported_parameter"


class UndersizedBaseDataset(ResearchDescriptorError):
    error_id = "undersized_base_dataset"


RESEARCH_KEYS = frozenset(
    {
        "schema",
        "dataset_id",
        "dataset_type",
        "provider",
        "instrument_id",
        "base_dataset_id",
        "base_descriptor",
        "period",
        "feature_set",
        "parameters",
        "schema_version",
        "quality_policy_version",
        "legal_record",
    }
)


def _reject(detail: str) -> None:
    raise ResearchDescriptorError(detail)


def _parse_utc(text: object, field_name: str) -> datetime:
    if not isinstance(text, str):
        _reject(f"{field_name} must be a UTC timestamp string")
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ResearchDescriptorError(
            f"{field_name} is not an approved UTC calendar timestamp: {text!r}"
        ) from exc


def minimum_parent_rows(parameters: dict[str, int]) -> int:
    """Design §6 arithmetic: max(windows needing closes) + label_horizon.

    ``f_roc_60`` reaches back ``roc_window`` bars for closes; ``f_rvol_20``
    consumes ``vol_window`` one-bar returns. The label horizon requires that
    many future bars to exist completely. With the approved parameters this is
    max(60, 20) + 24 = 84.
    """
    return max(parameters["roc_window"], parameters["vol_window"]) + parameters["label_horizon"]


MINIMUM_PARENT_ROWS = minimum_parent_rows(APPROVED_PARAMETERS)


@dataclass(frozen=True)
class ResearchDescriptor:
    schema: str
    dataset_id: str
    dataset_type: str
    provider: str
    instrument_id: str
    start_utc: datetime
    end_utc: datetime
    base_dataset_id: str
    base_descriptor_path: str
    feature_set: dict[str, str]
    parameters: dict[str, int]
    schema_version: str
    quality_policy_version: str
    legal_record: str
    minimum_rows: int
    base_descriptor: DerivedDatasetDescriptor = field(compare=False)

    def canonical_semantics(self) -> str:
        """JCS over validated semantics; stable under YAML key reordering."""
        payload = {
            "schema": self.schema,
            "dataset_id": self.dataset_id,
            "dataset_type": self.dataset_type,
            "provider": self.provider,
            "instrument_id": self.instrument_id,
            "base_dataset_id": self.base_dataset_id,
            "base_descriptor": self.base_descriptor_path,
            "period": {
                "start": self.start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": self.end_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            "feature_set": dict(self.feature_set),
            "parameters": dict(self.parameters),
            "schema_version": self.schema_version,
            "quality_policy_version": self.quality_policy_version,
            "legal_record": self.legal_record,
        }
        return canonicalize(payload)


def _resolve_referenced_descriptor(text: str, descriptor_path: Path) -> Path:
    """Resolve a referenced descriptor relative to this descriptor, walking up
    like the rights-record resolution; absolute references pass through."""
    candidate = Path(text)
    if candidate.is_absolute():
        return candidate
    target = Path(descriptor_path).resolve().parent
    resolved = target / text
    while not resolved.exists() and target != target.parent:
        target = target.parent
        resolved = target / text
    return resolved


def load_research_descriptor(path: Path | str) -> ResearchDescriptor:
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        _reject("research descriptor must be a YAML mapping")
    unknown = set(document) - RESEARCH_KEYS
    if unknown:
        _reject(f"unknown research-descriptor keys: {sorted(unknown)}")
    missing = RESEARCH_KEYS - set(document)
    if missing:
        _reject(f"missing research-descriptor keys: {sorted(missing)}")
    if document["schema"] != RESEARCH_SCHEMA:
        _reject(f"schema must equal {RESEARCH_SCHEMA!r}")
    if document["dataset_type"] != RESEARCH_DATASET_TYPE:
        _reject(f"dataset_type must equal {RESEARCH_DATASET_TYPE!r}")

    base_path = _resolve_referenced_descriptor(str(document["base_descriptor"]), Path(path))
    try:
        base = load_derived_descriptor(base_path)
    except QuantaraError as exc:
        raise ResearchDescriptorError(f"referenced base descriptor is unusable: {exc}") from exc

    # Identity binding against the loaded base descriptor's approved values.
    for name in ("provider", "instrument_id"):
        if document[name] != getattr(base, name):
            _reject(
                f"identity field {name} must equal the base descriptor's "
                f"approved value {getattr(base, name)!r}, got {document[name]!r}"
            )
    expected_dataset_id = f"{base.dataset_id}_research_core_v1"
    dataset_id = document["dataset_id"]
    if (
        not isinstance(dataset_id, str)
        or not DATASET_ID_PATTERN.fullmatch(dataset_id)
        or dataset_id != expected_dataset_id
    ):
        _reject(
            f"dataset_id must equal the base-derived identifier "
            f"{expected_dataset_id!r}, got {dataset_id!r}"
        )
    if document["base_dataset_id"] != base.dataset_id:
        _reject(
            "base_dataset_id must reference the loaded base descriptor's "
            f"dataset_id {base.dataset_id!r}, got {document['base_dataset_id']!r}"
        )

    period = document["period"]
    if not isinstance(period, dict) or set(period) != {"start", "end"}:
        _reject("period must be a mapping with exactly start/end")
    start = _parse_utc(period["start"], "period.start")
    end = _parse_utc(period["end"], "period.end")
    if (start, end) != (base.start_utc, base.end_utc):
        _reject("period must equal the base descriptor's period exactly")

    feature_set = document["feature_set"]
    if (
        not isinstance(feature_set, dict)
        or set(feature_set) != {"name", "version"}
        or feature_set["name"] != FEATURE_SET_NAME
        or str(feature_set["version"]) != FEATURE_SET_VERSION
    ):
        _reject(
            f"feature_set must be exactly {{name: {FEATURE_SET_NAME!r}, "
            f"version: {FEATURE_SET_VERSION!r}}}; unlisted feature sets are "
            "outside this slice's whitelist"
        )

    parameters = document["parameters"]
    if not isinstance(parameters, dict):
        _reject("parameters must be a mapping")
    unknown_parameters = set(parameters) - set(APPROVED_PARAMETERS)
    if unknown_parameters:
        raise UnsupportedParameter(
            f"unknown parameters {sorted(unknown_parameters)}; approved "
            f"parameters are {sorted(APPROVED_PARAMETERS)}"
        )
    missing_parameters = set(APPROVED_PARAMETERS) - set(parameters)
    if missing_parameters:
        raise UnsupportedParameter(f"missing parameters {sorted(missing_parameters)}")
    for name, approved in APPROVED_PARAMETERS.items():
        value = parameters[name]
        if isinstance(value, bool) or not isinstance(value, int):
            raise UnsupportedParameter(f"parameter {name}={value!r} must be an integer")
        if value != approved:
            raise UnsupportedParameter(
                f"parameter {name}={value!r} is outside the approved value "
                f"{approved!r}; generalization is forbidden"
            )

    if document["schema_version"] != SCHEMA_VERSION:
        _reject(f"schema_version must equal {SCHEMA_VERSION!r}")
    if str(document["quality_policy_version"]) != QUALITY_POLICY_VERSION:
        _reject(f"quality_policy_version must equal {QUALITY_POLICY_VERSION!r}")
    if document["legal_record"] != APPROVED_LEGAL_RECORD:
        _reject(
            f"legal_record must reference {APPROVED_LEGAL_RECORD!r}; the "
            "analytical layer gates on the v2 amendment only"
        )

    required = minimum_parent_rows(parameters)
    available = base.expected_row_count
    if available < required:
        raise UndersizedBaseDataset(
            f"base dataset {base.dataset_id} provides {available} rows; the "
            "research table requires at least max(windows needing closes) + "
            f"label_horizon = {required} rows ({available} < {required})"
        )

    return ResearchDescriptor(
        schema=document["schema"],
        dataset_id=dataset_id,
        dataset_type=document["dataset_type"],
        provider=document["provider"],
        instrument_id=document["instrument_id"],
        start_utc=start,
        end_utc=end,
        base_dataset_id=document["base_dataset_id"],
        base_descriptor_path=str(document["base_descriptor"]),
        feature_set={
            "name": feature_set["name"],
            "version": str(feature_set["version"]),
        },
        parameters={name: parameters[name] for name in APPROVED_PARAMETERS},
        schema_version=document["schema_version"],
        quality_policy_version=str(document["quality_policy_version"]),
        legal_record=document["legal_record"],
        minimum_rows=required,
        base_descriptor=base,
    )
