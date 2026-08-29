"""Shared pytest fixtures and descriptor/rights YAML builders."""

from __future__ import annotations

import calendar
import json
from datetime import UTC, datetime
from decimal import Decimal
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

VALID_TWO_MONTH_DESCRIPTOR_YAML = """\
schema: quantara.dataset-descriptor/v2
dataset_id: binance_usdm_btcusdt_klines_1m_2024_q1
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
months: ["2024-01", "2024-02"]
period:
  start: "2024-01-01T00:00:00Z"
  end: "2024-03-01T00:00:00Z"
source:
  allowed_hosts: [data.binance.vision]
schema_version: binance_usdm_kline_1m_v1
timestamp_semantics: closed_interval_v1
quality_policy_version: "1"
legal_record: configs/legal/binance-usdm-provider-rights.v2.yaml
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


def build_range_month_csv(
    month: str,
    *,
    drop_indices: frozenset[int] = frozenset(),
    duplicate_indices: frozenset[int] = frozenset(),
) -> bytes:
    """Build one exact calendar month for additive range-pipeline fixtures."""
    start = datetime.strptime(month, "%Y-%m").replace(tzinfo=UTC)
    row_count = calendar.monthrange(start.year, start.month)[1] * 1_440
    start_ms = int(start.timestamp() * 1_000)
    header = (
        "open_time,open,high,low,close,volume,close_time,"
        "quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore\n"
    )
    lines = [header]
    for index in range(row_count):
        if index in drop_indices:
            continue
        open_time = start_ms + index * 60_000
        line = (
            f"{open_time},42571.90,42600.00,42500.10,42590.50,12.5,"
            f"{open_time + 59_999},500000.25,3210,6.25,250000.125,0\n"
        )
        lines.append(line)
        if index in duplicate_indices:
            lines.append(line)
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


def rights_v3_yaml_dict() -> dict:
    """Synthetic-chain rights record with owner-approved private training."""
    document = rights_yaml(
        {
            "acquire_internal": op("OWNER_APPROVED_PENDING_COUNSEL"),
            "retain_raw_internal": op("OWNER_APPROVED_PENDING_COUNSEL"),
            "normalize_internal": op("OWNER_APPROVED_PENDING_COUNSEL"),
            "analyze_internal": op("OWNER_APPROVED_PENDING_COUNSEL"),
            "model_train_internal": op("OWNER_APPROVED_PENDING_COUNSEL"),
            "commercial_production_eligible": op("UNKNOWN"),
            "customer_display": op("UNKNOWN"),
            "raw_redistribution": op("UNKNOWN"),
        }
    )
    document["record_id"] = "binance-usdm-provider-rights.v3"
    document["review_date"] = "2026-08-29"
    return document


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


# --- Additive helpers for data slice 006 (dual-IC feature evaluation) --------

EVALUATION_DESCRIPTOR_TEMPLATE = """\
schema: quantara.evaluation-descriptor/v1
dataset_id: binance_usdm_btcusdt_klines_{interval}_2024_01_evaluation_dual_ic_v1
dataset_type: feature_evaluation
provider: binance
instrument_id: binance:usd_m_futures:BTCUSDT:perpetual
base_dataset_id: binance_usdm_btcusdt_klines_{interval}_2024_01
parent_descriptor: configs/datasets/{parent_name}
period:
  start: "2024-01-01T00:00:00Z"
  end: "2024-02-01T00:00:00Z"
evaluation_set:
  name: btcusdt_core_v1_dual_ic_v1
  version: "1"
features:
  - f_ret_1
  - f_roc_60
  - f_rvol_20
  - f_volratio_20
target: l_fwdret_24
metrics:
  - pearson_ic
  - spearman_ic
