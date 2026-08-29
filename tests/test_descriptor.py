"""Descriptor, rights-record, and error-id tests (spec §§3, 13.4, 14, 15.1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import EXTENDED_YEARS, VALID_DESCRIPTOR_YAML
from conftest import extended_year_1m_descriptor_text as _extended_year_1m_text
from conftest import write_text as _write
from quantara.descriptor import DescriptorError, load_descriptor
from quantara.hashing import descriptor_hash

VALID_V2_DESCRIPTOR_YAML = """\
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
months: ["2024-01", "2024-02", "2024-03"]
period:
  start: "2024-01-01T00:00:00Z"
  end: "2024-04-01T00:00:00Z"
source:
  allowed_hosts: [data.binance.vision]
schema_version: binance_usdm_kline_1m_v1
timestamp_semantics: closed_interval_v1
quality_policy_version: "1"
legal_record: configs/legal/binance-usdm-provider-rights.v2.yaml
"""


def _replace_field(source: str, field: str, value: str) -> str:
    lines = []
    for line in source.splitlines():
        if line.startswith(f"{field}:"):
            lines.append(f"{field}: {value}")
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"


def test_valid_descriptor_loads_with_derived_row_count(valid_path: Path) -> None:
    descriptor = load_descriptor(valid_path)
    assert descriptor.provider_symbol == "BTCUSDT"
    assert descriptor.instrument_id == "binance:usd_m_futures:BTCUSDT:perpetual"
    assert descriptor.interval == "1m"
    assert descriptor.schema_version == "binance_usdm_kline_1m_v1"
    # Derived by calendar math over [start, end), never copied as a constant.
    assert descriptor.expected_row_count == 44_640
    assert descriptor.archive_url == (
        "https://data.binance.vision/data/futures/um/monthly/klines/"
        "BTCUSDT/1m/BTCUSDT-1m-2024-01.zip"
    )
    assert descriptor.member_pattern == r"^BTCUSDT-1m-2024-01\.csv$"
    assert descriptor.months == ("2024-01",)


def test_semantic_hash_stability_across_formatting(tmp_path: Path) -> None:
    reordered = """\
legal_record: configs/legal/binance-usdm-provider-rights.v1.yaml
quality_policy_version: "1"
timestamp_semantics: closed_interval_v1   # trailing comment ignored
schema_version: binance_usdm_kline_1m_v1

interval: 1m
dataset_type: klines
contract_type: perpetual
settlement_asset: USDT
quote_asset: USDT
base_asset: BTC
provider_symbol: BTCUSDT
instrument_id: binance:usd_m_futures:BTCUSDT:perpetual
market_type: usd_m_futures
provider: binance
dataset_id: binance_usdm_btcusdt_klines_1m_2024_01
schema: quantara.dataset-descriptor/v1
period: {end: "2024-02-01T00:00:00Z", start: "2024-01-01T00:00:00Z"}
source:
  member_pattern: "^BTCUSDT-1m-2024-01\\\\.csv$"
  allowed_hosts: [data.binance.vision]
  checksum_url: https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01.zip.CHECKSUM
  archive_url: https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01.zip
