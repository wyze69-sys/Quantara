"""Strict descriptor contract for exact-decimal ridge walk-forward training."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

from quantara.errors import INVALID_DESCRIPTOR, QuantaraError
from quantara.jcs import canonicalize
from quantara.validation_descriptor import ValidationDescriptor, load_validation_descriptor

TRAINING_SCHEMA = "quantara.training-descriptor/v1"
TRAINING_DATASET_TYPE = "model_training"
APPROVED_MODEL = {
    "family": "ridge_linear",
    "lambda": "1",
    "solver": "gauss_elimination_partial_pivot",
}
APPROVED_STANDARDIZATION = "train_window_zscore"
APPROVED_BASELINES = ("majority_class_train_window", "sign_f_ret_1")
APPROVED_METRICS = ("pearson_ic", "directional_accuracy", "mse")
APPROVED_FEATURES = ("f_ret_1", "f_roc_60", "f_rvol_20", "f_volratio_20")
APPROVED_TARGET = "l_fwdret_24"
TRAINING_SET = {"name": "btcusdt_core_v1_ridge_v1", "version": "1"}
SCHEMA_VERSION = "quantara_model_training_v1"
QUALITY_POLICY_VERSION = "1"
APPROVED_LEGAL_RECORD = "configs/legal/binance-usdm-provider-rights.v3.yaml"

_DATASET_ID = re.compile(r"^[a-z0-9_]+$")
_KEYS = frozenset(
    {
        "schema", "dataset_id", "dataset_type", "provider", "instrument_id",
        "base_dataset_id", "parent_descriptor", "period", "model",
        "standardization", "baselines", "metrics", "features", "target",
        "training_set", "schema_version", "quality_policy_version", "legal_record",
    }
)


class TrainingDescriptorError(QuantaraError):
    error_id = INVALID_DESCRIPTOR


def _reject(detail: str) -> None:
    raise TrainingDescriptorError(detail)


def _parse_utc(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        _reject(f"{name} must be a UTC timestamp string")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise TrainingDescriptorError(f"{name} is not an approved UTC timestamp") from exc


def _resolve(text: str, descriptor_path: Path) -> Path:
    candidate = Path(text)
    if candidate.is_absolute():
        return candidate
    target = descriptor_path.resolve().parent
    resolved = target / candidate
    while not resolved.exists() and target != target.parent:
        target = target.parent
        resolved = target / candidate
    return resolved


@dataclass(frozen=True)
class TrainingDescriptor:
    schema: str
    dataset_id: str
    dataset_type: str
    provider: str
    instrument_id: str
    base_dataset_id: str
    parent_descriptor_path: str
    start_utc: datetime
    end_utc: datetime
    model: dict[str, str]
    standardization: str
    baselines: tuple[str, ...]
    metrics: tuple[str, ...]
    features: tuple[str, ...]
    target: str
    training_set: dict[str, str]
    schema_version: str
    quality_policy_version: str
    legal_record: str
    parent_descriptor: ValidationDescriptor = field(compare=False)

    def canonical_semantics(self) -> str:
        return canonicalize(
            {
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
                "model": dict(self.model),
                "standardization": self.standardization,
                "baselines": list(self.baselines),
                "metrics": list(self.metrics),
                "features": list(self.features),
                "target": self.target,
                "training_set": dict(self.training_set),
                "schema_version": self.schema_version,
                "quality_policy_version": self.quality_policy_version,
                "legal_record": self.legal_record,
            }
        )


def load_training_descriptor(path: Path | str) -> TrainingDescriptor:
    descriptor_path = Path(path)
    try:
        document = yaml.safe_load(descriptor_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        _reject(f"failed to read training descriptor YAML: {exc}")
    if not isinstance(document, dict):
        _reject("training descriptor must be a YAML mapping")
    unknown = set(document) - _KEYS
    missing = _KEYS - set(document)
    if unknown:
        _reject(f"unknown training-descriptor keys: {sorted(unknown)}")
    if missing:
        _reject(f"missing training-descriptor keys: {sorted(missing)}")
    exact = {
        "schema": TRAINING_SCHEMA,
        "dataset_type": TRAINING_DATASET_TYPE,
        "model": APPROVED_MODEL,
        "standardization": APPROVED_STANDARDIZATION,
        "baselines": list(APPROVED_BASELINES),
        "metrics": list(APPROVED_METRICS),
        "features": list(APPROVED_FEATURES),
        "target": APPROVED_TARGET,
        "training_set": TRAINING_SET,
        "schema_version": SCHEMA_VERSION,
        "legal_record": APPROVED_LEGAL_RECORD,
    }
    for name, expected in exact.items():
        if document[name] != expected:
            _reject(f"{name} must equal {expected!r}, got {document[name]!r}")
    if str(document["quality_policy_version"]) != QUALITY_POLICY_VERSION:
        _reject(f"quality_policy_version must equal {QUALITY_POLICY_VERSION!r}")

    parent_path = _resolve(str(document["parent_descriptor"]), descriptor_path)
    if not parent_path.exists():
        _reject(f"referenced parent validation descriptor does not exist: {parent_path}")
    try:
        parent = load_validation_descriptor(parent_path)
    except (QuantaraError, OSError) as exc:
        raise TrainingDescriptorError(
            f"referenced parent validation descriptor is unusable: {exc}"
        ) from exc
    for name in ("provider", "instrument_id", "base_dataset_id"):
        if document[name] != getattr(parent, name):
            _reject(f"identity field {name} must equal parent value")
    period = document["period"]
    if not isinstance(period, dict) or set(period) != {"start", "end"}:
        _reject("period must be a mapping with exactly start/end")
    start = _parse_utc(period["start"], "period.start")
    end = _parse_utc(period["end"], "period.end")
    if (start, end) != (parent.start_utc, parent.end_utc):
        _reject("period must equal the parent descriptor's period exactly")
    if parent.feature_set != {"name": "btcusdt_core_v1", "version": "1"}:
        _reject("parent feature_set is not approved")
    if parent.scheme != "anchored_walkforward_v1":
        _reject("parent scheme is not approved")
    if parent.fold_set != {"name": "btcusdt_core_v1_wf72_v1", "version": "1"}:
        _reject("parent fold_set is not approved")
    if parent.parameters != {"test_size": 72, "min_train_size": 336} or parent.embargo != 24:
        _reject("parent walk-forward parameters are not approved")
    expected_id = f"{parent.parent_descriptor.base_dataset_id}_training_ridge_v1"
    dataset_id = document["dataset_id"]
    if (
        not isinstance(dataset_id, str)
        or not _DATASET_ID.fullmatch(dataset_id)
        or dataset_id != expected_id
    ):
        _reject(f"dataset_id must equal {expected_id!r}, got {dataset_id!r}")
    return TrainingDescriptor(
        schema=TRAINING_SCHEMA,
        dataset_id=dataset_id,
        dataset_type=TRAINING_DATASET_TYPE,
        provider=document["provider"],
        instrument_id=document["instrument_id"],
        base_dataset_id=document["base_dataset_id"],
        parent_descriptor_path=str(document["parent_descriptor"]),
        start_utc=start,
        end_utc=end,
        model=dict(APPROVED_MODEL),
        standardization=APPROVED_STANDARDIZATION,
        baselines=APPROVED_BASELINES,
        metrics=APPROVED_METRICS,
        features=APPROVED_FEATURES,
        target=APPROVED_TARGET,
        training_set=dict(TRAINING_SET),
        schema_version=SCHEMA_VERSION,
        quality_policy_version=QUALITY_POLICY_VERSION,
        legal_record=APPROVED_LEGAL_RECORD,
        parent_descriptor=parent,
    )
