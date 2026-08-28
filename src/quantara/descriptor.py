"""Source descriptor and provider-rights record loading/validation (component 1).

Strictly validates the approved dataset descriptor: unknown keys are rejected,
identity fields must equal the governing specification exactly, the half-open
UTC period is parsed from calendar boundaries, the expected row count is
derived by calendar math, and source URLs may only come from template
interpolation of validated symbol/interval/month segments so path manipulation
through descriptor fields is impossible. The versioned provider-rights record
gates every performed operation before any network or filesystem action.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from quantara.errors import INVALID_DESCRIPTOR, QuantaraError
from quantara.jcs import canonicalize

__all__ = [
    "APPROVED_INTERNAL_OPERATIONS",
    "RIGHTS_OPERATIONS",
    "DatasetDescriptor",
    "DescriptorError",
    "RightsOperation",
    "RightsRecord",
    "load_descriptor",
    "load_rights_record",
]


class DescriptorError(QuantaraError):
    error_id = INVALID_DESCRIPTOR


V1_SCHEMA = "quantara.dataset-descriptor/v1"
V2_SCHEMA = "quantara.dataset-descriptor/v2"

COMMON_APPROVED_IDENTITIES: dict[str, str] = {
    "provider": "binance",
    "market_type": "usd_m_futures",
    "instrument_id": "binance:usd_m_futures:BTCUSDT:perpetual",
    "provider_symbol": "BTCUSDT",
    "base_asset": "BTC",
    "quote_asset": "USDT",
    "settlement_asset": "USDT",
    "contract_type": "perpetual",
    "dataset_type": "klines",
    "interval": "1m",
    "schema_version": "binance_usdm_kline_1m_v1",
    "timestamp_semantics": "closed_interval_v1",
}

APPROVED_IDENTITIES: dict[str, str] = {
    "schema": V1_SCHEMA,
    "dataset_id": "binance_usdm_btcusdt_klines_1m_2024_01",
    **COMMON_APPROVED_IDENTITIES,
}

V2_APPROVED_IDENTITIES: dict[str, str] = {
    "schema": V2_SCHEMA,
    "dataset_id": "binance_usdm_btcusdt_klines_1m_2024_q1",
    **COMMON_APPROVED_IDENTITIES,
}

V2_YEAR_APPROVED_IDENTITIES: dict[str, str] = {
    "schema": V2_SCHEMA,
    "dataset_id": "binance_usdm_btcusdt_klines_1m_2024",
    **COMMON_APPROVED_IDENTITIES,
}

V2_IDENTITY_TABLES: tuple[dict[str, str], ...] = (
    V2_APPROVED_IDENTITIES,
    V2_YEAR_APPROVED_IDENTITIES,
)


DESCRIPTOR_KEYS = frozenset(APPROVED_IDENTITIES) | {
    "period",
    "source",
    "quality_policy_version",
    "legal_record",
}
V2_DESCRIPTOR_KEYS = frozenset(V2_APPROVED_IDENTITIES) | {
    "months",
    "period",
    "source",
    "quality_policy_version",
    "legal_record",
}
V2_YEAR_DESCRIPTOR_KEYS = frozenset(V2_YEAR_APPROVED_IDENTITIES) | {
    "months",
    "period",
    "source",
    "quality_policy_version",
    "legal_record",
    "quality_approval",
}

SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]+$")
INTERVAL_PATTERN = re.compile(r"^1m$")
MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}$")
UTC_TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
HOSTNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.\-]*$")

ARCHIVE_URL_TEMPLATE = (
    "https://data.binance.vision/data/futures/um/monthly/klines/"
    "{symbol}/{interval}/{symbol}-{interval}-{month}.zip"
)
CHECKSUM_URL_TEMPLATE = ARCHIVE_URL_TEMPLATE + ".CHECKSUM"
MEMBER_PATTERN_TEMPLATE = r"^{symbol}-{interval}-{month}\.csv$"

RIGHTS_SCHEMA = "quantara.provider-rights/v1"
RIGHTS_TOP_LEVEL_KEYS = frozenset(
    {"schema", "record_id", "provider", "reviewer", "review_date", "operations"}
)
RIGHTS_OPERATION_KEYS = frozenset(
    {"state", "source_terms", "review_date", "reviewer", "rationale"}
)
RIGHTS_STATES = ("ALLOWED", "OWNER_APPROVED_PENDING_COUNSEL", "PROHIBITED", "UNKNOWN")

RIGHTS_OPERATIONS = (
    "acquire_internal",
    "retain_raw_internal",
    "normalize_internal",
    "analyze_internal",
    "model_train_internal",
    "commercial_production_eligible",
    "customer_display",
    "raw_redistribution",
)

APPROVED_INTERNAL_OPERATIONS = (
    "acquire_internal",
    "retain_raw_internal",
    "normalize_internal",
    "analyze_internal",
)


@dataclass(frozen=True)
class DatasetDescriptor:
    schema: str
    dataset_id: str
    provider: str
    market_type: str
    instrument_id: str
    provider_symbol: str
    base_asset: str
    quote_asset: str
    settlement_asset: str
    contract_type: str
    dataset_type: str
    interval: str
    start_utc: datetime
    end_utc: datetime
    archive_url: str
    checksum_url: str
    allowed_hosts: tuple[str, ...]
    member_pattern: str
    months: tuple[str, ...]
    archive_urls: tuple[str, ...]
    checksum_urls: tuple[str, ...]
    member_patterns: tuple[str, ...]
    schema_version: str
    timestamp_semantics: str
    quality_policy_version: str
    legal_record: str
    quality_approval: str | None = None

    @property
    def expected_row_count(self) -> int:
        """Derived by calendar math over [start, end) at one-minute cadence."""
        return (self.end_utc - self.start_utc) // timedelta(minutes=1)

    def canonical_semantics(self) -> str:
        """JCS serialization of validated semantics (formatting-independent)."""
        if self.schema == V1_SCHEMA:
            identities: dict[str, str] = APPROVED_IDENTITIES
        else:
            identities = _v2_identity_table_for(self.dataset_id)
        semantics: dict[str, Any] = dict(identities)
        source: dict[str, Any]
        if self.schema == V1_SCHEMA:
            source = {
                "archive_url": self.archive_url,
                "checksum_url": self.checksum_url,
                "allowed_hosts": list(self.allowed_hosts),
                "member_pattern": self.member_pattern,
            }
        else:
            semantics["months"] = list(self.months)
            source = {"allowed_hosts": list(self.allowed_hosts)}
        semantics.update(
            {
                "period": {
                    "start": self.start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end": self.end_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
                "source": source,
                "quality_policy_version": self.quality_policy_version,
                "legal_record": self.legal_record,
            }
        )
        if self.quality_approval is not None:
            semantics["quality_approval"] = self.quality_approval
        return canonicalize(semantics)


def _reject(detail: str) -> None:
    raise DescriptorError(detail)


def _parse_period(raw: Any) -> tuple[datetime, datetime]:
    if not isinstance(raw, dict) or set(raw) != {"start", "end"}:
        _reject("period must contain exactly 'start' and 'end'")
    start_text, end_text = raw["start"], raw["end"]
    for label, value in (("start", start_text), ("end", end_text)):
        if not isinstance(value, str) or not UTC_TIMESTAMP_PATTERN.match(value):
            _reject(f"period {label} must be an ISO-8601 UTC Z timestamp")
    start = datetime.strptime(start_text, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=UTC
    )
    end = datetime.strptime(end_text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    if start >= end:
        _reject("period start must precede period end")
    return start, end


def _validate_urls(
    source: dict[str, Any], symbol: str, interval: str, month: str
) -> tuple[str, str, tuple[str, ...]]:
    hosts = source.get("allowed_hosts")
    if (
        not isinstance(hosts, list)
        or not hosts
        or not all(isinstance(h, str) and HOSTNAME_PATTERN.match(h) for h in hosts)
    ):
        _reject("source.allowed_hosts must be a non-empty list of hostnames")
    allowed_hosts = tuple(str(host) for host in hosts)

    expected_archive = ARCHIVE_URL_TEMPLATE.format(
        symbol=symbol, interval=interval, month=month
    )
    expected_checksum = CHECKSUM_URL_TEMPLATE.format(
        symbol=symbol, interval=interval, month=month
    )
    for field, expected in (
        ("archive_url", expected_archive),
        ("checksum_url", expected_checksum),
    ):
        provided = source.get(field)
        if provided != expected:
            _reject(f"source.{field} must equal the allow-listed template expansion")
        parsed = urlparse(provided)
        if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
            _reject(f"source.{field} must be https on an allow-listed host")
        if parsed.query or parsed.fragment or parsed.username or parsed.password:
            _reject(f"source.{field} must not carry query, fragment, or credentials")
    return expected_archive, expected_checksum, allowed_hosts


def _month_start(month: str) -> datetime:
    if not isinstance(month, str) or not MONTH_PATTERN.fullmatch(month):
        _reject("months entries must be YYYY-MM strings")
    try:
        return datetime.strptime(month, "%Y-%m").replace(tzinfo=UTC)
    except ValueError:
        _reject("months entries must be valid YYYY-MM calendar months")


def _next_month(start: datetime) -> datetime:
    if start.month == 12:
        return start.replace(year=start.year + 1, month=1)
    return start.replace(month=start.month + 1)


def _parse_months(raw: Any, start: datetime, end: datetime) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw:
        _reject("months must be a non-empty list")
    if not all(isinstance(month, str) for month in raw):
        _reject("months entries must be YYYY-MM strings")
    months = tuple(raw)
    starts = tuple(_month_start(month) for month in months)
    if len(set(months)) != len(months):
        _reject("months must be unique")
    if any(
        current <= previous
        for previous, current in zip(starts, starts[1:], strict=False)
    ):
        _reject("months must be strictly chronological")
    if any(
        current != _next_month(previous)
        for previous, current in zip(starts, starts[1:], strict=False)
    ):
        _reject("months must form one consecutive calendar union")
    if start != starts[0] or end != _next_month(starts[-1]):
        _reject("period must equal the union of the listed month calendars")
    return months


def _validate_allowed_hosts(source: dict[str, Any]) -> tuple[str, ...]:
    if set(source) != {"allowed_hosts"}:
        _reject("v2 source must contain exactly 'allowed_hosts'")
    hosts = source["allowed_hosts"]
    if (
        not isinstance(hosts, list)
        or not hosts
        or not all(
            isinstance(host, str) and HOSTNAME_PATTERN.match(host) for host in hosts
        )
    ):
        _reject("source.allowed_hosts must be a non-empty list of hostnames")
    return tuple(hosts)


def _v2_identity_table_for(dataset_id: Any) -> dict[str, str]:
    """Return the approved v2 identity table whose dataset_id matches.

    A v2 descriptor must match exactly one approved range identity table
    (Q1 or the full 2024 calendar year); a dataset_id matching none of
    them is rejected with the same identity-drift message style.
    """
    for table in V2_IDENTITY_TABLES:
        if dataset_id == table["dataset_id"]:
            return table
    _reject(
        "dataset_id must equal one of the approved v2 range identities: "
        f"{[table['dataset_id'] for table in V2_IDENTITY_TABLES]!r}"
    )
    return V2_IDENTITY_TABLES[0]  # unreachable; _reject raises


def load_descriptor(path: Path | str) -> DatasetDescriptor:
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        _reject("descriptor must be a YAML mapping")
    schema = document.get("schema")
    if schema not in (V1_SCHEMA, V2_SCHEMA):
        _reject(f"schema must equal {V1_SCHEMA!r} or {V2_SCHEMA!r}")
    if schema == V1_SCHEMA:
        approved_identities = APPROVED_IDENTITIES
        descriptor_keys = DESCRIPTOR_KEYS
    elif document.get("dataset_id") == "binance_usdm_btcusdt_klines_1m_2024":
        approved_identities = V2_YEAR_APPROVED_IDENTITIES
        descriptor_keys = V2_YEAR_DESCRIPTOR_KEYS
    else:
        approved_identities = _v2_identity_table_for(document.get("dataset_id"))
        descriptor_keys = V2_DESCRIPTOR_KEYS
    keys = set(document)
    missing = descriptor_keys - keys
    if missing:
        _reject(f"missing descriptor keys: {sorted(missing)}")
    unknown = keys - descriptor_keys
    if unknown:
        _reject(f"unknown descriptor keys: {sorted(unknown)}")

    for field, approved in approved_identities.items():
        value = document[field]
        if not isinstance(value, str) or value != approved:
            _reject(f"{field} must equal approved value {approved!r}")

    symbol = document["provider_symbol"]
    interval = document["interval"]
    if not SYMBOL_PATTERN.match(symbol):
        _reject("provider_symbol must match [A-Z0-9]+")
    if not INTERVAL_PATTERN.match(interval):
        _reject("interval must be exactly '1m'")

    start, end = _parse_period(document["period"])
    source = document["source"]
    if not isinstance(source, dict):
        _reject("source must be a mapping")
    if schema == V1_SCHEMA:
        months = (start.strftime("%Y-%m"),)
        archive_url, checksum_url, allowed_hosts = _validate_urls(
            source, symbol, interval, months[0]
        )
        expected_member_pattern = MEMBER_PATTERN_TEMPLATE.format(
            symbol=symbol, interval=interval, month=months[0]
        )
        if source.get("member_pattern") != expected_member_pattern:
            _reject("source.member_pattern must equal the approved member pattern")
        archive_urls = (archive_url,)
        checksum_urls = (checksum_url,)
        member_patterns = (expected_member_pattern,)
    else:
        months = _parse_months(document["months"], start, end)
        allowed_hosts = _validate_allowed_hosts(source)
        archive_urls = tuple(
            ARCHIVE_URL_TEMPLATE.format(symbol=symbol, interval=interval, month=month)
            for month in months
        )
        checksum_urls = tuple(
            CHECKSUM_URL_TEMPLATE.format(symbol=symbol, interval=interval, month=month)
            for month in months
        )
        member_patterns = tuple(
            MEMBER_PATTERN_TEMPLATE.format(symbol=symbol, interval=interval, month=month)
            for month in months
        )
        archive_url = archive_urls[0]
        checksum_url = checksum_urls[0]
        expected_member_pattern = member_patterns[0]

    quality_policy_version = document["quality_policy_version"]
    legal_record = document["legal_record"]
    if not isinstance(quality_policy_version, str) or not quality_policy_version:
        _reject("quality_policy_version must be a non-empty string")
    if not isinstance(legal_record, str) or not legal_record:
        _reject("legal_record must be a non-empty relative path string")

    quality_approval: str | None = None
    if schema == V1_SCHEMA:
        if quality_policy_version != "1":
            _reject(
                f"v1 descriptor requires quality_policy_version '1', got {quality_policy_version!r}"
            )
        if "quality_approval" in document:
            _reject("v1 descriptor must not specify quality_approval")
    elif document["dataset_id"] == "binance_usdm_btcusdt_klines_1m_2024_q1":
        if quality_policy_version != "1":
            _reject(
                "Q1 v2 descriptor requires quality_policy_version '1', "
                f"got {quality_policy_version!r}"
            )
        if "quality_approval" in document:
            _reject("Q1 v2 descriptor must not specify quality_approval")
    elif document["dataset_id"] == "binance_usdm_btcusdt_klines_1m_2024":
        if quality_policy_version != "2":
            _reject(
                "full-year 2024 descriptor requires quality_policy_version '2', "
                f"got {quality_policy_version!r}"
            )
        if "quality_approval" not in document:
            _reject("full-year 2024 descriptor requires quality_approval path")
        quality_approval = document["quality_approval"]
        if (
            not isinstance(quality_approval, str)
            or quality_approval
            != "configs/quality/approvals/binance-usdm-btcusdt-1m-2024-zero-volume.v1.yaml"
        ):
            _reject(
                "quality_approval must equal approved path "
                "'configs/quality/approvals/binance-usdm-btcusdt-1m-2024-zero-volume.v1.yaml'"
            )
        from quantara.quality_approval import validate_approval_path

        try:
            validate_approval_path(quality_approval)
        except QuantaraError as exc:
            _reject(f"invalid quality_approval path: {exc}")
    else:
        _reject(f"unsupported descriptor combination: {document.get('dataset_id')}")

    return DatasetDescriptor(
        schema=document["schema"],
        dataset_id=document["dataset_id"],
        provider=document["provider"],
        market_type=document["market_type"],
        instrument_id=document["instrument_id"],
        provider_symbol=symbol,
        base_asset=document["base_asset"],
        quote_asset=document["quote_asset"],
        settlement_asset=document["settlement_asset"],
        contract_type=document["contract_type"],
        dataset_type=document["dataset_type"],
        interval=interval,
        start_utc=start,
        end_utc=end,
        archive_url=archive_url,
        checksum_url=checksum_url,
        allowed_hosts=allowed_hosts,
        member_pattern=expected_member_pattern,
        months=months,
        archive_urls=archive_urls,
        checksum_urls=checksum_urls,
        member_patterns=member_patterns,
        schema_version=document["schema_version"],
        timestamp_semantics=document["timestamp_semantics"],
        quality_policy_version=quality_policy_version,
        legal_record=legal_record,
        quality_approval=quality_approval,
    )


@dataclass(frozen=True)
class RightsOperation:
    state: str
    source_terms: str
    review_date: str
    reviewer: str
    rationale: str


@dataclass(frozen=True)
class RightsRecord:
    record_id: str
    provider: str
    reviewer: str
    review_date: str
    operations: dict[str, RightsOperation]

    def permits(self, operation: str) -> bool:
        """Spec §13.4 semantics: UNKNOWN/PROHIBITED block; ALLOWED always
        permits; OWNER_APPROVED_PENDING_COUNSEL permits only the named internal
        operations and can never make customer-facing or commercial-production
        behavior eligible."""
        entry = self.operations.get(operation)
        if entry is None:
            return False
        if operation in APPROVED_INTERNAL_OPERATIONS:
            return entry.state in ("ALLOWED", "OWNER_APPROVED_PENDING_COUNSEL")
        return entry.state == "ALLOWED"


def load_rights_record(path: Path | str) -> RightsRecord:
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        _reject("rights record must be a YAML mapping")
    missing = RIGHTS_TOP_LEVEL_KEYS - set(document)
    if missing:
        _reject(f"missing rights-record keys: {sorted(missing)}")
    unknown = set(document) - RIGHTS_TOP_LEVEL_KEYS
    if unknown:
        _reject(f"unknown rights-record keys: {sorted(unknown)}")
    if document["schema"] != RIGHTS_SCHEMA:
        _reject(f"rights schema must equal {RIGHTS_SCHEMA!r}")

    operations_raw = document["operations"]
    if not isinstance(operations_raw, dict) or set(operations_raw) != set(
        RIGHTS_OPERATIONS
    ):
        _reject(f"operations must cover exactly: {RIGHTS_OPERATIONS}")

    operations: dict[str, RightsOperation] = {}
    for name in RIGHTS_OPERATIONS:
        entry = operations_raw[name]
        if not isinstance(entry, dict) or set(entry) != RIGHTS_OPERATION_KEYS:
            _reject(f"operation {name} needs exactly {sorted(RIGHTS_OPERATION_KEYS)}")
        state = entry["state"]
        if state not in RIGHTS_STATES:
            _reject(f"operation {name} has invalid state {state!r}")
        operations[name] = RightsOperation(
            state=state,
            source_terms=str(entry["source_terms"]),
            review_date=str(entry["review_date"]),
            reviewer=str(entry["reviewer"]),
            rationale=str(entry["rationale"]),
        )

    return RightsRecord(
        record_id=str(document["record_id"]),
        provider=str(document["provider"]),
        reviewer=str(document["reviewer"]),
        review_date=str(document["review_date"]),
        operations=operations,
    )
