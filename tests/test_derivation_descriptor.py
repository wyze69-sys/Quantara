"""Derived-dataset descriptor loader tests (plan Task 1, design §5)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from conftest import VALID_DESCRIPTOR_YAML, write_text
from quantara.errors import QuantaraError
from quantara.hashing import descriptor_hash

BASE_NAME = "binance-usdm-btcusdt-1m-2024-01.yaml"


def derived_yaml(interval: str) -> str:
    return f"""\
schema: quantara.derived-dataset-descriptor/v1
dataset_id: binance_usdm_btcusdt_klines_{interval}_2024_01
provider: binance
market_type: usd_m_futures
instrument_id: binance:usd_m_futures:BTCUSDT:perpetual
provider_symbol: BTCUSDT
base_asset: BTC
quote_asset: USDT
settlement_asset: USDT
contract_type: perpetual
dataset_type: klines
interval: {interval}
base_dataset_id: binance_usdm_btcusdt_klines_1m_2024_01
base_descriptor: configs/datasets/{BASE_NAME}
period:
  start: "2024-01-01T00:00:00Z"
  end: "2024-02-01T00:00:00Z"
transformation:
  name: multi_timeframe_aggregation
  version: "1"
schema_version: binance_usdm_kline_{interval}_v1
timestamp_semantics: closed_interval_v1
quality_policy_version: "1"
legal_record: configs/legal/binance-usdm-provider-rights.v1.yaml
"""


@pytest.fixture()
def cfg(tmp_path: Path) -> Path:
    """Repo-shaped config tree: configs/datasets holds base + derived."""
    datasets = tmp_path / "configs" / "datasets"
    datasets.mkdir(parents=True)
    (datasets / BASE_NAME).write_text(VALID_DESCRIPTOR_YAML, encoding="utf-8")
    return tmp_path


def write_derived(cfg_root: Path, text: str, name: str) -> Path:
    return write_text(cfg_root / "configs" / "datasets" / name, text, name=name)


@pytest.mark.parametrize(
    ("interval", "timeframe_ms", "rows"),
    [("1h", 3_600_000, 744), ("1d", 86_400_000, 31)],
)
def test_valid_descriptors_expose_calendar_math(
    cfg: Path, interval: str, timeframe_ms: int, rows: int
) -> None:
    from quantara.derive_descriptor import load_derived_descriptor

    path = write_derived(cfg, derived_yaml(interval), f"derived-{interval}.yaml")
    descriptor = load_derived_descriptor(path)
    assert descriptor.interval == interval
    assert descriptor.timeframe_ms == timeframe_ms
    assert descriptor.expected_row_count == rows
    assert descriptor.base_descriptor.dataset_id == (
        "binance_usdm_btcusdt_klines_1m_2024_01"
    )
    assert descriptor.transformation == {
        "name": "multi_timeframe_aggregation",
        "version": "1",
    }


def test_semantic_hash_is_formatting_independent(cfg: Path) -> None:
    from quantara.derive_descriptor import load_derived_descriptor

    reordered = dict(reversed(list(yaml.safe_load(derived_yaml("1h")).items())))
    reordered["period"] = {
        "end": reordered["period"]["end"],
        "start": reordered["period"]["start"],
    }
    a = load_derived_descriptor(write_derived(cfg, derived_yaml("1h"), "a.yaml"))
    b = load_derived_descriptor(
        write_derived(cfg, yaml.safe_dump(reordered), "b.yaml")
    )
    assert descriptor_hash(a.canonical_semantics()) == descriptor_hash(
        b.canonical_semantics()
    )
    assert a.canonical_semantics() == b.canonical_semantics()


def test_distinct_timeframes_hash_differently(cfg: Path) -> None:
    from quantara.derive_descriptor import load_derived_descriptor

    h = load_derived_descriptor(write_derived(cfg, derived_yaml("1h"), "h.yaml"))
    d = load_derived_descriptor(write_derived(cfg, derived_yaml("1d"), "d.yaml"))
    assert h.canonical_semantics() != d.canonical_semantics()

def _rejects(cfg: Path, mutate, name: str) -> None:
    from quantara.derive_descriptor import load_derived_descriptor

    document = yaml.safe_load(derived_yaml("1h"))
    mutate(document)
    path = write_derived(cfg, yaml.safe_dump(document), name)
    with pytest.raises(QuantaraError):
        load_derived_descriptor(path)


def test_rejects_tampered_instrument(cfg: Path) -> None:
    _rejects(
        cfg,
        lambda d: d.update(instrument_id="binance:usd_m_futures:ETHUSDT:perpetual"),
        "tampered-instrument.yaml",
    )


def test_rejects_unsupported_timeframe_5m(cfg: Path) -> None:
    from quantara.derive_descriptor import UnsupportedTimeframe, load_derived_descriptor

    document = yaml.safe_load(derived_yaml("1h"))
    document["interval"] = "5m"
    document["schema_version"] = "binance_usdm_kline_5m_v1"
    document["dataset_id"] = "binance_usdm_btcusdt_klines_5m_2024_01"
    path = write_derived(cfg, yaml.safe_dump(document), "five-minutes.yaml")
    with pytest.raises(UnsupportedTimeframe) as excinfo:
        load_derived_descriptor(path)
    assert excinfo.value.error_id == "unsupported_timeframe"


def test_rejects_mid_hour_period_start(cfg: Path) -> None:
    _rejects(
        cfg,
        lambda d: d.update(
            period={"start": "2024-01-01T00:30:00Z", "end": "2024-02-01T00:30:00Z"}
        ),
        "mid-hour.yaml",
    )


def test_rejects_period_differing_from_base(cfg: Path) -> None:
    _rejects(
        cfg,
        lambda d: d.update(
            period={"start": "2024-01-01T00:00:00Z", "end": "2024-01-31T00:00:00Z"}
        ),
        "short-month.yaml",
    )


def test_rejects_wrong_schema_version(cfg: Path) -> None:
    _rejects(
        cfg,
        lambda d: d.update(schema_version="binance_usdm_kline_1m_v1"),
        "wrong-schema-version.yaml",
    )


def test_rejects_unknown_key(cfg: Path) -> None:
    _rejects(cfg, lambda d: d.update(sneaky_field="nope"), "unknown-key.yaml")


def test_rejects_non_divisible_period_before_compute(cfg: Path) -> None:
    from quantara.derive_descriptor import load_derived_descriptor

    document = yaml.safe_load(derived_yaml("1h"))
    # Length becomes 44,640 minutes + 30 minutes => not divisible by 60 minutes.
    document["period"]["end"] = "2024-02-01T00:30:00Z"
    path = write_derived(cfg, yaml.safe_dump(document), "non-divisible.yaml")
    with pytest.raises(QuantaraError, match="divide"):
        load_derived_descriptor(path)


def test_rejects_missing_transformation_shape(cfg: Path) -> None:
    _rejects(
        cfg,
        lambda d: d.update(transformation={"name": "something_else", "version": "9"}),
        "bad-transformation.yaml",
    )


def test_rejects_base_dataset_id_mismatch(cfg: Path) -> None:
    _rejects(
        cfg,
        lambda d: d.update(base_dataset_id="some_other_parent"),
        "bad-parent-id.yaml",
    )


# --- Slice 010B: policy-2 derived descriptors with warning approvals ------------

APPROVAL_NAME = "binance-usdm-btcusdt-1h-2024-derived-zero-volume.v1.yaml"
APPROVAL_PATH = f"configs/quality/approvals/{APPROVAL_NAME}"


def _write_year_tree(tmp_path: Path) -> Path:
    """Repo-shaped tree with the full-year policy-2 base descriptor and its
    approval record plus the v1 January rights, mirroring the real repo."""
    datasets = tmp_path / "configs" / "datasets"
    approvals = tmp_path / "configs" / "quality" / "approvals"
    legal = tmp_path / "configs" / "legal"
    datasets.mkdir(parents=True, exist_ok=True)
    approvals.mkdir(parents=True, exist_ok=True)
    legal.mkdir(parents=True, exist_ok=True)
    (datasets / "binance-usdm-btcusdt-1m-2024.yaml").write_text(
        Path("configs/datasets/binance-usdm-btcusdt-1m-2024.yaml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (approvals / APPROVAL_NAME).write_text(
        Path(f"configs/quality/approvals/{APPROVAL_NAME}").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (approvals / "binance-usdm-btcusdt-1m-2024-zero-volume.v1.yaml").write_text(
        Path(
            "configs/quality/approvals/"
            "binance-usdm-btcusdt-1m-2024-zero-volume.v1.yaml"
        ).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (legal / "binance-usdm-provider-rights.v2.yaml").write_text(
        Path("configs/legal/binance-usdm-provider-rights.v2.yaml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    return tmp_path


def _year_derived_yaml(policy: str, approval: str | None) -> str:
    lines = [
        "schema: quantara.derived-dataset-descriptor/v1",
        "dataset_id: binance_usdm_btcusdt_klines_1h_2024",
        "provider: binance",
        "market_type: usd_m_futures",
        "instrument_id: binance:usd_m_futures:BTCUSDT:perpetual",
        "provider_symbol: BTCUSDT",
        "base_asset: BTC",
        "quote_asset: USDT",
        "settlement_asset: USDT",
        "contract_type: perpetual",
        "dataset_type: klines",
        "interval: 1h",
        "base_dataset_id: binance_usdm_btcusdt_klines_1m_2024",
        "base_descriptor: configs/datasets/binance-usdm-btcusdt-1m-2024.yaml",
        "period:",
        '  start: "2024-01-01T00:00:00Z"',
        '  end: "2025-01-01T00:00:00Z"',
        "transformation:",
        "  name: multi_timeframe_aggregation",
        '  version: "1"',
        "schema_version: binance_usdm_kline_1h_v1",
        "timestamp_semantics: closed_interval_v1",
        f'quality_policy_version: "{policy}"',
    ]
    if approval is not None:
        lines.append(f"quality_approval: {approval}")
    lines.append(
        "legal_record: configs/legal/binance-usdm-provider-rights.v2.yaml"
    )
    return "\n".join(lines) + "\n"


def test_policy2_with_approval_accepted(cfg_year: Path) -> None:
    from quantara.derive_descriptor import load_derived_descriptor

    path = write_text(
        cfg_year / "configs" / "datasets" / "derived-year-1h.yaml",
        _year_derived_yaml("2", APPROVAL_PATH),
        name="derived-year-1h.yaml",
    )
    descriptor = load_derived_descriptor(path)
    assert descriptor.quality_policy_version == "2"
    assert descriptor.quality_approval == APPROVAL_PATH
    assert descriptor.dataset_id == "binance_usdm_btcusdt_klines_1h_2024"
    assert descriptor.expected_row_count == 8784


def test_policy2_without_approval_rejected(cfg_year: Path) -> None:
    from quantara.derive_descriptor import load_derived_descriptor

    path = write_text(
        cfg_year / "configs" / "datasets" / "derived-year-1h.yaml",
        _year_derived_yaml("2", None),
        name="derived-year-1h.yaml",
    )
    with pytest.raises(QuantaraError, match="quality_approval"):
        load_derived_descriptor(path)


def test_policy1_with_approval_rejected(cfg_year: Path) -> None:
    from quantara.derive_descriptor import load_derived_descriptor

    path = write_text(
        cfg_year / "configs" / "datasets" / "derived-year-1h.yaml",
        _year_derived_yaml("1", APPROVAL_PATH),
        name="derived-year-1h.yaml",
    )
    with pytest.raises(QuantaraError, match="quality_approval"):
        load_derived_descriptor(path)


def test_policy2_traversal_approval_path_rejected(cfg_year: Path) -> None:
    from quantara.derive_descriptor import load_derived_descriptor

    path = write_text(
        cfg_year / "configs" / "datasets" / "derived-year-1h.yaml",
        _year_derived_yaml("2", "../../../escape.yaml"),
        name="derived-year-1h.yaml",
    )
    with pytest.raises(QuantaraError):
        load_derived_descriptor(path)


def test_policy3_rejected(cfg_year: Path) -> None:
    from quantara.derive_descriptor import load_derived_descriptor

    path = write_text(
        cfg_year / "configs" / "datasets" / "derived-year-1h.yaml",
        _year_derived_yaml("3", APPROVAL_PATH),
        name="derived-year-1h.yaml",
    )
    with pytest.raises(QuantaraError, match="quality_policy_version"):
        load_derived_descriptor(path)


@pytest.fixture()
def cfg_year(tmp_path: Path) -> Path:
    return _write_year_tree(tmp_path)


FROZEN_JAN_SEMANTIC_SHA = (
    "87a2a23b49d36f693cac37e56fd6e06ebb1f72dd6a2a84b61a93356ad2442e6f"
)
FROZEN_Q1_SEMANTIC_SHA = (
    "59fdb7efa84dd0b19b2cf82b53a435d835bd9ab5e1f90252c98bd769c9062a82"
)


def test_january_q1_derived_descriptors_unchanged() -> None:
    """January/Q1 derived descriptors stay v1, loadable, hash-identical."""
    from quantara.derive_descriptor import load_derived_descriptor

    repo_root = Path(__file__).resolve().parents[1]
    jan = load_derived_descriptor(
        repo_root / "configs/datasets/binance-usdm-btcusdt-1h-2024-01-derived.yaml"
    )
    q1 = load_derived_descriptor(
        repo_root / "configs/datasets/binance-usdm-btcusdt-1h-2024-q1-derived.yaml"
    )
    assert jan.quality_policy_version == "1"
    assert q1.quality_policy_version == "1"
    assert descriptor_hash(jan.canonical_semantics()) == FROZEN_JAN_SEMANTIC_SHA
    assert descriptor_hash(q1.canonical_semantics()) == FROZEN_Q1_SEMANTIC_SHA
