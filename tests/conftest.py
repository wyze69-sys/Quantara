"""Shared pytest fixtures and descriptor/rights YAML builders."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

VALID_DESCRIPTOR_YAML = """\
schema: quantara.dataset-descriptor/v1
dataset_id: binance_usdm_btcusdt_klines_1m_2024_01
provider: binance
market_type: usd_m_futures
instrument_id: binance:usd_m_futures:BTCUSDT:perpetual
provider_symbol: BTCUSDT
base_asset: BTC
quote_asset: USDT
settlement_asset: USDT
contract_type: perpetual
dataset_type: klines
interval: 1m
period:
  start: "2024-01-01T00:00:00Z"
  end: "2024-02-01T00:00:00Z"
source:
  archive_url: https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01.zip
  checksum_url: https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01.zip.CHECKSUM
  allowed_hosts:
    - data.binance.vision
  member_pattern: "^BTCUSDT-1m-2024-01\\\\.csv$"
schema_version: binance_usdm_kline_1m_v1
timestamp_semantics: closed_interval_v1
quality_policy_version: "1"
legal_record: configs/legal/binance-usdm-provider-rights.v1.yaml
"""


def write_text(tmp_path: Path, text: str, name: str = "descriptor.yaml") -> Path:
    target = tmp_path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def op(state: str) -> dict[str, str]:
    return {
        "state": state,
        "source_terms": "Binance Terms of Use; data.binance.vision",
        "review_date": "2026-08-24",
        "reviewer": "wyze69-sys",
        "rationale": "test fixture",
    }


def rights_yaml(operations: dict) -> dict:
    return {
        "schema": "quantara.provider-rights/v1",
        "record_id": "binance-usdm-provider-rights.v1",
        "provider": "binance",
        "reviewer": "wyze69-sys",
        "review_date": "2026-08-24",
        "operations": operations,
    }


def rights_yaml_dict():
    return rights_yaml(
        {
            "acquire_internal": op("OWNER_APPROVED_PENDING_COUNSEL"),
            "retain_raw_internal": op("OWNER_APPROVED_PENDING_COUNSEL"),
            "normalize_internal": op("OWNER_APPROVED_PENDING_COUNSEL"),
            "analyze_internal": op("UNKNOWN"),
            "model_train_internal": op("UNKNOWN"),
            "commercial_production_eligible": op("UNKNOWN"),
            "customer_display": op("UNKNOWN"),
            "raw_redistribution": op("UNKNOWN"),
        }
    )


MONTH_ROW_COUNT = 44_640
MONTH_OPEN_START = 1704067200000


def build_month_csv() -> bytes:
    header = (
        "open_time,open,high,low,close,volume,close_time,"
        "quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore\n"
    )
    lines = [header]
    for i in range(MONTH_ROW_COUNT):
        t = MONTH_OPEN_START + i * 60_000
        lines.append(
            f"{t},42571.90,42600.00,42500.10,42590.50,12.5,"
            f"{t + 59_999},500000.25,3210,6.25,250000.125,0\n"
        )
    return "".join(lines).encode("utf-8")


def dataset_dir_for(data_root):
    return (
        Path(data_root)
        / "datasets"
        / "binance"
        / "usdm"
        / "klines"
        / "BTCUSDT"
        / "1m"
        / "year=2024"
        / "month=01"
    )


def build_varying_month_csv() -> bytes:
    """Slice 003b additive: like build_month_csv but with deterministic
    time-varying closes/volumes so derived bars are non-degenerate research
    parents (a constant series would trip the loud zero-variance check)."""
    header = (
        "open_time,open,high,low,close,volume,close_time,"
        "quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore\n"
    )
    lines = [header]
    for i in range(MONTH_ROW_COUNT):
        t = MONTH_OPEN_START + i * 60_000
        c = 42500 + (i % 97) * 3
        v = f"{10 + (i % 13)}.5"
        lines.append(
            f"{t},{c},{c + 5},{c - 5},{c},{v},{t + 59_999},500000.25,3210,6.25,250000.125,0\n"
        )
    return "".join(lines).encode("utf-8")


@pytest.fixture()
def valid_path(tmp_path: Path) -> Path:
    return write_text(tmp_path, VALID_DESCRIPTOR_YAML)


# --- Additive helpers for data slice 002 (plan Tasks 6+) ----------------------

DERIVED_DESCRIPTOR_TEMPLATE = """\
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
base_descriptor: configs/datasets/{base_name}
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

BASE_DESCRIPTOR_NAME = "binance-usdm-btcusdt-1m-2024-01.yaml"

HOUR_MS = 3_600_000


