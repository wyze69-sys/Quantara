"""D01 closed descriptors: frozen inventory, source construction, and fail-closed loading."""

import re
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import yaml

from quantara.protocol_v11 import load_protocol_v11
from quantara.series_descriptor import (
    SERIES_REGISTRY,
    SeriesArchive,
    SeriesDescriptor,
    SeriesDescriptorError,
    load_series_descriptor,
)

ROOT = Path(__file__).resolve().parents[1]
SERIES_ROOT = ROOT / "configs/series"
USDM_RIGHTS = "binance-usdm-provider-rights.v3"
# Independent expectations transcribed from the assigned D01 packet, not from
# either the new registry or the new YAML files.
EXPECTED = {
    "btc_settled_funding": (
        "binance-usdm-btcusdt-funding-settled-2020-2024", "BTCUSDT", "fundingRate",
    ),
    "btc_open_interest_5m": (
        "binance-usdm-btcusdt-open-interest-2020-09-2024", "BTCUSDT", "metrics",
    ),
    "btc_mark_price_1m": (
        "binance-usdm-btcusdt-mark-1m-2020-2024", "BTCUSDT", "markPriceKlines",
    ),
    "btc_index_price_1m": (
        "binance-usdm-btcusdt-index-1m-2020-2024", "BTCUSDT", "indexPriceKlines",
    ),
    "btc_native_premium_1m": (
        "binance-usdm-btcusdt-premium-1m-2020-2024", "BTCUSDT", "premiumIndexKlines",
    ),
    "binance_btc_spot_ohlcv_1m": (
        "binance-spot-btcusdt-1m-2020-2024", "BTCUSDT", "spot",
    ),
    "kraken_xbtusd_spot_ohlcv_1h": (
        "kraken-spot-xbtusd-1h-2020-2024", "XBTUSD", "kraken",
    ),
    "ethusdt_perp_ohlcv_1m": (
        "binance-usdm-ethusdt-traded-1m-2020-2024", "ETHUSDT", "klines",
    ),
    "eth_settled_funding": (
        "binance-usdm-ethusdt-funding-settled-2020-2024", "ETHUSDT", "fundingRate",
    ),
    "eth_open_interest_5m": (
        "binance-usdm-ethusdt-open-interest-2021-12-2024", "ETHUSDT", "metrics",
    ),
    "eth_mark_price_1m": (
        "binance-usdm-ethusdt-mark-1m-2020-2024", "ETHUSDT", "markPriceKlines",
    ),
    "eth_index_price_1m": (
        "binance-usdm-ethusdt-index-1m-2020-2024", "ETHUSDT", "indexPriceKlines",
    ),
    "eth_native_premium_1m": (
        "binance-usdm-ethusdt-premium-1m-2020-2024", "ETHUSDT", "premiumIndexKlines",
    ),
}
OI_STARTS = {"btc_open_interest_5m": "2020-09-01", "eth_open_interest_5m": "2021-12-01"}
KRAKEN_ID = "1ptNqWYidLkhb2VAKuLCxmp2OXEfGO-AP"


def config_path(series_id: str) -> Path:
    return SERIES_ROOT / f"{EXPECTED[series_id][0]}.yaml"


def document(series_id: str = "btc_mark_price_1m") -> dict:
    return yaml.safe_load(config_path(series_id).read_text(encoding="utf-8"))


def write_document(tmp_path: Path, raw: object) -> Path:
    path = tmp_path / "descriptor.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return path


def expected_periods(series_id: str) -> tuple[str, ...]:
    if series_id in OI_STARTS:
        start = date.fromisoformat(OI_STARTS[series_id])
        return tuple(
            (start + timedelta(days=offset)).isoformat()
            for offset in range((date(2024, 12, 31) - start).days + 1)
        )
    if EXPECTED[series_id][2] == "kraken":
        return ("2020-2024",)
    return tuple(f"{year}-{month:02d}" for year in range(2020, 2025) for month in range(1, 13))


