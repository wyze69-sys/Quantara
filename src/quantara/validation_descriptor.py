"""Validation-folds descriptor loading/validation (data slice 004).

Strict loader for ``quantara.validation-descriptor/v1`` descriptors: unknown
keys are rejected, identity fields must equal the referenced parent research
descriptor's approved values exactly, the period must equal the parent period,
the fold set is whitelisted, every parameter must carry its approved value
(any other value is a stable ``unsupported_parameter``, never a silent
generalization), embargo is derived and rejected if specified as an input, the
schema/policy/legal fields are fixed to approved values, and the minimum parent
size is derived arithmetically as ``min_train_size + embargo + test_size`` (432)
and enforced against the parent's expected row count — an undersized parent is
``undersized_parent_dataset``, rejected before any compute (design §10).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

from quantara.errors import INVALID_DESCRIPTOR, QuantaraError
from quantara.jcs import canonicalize
from quantara.research_descriptor import (
    ResearchDescriptor,
    UndersizedBaseDataset,
    load_research_descriptor,
)

__all__ = [
    "APPROVED_LEGAL_RECORD",
    "APPROVED_PARAMETERS",
    "FOLD_SET_NAME",
    "FOLD_SET_VERSION",
    "MINIMUM_PARENT_ROWS",
    "QUALITY_POLICY_VERSION",
    "SCHEMA_VERSION",
    "UndersizedParentDataset",
    "UnsupportedParameter",
    "VALIDATION_DATASET_TYPE",
    "VALIDATION_SCHEMA",
    "VALIDATION_SCHEME",
    "ValidationDescriptor",
    "ValidationDescriptorError",
    "load_validation_descriptor",
    "minimum_parent_rows",
]

VALIDATION_SCHEMA = "quantara.validation-descriptor/v1"
VALIDATION_DATASET_TYPE = "validation_folds"
VALIDATION_SCHEME = "anchored_walkforward_v1"
FOLD_SET_NAME = "btcusdt_core_v1_wf72_v1"
FOLD_SET_VERSION = "1"
SCHEMA_VERSION = "quantara_validation_folds_v1"
QUALITY_POLICY_VERSION = "1"
APPROVED_LEGAL_RECORD = "configs/legal/binance-usdm-provider-rights.v2.yaml"

# design §4 / §10: parameters restricted to these exact values.
APPROVED_PARAMETERS: dict[str, int] = {
    "test_size": 72,
    "min_train_size": 336,
}

DATASET_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")


class ValidationDescriptorError(QuantaraError):
    error_id = INVALID_DESCRIPTOR


class UnsupportedParameter(ValidationDescriptorError):
    error_id = "unsupported_parameter"


class UndersizedParentDataset(ValidationDescriptorError):
    error_id = "undersized_parent_dataset"


VALIDATION_KEYS = frozenset(
    {
        "schema",
        "dataset_id",
        "dataset_type",
        "provider",
        "instrument_id",
        "base_dataset_id",
        "parent_descriptor",
        "period",
        "feature_set",
        "scheme",
        "fold_set",
        "parameters",
        "schema_version",
        "quality_policy_version",
        "legal_record",
    }
)


def _reject(detail: str) -> None:
    raise ValidationDescriptorError(detail)


def _parse_utc(text: object, field_name: str) -> datetime:
    if not isinstance(text, str):
        _reject(f"{field_name} must be a UTC timestamp string")
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ValidationDescriptorError(
            f"{field_name} is not an approved UTC calendar timestamp: {text!r}"
        ) from exc


def minimum_parent_rows(parameters: dict[str, int], embargo: int) -> int:
    """Design §4 arithmetic: min_train_size + embargo + test_size.

    With approved parameters (336, 72) and embargo = label_horizon (24),
    this is 336 + 24 + 72 = 432 rows minimum.
    """
    return parameters["min_train_size"] + embargo + parameters["test_size"]


MINIMUM_PARENT_ROWS = minimum_parent_rows(APPROVED_PARAMETERS, 24)


@dataclass(frozen=True)
class ValidationDescriptor:
    schema: str
    dataset_id: str
    dataset_type: str
    provider: str
    instrument_id: str
    base_dataset_id: str
    parent_descriptor_path: str
    start_utc: datetime
    end_utc: datetime
    feature_set: dict[str, str]
    scheme: str
    fold_set: dict[str, str]
    parameters: dict[str, int]
    embargo: int
    schema_version: str
    quality_policy_version: str
    legal_record: str
    minimum_rows: int
    parent_descriptor: ResearchDescriptor = field(compare=False)

    def canonical_semantics(self) -> str:
        """JCS over validated semantics; stable under YAML key reordering."""
        payload = {
            "schema": self.schema,
            "dataset_id": self.dataset_id,
            "dataset_type": self.dataset_type,
            "provider": self.provider,
            "instrument_id": self.instrument_id,
            "base_dataset_id": self.base_dataset_id,
            "parent_descriptor": self.parent_descriptor_path,
            "period": {
                "start": self.start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": self.end_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            "feature_set": dict(self.feature_set),
            "scheme": self.scheme,
            "fold_set": dict(self.fold_set),
            "parameters": dict(self.parameters),
            "schema_version": self.schema_version,
            "quality_policy_version": self.quality_policy_version,
            "legal_record": self.legal_record,
        }
        return canonicalize(payload)


def _resolve_referenced_descriptor(text: str, descriptor_path: Path) -> Path:
    candidate = Path(text)
    if candidate.is_absolute():
        return candidate
    target = Path(descriptor_path).resolve().parent
    resolved = target / text
    while not resolved.exists() and target != target.parent:
        target = target.parent
        resolved = target / text
    return resolved


def load_validation_descriptor(path: Path | str) -> ValidationDescriptor:
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        _reject("validation descriptor must be a YAML mapping")
    unknown = set(document) - VALIDATION_KEYS
    if unknown:
        _reject(f"unknown validation-descriptor keys: {sorted(unknown)}")
    missing = VALIDATION_KEYS - set(document)
    if missing:
        _reject(f"missing validation-descriptor keys: {sorted(missing)}")
    if document["schema"] != VALIDATION_SCHEMA:
        _reject(f"schema must equal {VALIDATION_SCHEMA!r}")
    if document["dataset_type"] != VALIDATION_DATASET_TYPE:
        _reject(f"dataset_type must equal {VALIDATION_DATASET_TYPE!r}")
    if document["scheme"] != VALIDATION_SCHEME:
        _reject(f"scheme must equal {VALIDATION_SCHEME!r}")

    parent_path = _resolve_referenced_descriptor(
        str(document["parent_descriptor"]), Path(path)
    )
    try:
        parent = load_research_descriptor(parent_path)
    except UndersizedBaseDataset as exc:
        raise UndersizedParentDataset(
            f"parent research descriptor is undersized: {exc}"
        ) from exc
    except QuantaraError as exc:
        raise ValidationDescriptorError(
            f"referenced parent descriptor is unusable: {exc}"
        ) from exc

    # Identity binding against the loaded parent research descriptor's approved values.
    for name in ("provider", "instrument_id"):
        if document[name] != getattr(parent, name):
            _reject(
                f"identity field {name} must equal the parent descriptor's "
                f"approved value {getattr(parent, name)!r}, got {document[name]!r}"
            )
    if document["base_dataset_id"] != parent.base_dataset_id:
        _reject(
            "base_dataset_id must reference the parent descriptor's "
            f"base_dataset_id {parent.base_dataset_id!r}, got {document['base_dataset_id']!r}"
        )

    expected_dataset_id = f"{parent.base_dataset_id}_validation_wf_v1"
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

    period = document["period"]
    if not isinstance(period, dict) or set(period) != {"start", "end"}:
        _reject("period must be a mapping with exactly start/end")
    start = _parse_utc(period["start"], "period.start")
    end = _parse_utc(period["end"], "period.end")
    if (start, end) != (parent.start_utc, parent.end_utc):
        _reject("period must equal the parent descriptor's period exactly")

    feature_set = document["feature_set"]
    if (
        not isinstance(feature_set, dict)
        or set(feature_set) != {"name", "version"}
        or feature_set != parent.feature_set
    ):
        _reject(
            f"feature_set must equal the parent research descriptor's "
            f"feature_set {parent.feature_set!r}, got {feature_set!r}"
        )

    # Parent research parameters must equal the approved research values.
    expected_parent_params = {
        "roc_window": 60,
        "vol_window": 20,
        "volume_window": 20,
        "label_horizon": 24,
    }
    if parent.parameters != expected_parent_params:
        _reject(
            f"parent research parameters {parent.parameters!r} do not match "
            f"approved values {expected_parent_params!r}"
        )

    fold_set = document["fold_set"]
    if (
        not isinstance(fold_set, dict)
        or set(fold_set) != {"name", "version"}
        or fold_set["name"] != FOLD_SET_NAME
        or str(fold_set["version"]) != FOLD_SET_VERSION
    ):
        _reject(
            f"fold_set must be exactly {{name: {FOLD_SET_NAME!r}, "
            f"version: {FOLD_SET_VERSION!r}}}; unlisted fold sets are "
            "outside this slice's whitelist"
        )

    parameters = document["parameters"]
    if not isinstance(parameters, dict):
        _reject("parameters must be a mapping")
    if "embargo" in parameters:
        raise UnsupportedParameter(
            "embargo is derived from parent label_horizon and must not be "
            "specified in parameters"
        )
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

    embargo = parent.parameters["label_horizon"]

    if document["schema_version"] != SCHEMA_VERSION:
        _reject(f"schema_version must equal {SCHEMA_VERSION!r}")
    if str(document["quality_policy_version"]) != QUALITY_POLICY_VERSION:
        _reject(f"quality_policy_version must equal {QUALITY_POLICY_VERSION!r}")
    if document["legal_record"] != APPROVED_LEGAL_RECORD:
        _reject(
            f"legal_record must reference {APPROVED_LEGAL_RECORD!r}; the "
            "analytical layer gates on the v2 amendment only"
        )

    required = minimum_parent_rows(parameters, embargo)
    available = parent.base_descriptor.expected_row_count
    if available < required:
        raise UndersizedParentDataset(
            f"parent dataset {parent.dataset_id} provides {available} rows; the "
            "validation folds require at least min_train_size + embargo + test_size = "
            f"{required} rows ({available} < {required})"
        )

    return ValidationDescriptor(
        schema=document["schema"],
        dataset_id=dataset_id,
        dataset_type=document["dataset_type"],
        provider=document["provider"],
        instrument_id=document["instrument_id"],
        base_dataset_id=document["base_dataset_id"],
        parent_descriptor_path=str(document["parent_descriptor"]),
        start_utc=start,
        end_utc=end,
        feature_set={
            "name": feature_set["name"],
            "version": str(feature_set["version"]),
        },
        scheme=document["scheme"],
        fold_set={
            "name": fold_set["name"],
            "version": str(fold_set["version"]),
        },
        parameters={name: parameters[name] for name in APPROVED_PARAMETERS},
        embargo=embargo,
        schema_version=document["schema_version"],
        quality_policy_version=str(document["quality_policy_version"]),
        legal_record=document["legal_record"],
        minimum_rows=required,
        parent_descriptor=parent,
    )
