"""Closed, additive Protocol v1 source-series descriptors (D01).

Only a registered series and one of its generated object periods can select a
source. Documents repeat the frozen contract for review; no input field is used
as a URL/path template. Period start/end are inclusive UTC calendar dates, not
claims of complete observations. Missing observations remain null downstream.

This module neither acquires data nor selects model features. Kraken's single
archive extends outside the descriptor window: acquisition must remain
value-blind outside that window and apply D02's separate integrity anchors.
Existing kline-v1 identities, parsers, and hash domains are untouched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

from quantara.descriptor import DescriptorError, RightsRecord, load_rights_record
from quantara.jcs import canonicalize


class SeriesDescriptorError(DescriptorError):
    """The document or object selection violates the frozen series contract."""


_SCHEMA = "quantara.series-descriptor/v1"
_END = "2024-12-31"
_BINANCE_HOST = "data.binance.vision"
_KRAKEN_HOST = "drive.usercontent.google.com"
_KRAKEN_OBJECT = "1ptNqWYidLkhb2VAKuLCxmp2OXEfGO-AP"
_KRAKEN_MEMBER = "master_q4/XBTUSD_60.csv"
_DEFAULT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class _Series:
    provider: str
    venue: str
    market_type: str
    provider_symbol: str
    source_family: str
    object_cadence: str
    observation_cadence: str
    parser: str
    canonical_value: str
    timestamp_role: str
    csv_header_policy: str
    start: str
    legal_record: str
    rights_provider: str


def _usdm(symbol: str, family: str, start: str = "2020-01-01") -> _Series:
    """Build registry constants only; never called with document values."""
    if family == "fundingRate":
        provider = "binance_usd_m_futures"
        cadence, observation = "monthly", "per_settlement_event"
        parser, value = "binance_settled_funding_csv/v1", "last_funding_rate"
        timestamp, header = "settlement", "present"
    elif family == "metrics":
        provider = "binance_futures"
        cadence, observation = "daily", "5m"
        parser, value = "binance_open_interest_csv/v1", "sum_open_interest"
        # v1.1 does not claim the provider timestamp is a documented interval
        # start. Its conservative eligibility rule is implemented downstream.
        timestamp, header = "UNRESOLVED_CONSERVATIVE", "present"
    else:
        provider = "binance_usd_m_futures" if family == "klines" else "binance_futures"
        cadence, observation = "monthly", "1m"
        parser, value = "binance_usdm_kline_series_csv/v1", "ohlcv"
        timestamp = "interval_start"
        header = "absent_before_2022-01" if family == "klines" else "absent_before_2022-12"
    return _Series(
        provider, "binance", "perpetual", symbol, family, cadence, observation,
        parser, value, timestamp, header, start, "binance-usdm-provider-rights.v3", "binance",
    )


# Exact v1.1 inventory less btcusdt_perp_ohlcv, whose existing lane is immutable.
# No mutable backing dictionary is exposed. Family/header contracts come from
# A1/A2/A7/A8 and the corrected A3/A4 source audits; Kraken identity comes from A9.
SERIES_REGISTRY = MappingProxyType({
    "btc_settled_funding": _usdm("BTCUSDT", "fundingRate"),
    "btc_open_interest_5m": _usdm("BTCUSDT", "metrics", "2020-09-01"),
    "btc_mark_price_1m": _usdm("BTCUSDT", "markPriceKlines"),
    "btc_index_price_1m": _usdm("BTCUSDT", "indexPriceKlines"),
    "btc_native_premium_1m": _usdm("BTCUSDT", "premiumIndexKlines"),
    "binance_btc_spot_ohlcv_1m": _Series(
        "binance_spot", "binance", "spot", "BTCUSDT", "spot", "monthly", "1m",
        "binance_spot_kline_series_csv/v1", "ohlcv", "interval_start", "absent",
        "2020-01-01", "binance-spot-provider-rights.v1", "binance_spot",
    ),
    "kraken_xbtusd_spot_ohlcv_1h": _Series(
        "kraken", "kraken", "spot", "XBTUSD", "kraken", "archive", "1h",
        "kraken_ohlcvt_csv/v1", "ohlcvt", "DOCUMENTED_INTERVAL_START", "absent",
        "2020-01-01", "kraken-spot-provider-rights.v1", "kraken",
    ),
    "ethusdt_perp_ohlcv_1m": _usdm("ETHUSDT", "klines"),
    "eth_settled_funding": _usdm("ETHUSDT", "fundingRate"),
    "eth_open_interest_5m": _usdm("ETHUSDT", "metrics", "2021-12-01"),
    "eth_mark_price_1m": _usdm("ETHUSDT", "markPriceKlines"),
    "eth_index_price_1m": _usdm("ETHUSDT", "indexPriceKlines"),
    "eth_native_premium_1m": _usdm("ETHUSDT", "premiumIndexKlines"),
})


def _registered(series_id: str) -> _Series:
    if type(series_id) is not str or series_id not in SERIES_REGISTRY:
        raise SeriesDescriptorError("series_id must name one of the 13 frozen series")
    return SERIES_REGISTRY[series_id]


def _periods(spec: _Series) -> tuple[str, ...]:
    if spec.object_cadence == "archive":
        return ("2020-2024",)
    start, end = date.fromisoformat(spec.start), date.fromisoformat(_END)
    if spec.object_cadence == "daily":
        return tuple(
            (start + timedelta(days=offset)).isoformat()
            for offset in range((end - start).days + 1)
        )
    return tuple(
        f"{year}-{month:02d}"
        for year in range(start.year, end.year + 1)
        for month in range(1, 13)
        if start <= date(year, month, 1) <= end
    )


@dataclass(frozen=True, slots=True)
class SeriesDescriptor:
    """Immutable registered identity; use load_series_descriptor for rights-gated loading."""

    series_id: str

    def __post_init__(self) -> None:
        _registered(self.series_id)

    @property
    def legal_record(self) -> str:
        return _registered(self.series_id).legal_record

    @property
    def allowed_hosts(self) -> tuple[str, ...]:
        spec = _registered(self.series_id)
        return (_KRAKEN_HOST if spec.source_family == "kraken" else _BINANCE_HOST,)

    @property
    def object_periods(self) -> tuple[str, ...]:
        """Complete object inventory; does not assert objects or rows are available."""
        return _periods(_registered(self.series_id))

    def archive_for(self, period: str) -> SeriesArchive:
        return SeriesArchive(self.series_id, period)

    def to_dict(self) -> dict[str, Any]:
        """Detached document with exactly the frozen schema, suitable for YAML round trips."""
        spec = _registered(self.series_id)
        source: dict[str, Any] = {"allowed_hosts": list(self.allowed_hosts)}
        if spec.source_family == "kraken":
            source.update(object_id=_KRAKEN_OBJECT, member=_KRAKEN_MEMBER)
        document = {
            "schema": _SCHEMA,
            "series_id": self.series_id,
            "provider": spec.provider,
            "venue": spec.venue,
            "market_type": spec.market_type,
            "provider_symbol": spec.provider_symbol,
            "object_cadence": spec.object_cadence,
            "observation_cadence": spec.observation_cadence,
            "parser": spec.parser,
            "canonical_value": spec.canonical_value,
            "timestamp_role": spec.timestamp_role,
            "csv_header_policy": spec.csv_header_policy,
            "period": {"start": spec.start, "end": _END, "timezone": "UTC"},
            "source": source,
            "legal_record": spec.legal_record,
        }
        if spec.source_family == "kraken":
            document["no_trade_intervals"] = "omitted"
        return document

    def canonical_semantics(self) -> str:
        """JCS for this new schema; no legacy hash domain or manifest is changed."""
        return canonicalize(self.to_dict())

    def load_rights(self, repo_root: Path | str = _DEFAULT_ROOT) -> RightsRecord:
        """Resolve the frozen filename and validate identity; operations stay separately gated."""
        spec = _registered(self.series_id)
        path = Path(repo_root) / "configs/legal" / f"{spec.legal_record}.yaml"
        try:
            record = load_rights_record(path)
        except (OSError, UnicodeError, yaml.YAMLError, DescriptorError) as exc:
            raise SeriesDescriptorError("bound rights record is missing or invalid") from exc
        if record.record_id != spec.legal_record:
            raise SeriesDescriptorError("rights record record_id does not match frozen binding")
        if record.provider != spec.rights_provider:
            raise SeriesDescriptorError("rights record provider does not match frozen binding")
        return record


@dataclass(frozen=True, slots=True)
class SeriesArchive:
    """A closed source selection; URL, host, member, and parser policy are never input."""

    series_id: str
    period: str

    def __post_init__(self) -> None:
        spec = _registered(self.series_id)
        if type(self.period) is not str or self.period not in _periods(spec):
            raise SeriesDescriptorError("object period must be in the frozen series window")

    @property
    def member(self) -> str:
        spec = _registered(self.series_id)
        if spec.source_family == "kraken":
            return _KRAKEN_MEMBER
        suffix = spec.source_family if spec.source_family in ("fundingRate", "metrics") else "1m"
        return f"{spec.provider_symbol}-{suffix}-{self.period}.csv"

    @property
    def member_pattern(self) -> str:
        # Absolute anchors also exclude trailing newlines with re.match/search.
        return rf"\A{re.escape(self.member)}\Z"

    @property
    def archive_url(self) -> str:
        spec = _registered(self.series_id)
        family, symbol = spec.source_family, spec.provider_symbol
        if family == "kraken":
            return f"https://{_KRAKEN_HOST}/download?id={_KRAKEN_OBJECT}&export=download"
        if family == "spot":
            directory = "data/spot/monthly/klines/BTCUSDT/1m"
        elif family == "metrics":
            directory = f"data/futures/um/daily/metrics/{symbol}"
        elif family == "fundingRate":
            directory = f"data/futures/um/monthly/fundingRate/{symbol}"
        else:
            directory = f"data/futures/um/monthly/{family}/{symbol}/1m"
        return f"https://{_BINANCE_HOST}/{directory}/{self.member.removesuffix('.csv')}.zip"

    @property
    def checksum_url(self) -> str | None:
        if _registered(self.series_id).source_family == "kraken":
            return None  # D02 provides independent retrieval anchors, not an operator signature.
        return self.archive_url + ".CHECKSUM"

    @property
    def csv_header(self) -> str:
        policy = _registered(self.series_id).csv_header_policy
        if policy.startswith("absent_before_"):
            return "absent" if self.period < policy.removeprefix("absent_before_") else "present"
        return policy


class _ClosedLoader(yaml.SafeLoader):
    """Reject duplicate keys and YAML merge keys rather than silently overriding them."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict:
        mapping = {}
        for key_node, value_node in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                raise SeriesDescriptorError("YAML merge keys are forbidden")
            key = self.construct_object(key_node, deep=deep)
            if type(key) is not str:
                raise SeriesDescriptorError("YAML mapping keys must be strings")
            if key in mapping:
                raise SeriesDescriptorError("duplicate YAML mapping key")
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def _match_contract(actual: Any, expected: Any, field: str) -> None:
    if type(actual) is not type(expected):
        raise SeriesDescriptorError(f"{field} must have the frozen type")
    if isinstance(expected, dict):
        missing = expected.keys() - actual.keys()
        unknown = actual.keys() - expected.keys()
        if missing:
            raise SeriesDescriptorError(f"missing {field} keys: {sorted(missing)}")
        if unknown:
            raise SeriesDescriptorError(f"unknown {field} keys are forbidden")
        for key, value in expected.items():
            _match_contract(actual[key], value, f"{field}.{key}")
    elif actual != expected:
        raise SeriesDescriptorError(f"{field} must equal its frozen registry value")


def load_series_descriptor(
    path: Path | str, *, repo_root: Path | str = _DEFAULT_ROOT,
) -> SeriesDescriptor:
    """Load only an exact registered document with an existing, correctly bound rights record.

    repo_root locates trusted repository configuration for relocated checkouts;
    it is never read from descriptor fields. Actual acquisition/normalization
    must additionally check the returned rights record's operation permissions.
    """
    try:
        document = yaml.load(Path(path).read_text(encoding="utf-8"), Loader=_ClosedLoader)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise SeriesDescriptorError("descriptor must be readable, valid safe YAML") from exc
    if not isinstance(document, dict):
        raise SeriesDescriptorError("descriptor must be a YAML mapping")
    descriptor = SeriesDescriptor(document.get("series_id"))
    _match_contract(document, descriptor.to_dict(), "descriptor")
    descriptor.load_rights(repo_root)
    return descriptor