def test_exact_registry_matches_frozen_protocol_and_config_inventory() -> None:
    # The existing protocol loader authenticates the frozen protocol hash, so
    # editing both new files cannot silently widen the scientific inventory.
    inventory = load_protocol_v11(ROOT / "configs/protocols/quantara-protocol-v1_1.yaml")
    remaining = {
        row["series_id"]: row for row in inventory.to_dict()["inventory"]
        if row["status"] == "frozen_inventory"
    }
    assert set(SERIES_REGISTRY) == set(EXPECTED) == set(remaining)
    assert {path.stem for path in SERIES_ROOT.glob("*.yaml")} == {
        row[0] for row in EXPECTED.values()
    }
    for series_id, row in remaining.items():
        actual = load_series_descriptor(config_path(series_id)).to_dict()
        for field in ("provider", "venue", "market_type"):
            assert actual[field] == row[field]
        assert actual["observation_cadence"] == row["native_interval"]


@pytest.mark.parametrize("series_id", EXPECTED)
def test_configs_round_trip_and_every_generated_source(series_id: str, tmp_path: Path) -> None:
    descriptor = load_series_descriptor(config_path(series_id))
    raw = document(series_id)
    assert descriptor.to_dict() == raw
    restored = load_series_descriptor(write_document(tmp_path, descriptor.to_dict()))
    assert restored == descriptor
    assert restored.canonical_semantics() == descriptor.canonical_semantics()
    assert raw["schema"] == "quantara.series-descriptor/v1"
    assert raw["period"] == {
        "start": OI_STARTS.get(series_id, "2020-01-01"),
        "end": "2024-12-31", "timezone": "UTC",
    }
    assert descriptor.object_periods == expected_periods(series_id)
    _, symbol, family = EXPECTED[series_id]
    assert raw["provider_symbol"] == symbol
    expected_rights = {
        "spot": "binance-spot-provider-rights.v1", "kraken": "kraken-spot-provider-rights.v1",
    }.get(family, USDM_RIGHTS)
    assert descriptor.legal_record == expected_rights
    for period in descriptor.object_periods:
        archive = descriptor.archive_for(period)
        if family == "kraken":
            host = "drive.usercontent.google.com"
            expected_url = f"https://{host}/download?id={KRAKEN_ID}&export=download"
            expected_member = "master_q4/XBTUSD_60.csv"
            assert archive.checksum_url is None
        else:
            host = "data.binance.vision"
            if family == "metrics":
                directory = f"data/futures/um/daily/metrics/{symbol}"
                stem = f"{symbol}-metrics-{period}"
            elif family == "fundingRate":
                directory = f"data/futures/um/monthly/fundingRate/{symbol}"
                stem = f"{symbol}-fundingRate-{period}"
            else:
                directory = (
                    "data/spot/monthly/klines/BTCUSDT/1m" if family == "spot" else
                    f"data/futures/um/monthly/{family}/{symbol}/1m"
                )
                stem = f"{symbol}-1m-{period}"
            expected_url = f"https://{host}/{directory}/{stem}.zip"
            expected_member = f"{stem}.csv"
            assert archive.checksum_url == expected_url + ".CHECKSUM"
        assert archive.archive_url == expected_url
        assert archive.member == expected_member
        assert descriptor.allowed_hosts == (host,)
        assert urlsplit(archive.archive_url).hostname == host
        assert re.fullmatch(archive.member_pattern, expected_member)
        for bad_member in ("../" + expected_member, "/" + expected_member,
                           expected_member + "\n", expected_member.replace(".csv", "Xcsv")):
            assert not re.fullmatch(archive.member_pattern, bad_member)


@pytest.mark.parametrize("series_id", EXPECTED)
@pytest.mark.parametrize("year", [2019, 2025])
def test_period_years_are_closed(series_id: str, year: int, tmp_path: Path) -> None:
    raw = document(series_id)
    for field, value in (("start", f"{year}-01-01"), ("end", f"{year}-12-31")):
        bad = deepcopy(raw)
        bad["period"][field] = value
        with pytest.raises(SeriesDescriptorError, match=rf"period\.{field}"):
            load_series_descriptor(write_document(tmp_path, bad))
    descriptor = load_series_descriptor(config_path(series_id))
    for period in (f"{year}-01", f"{year}-01-01", f"{year}-{year}"):
        with pytest.raises(SeriesDescriptorError, match="period"):
            descriptor.archive_for(period)


