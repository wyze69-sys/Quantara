"""Dual-IC feature evaluation descriptor loading and validation (data slice 006).

Strict loader for ``quantara.evaluation-descriptor/v1`` descriptors: unknown
keys are rejected, identity fields must equal the referenced parent validation
descriptor's approved values exactly, the period must equal the parent period,
features/target/metrics are strictly validated against approved sets and order,
schema/policy/legal fields are fixed to approved values, and the dataset ID is
derived deterministically from the parent base dataset ID.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

from quantara.errors import INVALID_DESCRIPTOR, QuantaraError
from quantara.jcs import canonicalize
from quantara.validation_descriptor import (
    ValidationDescriptor,
    load_validation_descriptor,
)

__all__ = [
    "APPROVED_FEATURES",
    "APPROVED_LEGAL_RECORD",
    "APPROVED_METRICS",
    "APPROVED_TARGET",
    "EVALUATION_DATASET_TYPE",
    "EVALUATION_SCHEMA",
    "EVALUATION_SET",
    "EvaluationDescriptor",
    "EvaluationDescriptorError",
    "QUALITY_POLICY_VERSION",
    "SCHEMA_VERSION",
    "load_evaluation_descriptor",
]

EVALUATION_SCHEMA = "quantara.evaluation-descriptor/v1"
EVALUATION_DATASET_TYPE = "feature_evaluation"
EVALUATION_SET: dict[str, str] = {
    "name": "btcusdt_core_v1_dual_ic_v1",
    "version": "1",
}
APPROVED_FEATURES: tuple[str, ...] = (
    "f_ret_1",
    "f_roc_60",
    "f_rvol_20",
    "f_volratio_20",
)
APPROVED_TARGET = "l_fwdret_24"
APPROVED_METRICS: tuple[str, ...] = (
    "pearson_ic",
    "spearman_ic",
)
SCHEMA_VERSION = "quantara_feature_evaluation_v1"
QUALITY_POLICY_VERSION = "1"
APPROVED_LEGAL_RECORD = "configs/legal/binance-usdm-provider-rights.v2.yaml"

DATASET_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")

EVALUATION_KEYS = frozenset(
    {
        "schema",
        "dataset_id",
        "dataset_type",
        "provider",
        "instrument_id",
        "base_dataset_id",
        "parent_descriptor",
        "period",
        "evaluation_set",
        "features",
        "target",
        "metrics",
        "schema_version",
        "quality_policy_version",
        "legal_record",
    }
)


class EvaluationDescriptorError(QuantaraError):
    error_id = INVALID_DESCRIPTOR


def _reject(detail: str) -> None:
    raise EvaluationDescriptorError(detail)


def _parse_utc(text: object, field_name: str) -> datetime:
    if not isinstance(text, str):
        _reject(f"{field_name} must be a UTC timestamp string")
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise EvaluationDescriptorError(
            f"{field_name} is not an approved UTC calendar timestamp: {text!r}"
        ) from exc


@dataclass(frozen=True)
class EvaluationDescriptor:
    schema: str
    dataset_id: str
    dataset_type: str
    provider: str
    instrument_id: str
    base_dataset_id: str
    parent_descriptor_path: str
    start_utc: datetime
    end_utc: datetime
    evaluation_set: dict[str, str]
    features: tuple[str, ...]
    target: str
    metrics: tuple[str, ...]
    schema_version: str
    quality_policy_version: str
    legal_record: str
    parent_descriptor: ValidationDescriptor = field(compare=False)

    def canonical_semantics(self) -> str:
        """JCS over validated descriptor semantics; stable under YAML key reordering."""
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
            "evaluation_set": dict(self.evaluation_set),
            "features": list(self.features),
            "target": self.target,
            "metrics": list(self.metrics),
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


def load_evaluation_descriptor(path: Path | str) -> EvaluationDescriptor:
    descriptor_path = Path(path)
    try:
        document = yaml.safe_load(descriptor_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        _reject(f"failed to read evaluation descriptor YAML: {exc}")

    if not isinstance(document, dict):
        _reject("evaluation descriptor must be a YAML mapping")

    unknown = set(document) - EVALUATION_KEYS
    if unknown:
        _reject(f"unknown evaluation-descriptor keys: {sorted(unknown)}")
    missing = EVALUATION_KEYS - set(document)
    if missing:
        _reject(f"missing evaluation-descriptor keys: {sorted(missing)}")

    if document["schema"] != EVALUATION_SCHEMA:
        _reject(f"schema must equal {EVALUATION_SCHEMA!r}")
    if document["dataset_type"] != EVALUATION_DATASET_TYPE:
        _reject(f"dataset_type must equal {EVALUATION_DATASET_TYPE!r}")

    # Evaluation set
    evaluation_set = document["evaluation_set"]
    if (
        not isinstance(evaluation_set, dict)
        or set(evaluation_set) != {"name", "version"}
        or evaluation_set["name"] != EVALUATION_SET["name"]
        or str(evaluation_set["version"]) != EVALUATION_SET["version"]
    ):
        _reject(f"evaluation_set must equal {EVALUATION_SET!r}, got {evaluation_set!r}")

    # Features
    features = document["features"]
    if not isinstance(features, list) or tuple(features) != APPROVED_FEATURES:
        _reject(
            "features must equal approved ordered list "
            f"{list(APPROVED_FEATURES)!r}, got {features!r}"
        )

    # Target
    target = document["target"]
    if target != APPROVED_TARGET:
        _reject(f"target must equal {APPROVED_TARGET!r}, got {target!r}")

    # Metrics
    metrics = document["metrics"]
    if not isinstance(metrics, list) or tuple(metrics) != APPROVED_METRICS:
        _reject(
            f"metrics must equal approved ordered list {list(APPROVED_METRICS)!r}, got {metrics!r}"
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

    # Resolve parent validation descriptor
    parent_path = _resolve_referenced_descriptor(
        str(document["parent_descriptor"]), descriptor_path
    )
    if not parent_path.exists():
        _reject(f"referenced parent validation descriptor does not exist: {parent_path}")
    try:
        parent = load_validation_descriptor(parent_path)
    except (QuantaraError, OSError) as exc:
        raise EvaluationDescriptorError(
            f"referenced parent validation descriptor is unusable: {exc}"
        ) from exc

    # Identity binding against parent validation descriptor
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

    # Period must match parent period exactly
    period = document["period"]
    if not isinstance(period, dict) or set(period) != {"start", "end"}:
        _reject("period must be a mapping with exactly start/end")
    start = _parse_utc(period["start"], "period.start")
    end = _parse_utc(period["end"], "period.end")
    if (start, end) != (parent.start_utc, parent.end_utc):
        _reject("period must equal the parent descriptor's period exactly")

    # Parent validation scheme and fold set contracts
    if parent.feature_set != {"name": "btcusdt_core_v1", "version": "1"}:
        _reject(
            f"parent feature_set {parent.feature_set!r} does not match "
            "approved 'btcusdt_core_v1' v1"
        )
    if parent.scheme != "anchored_walkforward_v1":
        _reject(f"parent scheme {parent.scheme!r} does not match 'anchored_walkforward_v1'")
    if parent.fold_set != {"name": "btcusdt_core_v1_wf72_v1", "version": "1"}:
        _reject(
            f"parent fold_set {parent.fold_set!r} does not match "
            "approved 'btcusdt_core_v1_wf72_v1' v1"
        )
    if parent.parameters != {"test_size": 72, "min_train_size": 336}:
        _reject(
            f"parent parameters {parent.parameters!r} do not match "
            "approved values test_size=72, min_train_size=336"
        )
    if parent.embargo != 24:
        _reject(f"parent embargo {parent.embargo!r} does not match approved value 24")

    # Derived dataset ID
    expected_dataset_id = f"{parent.parent_descriptor.base_dataset_id}_evaluation_dual_ic_v1"
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

    return EvaluationDescriptor(
        schema=document["schema"],
        dataset_id=dataset_id,
        dataset_type=document["dataset_type"],
        provider=document["provider"],
        instrument_id=document["instrument_id"],
        base_dataset_id=document["base_dataset_id"],
        parent_descriptor_path=str(document["parent_descriptor"]),
        start_utc=start,
        end_utc=end,
        evaluation_set={
            "name": evaluation_set["name"],
            "version": str(evaluation_set["version"]),
        },
        features=APPROVED_FEATURES,
        target=APPROVED_TARGET,
        metrics=APPROVED_METRICS,
        schema_version=document["schema_version"],
        quality_policy_version=str(document["quality_policy_version"]),
        legal_record=document["legal_record"],
        parent_descriptor=parent,
    )