schema_version: quantara_feature_evaluation_v1
quality_policy_version: "1"
legal_record: configs/legal/binance-usdm-provider-rights.v2.yaml
"""


def write_evaluation_descriptor(root: Path, interval: str = "1h") -> Path:
    target = (
        root
        / "configs"
        / "datasets"
        / f"binance-usdm-btcusdt-{interval}-2024-01-evaluation-dual-ic-v1.yaml"
    )
    parent_name = f"binance-usdm-btcusdt-{interval}-2024-01-validation-wf-v1.yaml"
    target.write_text(
        EVALUATION_DESCRIPTOR_TEMPLATE.format(
            interval=interval,
            parent_name=parent_name,
        ),
        encoding="utf-8",
    )
    return target


def evaluation_cfg_tree(tmp_path: Path) -> Path:
    """Repo-shaped tree with research, validation, and evaluation descriptors."""
    root = validation_cfg_tree(tmp_path)
    write_validation_descriptor(root, "1h")
    write_validation_descriptor(root, "1d")
    return root


TRAINING_DESCRIPTOR_TEMPLATE = """\
schema: quantara.training-descriptor/v1
dataset_id: binance_usdm_btcusdt_klines_{interval}_2024_q1_training_ridge_v1
dataset_type: model_training
provider: binance
instrument_id: binance:usd_m_futures:BTCUSDT:perpetual
base_dataset_id: binance_usdm_btcusdt_klines_{interval}_2024_q1
parent_descriptor: configs/datasets/{parent_name}
period:
  start: "2024-01-01T00:00:00Z"
  end: "2024-04-01T00:00:00Z"
model: {{ family: ridge_linear, lambda: "1", solver: gauss_elimination_partial_pivot }}
standardization: train_window_zscore
baselines: [majority_class_train_window, sign_f_ret_1]
metrics: [pearson_ic, directional_accuracy, mse]
features: [f_ret_1, f_roc_60, f_rvol_20, f_volratio_20]
target: l_fwdret_24
training_set: {{ name: btcusdt_core_v1_ridge_v1, version: "1" }}
schema_version: quantara_model_training_v1
quality_policy_version: "1"
legal_record: configs/legal/binance-usdm-provider-rights.v3.yaml
"""


def write_training_descriptor(root: Path, interval: str = "1h") -> Path:
    target = (
        root
        / "configs"
        / "datasets"
        / f"binance-usdm-btcusdt-{interval}-2024-q1-training-ridge-v1.yaml"
    )
    parent_name = f"binance-usdm-btcusdt-{interval}-2024-q1-validation-wf-v1.yaml"
    target.write_text(
        TRAINING_DESCRIPTOR_TEMPLATE.format(
            interval=interval,
            parent_name=parent_name,
        ),
        encoding="utf-8",
    )
    legal = root / "configs" / "legal"
    (legal / "binance-usdm-provider-rights.v3.yaml").write_text(
        yaml.safe_dump(rights_v3_yaml_dict(), sort_keys=False),
        encoding="utf-8",
    )
    return target


# --- Additive helpers for data slice 012 (logistic IRLS kill criteria) --------

LOGISTIC_TRAINING_DESCRIPTOR_TEMPLATE = """\
schema: quantara.training-descriptor/v1
dataset_id: binance_usdm_btcusdt_klines_{interval}_2024_q1_training_logistic_v1
dataset_type: model_training
provider: binance
instrument_id: binance:usd_m_futures:BTCUSDT:perpetual
base_dataset_id: binance_usdm_btcusdt_klines_{interval}_2024_q1
parent_descriptor: configs/datasets/{parent_name}
period:
  start: "2024-01-01T00:00:00Z"
  end: "2024-04-01T00:00:00Z"
model:
  family: logistic_irls
  lambda: "1"
  max_iterations: 50
  tolerance: "0.000000000001"
  eta_clamp: "24"
  mu_clamp: "0.000000000001"
  solver: gauss_elimination_partial_pivot
standardization: train_window_zscore
baselines: [majority_class_train_window, sign_f_ret_1, climatology_p]
metrics: [directional_accuracy, log_loss, brier, direction_ic, pearson_ic]
features: [f_ret_1, f_roc_60, f_rvol_20, f_volratio_20]
target: l_fwddir_24
training_set: {{ name: btcusdt_core_v1_logistic_v1, version: "1" }}
kill_criteria:
  directional_accuracy_min: "{directional_accuracy_min}"
  direction_ic_min: "{direction_ic_min}"
  log_loss_max: "{log_loss_max}"
  brier_max: "{brier_max}"