@pytest.mark.parametrize("series_id", OI_STARTS)
def test_oi_start_and_daily_objects_are_not_snapshot_cadence(
    series_id: str, tmp_path: Path,
) -> None:
    raw = document(series_id)
    descriptor = load_series_descriptor(config_path(series_id))
    assert raw["object_cadence"] == "daily"
    assert raw["observation_cadence"] == "5m"
    assert raw["canonical_value"] == "sum_open_interest"
    assert raw["timestamp_role"] == "UNRESOLVED_CONSERVATIVE"
    prior = (date.fromisoformat(OI_STARTS[series_id]) - timedelta(days=1)).isoformat()
    raw["period"]["start"] = prior
    with pytest.raises(SeriesDescriptorError, match=r"period\.start"):
        load_series_descriptor(write_document(tmp_path, raw))
    with pytest.raises(SeriesDescriptorError, match="period"):
        descriptor.archive_for(prior)
    assert len(descriptor.object_periods) == (1583 if series_id.startswith("btc") else 1127)


@pytest.mark.parametrize("series_id", EXPECTED)
@pytest.mark.parametrize("bad", ["../2024-01", "/2024-01", "C:\\2024-01", "2024-01/..",
                                     "2024-01?url=https://evil.invalid", "2024-01\n", "2024-13",
                                     "2024-02-30", "2024-1", "２０２４-01", None, 202401, []])
def test_object_period_injection_is_rejected(series_id: str, bad: object) -> None:
    descriptor = load_series_descriptor(config_path(series_id))
    with pytest.raises(SeriesDescriptorError, match="period"):
        descriptor.archive_for(bad)
    with pytest.raises(SeriesDescriptorError, match="period"):
        SeriesArchive(series_id, bad)


@pytest.mark.parametrize("field,bad", [
    ("provider", "unregistered"), ("provider_symbol", "SOLUSDT"),
    ("provider_symbol", "../BTCUSDT"), ("provider_symbol", "/BTCUSDT"),
    ("provider_symbol", "BTCUSDT?url=https://evil.invalid"),
    ("observation_cadence", "5m"), ("object_cadence", "daily"),
    ("parser", "../../parser.py"), ("parser", "unregistered"),
    ("legal_record", "binance-spot-provider-rights.v1"),
    ("legal_record", "../../rights.yaml"), ("legal_record", None),
    ("canonical_value", "sum_open_interest_value"), ("timestamp_role", "interval_end"),
    ("schema", "quantara.series-descriptor/v2"),
])
def test_fixed_fields_reject_tampering(field: str, bad: object, tmp_path: Path) -> None:
    raw = document()
    raw[field] = bad
    with pytest.raises(SeriesDescriptorError, match=field):
        load_series_descriptor(write_document(tmp_path, raw))


@pytest.mark.parametrize("field", ["feature", "features", "feature_columns", "label", "labels",
                                   "model", "model_features", "target", "interval", "symbol",
                                   "month", "date", "path", "anything_else"])
def test_unknown_and_model_fields_rejected_at_every_level(field: str, tmp_path: Path) -> None:
    for block in (None, "source", "period"):
        raw = document()
        (raw if block is None else raw[block])[field] = "../injected"
        with pytest.raises(SeriesDescriptorError, match="unknown.*keys"):
            load_series_descriptor(write_document(tmp_path, raw))


@pytest.mark.parametrize("host", ["evil.invalid", "data.binance.vision.evil.invalid",
                                  "data.binance.vision@evil.invalid", "../data.binance.vision",
                                  "https://data.binance.vision", "drive.google.com"])
@pytest.mark.parametrize("series_id", ["btc_settled_funding", "kraken_xbtusd_spot_ohlcv_1h"])
def test_host_is_frozen_per_provider(host: str, series_id: str, tmp_path: Path) -> None:
    raw = document(series_id)
    raw["source"]["allowed_hosts"] = [host]
    with pytest.raises(SeriesDescriptorError, match="allowed_hosts"):
        load_series_descriptor(write_document(tmp_path, raw))


