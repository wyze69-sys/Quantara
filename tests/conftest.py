"""Shared pytest fixtures and descriptor/rights YAML builders."""

from __future__ import annotations

from pathlib import Path

import pytest

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
        / "datasets" / "binance" / "usdm" / "klines"
        / "BTCUSDT" / "1m" / "year=2024" / "month=01"
    )


@pytest.fixture()
def valid_path(tmp_path: Path) -> Path:
    return write_text(tmp_path, VALID_DESCRIPTOR_YAML)