schema_version: quantara_model_training_v1
quality_policy_version: "1"
legal_record: configs/legal/binance-usdm-provider-rights.v3.yaml
"""

# The pre-registered constants (plan slice 012 section 4).
LOGISTIC_KILL_CRITERIA = {
    "directional_accuracy_min": "0.534900284900284900",
    "direction_ic_min": "0.020000000000000000",
    "log_loss_max": "0.762500000000000000",
    "brier_max": "0.250000000000000000",
}
# An unreachable K1 bar used only to drive the kill branch in synthetic tests;
# loading it requires the test to patch the descriptor's approved constants, so
# the real pre-registered bar can never be relaxed by accident.
LOGISTIC_KILL_CRITERIA_IMPOSSIBLE = {
    **LOGISTIC_KILL_CRITERIA,
    "directional_accuracy_min": "0.990000000000000000",
}


def write_training_descriptor_logistic(
    root: Path, interval: str = "1h", kill_criteria: dict | None = None
) -> Path:
    """Write a synthetic-chain logistic training descriptor.

    ``kill_criteria`` defaults to the pre-registered constants; an override
    writes the impossible-criteria variant for dual-outcome pipeline tests.
    """
    target = (
        root
        / "configs"
        / "datasets"
        / f"binance-usdm-btcusdt-{interval}-2024-q1-training-logistic-v1.yaml"
    )
    parent_name = f"binance-usdm-btcusdt-{interval}-2024-q1-validation-wf-v1.yaml"
    constants = dict(kill_criteria or LOGISTIC_KILL_CRITERIA)
    target.write_text(
        LOGISTIC_TRAINING_DESCRIPTOR_TEMPLATE.format(
            interval=interval,
            parent_name=parent_name,
            **constants,
        ),
        encoding="utf-8",
    )
    legal = root / "configs" / "legal"
    legal.mkdir(parents=True, exist_ok=True)
    (legal / "binance-usdm-provider-rights.v3.yaml").write_text(
        yaml.safe_dump(rights_v3_yaml_dict(), sort_keys=False),
        encoding="utf-8",
    )
    return target


# --- Additive helpers for data slice 010 (2024 full-year range) ---------------

YEAR_1M_BASE_DESCRIPTOR_YAML = """\
schema: quantara.dataset-descriptor/v2
dataset_id: binance_usdm_btcusdt_klines_1m_2024
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
months: ["2024-01", "2024-02", "2024-03", "2024-04", "2024-05", "2024-06", \
"2024-07", "2024-08", "2024-09", "2024-10", "2024-11", "2024-12"]
period:
  start: "2024-01-01T00:00:00Z"
  end: "2025-01-01T00:00:00Z"
source:
  allowed_hosts:
    - data.binance.vision
schema_version: binance_usdm_kline_1m_v1
timestamp_semantics: closed_interval_v1
quality_policy_version: "1"
legal_record: configs/legal/binance-usdm-provider-rights.v2.yaml
"""

YEAR_DERIVED_DESCRIPTOR_TEMPLATE = """\
schema: quantara.derived-dataset-descriptor/v1
dataset_id: binance_usdm_btcusdt_klines_{interval}_2024
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
base_dataset_id: binance_usdm_btcusdt_klines_1m_2024
base_descriptor: configs/datasets/binance-usdm-btcusdt-1m-2024.yaml
period:
  start: "2024-01-01T00:00:00Z"
  end: "2025-01-01T00:00:00Z"
transformation:
  name: multi_timeframe_aggregation
  version: "1"
schema_version: binance_usdm_kline_{interval}_v1
timestamp_semantics: closed_interval_v1
quality_policy_version: "1"
legal_record: configs/legal/binance-usdm-provider-rights.v2.yaml
"""

YEAR_BASE_DESCRIPTOR_NAME = "binance-usdm-btcusdt-1m-2024.yaml"


def write_year_derived_descriptor(root: Path, interval: str) -> Path:
    target = (
        root
        / "configs"
        / "datasets"
        / f"binance-usdm-btcusdt-{interval}-2024-derived.yaml"
    )
    target.write_text(
        YEAR_DERIVED_DESCRIPTOR_TEMPLATE.format(interval=interval),
        encoding="utf-8",
    )
    return target


def year_cfg_tree(tmp_path: Path) -> Path:
    """Repo-shaped tree with the year v2 base descriptor, 1h/1d derived
    descriptors, and v1/v2 rights records (data slice 010)."""
    datasets = tmp_path / "configs" / "datasets"
    legal = tmp_path / "configs" / "legal"
    datasets.mkdir(parents=True, exist_ok=True)
    legal.mkdir(parents=True, exist_ok=True)
    (datasets / YEAR_BASE_DESCRIPTOR_NAME).write_text(
        YEAR_1M_BASE_DESCRIPTOR_YAML, encoding="utf-8"
    )
    write_year_derived_descriptor(tmp_path, "1h")
    write_year_derived_descriptor(tmp_path, "1d")
    (legal / "binance-usdm-provider-rights.v1.yaml").write_text(
        yaml.safe_dump(rights_yaml_dict()), encoding="utf-8"
    )
    (legal / RESEARCH_LEGAL_V2_NAME).write_text(
        yaml.safe_dump(rights_v2_yaml_dict()), encoding="utf-8"
    )
    return tmp_path


YEAR_RESEARCH_DESCRIPTOR_TEMPLATE = """\
schema: quantara.research-descriptor/v1
dataset_id: binance_usdm_btcusdt_klines_{interval}_2024_research_core_v1
dataset_type: research_table
provider: binance
instrument_id: binance:usd_m_futures:BTCUSDT:perpetual
base_dataset_id: binance_usdm_btcusdt_klines_{interval}_2024
base_descriptor: configs/datasets/binance-usdm-btcusdt-{interval}-2024-derived.yaml
period:
  start: "2024-01-01T00:00:00Z"
  end: "2025-01-01T00:00:00Z"
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