@pytest.mark.parametrize("field", ["archive_url", "checksum_url", "member", "member_pattern",
                                   "month", "date", "path"])
def test_binance_source_overrides_are_forbidden(field: str, tmp_path: Path) -> None:
    raw = document()
    raw["source"][field] = "../../https://evil.invalid/2025-01"
    with pytest.raises(SeriesDescriptorError, match="unknown.*keys"):
        load_series_descriptor(write_document(tmp_path, raw))


def test_kraken_is_only_the_frozen_member_with_no_d02_anchors(tmp_path: Path) -> None:
    raw = document("kraken_xbtusd_spot_ohlcv_1h")
    assert raw["source"] == {
        "allowed_hosts": ["drive.usercontent.google.com"],
        "object_id": KRAKEN_ID, "member": "master_q4/XBTUSD_60.csv",
    }
    assert raw["observation_cadence"] == "1h"
    assert raw["timestamp_role"] == "DOCUMENTED_INTERVAL_START"
    assert raw["canonical_value"] == "ohlcvt"
    assert raw["no_trade_intervals"] == "omitted"
    for field in ("object_id", "member"):
        for bad_value in ("../XBTUSD_60.csv", "/XBTUSD_60.csv", "https://evil.invalid",
                          "master_q4/XBTUSD_1.csv"):
            bad = deepcopy(raw)
            bad["source"][field] = bad_value
            with pytest.raises(SeriesDescriptorError, match=field):
                load_series_descriptor(write_document(tmp_path, bad))
    for field in ("remote_size", "crc32", "member_sha256", "range_requests"):
        bad = deepcopy(raw)
        bad["source"][field] = "forbidden_in_D01"
        with pytest.raises(SeriesDescriptorError, match="unknown.*keys"):
            load_series_descriptor(write_document(tmp_path, bad))


def test_header_policies_preserve_physical_row_zero() -> None:
    spot = load_series_descriptor(config_path("binance_btc_spot_ohlcv_1m"))
    assert all(spot.archive_for(period).csv_header == "absent" for period in spot.object_periods)
    traded = load_series_descriptor(config_path("ethusdt_perp_ohlcv_1m"))
    assert traded.archive_for("2021-12").csv_header == "absent"
    assert traded.archive_for("2022-01").csv_header == "present"
    for series_id, (_, _, family) in EXPECTED.items():
        descriptor = load_series_descriptor(config_path(series_id))
        if family in ("markPriceKlines", "indexPriceKlines", "premiumIndexKlines"):
            assert descriptor.archive_for("2022-11").csv_header == "absent"
            assert descriptor.archive_for("2022-12").csv_header == "present"
        elif family in ("fundingRate", "metrics"):
            assert descriptor.archive_for(descriptor.object_periods[0]).csv_header == "present"
    kraken = load_series_descriptor(config_path("kraken_xbtusd_spot_ohlcv_1h"))
    assert kraken.archive_for("2020-2024").csv_header == "absent"


@pytest.mark.parametrize("series_id", EXPECTED)
def test_missing_and_wrong_rights_binding_fails_to_load(series_id: str, tmp_path: Path) -> None:
    raw = document(series_id)
    del raw["legal_record"]
    with pytest.raises(SeriesDescriptorError, match="missing.*legal_record"):
        load_series_descriptor(write_document(tmp_path, raw))
    raw = document(series_id)
    raw["legal_record"] = "unregistered-rights.v1"
    with pytest.raises(SeriesDescriptorError, match="legal_record"):
        load_series_descriptor(write_document(tmp_path, raw))
    with pytest.raises(SeriesDescriptorError, match="rights record"):
        load_series_descriptor(config_path(series_id), repo_root=tmp_path)


@pytest.mark.parametrize("series_id", ["btc_settled_funding", "binance_btc_spot_ohlcv_1m",
                                     "kraken_xbtusd_spot_ohlcv_1h"])