def make_minute_row(
    open_time_ms: int,
    o="100",
    h="110",
    lo="90",
    c="105",
    bv="1.5",
    qv="150",
    n=10,
    tbv="0.5",
    tqv="50",
    ignore="0",
):
    from decimal import Decimal

    from quantara.canonical import CanonicalRow

    d = Decimal
    return CanonicalRow(
        identity=(
            "binance",
            "usd_m_futures",
            "binance:usd_m_futures:BTCUSDT:perpetual",
            "BTCUSDT",
            "BTC",
            "USDT",
            "USDT",
            "perpetual",
            "1m",
            "binance_usdm_kline_1m_v1",
        ),
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + 59_999,
        nominal_available_ms=open_time_ms + 60_000,
        open=d(o),
        high=d(h),
        low=d(lo),
        close=d(c),
        base_asset_volume=d(bv),
        quote_asset_volume=d(qv),
        trade_count=int(n),
        taker_buy_base_volume=d(tbv),
        taker_buy_quote_volume=d(tqv),
        source_ignore=ignore,
    )


def build_month_minute_rows(count: int = MONTH_ROW_COUNT) -> list:
    return [make_minute_row(MONTH_OPEN_START + i * 60_000) for i in range(count)]


def derived_cfg_tree(tmp_path: Path) -> Path:
    """Repo-shaped config tree with the base descriptor and rights record."""
    datasets = tmp_path / "configs" / "datasets"
    legal = tmp_path / "configs" / "legal"
    datasets.mkdir(parents=True, exist_ok=True)
    legal.mkdir(parents=True, exist_ok=True)
    (datasets / BASE_DESCRIPTOR_NAME).write_text(VALID_DESCRIPTOR_YAML, encoding="utf-8")
    (legal / "binance-usdm-provider-rights.v1.yaml").write_text(
        yaml.safe_dump(rights_yaml_dict()), encoding="utf-8"
    )
    return tmp_path


def write_derived_descriptor(root: Path, interval: str) -> Path:
    target = root / "configs" / "datasets" / f"binance-usdm-btcusdt-{interval}-2024-01-derived.yaml"
    target.write_text(
        DERIVED_DESCRIPTOR_TEMPLATE.format(interval=interval, base_name=BASE_DESCRIPTOR_NAME),
        encoding="utf-8",
    )
    return target


# --- Additive helpers for data slice 003b (research tables) -------------------

RESEARCH_LEGAL_V2_NAME = "binance-usdm-provider-rights.v2.yaml"


def rights_v2_yaml_dict() -> dict:
    """Mirrors configs/legal/binance-usdm-provider-rights.v2.yaml semantics."""
    return rights_yaml(
        {
            "acquire_internal": op("OWNER_APPROVED_PENDING_COUNSEL"),
            "retain_raw_internal": op("OWNER_APPROVED_PENDING_COUNSEL"),
            "normalize_internal": op("OWNER_APPROVED_PENDING_COUNSEL"),
            "analyze_internal": op("OWNER_APPROVED_PENDING_COUNSEL"),
            "model_train_internal": op("UNKNOWN"),
            "commercial_production_eligible": op("UNKNOWN"),
            "customer_display": op("UNKNOWN"),
            "raw_redistribution": op("UNKNOWN"),
        }
    )


def research_cfg_tree(tmp_path: Path) -> Path:
    """Repo-shaped tree: 1m base + 1h/1d derived descriptors + v1/v2 rights."""
    root = derived_cfg_tree(tmp_path)
    write_derived_descriptor(root, "1h")
    write_derived_descriptor(root, "1d")
    (root / "configs" / "legal" / RESEARCH_LEGAL_V2_NAME).write_text(
        yaml.safe_dump(rights_v2_yaml_dict()), encoding="utf-8"
    )
    return root


RESEARCH_DESCRIPTOR_TEMPLATE = """\
schema: quantara.research-descriptor/v1
dataset_id: binance_usdm_btcusdt_klines_{interval}_2024_01_research_core_v1
dataset_type: research_table
provider: binance
instrument_id: binance:usd_m_futures:BTCUSDT:perpetual
base_dataset_id: binance_usdm_btcusdt_klines_{interval}_2024_01
base_descriptor: configs/datasets/{base_name}
period:
  start: "2024-01-01T00:00:00Z"
  end: "2024-02-01T00:00:00Z"
feature_set:
  name: btcusdt_core_v1
  version: "1"
parameters:
  roc_window: 60
  vol_window: 20
  volume_window: 20
  label_horizon: 24
schema_version: quantara_research_featureset_v1
quality_policy_version: "1"
legal_record: configs/legal/binance-usdm-provider-rights.v2.yaml
"""


def write_research_descriptor(root: Path, interval: str = "1h") -> Path:
    target = (
        root
        / "configs"
        / "datasets"
        / f"binance-usdm-btcusdt-{interval}-2024-01-research-core-v1.yaml"
    )
    target.write_text(
        RESEARCH_DESCRIPTOR_TEMPLATE.format(
            interval=interval,
            base_name=f"binance-usdm-btcusdt-{interval}-2024-01-derived.yaml",
        ),
        encoding="utf-8",
    )
    return target


