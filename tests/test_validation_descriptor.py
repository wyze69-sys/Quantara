"""Validation-folds descriptor loading/validation tests (plan Task 1).

Covers every loader rule with a rejection fixture: unknown keys, identity
drift against the loaded parent research descriptor, period inequality,
feature-set mismatch, unsupported scheme/dataset_type/schema,
``unsupported_parameter`` on every approved parameter, rejection of user-set
embargo, fixed schema/policy/legal fields, JCS stability under key reordering,
and the 31-row 1d parent ``undersized_parent_dataset`` rejection arithmetic.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from conftest import validation_cfg_tree, write_validation_descriptor
from quantara.validation_descriptor import (
    MINIMUM_PARENT_ROWS,
    UndersizedParentDataset,
    UnsupportedParameter,
    ValidationDescriptorError,
    load_validation_descriptor,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATION_CONFIG = (
    REPO_ROOT
    / "configs"
    / "datasets"
    / "binance-usdm-btcusdt-1h-2024-01-validation-wf-v1.yaml"
)


def test_repo_config_loads_against_real_research_descriptor() -> None:
    descriptor = load_validation_descriptor(VALIDATION_CONFIG)
    assert descriptor.schema == "quantara.validation-descriptor/v1"
    assert descriptor.dataset_id == (
        "binance_usdm_btcusdt_klines_1h_2024_01_validation_wf_v1"
    )
    assert descriptor.dataset_type == "validation_folds"
    assert descriptor.scheme == "anchored_walkforward_v1"
    assert descriptor.fold_set == {"name": "btcusdt_core_v1_wf72_v1", "version": "1"}
    assert descriptor.parameters == {"test_size": 72, "min_train_size": 336}
    assert descriptor.embargo == 24
    assert descriptor.minimum_rows == MINIMUM_PARENT_ROWS == 432
    assert descriptor.parent_descriptor.base_descriptor.expected_row_count == 744


def _write_variant(tmp_path: Path, **changes) -> Path:
    """A repo-shaped tree whose validation descriptor carries mutations."""
    root = validation_cfg_tree(tmp_path)
    descriptor = write_validation_descriptor(root, "1h")
    document = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
    for key, value in changes.items():
        if value is _DELETE:
            document.pop(key, None)
        else:
            document[key] = value
    descriptor.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return descriptor


_DELETE = object()


def _assert_invalid(tmp_path: Path, **changes) -> ValidationDescriptorError:
    descriptor = _write_variant(tmp_path, **changes)
    with pytest.raises(ValidationDescriptorError) as excinfo:
        load_validation_descriptor(descriptor)
    return excinfo.value


def test_unknown_key_rejected(tmp_path: Path) -> None:
    error = _assert_invalid(tmp_path, extra_key="nope")
    assert "unknown" in error.message


def test_missing_key_rejected(tmp_path: Path) -> None:
    error = _assert_invalid(tmp_path, legal_record=_DELETE)
    assert "missing" in error.message


def test_wrong_schema_rejected(tmp_path: Path) -> None:
    _assert_invalid(tmp_path, schema="quantara.research-descriptor/v1")


def test_wrong_dataset_type_rejected(tmp_path: Path) -> None:
    _assert_invalid(tmp_path, dataset_type="research_table")


def test_wrong_scheme_rejected(tmp_path: Path) -> None:
    _assert_invalid(tmp_path, scheme="rolling_v1")


def test_identity_drift_rejected(tmp_path: Path) -> None:
    _assert_invalid(
        tmp_path, instrument_id="binance:usd_m_futures:ETHUSDT:perpetual"
    )
    _assert_invalid(tmp_path, provider="coinbase")
    _assert_invalid(tmp_path, base_dataset_id="other_base")


def test_period_mismatch_rejected(tmp_path: Path) -> None:
    _assert_invalid(
        tmp_path,
        period={
            "start": "2024-01-01T00:00:00Z",
            "end": "2024-01-15T00:00:00Z",
        },
    )


def test_feature_set_mismatch_rejected(tmp_path: Path) -> None:
    _assert_invalid(
        tmp_path,
        feature_set={"name": "other_features", "version": "1"},
    )


def test_fold_set_mismatch_rejected(tmp_path: Path) -> None:
    _assert_invalid(
        tmp_path,
        fold_set={"name": "other_fold_set", "version": "1"},
    )


def test_embargo_in_parameters_rejected(tmp_path: Path) -> None:
    descriptor = _write_variant(
        tmp_path,
        parameters={"test_size": 72, "min_train_size": 336, "embargo": 24},
    )
    with pytest.raises(UnsupportedParameter) as excinfo:
        load_validation_descriptor(descriptor)
    assert "embargo" in excinfo.value.message
    assert excinfo.value.error_id == "unsupported_parameter"


@pytest.mark.parametrize(
    "bad_params",
    [
        {"test_size": 48, "min_train_size": 336},
        {"test_size": 72, "min_train_size": 168},
        {"test_size": "72", "min_train_size": 336},
        {"test_size": True, "min_train_size": 336},
        {"test_size": 72},
        {"test_size": 72, "min_train_size": 336, "extra": 10},
    ],
)
def test_unsupported_parameters_rejected(tmp_path: Path, bad_params: dict) -> None:
    descriptor = _write_variant(tmp_path, parameters=bad_params)
    with pytest.raises(UnsupportedParameter) as excinfo:
        load_validation_descriptor(descriptor)
    assert excinfo.value.error_id == "unsupported_parameter"


def test_undersized_parent_rejected(tmp_path: Path) -> None:
    root = validation_cfg_tree(tmp_path)
    # Write validation descriptor targeting 1d parent (31 rows < 432)
    descriptor = write_validation_descriptor(root, "1d")
    with pytest.raises(UndersizedParentDataset) as excinfo:
        load_validation_descriptor(descriptor)
    assert excinfo.value.error_id == "undersized_parent_dataset"
    assert "31" in excinfo.value.message


def test_canonical_semantics_stability(tmp_path: Path) -> None:
    root = validation_cfg_tree(tmp_path)
    first = write_validation_descriptor(root, "1h")
    content = yaml.safe_load(first.read_text(encoding="utf-8"))
    reordered = root / "configs" / "datasets" / "reordered.yaml"
    reordered_keys = list(reversed(list(content.keys())))
    reordered_dict = {k: content[k] for k in reordered_keys}
    reordered.write_text(yaml.safe_dump(reordered_dict, sort_keys=False), encoding="utf-8")

    left = load_validation_descriptor(first)
    right = load_validation_descriptor(reordered)
    assert left.canonical_semantics() == right.canonical_semantics()


def test_wrong_legal_record_rejected(tmp_path: Path) -> None:
    _assert_invalid(
        tmp_path,
        legal_record="configs/legal/binance-usdm-provider-rights.v1.yaml",
    )


# --- Task 2: Hashing tests ---------------------------------------------------


def test_validation_schema_fingerprint_determinism_and_domain_separation() -> None:
    from quantara.hashing import (
        research_schema_fingerprint,
        schema_fingerprint,
        validation_schema_fingerprint,
    )

    base = validation_schema_fingerprint()
    assert len(base) == 64
    assert base == validation_schema_fingerprint()

    # Predecessor fingerprints are distinct
    kline_fp = schema_fingerprint()
    research_fp = research_schema_fingerprint()
    assert base != kline_fp
    assert base != research_fp
    assert kline_fp == "feab7d2bb40de94e3621d6ff9847363eddd52b7fd8cd3c07f66def664da614c8"

    # Sensitivity to every dimension
    assert base != validation_schema_fingerprint(schema_id="other_schema")
    assert base != validation_schema_fingerprint(scheme="other_scheme")
    assert base != validation_schema_fingerprint(
        parameters={"test_size": 48, "min_train_size": 336, "embargo": 24}
    )
    assert base != validation_schema_fingerprint(fold_set_name="other_folds")
    assert base != validation_schema_fingerprint(fold_set_version="2")
    assert base != validation_schema_fingerprint(
        parent_fingerprint="0" * 64
    )


def test_validation_content_hash_determinism_and_types() -> None:
    from quantara.hashing import (
        HashPayloadError,
        validation_content_hash,
        validation_schema_fingerprint,
    )

    fp = validation_schema_fingerprint()
    artifact = {
        "schema": "quantara.validation_folds/v1",
        "fold_set": "btcusdt_core_v1_wf72_v1",
        "scheme": "anchored_walkforward_v1",
        "parent_rows": 744,
        "folds": [{"fold_id": 0}],
    }
    h1 = validation_content_hash(fp, artifact)
    assert len(h1) == 64
    assert h1 == validation_content_hash(fp, artifact)

    # String and bytes forms match
    from quantara.jcs import canonicalize

    canonical_str = canonicalize(artifact)
    assert h1 == validation_content_hash(fp, canonical_str)
    assert h1 == validation_content_hash(fp, canonical_str.encode("utf-8"))

    # Different content produces different hash
    artifact_diff = dict(artifact, parent_rows=745)
    assert h1 != validation_content_hash(fp, artifact_diff)

    # Different fingerprint produces different hash
    assert h1 != validation_content_hash("0" * 64, artifact)

    # Invalid type rejected
    with pytest.raises(HashPayloadError):
        validation_content_hash(fp, 12345)  # type: ignore[arg-type]