@pytest.mark.parametrize("field", ["record_id", "provider"])
def test_rights_file_identity_is_checked(series_id: str, field: str, tmp_path: Path) -> None:
    legal_path = Path("configs/legal") / f"{document(series_id)['legal_record']}.yaml"
    raw = yaml.safe_load((ROOT / legal_path).read_text(encoding="utf-8"))
    raw[field] = "wrong_identity"
    target = tmp_path / legal_path
    target.parent.mkdir(parents=True)
    target.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(SeriesDescriptorError, match=f"rights record.*{field}"):
        load_series_descriptor(config_path(series_id), repo_root=tmp_path)


@pytest.mark.parametrize("column", ["sum_open_interest_value", "count_toptrader_long_short_ratio",
                                    "sum_toptrader_long_short_ratio", "count_long_short_ratio",
                                    "sum_taker_long_short_vol_ratio"])
def test_incidental_metrics_cannot_be_canonical(column: str, tmp_path: Path) -> None:
    for series_id in OI_STARTS:
        raw = document(series_id)
        raw["canonical_value"] = column
        with pytest.raises(SeriesDescriptorError, match="canonical_value"):
            load_series_descriptor(write_document(tmp_path, raw))
    with pytest.raises(SeriesDescriptorError, match="series_id"):
        SeriesDescriptor(column)


@pytest.mark.parametrize("raw", [None, [], "scalar", {1: "bad"}, {"series_id": []}])
def test_invalid_document_shapes_have_clear_errors(raw: object, tmp_path: Path) -> None:
    with pytest.raises(SeriesDescriptorError):
        load_series_descriptor(write_document(tmp_path, raw))


@pytest.mark.parametrize("block", [None, "period", "source"])
def test_missing_keys_fail_closed(block: str | None, tmp_path: Path) -> None:
    raw = document()
    target = raw if block is None else raw[block]
    for key in tuple(target):
        bad = deepcopy(raw)
        del (bad if block is None else bad[block])[key]
        with pytest.raises(SeriesDescriptorError, match="missing|series_id"):
            load_series_descriptor(write_document(tmp_path, bad))


@pytest.mark.parametrize("suffix", ["series_id: btc_mark_price_1m\n", "source: {}\n",
                                    "period: {}\n", "legal_record: wrong\n"])
def test_duplicate_yaml_keys_rejected(suffix: str, tmp_path: Path) -> None:
    path = tmp_path / "duplicate.yaml"
    path.write_text(config_path("btc_mark_price_1m").read_text() + suffix, encoding="utf-8")
    with pytest.raises(SeriesDescriptorError, match="duplicate"):
        load_series_descriptor(path)


def test_yaml_merge_and_unsafe_tags_rejected(tmp_path: Path) -> None:
    for text in ("!!python/object:object {}", "{series_id: btc_mark_price_1m, <<: {extra: yes}}"):
        path = tmp_path / "bad.yaml"
        path.write_text(text, encoding="utf-8")
        with pytest.raises(SeriesDescriptorError, match="YAML"):
            load_series_descriptor(path)


def test_registry_and_objects_cannot_be_reconfigured() -> None:
    descriptor = load_series_descriptor(config_path("btc_mark_price_1m"))
    with pytest.raises(TypeError):
        SERIES_REGISTRY["SOLUSDT"] = SERIES_REGISTRY[descriptor.series_id]
    with pytest.raises(FrozenInstanceError):
        SERIES_REGISTRY[descriptor.series_id].provider_symbol = "SOLUSDT"
    with pytest.raises(FrozenInstanceError):
        descriptor.series_id = "SOLUSDT"
    with pytest.raises(SeriesDescriptorError, match="series_id"):
        replace(descriptor, series_id="btcusdt_perp_ohlcv")
    archive = descriptor.archive_for("2024-01")
    with pytest.raises(SeriesDescriptorError, match="period"):
        replace(archive, period="2025-01")
    exported = descriptor.to_dict()
    exported["source"]["allowed_hosts"].append("evil.invalid")
    assert descriptor.allowed_hosts == ("data.binance.vision",)
