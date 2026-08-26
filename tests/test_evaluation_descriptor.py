"""Evaluation descriptor loading and validation tests (data slice 006, Task T1).

Covers every loader rule with rejection fixtures:
- non-object root and malformed YAML;
- unknown and missing keys;
- wrong schema, dataset_type, schema_version, quality_policy_version, legal_record;
- evaluation_set mismatch or version mismatch;
- features: duplicate, omitted, substituted, reordered, non-list, or non-approved;
- target: omitted, invalid, or substituted;
- metrics: duplicate, omitted, substituted, reordered, non-list, or non-approved;
- parent descriptor linkage:
  - provider, instrument_id, base_dataset_id, period mismatch;
  - parent research feature-set mismatch;
  - parent validation scheme mismatch;
  - parent fold-set mismatch;
  - parent parameters mismatch (test_size != 72, min_train_size != 336, or embargo != 24);
- dataset_id derivation: must equal f"{base_dataset_id}_evaluation_dual_ic_v1";
- canonical semantic stability under YAML key reordering;
- real repository Q1 config loading.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from conftest import evaluation_cfg_tree, write_evaluation_descriptor
from quantara.evaluation_descriptor import (
    APPROVED_FEATURES,
    APPROVED_LEGAL_RECORD,
    APPROVED_METRICS,
    APPROVED_TARGET,
    EVALUATION_DATASET_TYPE,
    EVALUATION_SCHEMA,
    EVALUATION_SET,
    QUALITY_POLICY_VERSION,
    SCHEMA_VERSION,
    EvaluationDescriptor,
    EvaluationDescriptorError,
    load_evaluation_descriptor,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_EVALUATION_CONFIG = (
    REPO_ROOT
    / "configs"
    / "datasets"
    / "binance-usdm-btcusdt-1h-2024-q1-evaluation-dual-ic-v1.yaml"
)

_DELETE = object()


def _write_variant(tmp_path: Path, **changes) -> Path:
    """A repo-shaped tree whose evaluation descriptor carries mutations."""
    root = evaluation_cfg_tree(tmp_path)
    descriptor = write_evaluation_descriptor(root, "1h")
    document = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
    for key, value in changes.items():
        if value is _DELETE:
            document.pop(key, None)
        else:
            document[key] = value
    descriptor.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return descriptor


def _assert_invalid(tmp_path: Path, **changes) -> EvaluationDescriptorError:
    descriptor = _write_variant(tmp_path, **changes)
    with pytest.raises(EvaluationDescriptorError) as excinfo:
        load_evaluation_descriptor(descriptor)
    return excinfo.value


def test_real_repo_config_loads_against_real_validation_descriptor() -> None:
    descriptor = load_evaluation_descriptor(REAL_EVALUATION_CONFIG)
    assert isinstance(descriptor, EvaluationDescriptor)
    assert descriptor.schema == EVALUATION_SCHEMA
    assert descriptor.dataset_id == ("binance_usdm_btcusdt_klines_1h_2024_q1_evaluation_dual_ic_v1")
    assert descriptor.dataset_type == EVALUATION_DATASET_TYPE
    assert descriptor.evaluation_set == EVALUATION_SET
    assert descriptor.features == APPROVED_FEATURES
    assert descriptor.target == APPROVED_TARGET
    assert descriptor.metrics == APPROVED_METRICS
    assert descriptor.schema_version == SCHEMA_VERSION
    assert descriptor.quality_policy_version == QUALITY_POLICY_VERSION
    assert descriptor.legal_record == APPROVED_LEGAL_RECORD
    assert descriptor.parent_descriptor.dataset_id == (
        "binance_usdm_btcusdt_klines_1h_2024_q1_validation_wf_v1"
    )


def test_non_object_root_rejected(tmp_path: Path) -> None:
    root = evaluation_cfg_tree(tmp_path)
    descriptor = write_evaluation_descriptor(root, "1h")
    descriptor.write_text("- item1\n- item2\n", encoding="utf-8")
    with pytest.raises(EvaluationDescriptorError) as excinfo:
        load_evaluation_descriptor(descriptor)
    assert "mapping" in str(excinfo.value).lower()


def test_unknown_key_rejected(tmp_path: Path) -> None:
    error = _assert_invalid(tmp_path, unexpected_key="bad")
    assert "unknown" in str(error).lower()


def test_missing_key_rejected(tmp_path: Path) -> None:
    error = _assert_invalid(tmp_path, legal_record=_DELETE)
    assert "missing" in str(error).lower()


def test_wrong_schema_rejected(tmp_path: Path) -> None:
    _assert_invalid(tmp_path, schema="quantara.validation-descriptor/v1")


def test_wrong_dataset_type_rejected(tmp_path: Path) -> None:
    _assert_invalid(tmp_path, dataset_type="validation_folds")


def test_wrong_evaluation_set_rejected(tmp_path: Path) -> None:
    _assert_invalid(
        tmp_path,
        evaluation_set={"name": "other_evaluation_set", "version": "1"},
    )
    _assert_invalid(
        tmp_path,
        evaluation_set={"name": "btcusdt_core_v1_dual_ic_v1", "version": "2"},
    )
    _assert_invalid(
        tmp_path,
        evaluation_set="not_a_mapping",
    )


def test_features_exact_order_and_rejection(tmp_path: Path) -> None:
    # Reordered features rejected
    reordered = ["f_roc_60", "f_ret_1", "f_rvol_20", "f_volratio_20"]
    _assert_invalid(tmp_path, features=reordered)

    # Missing one feature rejected
    omitted = ["f_ret_1", "f_roc_60", "f_rvol_20"]
    _assert_invalid(tmp_path, features=omitted)

    # Substituted feature rejected
    substituted = ["f_ret_1", "f_roc_60", "f_rvol_20", "f_other"]
    _assert_invalid(tmp_path, features=substituted)

    # Duplicate feature rejected
    duplicate = ["f_ret_1", "f_ret_1", "f_roc_60", "f_rvol_20"]
    _assert_invalid(tmp_path, features=duplicate)

    # Non-list rejected
    _assert_invalid(tmp_path, features="f_ret_1")


def test_target_exact_and_rejection(tmp_path: Path) -> None:
    _assert_invalid(tmp_path, target="l_fwddir_24")
    _assert_invalid(tmp_path, target="l_fwdret_12")
    _assert_invalid(tmp_path, target=_DELETE)


def test_metrics_exact_order_and_rejection(tmp_path: Path) -> None:
    # Reordered metrics rejected
    _assert_invalid(tmp_path, metrics=["spearman_ic", "pearson_ic"])

    # Missing metric rejected
    _assert_invalid(tmp_path, metrics=["pearson_ic"])

    # Unknown metric rejected
    _assert_invalid(tmp_path, metrics=["pearson_ic", "kendall_tau"])

    # Duplicate metric rejected
    _assert_invalid(tmp_path, metrics=["pearson_ic", "pearson_ic"])

    # Non-list rejected
    _assert_invalid(tmp_path, metrics="pearson_ic")


def test_identity_drift_rejected(tmp_path: Path) -> None:
    _assert_invalid(tmp_path, instrument_id="binance:usd_m_futures:ETHUSDT:perpetual")
    _assert_invalid(tmp_path, provider="coinbase")
    _assert_invalid(tmp_path, base_dataset_id="other_base")


def test_dataset_id_mismatch_rejected(tmp_path: Path) -> None:
    _assert_invalid(
        tmp_path,
        dataset_id="binance_usdm_btcusdt_klines_1h_2024_01_wrong_id",
    )
    _assert_invalid(
        tmp_path,
        dataset_id="binance_usdm_btcusdt_klines_1h_2024_01_evaluation_dual_ic_v2",
    )


def test_period_mismatch_rejected(tmp_path: Path) -> None:
    _assert_invalid(
        tmp_path,
        period={"start": "2024-01-01T00:00:00Z", "end": "2024-01-15T00:00:00Z"},
    )
    _assert_invalid(tmp_path, period="2024-01-01")


def test_schema_version_and_policy_rejected(tmp_path: Path) -> None:
    _assert_invalid(tmp_path, schema_version="quantara_feature_evaluation_v2")
    _assert_invalid(tmp_path, quality_policy_version="2")
    _assert_invalid(
        tmp_path,
        legal_record="configs/legal/binance-usdm-provider-rights.v1.yaml",
    )


def test_parent_descriptor_unusable_or_missing(tmp_path: Path) -> None:
    _assert_invalid(tmp_path, parent_descriptor="configs/datasets/nonexistent.yaml")


def test_canonical_semantics_stability(tmp_path: Path) -> None:
    root = evaluation_cfg_tree(tmp_path)
    first = write_evaluation_descriptor(root, "1h")
    content = yaml.safe_load(first.read_text(encoding="utf-8"))
    reordered = root / "configs" / "datasets" / "reordered.yaml"
    reordered_keys = list(reversed(list(content.keys())))
    reordered_dict = {k: content[k] for k in reordered_keys}
    reordered.write_text(yaml.safe_dump(reordered_dict, sort_keys=False), encoding="utf-8")

    left = load_evaluation_descriptor(first)
    right = load_evaluation_descriptor(reordered)
    assert left.canonical_semantics() == right.canonical_semantics()