YEAR_VALIDATION_DESCRIPTOR_TEMPLATE = """\
schema: quantara.validation-descriptor/v1
dataset_id: binance_usdm_btcusdt_klines_{interval}_2024_validation_wf_v1
dataset_type: validation_folds
provider: binance
instrument_id: binance:usd_m_futures:BTCUSDT:perpetual
base_dataset_id: binance_usdm_btcusdt_klines_{interval}_2024
parent_descriptor: configs/datasets/{parent_name}
period:
  start: "2024-01-01T00:00:00Z"
  end: "2025-01-01T00:00:00Z"
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

YEAR_EVALUATION_DESCRIPTOR_TEMPLATE = """\
schema: quantara.evaluation-descriptor/v1
dataset_id: binance_usdm_btcusdt_klines_{interval}_2024_evaluation_dual_ic_v1
dataset_type: feature_evaluation
provider: binance
instrument_id: binance:usd_m_futures:BTCUSDT:perpetual
base_dataset_id: binance_usdm_btcusdt_klines_{interval}_2024
parent_descriptor: configs/datasets/{parent_name}
period:
  start: "2024-01-01T00:00:00Z"
  end: "2025-01-01T00:00:00Z"
evaluation_set:
  name: btcusdt_core_v1_dual_ic_v1
  version: "1"
features:
  - f_ret_1
  - f_roc_60
  - f_rvol_20
  - f_volratio_20
target: l_fwdret_24
metrics:
  - pearson_ic
  - spearman_ic
schema_version: quantara_feature_evaluation_v1
quality_policy_version: "1"
legal_record: configs/legal/binance-usdm-provider-rights.v2.yaml
"""


def write_year_research_descriptor(root: Path, interval: str = "1h") -> Path:
    target = (
        root
        / "configs"
        / "datasets"
        / f"binance-usdm-btcusdt-{interval}-2024-research-core-v1.yaml"
    )
    target.write_text(
        YEAR_RESEARCH_DESCRIPTOR_TEMPLATE.format(interval=interval),
        encoding="utf-8",
    )
    return target


def write_year_validation_descriptor(root: Path, interval: str = "1h") -> Path:
    target = (
        root
        / "configs"
        / "datasets"
        / f"binance-usdm-btcusdt-{interval}-2024-validation-wf-v1.yaml"
    )
    parent_name = f"binance-usdm-btcusdt-{interval}-2024-research-core-v1.yaml"
    target.write_text(
        YEAR_VALIDATION_DESCRIPTOR_TEMPLATE.format(
            interval=interval, parent_name=parent_name
        ),
        encoding="utf-8",
    )
    return target


def write_year_evaluation_descriptor(root: Path, interval: str = "1h") -> Path:
    target = (
        root
        / "configs"
        / "datasets"
        / f"binance-usdm-btcusdt-{interval}-2024-evaluation-dual-ic-v1.yaml"
    )
    parent_name = f"binance-usdm-btcusdt-{interval}-2024-validation-wf-v1.yaml"
    target.write_text(
        YEAR_EVALUATION_DESCRIPTOR_TEMPLATE.format(
            interval=interval, parent_name=parent_name
        ),
        encoding="utf-8",
    )
    return target


def year_chain_cfg_tree(tmp_path: Path) -> Path:
    """Repo-shaped tree with the complete year 1m/1h/1d descriptor chain."""
    root = year_cfg_tree(tmp_path)
    write_year_research_descriptor(root, "1h")
    write_year_validation_descriptor(root, "1h")
    write_year_evaluation_descriptor(root, "1h")
    return root


# --- Additive helpers for data slice 015-extended (2020/2021/2022 years) ------

# The three approved slice 015-extended calendar years. The tuple is the
# single source of truth for the per-year test helpers below; a year absent
# from it has no approved identity table and must fail descriptor loading.
EXTENDED_YEARS: tuple[int, ...] = (2020, 2021, 2022)

EXTENDED_YEAR_1M_DESCRIPTOR_TEMPLATE = """\
schema: quantara.dataset-descriptor/v2
dataset_id: binance_usdm_btcusdt_klines_1m_{year}
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
months: {months}
period:
  start: "{year}-01-01T00:00:00Z"
  end: "{next_year}-01-01T00:00:00Z"
