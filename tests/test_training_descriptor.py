"""Strict training-descriptor contract tests for slice 011."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from quantara.training_descriptor import (
    APPROVED_BASELINES,
    APPROVED_FEATURES,
    APPROVED_METRICS,
    APPROVED_MODEL,
    APPROVED_TARGET,
    TRAINING_DATASET_TYPE,
    TRAINING_SCHEMA,
    TrainingDescriptorError,
    load_training_descriptor,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_CONFIG = (
    REPO_ROOT
    / "configs"
    / "datasets"
    / "binance-usdm-btcusdt-1h-2024-training-ridge-v1.yaml"
)
PARENT = (
    REPO_ROOT
    / "configs"
    / "datasets"
    / "binance-usdm-btcusdt-1h-2024-validation-wf-v1.yaml"
)
_DELETE = object()


def _document() -> dict:
    return {
        "schema": TRAINING_SCHEMA,
        "dataset_id": "binance_usdm_btcusdt_klines_1h_2024_training_ridge_v1",
        "dataset_type": TRAINING_DATASET_TYPE,
        "provider": "binance",
        "instrument_id": "binance:usd_m_futures:BTCUSDT:perpetual",
        "base_dataset_id": "binance_usdm_btcusdt_klines_1h_2024",
        "parent_descriptor": str(PARENT),
        "period": {
            "start": "2024-01-01T00:00:00Z",
            "end": "2025-01-01T00:00:00Z",
        },
        "model": dict(APPROVED_MODEL),
        "standardization": "train_window_zscore",
        "baselines": list(APPROVED_BASELINES),
        "metrics": list(APPROVED_METRICS),
        "features": list(APPROVED_FEATURES),
        "target": APPROVED_TARGET,
        "training_set": {"name": "btcusdt_core_v1_ridge_v1", "version": "1"},
        "schema_version": "quantara_model_training_v1",
        "quality_policy_version": "1",
        "legal_record": "configs/legal/binance-usdm-provider-rights.v3.yaml",
    }


def _write(tmp_path: Path, **changes: object) -> Path:
    doc = _document()
    for key, value in changes.items():
        if value is _DELETE:
            doc.pop(key)
        else:
            doc[key] = value
    path = tmp_path / "training.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return path


def _invalid(tmp_path: Path, **changes: object) -> None:
    with pytest.raises(TrainingDescriptorError):
        load_training_descriptor(_write(tmp_path, **changes))


def test_real_training_descriptor_loads_and_resolves_parent() -> None:
    desc = load_training_descriptor(REAL_CONFIG)
    assert desc.dataset_id.endswith("_training_ridge_v1")
    assert desc.parent_descriptor.dataset_id.endswith("_validation_wf_v1")
    assert desc.model == APPROVED_MODEL
    assert desc.features == APPROVED_FEATURES
    assert desc.baselines == APPROVED_BASELINES
    assert desc.metrics == APPROVED_METRICS


def test_unknown_missing_and_root_rejected(tmp_path: Path) -> None:
    _invalid(tmp_path, unknown=True)
    _invalid(tmp_path, legal_record=_DELETE)
    path = tmp_path / "list.yaml"
    path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
    with pytest.raises(TrainingDescriptorError):
        load_training_descriptor(path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema", "quantara.training-descriptor/v2"),
        ("dataset_type", "feature_evaluation"),
        ("provider", "other"),
        ("instrument_id", "other"),
        ("base_dataset_id", "other"),
        ("dataset_id", "wrong"),
        ("period", {"start": "2024-01-01T00:00:00Z", "end": "2024-02-01T00:00:00Z"}),
        (
            "model",
            {
                "family": "ridge_linear",
                "lambda": "2",
                "solver": "gauss_elimination_partial_pivot",
            },
        ),
        ("standardization", "full_year_zscore"),
        ("baselines", ["majority_class"]),
        ("metrics", ["pearson_ic", "mse"]),
        ("features", ["f_ret_1"]),
        ("target", "l_fwddir_24"),
        ("training_set", {"name": "wrong", "version": "1"}),
        ("schema_version", "quantara_model_training_v2"),
        ("quality_policy_version", "2"),
        ("legal_record", "configs/legal/binance-usdm-provider-rights.v2.yaml"),
        ("parent_descriptor", "missing.yaml"),
    ],
)
def test_contract_drift_rejected(tmp_path: Path, field: str, value: object) -> None:
    _invalid(tmp_path, **{field: value})


def test_canonical_semantics_stable_under_key_reordering(tmp_path: Path) -> None:
    first = _write(tmp_path)
    doc = yaml.safe_load(first.read_text(encoding="utf-8"))
    second = tmp_path / "reordered.yaml"
    second.write_text(
        yaml.safe_dump({key: doc[key] for key in reversed(doc)}, sort_keys=False),
        encoding="utf-8",
    )
    assert (
        load_training_descriptor(first).canonical_semantics()
        == load_training_descriptor(second).canonical_semantics()
    )