"""
    first = load_descriptor(_write(tmp_path / "a", VALID_DESCRIPTOR_YAML))
    second = load_descriptor(_write(tmp_path / "b", reordered))
    assert first.canonical_semantics() == second.canonical_semantics()


def test_unknown_key_is_rejected(valid_path: Path) -> None:
    text = VALID_DESCRIPTOR_YAML.replace(
        "interval: 1m\n", "interval: 1m\nextra_key: nope\n"
    )
    with pytest.raises(DescriptorError, match="unknown"):
        load_descriptor(_write(valid_path.parent, text))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider", "binance-spot"),
        ("market_type", "coin_m"),
        ("instrument_id", "binance:usd_m_futures:ETHUSDT:perpetual"),
        ("provider_symbol", "ETHUSDT"),
        ("interval", "5m"),
        ("dataset_type", "trades"),
        ("schema_version", "some_other_v2"),
        ("timestamp_semantics", "open_interval_v1"),
        ("base_asset", "SOL"),
    ],
)
def test_identity_drift_is_rejected(valid_path: Path, field: str, value: str) -> None:
    rebuilt = _replace_field(VALID_DESCRIPTOR_YAML, field, value)
    with pytest.raises(DescriptorError):
        load_descriptor(_write(valid_path.parent, rebuilt))


def test_valid_v2_descriptor_derives_month_sources_and_q1_count(tmp_path: Path) -> None:
    descriptor = load_descriptor(_write(tmp_path, VALID_V2_DESCRIPTOR_YAML))
    assert descriptor.months == ("2024-01", "2024-02", "2024-03")
    assert descriptor.expected_row_count == 131_040
    assert descriptor.archive_urls == (
        "https://data.binance.vision/data/futures/um/monthly/klines/"
        "BTCUSDT/1m/BTCUSDT-1m-2024-01.zip",
        "https://data.binance.vision/data/futures/um/monthly/klines/"
        "BTCUSDT/1m/BTCUSDT-1m-2024-02.zip",
        "https://data.binance.vision/data/futures/um/monthly/klines/"
        "BTCUSDT/1m/BTCUSDT-1m-2024-03.zip",
    )
    assert descriptor.checksum_urls[-1].endswith("2024-03.zip.CHECKSUM")
    assert descriptor.member_patterns[-1] == r"^BTCUSDT-1m-2024-03\.csv$"


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('months: ["2024-01", "2024-02", "2024-03"]', "months: []", "non-empty"),
        (
            'months: ["2024-01", "2024-02", "2024-03"]',
            'months: ["2024-01", "2024-01", "2024-03"]',
            "unique",
        ),
        (
            'months: ["2024-01", "2024-02", "2024-03"]',
            'months: ["2024-02", "2024-01", "2024-03"]',
            "chronological",
        ),
        (
            'months: ["2024-01", "2024-02", "2024-03"]',
            'months: ["2024-01", "2024-03"]',
            "consecutive",
        ),
        (
            'months: ["2024-01", "2024-02", "2024-03"]',
            'months: ["2024-01", "2024-13", "2024-03"]',
            "calendar",
        ),
        (
            'end: "2024-04-01T00:00:00Z"',
            'end: "2024-03-01T00:00:00Z"',
            "union",
        ),
    ],
)
def test_v2_month_matrix_rejects_invalid_ranges(
    tmp_path: Path, old: str, new: str, message: str
) -> None:
    text = VALID_V2_DESCRIPTOR_YAML.replace(old, new)
    with pytest.raises(DescriptorError, match=message):
        load_descriptor(_write(tmp_path, text))


def test_v2_rejects_unknown_source_and_top_level_keys(tmp_path: Path) -> None:
    with pytest.raises(DescriptorError, match="exactly 'allowed_hosts'"):
        load_descriptor(
            _write(
                tmp_path / "source",
                VALID_V2_DESCRIPTOR_YAML.replace(
                    "  allowed_hosts: [data.binance.vision]",
                    "  allowed_hosts: [data.binance.vision]\n  archive_url: forbidden",
                ),
            )
        )
    with pytest.raises(DescriptorError, match="unknown descriptor keys"):
        load_descriptor(
            _write(
                tmp_path / "top",
                VALID_V2_DESCRIPTOR_YAML.replace(
                    "interval: 1m", "interval: 1m\nextra: nope"
                ),
            )
        )


# --- Additive: data slice 010 (full-year 2024 v2 range identity) ----------------


VALID_V2_YEAR_DESCRIPTOR_YAML = """\
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
  allowed_hosts: [data.binance.vision]
