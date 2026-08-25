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


@pytest.fixture()
def valid_path(tmp_path: Path) -> Path:
    return write_text(tmp_path, VALID_DESCRIPTOR_YAML)
