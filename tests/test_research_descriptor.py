"""Research-table descriptor loading/validation tests (plan Task 1).

Covers every loader rule with a rejection fixture: unknown keys, identity
drift against the loaded base descriptor, period inequality, feature-set
whitelist, ``unsupported_parameter`` on every approved parameter, fixed
schema/policy/legal fields, JCS stability under key reordering, and the
31-row-base ``undersized_base_dataset`` rejection arithmetic.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from conftest import research_cfg_tree, write_research_descriptor
from quantara.research_descriptor import (
    MINIMUM_PARENT_ROWS,
    ResearchDescriptorError,
    UndersizedBaseDataset,
    load_research_descriptor,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
RESEARCH_CONFIG = (
    REPO_ROOT / "configs" / "datasets" / "binance-usdm-btcusdt-1h-2024-01-research-core-v1.yaml"
)


def test_repo_config_loads_against_real_base_descriptor() -> None:
    descriptor = load_research_descriptor(RESEARCH_CONFIG)
    assert descriptor.schema == "quantara.research-descriptor/v1"
    assert descriptor.dataset_id == ("binance_usdm_btcusdt_klines_1h_2024_01_research_core_v1")
    assert descriptor.base_descriptor.interval == "1h"
    assert descriptor.base_descriptor.expected_row_count == 744
    assert descriptor.minimum_rows == MINIMUM_PARENT_ROWS == 84


def _write_variant(tmp_path: Path, **changes) -> Path:
    """A repo-shaped tree whose research descriptor carries mutations."""
    root = research_cfg_tree(tmp_path)
    descriptor = write_research_descriptor(root, "1h")
    document = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
    for key, value in changes.items():
        if value is _DELETE:
            document.pop(key, None)
        elif isinstance(value, dict) and isinstance(document.get(key), dict):
            document[key] = {**document[key], **value}
        else:
            document[key] = value
    descriptor.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return descriptor


_DELETE = object()


def _assert_invalid(tmp_path: Path, **changes) -> ResearchDescriptorError:
    descriptor = _write_variant(tmp_path, **changes)
    with pytest.raises(ResearchDescriptorError) as excinfo:
        load_research_descriptor(descriptor)
    return excinfo.value


def test_unknown_key_rejected(tmp_path: Path) -> None:
    error = _assert_invalid(tmp_path, extra_key="nope")
    assert "unknown" in error.message


def test_missing_key_rejected(tmp_path: Path) -> None:
    error = _assert_invalid(tmp_path, legal_record=_DELETE)
    assert "missing" in error.message


def test_wrong_schema_rejected(tmp_path: Path) -> None:
    _assert_invalid(tmp_path, schema="quantara.dataset-descriptor/v1")


def test_wrong_dataset_type_rejected(tmp_path: Path) -> None:
    _assert_invalid(tmp_path, dataset_type="klines")


def test_identity_drift_rejected(tmp_path: Path) -> None:
    _assert_invalid(tmp_path, instrument_id="binance:usd_m_futures:ETHUSDT:perpetual")
    _assert_invalid(tmp_path, provider="okx")


def test_base_dataset_binding_enforced(tmp_path: Path) -> None:
    _assert_invalid(tmp_path, base_dataset_id="some_other_dataset")


def test_period_must_equal_base_period(tmp_path: Path) -> None:
    _assert_invalid(
        tmp_path,
        period={
            "start": "2024-01-01T00:00:00Z",
            "end": "2024-01-31T00:00:00Z",
        },
    )


def test_unlisted_feature_set_rejected(tmp_path: Path) -> None:
    _assert_invalid(tmp_path, feature_set={"name": "other_core_v9"})
    _assert_invalid(tmp_path, feature_set={"version": "2"})


@pytest.mark.parametrize(
    ("parameters"),
    [
        {"roc_window": 30},
        {"vol_window": 10},
        {"volume_window": 60},
        {"label_horizon": 12},
        {"extra_param": 1},
    ],
)
def test_any_other_parameter_is_unsupported_parameter(tmp_path: Path, parameters: dict) -> None:
    error = _assert_invalid(tmp_path, parameters=parameters)
    assert error.error_id == "unsupported_parameter"


def test_fixed_schema_and_policy_fields(tmp_path: Path) -> None:
    _assert_invalid(tmp_path, schema_version="quantara_research_featureset_v2")
    _assert_invalid(tmp_path, quality_policy_version="2")


def test_legal_record_must_be_the_v2_amendment(tmp_path: Path) -> None:
    _assert_invalid(
        tmp_path,
        legal_record="configs/legal/binance-usdm-provider-rights.v1.yaml",
    )


def test_canonical_semantics_stable_under_key_reordering(tmp_path: Path) -> None:
    from quantara.hashing import descriptor_hash

    root = research_cfg_tree(tmp_path)
    first = write_research_descriptor(root, "1h")
    reordered = root / "configs" / "datasets" / "reordered.yaml"
    document = yaml.safe_load(first.read_text(encoding="utf-8"))
    reordered.write_text(yaml.safe_dump(document, sort_keys=True), encoding="utf-8")
    left = load_research_descriptor(first)
    right = load_research_descriptor(reordered)
    assert left.canonical_semantics() == right.canonical_semantics()
    assert descriptor_hash(left.canonical_semantics()) == descriptor_hash(
        right.canonical_semantics()
    )


def test_daily_base_is_structurally_undersized(tmp_path: Path) -> None:
    root = research_cfg_tree(tmp_path)
    descriptor = write_research_descriptor(root, "1d")
    with pytest.raises(UndersizedBaseDataset) as excinfo:
        load_research_descriptor(descriptor)
    assert excinfo.value.error_id == "undersized_base_dataset"
    message = excinfo.value.message
    assert "31" in message and "84" in message


def test_minimum_parent_rows_arithmetic() -> None:
    assert MINIMUM_PARENT_ROWS == max(60, 20) + 24 == 84