schema_version: binance_usdm_kline_1m_v1
timestamp_semantics: closed_interval_v1
quality_policy_version: "2"
quality_approval: configs/quality/approvals/binance-usdm-btcusdt-1m-2024-zero-volume.v1.yaml
legal_record: configs/legal/binance-usdm-provider-rights.v2.yaml
"""


def test_valid_v2_year_descriptor_loads_with_12_months(tmp_path: Path) -> None:
    descriptor = load_descriptor(_write(tmp_path, VALID_V2_YEAR_DESCRIPTOR_YAML))
    assert descriptor.dataset_id == "binance_usdm_btcusdt_klines_1m_2024"
    assert descriptor.months == tuple(f"2024-{month:02d}" for month in range(1, 13))
    assert descriptor.expected_row_count == 527_040  # leap year: 366 * 1440
    assert descriptor.start_utc.strftime("%Y-%m-%dT%H:%M:%SZ") == "2024-01-01T00:00:00Z"
    assert descriptor.end_utc.strftime("%Y-%m-%dT%H:%M:%SZ") == "2025-01-01T00:00:00Z"
    assert descriptor.quality_policy_version == "2"
    assert (
        descriptor.quality_approval
        == "configs/quality/approvals/binance-usdm-btcusdt-1m-2024-zero-volume.v1.yaml"
    )
    assert len(descriptor.archive_urls) == 12
    assert descriptor.archive_urls[0].endswith("BTCUSDT-1m-2024-01.zip")
    assert descriptor.archive_urls[-1].endswith("BTCUSDT-1m-2024-12.zip")
    assert descriptor.checksum_urls[-1].endswith("BTCUSDT-1m-2024-12.zip.CHECKSUM")
    assert descriptor.member_patterns[-1] == r"^BTCUSDT-1m-2024-12\.csv$"
    assert "quality_approval" in descriptor.canonical_semantics()


def test_v2_year_rejects_unknown_range_dataset_id(tmp_path: Path) -> None:
    for bad_id in (
        "binance_usdm_btcusdt_klines_1m_2024_h1",
        "binance_usdm_btcusdt_klines_1m_2025",
    ):
        text = VALID_V2_YEAR_DESCRIPTOR_YAML.replace(
            "dataset_id: binance_usdm_btcusdt_klines_1m_2024\n",
            f"dataset_id: {bad_id}\n",
        )
        with pytest.raises(DescriptorError, match="dataset_id"):
            load_descriptor(_write(tmp_path / bad_id, text))


def test_v1_rejects_policy_2_and_quality_approval(valid_path: Path) -> None:
    text_policy = VALID_DESCRIPTOR_YAML.replace(
        'quality_policy_version: "1"', 'quality_policy_version: "2"'
    )
    with pytest.raises(DescriptorError, match="quality_policy_version"):
        load_descriptor(_write(valid_path.parent / "bad_policy", text_policy))

    text_approval = VALID_DESCRIPTOR_YAML + "quality_approval: foo.yaml\n"
    with pytest.raises(DescriptorError, match="unknown descriptor keys"):
        load_descriptor(_write(valid_path.parent / "bad_approval", text_approval))


def test_v2_q1_rejects_policy_2_and_quality_approval(tmp_path: Path) -> None:
    text_policy = VALID_V2_DESCRIPTOR_YAML.replace(
        'quality_policy_version: "1"', 'quality_policy_version: "2"'
    )
    with pytest.raises(DescriptorError, match="quality_policy_version"):
        load_descriptor(_write(tmp_path / "bad_q1_policy", text_policy))

    text_approval = VALID_V2_DESCRIPTOR_YAML + "quality_approval: foo.yaml\n"
    with pytest.raises(DescriptorError, match="unknown descriptor keys"):
        load_descriptor(_write(tmp_path / "bad_q1_approval", text_approval))


def test_v2_year_rejects_policy_1_and_missing_or_bad_approval(tmp_path: Path) -> None:
    text_policy = VALID_V2_YEAR_DESCRIPTOR_YAML.replace(
        'quality_policy_version: "2"', 'quality_policy_version: "1"'
    )
    with pytest.raises(DescriptorError, match="quality_policy_version"):
        load_descriptor(_write(tmp_path / "bad_year_policy", text_policy))

    text_missing = (
        "\n".join(
            line
            for line in VALID_V2_YEAR_DESCRIPTOR_YAML.splitlines()
            if not line.startswith("quality_approval:")
        )
        + "\n"
    )
    with pytest.raises(DescriptorError, match="missing descriptor keys"):
        load_descriptor(_write(tmp_path / "missing_year_approval", text_missing))

    text_bad_path = _replace_field(
        VALID_V2_YEAR_DESCRIPTOR_YAML, "quality_approval", "configs/quality/bad.yaml"
    )
    with pytest.raises(DescriptorError, match="quality_approval"):
        load_descriptor(_write(tmp_path / "bad_year_approval", text_bad_path))


# --- Additive: data slice 015-extended (2020/2021/2022 year identities) --------

# Frozen JCS canonical-semantics digests for the three approved 015-extended
# year descriptors under the pre-registered policy-"1" combination. These are
# the round-trip anchors required by gate G1: a silent identity, month-set,
# period, host, or policy drift changes the digest and fails here.
EXTENDED_YEAR_CANONICAL_DIGESTS = {
    2020: "eb589f21f01499444b832fcbfa611addc5bb2889a2d2b8cedbc926d7551dd7f9",
    2021: "4e3e359ccaded605e9f82003e99fba81b72f09bfbb359f8a011852293903f19f",
    2022: "b1eb75e9b0f569632454eb6489ecf5eaf91db397eb408a77e2a6254102936f00",
}

EXTENDED_YEAR_EXPECTED_ROWS = {2020: 527_040, 2021: 525_600, 2022: 525_600}


@pytest.mark.parametrize("year", EXTENDED_YEARS)
def test_extended_year_descriptor_round_trip(tmp_path: Path, year: int) -> None:
    """One round-trip per approved year: load, then assert frozen JCS bytes."""
    path = _write(
        tmp_path / str(year),
        _extended_year_1m_text(year),
        name=f"binance-usdm-btcusdt-1m-{year}.yaml",
    )
    descriptor = load_descriptor(path)
    assert descriptor.dataset_id == f"binance_usdm_btcusdt_klines_1m_{year}"
    assert descriptor.months == tuple(f"{year}-{month:02d}" for month in range(1, 13))
    assert descriptor.expected_row_count == EXTENDED_YEAR_EXPECTED_ROWS[year]
    assert (
        descriptor.start_utc.strftime("%Y-%m-%dT%H:%M:%SZ") == f"{year}-01-01T00:00:00Z"
    )
    assert (
        descriptor.end_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        == f"{year + 1}-01-01T00:00:00Z"
    )
    assert descriptor.quality_policy_version == "1"
    assert descriptor.quality_approval is None
    assert len(descriptor.archive_urls) == 12
    assert descriptor.archive_urls[0].endswith(f"BTCUSDT-1m-{year}-01.zip")
    assert descriptor.archive_urls[-1].endswith(f"BTCUSDT-1m-{year}-12.zip")
    assert descriptor.checksum_urls[-1].endswith(f"BTCUSDT-1m-{year}-12.zip.CHECKSUM")
    assert descriptor.member_patterns[-1] == rf"^BTCUSDT-1m-{year}-12\.csv$"
    assert (
        descriptor_hash(descriptor.canonical_semantics())
        == EXTENDED_YEAR_CANONICAL_DIGESTS[year]
    )


@pytest.mark.parametrize("year", EXTENDED_YEARS)
def test_extended_year_rejects_unapproved_policy_combinations(
    tmp_path: Path, year: int
) -> None:
    """Only ("1", no approval) and ("2", that year's exact path) are approved."""
    base = _extended_year_1m_text(year)
    approved_path = (
        "configs/quality/approvals/"
        f"binance-usdm-btcusdt-1m-{year}-zero-volume.v1.yaml"
    )

    # Policy 1 must not carry an approval path.
    text = base + f"quality_approval: {approved_path}\n"
    with pytest.raises(DescriptorError, match="quality_approval"):
        load_descriptor(_write(tmp_path / f"{year}-p1-approval", text))

    # Policy 2 requires an approval path.
    text = base.replace('quality_policy_version: "1"', 'quality_policy_version: "2"')
    with pytest.raises(DescriptorError, match="quality_approval"):
        load_descriptor(_write(tmp_path / f"{year}-p2-missing", text))

    # Policy 2 with another year's approval path is rejected.
    other = 2021 if year != 2021 else 2022
    wrong_path = (
        "configs/quality/approvals/"
        f"binance-usdm-btcusdt-1m-{other}-zero-volume.v1.yaml"
    )
    text = (
        base.replace('quality_policy_version: "1"', 'quality_policy_version: "2"')
        + f"quality_approval: {wrong_path}\n"
    )
    with pytest.raises(DescriptorError, match="quality_approval"):
        load_descriptor(_write(tmp_path / f"{year}-p2-wrong", text))

    # Any other policy version is rejected outright.
    text = base.replace('quality_policy_version: "1"', 'quality_policy_version: "3"')
    with pytest.raises(DescriptorError, match="quality_policy_version"):
        load_descriptor(_write(tmp_path / f"{year}-p3", text))


def test_extended_year_identities_do_not_admit_unapproved_years(
    tmp_path: Path,
) -> None:
    """2019/2023 are not approved identities; only 2020-2022 were added."""
    for unapproved in (2019, 2023):
        text = _extended_year_1m_text(2020).replace("2020", str(unapproved))
        with pytest.raises(DescriptorError, match="dataset_id"):
            load_descriptor(_write(tmp_path / f"unapproved-{unapproved}", text))


@pytest.mark.parametrize("year", EXTENDED_YEARS)
def test_repository_extended_year_descriptor_matches_approved_contract(
    year: int,
) -> None:
    """The committed repository descriptor obeys the approved year contract."""
    repo_root = Path(__file__).resolve().parents[1]
    descriptor = load_descriptor(
        repo_root / "configs" / "datasets" / f"binance-usdm-btcusdt-1m-{year}.yaml"
    )
    assert descriptor.dataset_id == f"binance_usdm_btcusdt_klines_1m_{year}"
    assert descriptor.months == tuple(f"{year}-{month:02d}" for month in range(1, 13))
    assert descriptor.expected_row_count == EXTENDED_YEAR_EXPECTED_ROWS[year]
    assert descriptor.allowed_hosts == ("data.binance.vision",)
    assert descriptor.legal_record == (
        "configs/legal/binance-usdm-provider-rights.v3.yaml"
    )
    if descriptor.quality_policy_version == "1":
        assert descriptor.quality_approval is None
    else:
        assert descriptor.quality_policy_version == "2"
        assert descriptor.quality_approval == (
            "configs/quality/approvals/"
            f"binance-usdm-btcusdt-1m-{year}-zero-volume.v1.yaml"
        )