source:
  allowed_hosts:
    - data.binance.vision
schema_version: binance_usdm_kline_1m_v1
timestamp_semantics: closed_interval_v1
quality_policy_version: "1"
legal_record: configs/legal/binance-usdm-provider-rights.v3.yaml
"""

EXTENDED_YEAR_DERIVED_DESCRIPTOR_TEMPLATE = """\
schema: quantara.derived-dataset-descriptor/v1
dataset_id: binance_usdm_btcusdt_klines_{interval}_{year}
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
base_dataset_id: binance_usdm_btcusdt_klines_1m_{year}
base_descriptor: configs/datasets/binance-usdm-btcusdt-1m-{year}.yaml
period:
  start: "{year}-01-01T00:00:00Z"
  end: "{next_year}-01-01T00:00:00Z"
transformation:
  name: multi_timeframe_aggregation
  version: "1"
schema_version: binance_usdm_kline_{interval}_v1
timestamp_semantics: closed_interval_v1
quality_policy_version: "1"
legal_record: configs/legal/binance-usdm-provider-rights.v3.yaml
"""


def extended_year_months(year: int) -> list[str]:
    """The twelve consecutive calendar months of one approved year."""
    return [f"{year}-{month:02d}" for month in range(1, 13)]


def extended_year_1m_descriptor_text(year: int) -> str:
    """Render the approved 1m year descriptor for one 015-extended year."""
    months = extended_year_months(year)
    return EXTENDED_YEAR_1M_DESCRIPTOR_TEMPLATE.format(
        year=year,
        next_year=year + 1,
        months="[" + ", ".join(f'"{month}"' for month in months) + "]",
    )


def extended_year_derived_descriptor_text(year: int, interval: str) -> str:
    """Render the approved 1h/1d derived descriptor for one year."""
    return EXTENDED_YEAR_DERIVED_DESCRIPTOR_TEMPLATE.format(
        year=year, next_year=year + 1, interval=interval
    )


def write_extended_year_descriptors(root: Path, year: int) -> dict[str, Path]:
    """Write the 1m/1h/1d descriptor trio for one 015-extended year."""
    datasets = root / "configs" / "datasets"
    datasets.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    base = datasets / f"binance-usdm-btcusdt-1m-{year}.yaml"
    base.write_text(extended_year_1m_descriptor_text(year), encoding="utf-8")
    written["1m"] = base
    for interval in ("1h", "1d"):
        target = datasets / f"binance-usdm-btcusdt-{interval}-{year}-derived.yaml"
        target.write_text(
            extended_year_derived_descriptor_text(year, interval), encoding="utf-8"
        )
        written[interval] = target
    return written


def extended_year_cfg_tree(tmp_path: Path, year: int) -> Path:
    """Repo-shaped tree with one 015-extended year's descriptors and rights."""
    legal = tmp_path / "configs" / "legal"
    legal.mkdir(parents=True, exist_ok=True)
    (legal / "binance-usdm-provider-rights.v3.yaml").write_text(
        yaml.safe_dump(rights_v3_yaml_dict(), sort_keys=False), encoding="utf-8"
    )
    write_extended_year_descriptors(tmp_path, year)
    return tmp_path


def write_synthetic_sidecar(path: Path, ics: list[Decimal]) -> Path:
    """Write a frozen-shape IC sidecar for diagnostic integration tests."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "quantara.ic_stability_sidecar/v1",
                "attempt_id": path.stem.removeprefix("per_fold_"),
                "code_revision": "f" * 40,
                "records": [
                    {
                        "fold_index": fold_index,
                        "direction_ic": str(ic),
                        "direction_ic_defined": True,
                    }
                    for fold_index, ic in enumerate(ics)
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path
