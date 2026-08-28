"""Logistic training-descriptor contract tests for slice 012.

Includes the slice 011 ridge regression pin: the committed ridge config must
keep loading with an unchanged dataset_id, descriptor identity, and
``canonical_semantics()``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from quantara.training_descriptor import (
    APPROVED_BASELINES_LOGISTIC,
    APPROVED_FEATURES,
    APPROVED_KILL_CRITERIA,
    APPROVED_METRICS_LOGISTIC,
    APPROVED_MODEL,
    APPROVED_MODEL_LOGISTIC,
    APPROVED_TARGET_LOGISTIC,
    MODEL_FAMILIES,
    TRAINING_DATASET_TYPE,
    TRAINING_SCHEMA,
    TRAINING_SET_LOGISTIC,
    TrainingDescriptorError,
    load_training_descriptor,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_ROOT = REPO_ROOT / "configs" / "datasets"
RIDGE_CONFIG = CONFIG_ROOT / "binance-usdm-btcusdt-1h-2024-training-ridge-v1.yaml"
LOGISTIC_CONFIG = CONFIG_ROOT / "binance-usdm-btcusdt-1h-2024-training-logistic-v1.yaml"
PARENT = CONFIG_ROOT / "binance-usdm-btcusdt-1h-2024-validation-wf-v1.yaml"

# Byte/identity pins captured from the frozen slice 011 committed config.
RIDGE_DATASET_ID = "binance_usdm_btcusdt_klines_1h_2024_training_ridge_v1"
RIDGE_FILE_SHA256 = "d555a0f6f7866996adf4f467443913afb5f293a0e877bc2a3e0b2fb2fca5dcc9"
RIDGE_SEMANTICS_SHA256 = (
    "7810e0c9c37f4c8048a93cf6dab80854a0c2d3bc10d0854cbedfc443022b7daf"
)
_DELETE = object()


def _document() -> dict:
    return {
        "schema": TRAINING_SCHEMA,
        "dataset_id": "binance_usdm_btcusdt_klines_1h_2024_training_logistic_v1",
        "dataset_type": TRAINING_DATASET_TYPE,
        "provider": "binance",
        "instrument_id": "binance:usd_m_futures:BTCUSDT:perpetual",
        "base_dataset_id": "binance_usdm_btcusdt_klines_1h_2024",
        "parent_descriptor": str(PARENT),
        "period": {"start": "2024-01-01T00:00:00Z", "end": "2025-01-01T00:00:00Z"},
        "model": dict(APPROVED_MODEL_LOGISTIC),
        "standardization": "train_window_zscore",
        "baselines": list(APPROVED_BASELINES_LOGISTIC),
        "metrics": list(APPROVED_METRICS_LOGISTIC),
        "features": list(APPROVED_FEATURES),
        "target": APPROVED_TARGET_LOGISTIC,
        "training_set": dict(TRAINING_SET_LOGISTIC),
        "kill_criteria": dict(APPROVED_KILL_CRITERIA),
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
    path = tmp_path / "training-logistic.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return path


def _invalid(tmp_path: Path, **changes: object) -> None:
    with pytest.raises(TrainingDescriptorError):
        load_training_descriptor(_write(tmp_path, **changes))


def test_ridge_regression_pin_is_byte_and_identity_stable() -> None:
    assert hashlib.sha256(RIDGE_CONFIG.read_bytes()).hexdigest() == RIDGE_FILE_SHA256
    desc = load_training_descriptor(RIDGE_CONFIG)
    assert desc.dataset_id == RIDGE_DATASET_ID
    assert desc.model == APPROVED_MODEL
    assert desc.target == "l_fwdret_24"
    assert desc.kill_criteria is None
    semantics = desc.canonical_semantics()
    assert hashlib.sha256(semantics.encode("utf-8")).hexdigest() == RIDGE_SEMANTICS_SHA256
    assert "kill_criteria" not in semantics


def test_real_logistic_descriptor_loads_with_frozen_parameters() -> None:
    desc = load_training_descriptor(LOGISTIC_CONFIG)
    assert desc.dataset_id == "binance_usdm_btcusdt_klines_1h_2024_training_logistic_v1"
    assert desc.model == APPROVED_MODEL_LOGISTIC
    assert desc.model["family"] == "logistic_irls"
    assert desc.model["lambda"] == "1"
    assert desc.model["max_iterations"] == 50
    assert desc.model["tolerance"] == "0.000000000001"
    assert desc.model["eta_clamp"] == "24"
    assert desc.model["mu_clamp"] == "0.000000000001"
    assert desc.target == "l_fwddir_24"
    assert desc.metrics == APPROVED_METRICS_LOGISTIC
    assert desc.baselines == APPROVED_BASELINES_LOGISTIC
    assert desc.training_set == TRAINING_SET_LOGISTIC
    assert desc.kill_criteria == APPROVED_KILL_CRITERIA
    assert desc.parent_descriptor.dataset_id.endswith("_validation_wf_v1")
    assert "kill_criteria" in desc.canonical_semantics()


def test_model_families_are_exactly_the_two_approved_families() -> None:
    assert set(MODEL_FAMILIES) == {"ridge_linear", "logistic_irls"}


def test_kill_criteria_constants_are_the_pre_registered_values() -> None:
    assert APPROVED_KILL_CRITERIA == {
        "directional_accuracy_min": "0.534900284900284900",
        "direction_ic_min": "0.020000000000000000",
        "log_loss_max": "0.762500000000000000",
        "brier_max": "0.250000000000000000",
    }


def test_synthetic_logistic_document_loads(tmp_path: Path) -> None:
    desc = load_training_descriptor(_write(tmp_path))
    assert desc.kill_criteria == APPROVED_KILL_CRITERIA


def test_numerically_equal_kill_constants_normalize_to_q18(tmp_path: Path) -> None:
    desc = load_training_descriptor(
        _write(
            tmp_path,
            kill_criteria={
                "directional_accuracy_min": "0.5349002849002849",
                "direction_ic_min": "0.02",
                "log_loss_max": "0.7625",
                "brier_max": "0.25",
            },
        )
    )
    assert desc.kill_criteria == APPROVED_KILL_CRITERIA


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("kill_criteria", _DELETE),
        ("kill_criteria", {}),
        ("kill_criteria", "0.02"),
        (
            "kill_criteria",
            {
                "directional_accuracy_min": "0.500000000000000000",
                "direction_ic_min": "0.020000000000000000",
                "log_loss_max": "0.762500000000000000",
                "brier_max": "0.250000000000000000",
            },
        ),
        (
            "kill_criteria",
            {
                "directional_accuracy_min": "0.534900284900284900",
                "direction_ic_min": "0.010000000000000000",
                "log_loss_max": "0.762500000000000000",
                "brier_max": "0.250000000000000000",
            },
        ),
        (
            "kill_criteria",
            {
                "directional_accuracy_min": "0.534900284900284900",
                "direction_ic_min": "0.020000000000000000",
                "log_loss_max": "0.800000000000000000",
                "brier_max": "0.250000000000000000",
            },
        ),
        (
            "kill_criteria",
            {
                "directional_accuracy_min": "0.534900284900284900",
                "direction_ic_min": "0.020000000000000000",
                "log_loss_max": "0.762500000000000000",
                "brier_max": "0.300000000000000000",
            },
        ),
        (
            "kill_criteria",
            {
                "directional_accuracy_min": "0.534900284900284900",
                "direction_ic_min": "0.020000000000000000",
                "log_loss_max": "0.762500000000000000",
            },
        ),
        (
            "kill_criteria",
            {
                "directional_accuracy_min": "0.534900284900284900",
                "direction_ic_min": "0.020000000000000000",
                "log_loss_max": "0.762500000000000000",
                "brier_max": "0.250000000000000000",
                "extra": "1",
            },
        ),
    ],
)
def test_kill_criteria_block_is_required_and_exact(
    tmp_path: Path, field: str, value: object
) -> None:
    _invalid(tmp_path, **{field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("dataset_id", "binance_usdm_btcusdt_klines_1h_2024_training_ridge_v1"),
        ("dataset_id", "wrong"),
        ("target", "l_fwdret_24"),
        ("training_set", {"name": "btcusdt_core_v1_ridge_v1", "version": "1"}),
        ("metrics", ["pearson_ic", "directional_accuracy", "mse"]),
        ("baselines", ["majority_class_train_window", "sign_f_ret_1"]),
        ("standardization", "full_year_zscore"),
        ("features", ["f_ret_1"]),
        ("schema_version", "quantara_model_training_v2"),
        ("quality_policy_version", "2"),
        ("legal_record", "configs/legal/binance-usdm-provider-rights.v2.yaml"),
        ("model", {"family": "logistic_irls"}),
        (
            "model",
            {**APPROVED_MODEL_LOGISTIC, "lambda": "2"},
        ),
        (
            "model",
            {**APPROVED_MODEL_LOGISTIC, "max_iterations": 100},
        ),
        (
            "model",
            {**APPROVED_MODEL_LOGISTIC, "tolerance": "0.00000001"},
        ),
        (
            "model",
            {**APPROVED_MODEL_LOGISTIC, "eta_clamp": "36"},
        ),
        (
            "model",
            {**APPROVED_MODEL_LOGISTIC, "mu_clamp": "0.0000001"},
        ),
        (
            "model",
            {**APPROVED_MODEL_LOGISTIC, "solver": "newton_raphson"},
        ),
        ("model", {"family": "logistic_probit", "lambda": "1"}),
        ("model", "logistic_irls"),
    ],
)
def test_logistic_contract_drift_rejected(
    tmp_path: Path, field: str, value: object
) -> None:
    _invalid(tmp_path, **{field: value})


def test_ridge_document_must_not_carry_a_kill_criteria_block(tmp_path: Path) -> None:
    ridge = yaml.safe_load(RIDGE_CONFIG.read_text(encoding="utf-8"))
    ridge["parent_descriptor"] = str(PARENT)
    path = tmp_path / "ridge.yaml"
    path.write_text(yaml.safe_dump(ridge, sort_keys=False), encoding="utf-8")
    assert load_training_descriptor(path).kill_criteria is None
    ridge["kill_criteria"] = dict(APPROVED_KILL_CRITERIA)
    path.write_text(yaml.safe_dump(ridge, sort_keys=False), encoding="utf-8")
    with pytest.raises(TrainingDescriptorError):
        load_training_descriptor(path)


def test_logistic_canonical_semantics_stable_under_key_reordering(tmp_path: Path) -> None:
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