HOUR_BAR_START = 1_704_067_200_000  # 2024-01-01T00:00:00Z, hour bars


def make_hour_bar(open_time_ms: int, close: str, volume: str = "12.5"):
    """One canonical-shaped 1h bar row (23-field content array ordering is the
    caller's concern; this builds CanonicalRow objects used as parents)."""
    from decimal import Decimal

    from quantara.canonical import CanonicalRow

    d = Decimal
    return CanonicalRow(
        identity=(
            "binance",
            "usd_m_futures",
            "binance:usd_m_futures:BTCUSDT:perpetual",
            "BTCUSDT",
            "BTC",
            "USDT",
            "USDT",
            "perpetual",
            "1h",
            "binance_usdm_kline_1h_v1",
        ),
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + 3_599_999,
        nominal_available_ms=open_time_ms + 3_600_000,
        open=d(close),
        high=d(close),
        low=d(close),
        close=d(close),
        base_asset_volume=d(volume),
        quote_asset_volume=d("150"),
        trade_count=10,
        taker_buy_base_volume=d("0.5"),
        taker_buy_quote_volume=d("50"),
        source_ignore="0",
    )


def publish_month_via_slice_001(tmp_path: Path, price_offset: int = 0):
    """Publish the synthetic 44,640-row month through the REAL slice 001
    pipeline (MockTransport); returns (repo_root, data_root). A nonzero
    ``price_offset`` shifts every close so a second call against the SAME
    tmp tree legitimately republishes a corrected dataset."""
    import hashlib
    import zipfile

    import httpx

    from quantara.pipeline import run_pipeline

    root = research_cfg_tree(tmp_path)
    archive = tmp_path / f"BTCUSDT-1m-2024-01-{price_offset}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        csv = build_varying_month_csv().decode("utf-8")
        if price_offset:
            lines = csv.splitlines(keepends=True)
            header, body = lines[0], lines[1:]
            shifted = []
            for line in body:
                fields = line.split(",")
                # Shift the whole OHLC complex so invariants still hold.
                for i in (1, 2, 3, 4):
                    fields[i] = str(int(fields[i]) + price_offset)
                shifted.append(",".join(fields))
            csv = header + "".join(shifted)
        zf.writestr("BTCUSDT-1m-2024-01.csv", csv)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".CHECKSUM"):
            return httpx.Response(200, text=f"{digest}  BTCUSDT-1m-2024-01.zip\n")
        return httpx.Response(200, content=archive.read_bytes())

    base_descriptor = tmp_path / "configs" / "datasets" / BASE_DESCRIPTOR_NAME
    code = run_pipeline(
        descriptor_path=base_descriptor,
        data_root=tmp_path / "data",
        repo_root=root,
        transport=httpx.MockTransport(handler),
    )
    assert code == 0
    return root, tmp_path / "data"


# --- Additive helpers for data slice 004 (validation folds) -------------------

VALIDATION_DESCRIPTOR_TEMPLATE = """\
schema: quantara.validation-descriptor/v1
dataset_id: binance_usdm_btcusdt_klines_{interval}_2024_01_validation_wf_v1
dataset_type: validation_folds
provider: binance
instrument_id: binance:usd_m_futures:BTCUSDT:perpetual
base_dataset_id: binance_usdm_btcusdt_klines_{interval}_2024_01
parent_descriptor: configs/datasets/{parent_name}
period:
  start: "2024-01-01T00:00:00Z"
  end: "2024-02-01T00:00:00Z"
feature_set:
  name: btcusdt_core_v1
  version: "1"
scheme: anchored_walkforward_v1
fold_set:
  name: btcusdt_core_v1_wf72_v1
  version: "1"
parameters:
  test_size: 72
  min_train_size: 336
schema_version: quantara_validation_folds_v1
quality_policy_version: "1"
legal_record: configs/legal/binance-usdm-provider-rights.v2.yaml
"""


def write_validation_descriptor(root: Path, interval: str = "1h") -> Path:
    target = (
        root
        / "configs"
        / "datasets"
        / f"binance-usdm-btcusdt-{interval}-2024-01-validation-wf-v1.yaml"
    )
    parent_name = f"binance-usdm-btcusdt-{interval}-2024-01-research-core-v1.yaml"
    target.write_text(
        VALIDATION_DESCRIPTOR_TEMPLATE.format(
            interval=interval,
            parent_name=parent_name,
        ),
        encoding="utf-8",
    )
    return target


def validation_cfg_tree(tmp_path: Path) -> Path:
    """Repo-shaped tree with 1h/1d research parents and validation descriptors."""
    root = research_cfg_tree(tmp_path)
    write_research_descriptor(root, "1h")
    write_research_descriptor(root, "1d")
    return root
