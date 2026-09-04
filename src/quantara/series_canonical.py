"""D03 scalar-series/v1 schema, content identity and exact Parquet persistence.

No kline-v1 identity is modified. Timestamp columns are UTC epoch-ms int64.
Unknown provenance and inapplicable fields are null. The OI provider timestamp
is never relabelled as interval open/close; its eligibility delay is 300000 ms.
The two named payload slots are mutually exclusive, present values are Decimal,
and OI value is Q18 text diagnostic evidence, never a model-feature payload.

Content arrays bind every column in schema order, including the SHA-256 of the
whole source member (whose raw bytes include incidental ratios). They contain no
ratio values or per-ratio hashes. This module grants no quality/publication state.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from quantara.hashing import render_decimal_18
from quantara.jcs import canonicalize
from quantara.series_descriptor import (
    SERIES_REGISTRY,
    SeriesArchive,
    SeriesDescriptor,
    SeriesDescriptorError,
)
from quantara.series_parsing import (
    DERIVED_PRICE_FAMILIES,
    KlineParseError,
    KlineParseResult,
    ScalarParseError,
    ScalarParseResult,
    kline_bounds,
    require_scalar_decimal,
)

SCHEMA_VERSION = 'quantara.scalar-series/v1'
CONTENT_HASH_DOMAIN = 'quantara-scalar-series-content-v1'
SCALAR_COLUMNS = (
    ('provider', 'string', False),
    ('venue', 'string', False),
    ('market_type', 'string', False),
    ('instrument_id', 'string', False),
    ('provider_symbol', 'string', False),
    ('series_id', 'string', False),
    ('native_interval', 'string', False),
    ('source_file', 'string', False),
    ('source_sha256', 'string', False),
    ('event_ts', 'int64', False),
    ('interval_open_ts', 'int64', True),
    ('interval_close_ts', 'int64', True),
    ('settlement_or_snapshot_ts', 'int64', False),
    ('archive_publication_ts', 'int64', True),
    ('ingestion_ts', 'int64', True),
    ('eligibility_ts', 'int64', False),
    ('quality_flags', 'string', True),
    ('timestamp_role', 'string', False),
    ('funding_interval_hours', 'string', True),
    ('last_funding_rate', 'decimal128(38, 18)', True),
    ('sum_open_interest', 'decimal128(38, 18)', True),
    ('sum_open_interest_value', 'string', True),
)
_TYPES = {'string': pa.string(), 'int64': pa.int64(), 'decimal128(38, 18)': pa.decimal128(38, 18)}
PARQUET_SCHEMA = pa.schema(
    [pa.field(name, _TYPES[kind], nullable=nullable) for name, kind, nullable in SCALAR_COLUMNS],
    metadata={b'schema_version': SCHEMA_VERSION.encode('ascii')},
)
WRITER_CONFIG = {
    'compression': 'zstd', 'version': '2.6', 'data_page_version': '2.0', 'store_schema': True,
}
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class ScalarCanonicalError(ValueError):
    """A row violates the closed scalar schema or canonical ordering."""


class ScalarParquetFailure(ScalarCanonicalError):
    """Persistence failed or schema/typed read-back is invalid."""


class ScalarReconciliationMismatch(ScalarCanonicalError):
    """Persisted rows are not exactly the expected rows."""


@dataclass(frozen=True, slots=True)
class ScalarCanonicalRow:
    provider: str
    venue: str
    market_type: str
    instrument_id: str
    provider_symbol: str
    series_id: str
    native_interval: str
    source_file: str
    source_sha256: str
    event_ts: int
    interval_open_ts: int | None
    interval_close_ts: int | None
    settlement_or_snapshot_ts: int
    archive_publication_ts: int | None
    ingestion_ts: int | None
    eligibility_ts: int
    quality_flags: str | None
    timestamp_role: str
    funding_interval_hours: str | None
    last_funding_rate: Decimal | None
    sum_open_interest: Decimal | None
    sum_open_interest_value: str | None

    def to_content_array(self) -> list[object]:
        validate_scalar_row(self)
        return [render_decimal_18(value) if type(value) is Decimal else value
                for name, _, _ in SCALAR_COLUMNS for value in (getattr(self, name),)]


def validate_scalar_row(row: ScalarCanonicalRow) -> None:
    """Validate before hashing/writing and after reading; no coercion permitted."""
    if type(row) is not ScalarCanonicalRow:
        raise ScalarCanonicalError('expected ScalarCanonicalRow')
    for name, kind, nullable in SCALAR_COLUMNS:
        value = getattr(row, name)
        if value is None:
            if nullable:
                continue
            raise ScalarCanonicalError(f'{name} cannot be null')
        if kind == 'string' and (type(value) is not str or not value):
            raise ScalarCanonicalError(f'{name} must be nonempty text')
        if kind == 'int64' and (type(value) is not int or not 0 <= value < 2**63):
            raise ScalarCanonicalError(f'{name} must be nonnegative int64 milliseconds')
        if kind == 'decimal128(38, 18)':
            try:
                require_scalar_decimal(value)
            except ScalarParseError as exc:
                raise ScalarCanonicalError(f'{name} violates decimal128(38,18)') from exc
    try:
        spec = SeriesDescriptor(row.series_id).to_dict()
    except SeriesDescriptorError as exc:
        raise ScalarCanonicalError('unregistered series') from exc
    if spec['canonical_value'] not in ('last_funding_rate', 'sum_open_interest'):
        raise ScalarCanonicalError('non-scalar series is forbidden')
    for name in ('provider', 'venue', 'market_type', 'provider_symbol', 'timestamp_role'):
        if getattr(row, name) != spec[name]:
            raise ScalarCanonicalError(f'{name} differs from frozen descriptor')
    if (row.instrument_id != f'binance:usd_m_futures:{row.provider_symbol}:perpetual'
            or row.native_interval != spec['observation_cadence']):
        raise ScalarCanonicalError('instrument or native cadence drift')
    if not re.fullmatch(r'[0-9a-f]{64}', row.source_sha256):
        raise ScalarCanonicalError('source_sha256 must be lowercase SHA-256')
    if row.interval_open_ts is not None or row.interval_close_ts is not None:
        raise ScalarCanonicalError('scalar source does not establish interval bounds')
    if row.quality_flags is not None:
        raise ScalarCanonicalError('D03 has no quality finding or approval authority')
    funding = spec['canonical_value'] == 'last_funding_rate'
    delay = 1 if funding else 300_000
    if row.event_ts != row.settlement_or_snapshot_ts or row.eligibility_ts != row.event_ts + delay:
        raise ScalarCanonicalError('event/settlement/snapshot eligibility mismatch')
    try:
        moment = _EPOCH + timedelta(milliseconds=row.event_ts)
    except OverflowError as exc:
        raise ScalarCanonicalError('event outside frozen calendar range') from exc
    if not spec['period']['start'] <= moment.date().isoformat() <= spec['period']['end']:
        raise ScalarCanonicalError('event outside frozen series window')
    period = moment.strftime('%Y-%m' if funding else '%Y-%m-%d')
    family = 'fundingRate' if funding else 'metrics'
    if row.source_file != f'{row.provider_symbol}-{family}-{period}.csv':
        raise ScalarCanonicalError('source member does not match event and descriptor')
    if funding:
        interval = row.funding_interval_hours
        if (interval is None or not re.fullmatch(r'[0-9]{1,19}', interval)
                or not 0 < int(interval) < 2**63 or row.last_funding_rate is None
                or row.sum_open_interest is not None or row.sum_open_interest_value is not None):
            raise ScalarCanonicalError('funding payload/evidence shape mismatch')
    else:
        if (row.sum_open_interest is None or row.sum_open_interest < 0
                or row.last_funding_rate is not None or row.funding_interval_hours is not None
                or row.sum_open_interest_value is None):
            raise ScalarCanonicalError('OI payload/evidence shape mismatch')
        try:
            diagnostic = require_scalar_decimal(Decimal(row.sum_open_interest_value))
            if diagnostic < 0 or render_decimal_18(diagnostic) != row.sum_open_interest_value:
                raise ScalarParseError('diagnostic is not nonnegative Q18 text')
        except (ScalarParseError, ArithmeticError, ValueError) as exc:
            raise ScalarCanonicalError('invalid OI diagnostic evidence') from exc


def _ordered(rows: Iterable[ScalarCanonicalRow]) -> tuple[ScalarCanonicalRow, ...]:
    materialized = tuple(rows)
    previous = None
    for row in materialized:
        validate_scalar_row(row)
        key = (row.series_id, row.event_ts)
        if previous is not None and key <= previous:
            raise ScalarCanonicalError('canonical series/time keys must be strictly increasing')
        previous = key
    return materialized


def build_scalar_rows(
    parsed: ScalarParseResult, *, ingestion_ts: int | None = None,
    archive_publication_ts: int | None = None,
) -> tuple[ScalarCanonicalRow, ...]:
    """Assemble only actual parsed observations; no cadence filling or quality approval."""
    spec = SeriesDescriptor(parsed.archive.series_id).to_dict()
    funding = spec['canonical_value'] == 'last_funding_rate'
    rows = []
    for source in parsed.rows:
        diagnostic = source.sum_open_interest_value
        if diagnostic is not None:
            try:
                diagnostic = render_decimal_18(require_scalar_decimal(diagnostic))
            except ScalarParseError as exc:
                raise ScalarCanonicalError('invalid diagnostic Decimal') from exc
        rows.append(ScalarCanonicalRow(
            spec['provider'], spec['venue'], spec['market_type'],
            f"binance:usd_m_futures:{spec['provider_symbol']}:perpetual",
            spec['provider_symbol'], parsed.archive.series_id, spec['observation_cadence'],
            parsed.archive.member, parsed.source_sha256, source.event_ts, None, None,
            source.event_ts, archive_publication_ts, ingestion_ts,
            source.event_ts + (1 if funding else 300_000), None, spec['timestamp_role'],
            source.funding_interval_hours, source.last_funding_rate, source.sum_open_interest,
            diagnostic,
        ))
    return _ordered(rows)


def scalar_schema_fingerprint() -> str:
    payload = {
        'domain': 'quantara-scalar-series-schema-v1', 'schema_version': SCHEMA_VERSION,
        'columns': [{'index': i, 'name': n, 'type': t, 'nullable': null}
                    for i, (n, t, null) in enumerate(SCALAR_COLUMNS)],
    }
    return hashlib.sha256(canonicalize(payload).encode('utf-8')).hexdigest()


def scalar_content_hash(rows: Iterable[ScalarCanonicalRow]) -> str:
    """SHA-256(domain NUL schema-fingerprint NL JCS-row NL ...)."""
    digest = hashlib.sha256(CONTENT_HASH_DOMAIN.encode('ascii') + b'\0')
    digest.update(scalar_schema_fingerprint().encode('ascii') + b'\n')
    for row in _ordered(rows):
        digest.update(canonicalize(row.to_content_array()).encode('utf-8') + b'\n')
    return digest.hexdigest()


def write_scalar_parquet(rows: Iterable[ScalarCanonicalRow], path: Path) -> None:
    rows = _ordered(rows)
    try:
        table = pa.Table.from_pylist([asdict(row) for row in rows], schema=PARQUET_SCHEMA)
        with pq.ParquetWriter(path, PARQUET_SCHEMA, **WRITER_CONFIG) as writer:
            writer.write_table(table)
    except Exception as exc:
        raise ScalarParquetFailure('scalar Parquet write failed') from exc
    reconcile_scalar_parquet(rows, path)


def read_scalar_rows(path: Path) -> tuple[ScalarCanonicalRow, ...]:
    """Check stored schema before explicit-schema decoding; reject coercible drift."""
    try:
        with pq.ParquetFile(Path(path)) as source:
            if not source.schema_arrow.equals(PARQUET_SCHEMA, check_metadata=True):
                raise ScalarParquetFailure('stored scalar schema differs from frozen schema')
            # Schema is already verified: casting cannot hide original type drift.
            table = source.read().cast(PARQUET_SCHEMA, safe=True)
        return _ordered(ScalarCanonicalRow(**values) for values in table.to_pylist())
    except ScalarParquetFailure:
        raise
    except Exception as exc:
        raise ScalarParquetFailure('scalar Parquet read-back failed') from exc


def reconcile_scalar_parquet(rows: Iterable[ScalarCanonicalRow], path: Path) -> None:
    expected = _ordered(rows)
    actual = read_scalar_rows(path)
    if len(actual) != len(expected):
        raise ScalarReconciliationMismatch('scalar row count differs')
    for position, (left, right) in enumerate(zip(expected, actual, strict=True)):
        if left.to_content_array() != right.to_content_array():
            raise ScalarReconciliationMismatch(f'scalar row {position} differs')


# Additive D04 schema. Structural zero volumes are exact source observations;
# absent Kraken-only-inapplicable fields are null. Derived source_count is
# evidence, never trade_count. source_ignore is verbatim evidence, not a feature.
KLINE_SCHEMA_VERSION = 'quantara.kline-series/v1'
KLINE_CONTENT_HASH_DOMAIN = 'quantara-kline-series-content-v1'
KLINE_COLUMNS = (
    ('provider', 'string', False),
    ('venue', 'string', False),
    ('market_type', 'string', False),
    ('instrument_id', 'string', False),
    ('provider_symbol', 'string', False),
    ('series_id', 'string', False),
    ('native_interval', 'string', False),
    ('source_file', 'string', False),
    ('source_sha256', 'string', False),
    ('event_ts', 'int64', False),
    ('interval_open_ts', 'int64', False),
    ('interval_close_ts', 'int64', False),
    ('settlement_or_snapshot_ts', 'int64', True),
    ('archive_publication_ts', 'int64', True),
    ('ingestion_ts', 'int64', True),
    ('eligibility_ts', 'int64', False),
    ('quality_flags', 'string', True),
    ('timestamp_role', 'string', False),
    ('open', 'decimal128(38, 18)', False),
    ('high', 'decimal128(38, 18)', False),
    ('low', 'decimal128(38, 18)', False),
    ('close', 'decimal128(38, 18)', False),
    ('volume', 'decimal128(38, 18)', False),
    ('quote_volume', 'decimal128(38, 18)', True),
    ('trade_count', 'int64', True),
    ('taker_buy_volume', 'decimal128(38, 18)', True),
    ('taker_buy_quote_volume', 'decimal128(38, 18)', True),
    ('source_count', 'int64', False),
    ('source_ignore', 'string', True),
    ('volume_semantics', 'string', False),
)
KLINE_PARQUET_SCHEMA = pa.schema(
    [pa.field(n, _TYPES[t], nullable=null) for n, t, null in KLINE_COLUMNS],
    metadata={b'schema_version': KLINE_SCHEMA_VERSION.encode('ascii')},
)
KLINE_WRITER_CONFIG = {
    'compression': 'zstd', 'version': '2.6', 'data_page_version': '2.0', 'store_schema': True,
}


class KlineCanonicalError(ValueError):
    """Invalid D04 row, ordering, or gap evidence."""


class KlineParquetFailure(KlineCanonicalError):
    """Invalid persistence or typed read-back."""


class KlineReconciliationMismatch(KlineCanonicalError):
    """Persisted rows differ from the expected sequence."""


@dataclass(frozen=True, slots=True)
class KlineCanonicalRow:
    provider: str
    venue: str
    market_type: str
    instrument_id: str
    provider_symbol: str
    series_id: str
    native_interval: str
    source_file: str
    source_sha256: str
    event_ts: int
    interval_open_ts: int
    interval_close_ts: int
    settlement_or_snapshot_ts: int | None
    archive_publication_ts: int | None
    ingestion_ts: int | None
    eligibility_ts: int
    quality_flags: str | None
    timestamp_role: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal | None
    trade_count: int | None
    taker_buy_volume: Decimal | None
    taker_buy_quote_volume: Decimal | None
    source_count: int
    source_ignore: str | None
    volume_semantics: str

    def to_content_array(self) -> list[object]:
        validate_kline_row(self)
        return [render_decimal_18(v) if type(v) is Decimal else v
                for n, _, _ in KLINE_COLUMNS for v in (getattr(self, n),)]


def _kline_instrument(series_id: str) -> str:
    spec = SERIES_REGISTRY[series_id]
    if spec.market_type == 'perpetual':
        return f'binance:usd_m_futures:{spec.provider_symbol}:perpetual'
    return f'{spec.venue}:spot:{spec.provider_symbol}'


def validate_kline_row(row: KlineCanonicalRow) -> None:
    """Revalidate exact types, descriptor identity and family semantics at every boundary."""
    if type(row) is not KlineCanonicalRow:
        raise KlineCanonicalError('expected KlineCanonicalRow')
    for name, kind, nullable in KLINE_COLUMNS:
        value = getattr(row, name)
        if value is None:
            if nullable:
                continue
            raise KlineCanonicalError(f'{name} cannot be null')
        if kind == 'string' and (type(value) is not str or (not value and name != 'source_ignore')):
            raise KlineCanonicalError(f'{name} must be text')
        if kind == 'int64' and (type(value) is not int or not 0 <= value < 2**63):
            raise KlineCanonicalError(f'{name} must be nonnegative int64')
        if kind == 'decimal128(38, 18)':
            try:
                require_scalar_decimal(value)
            except ScalarParseError:
                raise KlineCanonicalError(f'{name} violates exact decimal128(38,18)') from None
    if row.series_id not in SERIES_REGISTRY:
        raise KlineCanonicalError('unregistered series')
    spec = SERIES_REGISTRY[row.series_id]
    if spec.canonical_value not in ('ohlcv', 'ohlcvt'):
        raise KlineCanonicalError('non-kline series is forbidden')
    for name in ('provider', 'venue', 'market_type', 'provider_symbol', 'timestamp_role'):
        if getattr(row, name) != getattr(spec, name):
            raise KlineCanonicalError(f'{name} differs from frozen descriptor')
    if (row.instrument_id != _kline_instrument(row.series_id)
            or row.native_interval != spec.observation_cadence):
        raise KlineCanonicalError('instrument or native interval drift')
    if not re.fullmatch(r'[0-9a-f]{64}', row.source_sha256):
        raise KlineCanonicalError('source_sha256 must be lowercase SHA-256')
    kraken = spec.source_family == 'kraken'
    derived = spec.source_family in DERIVED_PRICE_FAMILIES
    step = 3600000 if kraken else 60000
    if (row.event_ts % step or row.interval_open_ts != row.event_ts
            or row.interval_close_ts != row.event_ts + step - 1
            or row.eligibility_ts != row.interval_close_ts + 1):
        raise KlineCanonicalError('interval or eligibility arithmetic mismatch')
    if row.quality_flags is not None or row.settlement_or_snapshot_ts is not None:
        raise KlineCanonicalError('kline has no quality authority or settlement/snapshot event')
    if not 1577836800000 <= row.event_ts < 1735689600000:
        raise KlineCanonicalError('event outside frozen series window')
    moment = _EPOCH + timedelta(milliseconds=row.event_ts)
    member = ('master_q4/XBTUSD_60.csv' if kraken
              else f'{spec.provider_symbol}-1m-{moment:%Y-%m}.csv')
    if row.source_file != member:
        raise KlineCanonicalError('source member differs from event and descriptor')
    prices = (row.open, row.high, row.low, row.close)
    if not derived and any(v.is_signed() for v in prices):
        raise KlineCanonicalError('traded prices must be unsigned')
    if (row.low > min(row.open, row.close) or row.high < max(row.open, row.close)
            or row.high < row.low):
        raise KlineCanonicalError('OHLC invariant failed')
    volumes = (row.volume, row.quote_volume, row.taker_buy_volume, row.taker_buy_quote_volume)
    if any(v is not None and v.is_signed() for v in volumes):
        raise KlineCanonicalError('volumes must be unsigned')
    if kraken:
        if any(v is not None for v in volumes[1:]) or row.source_ignore is not None:
            raise KlineCanonicalError('Kraken has no Binance-only source columns')
    elif any(v is None for v in volumes) or row.source_ignore is None:
        raise KlineCanonicalError('Binance source columns must be present')
    if derived:
        if any(v != 0 for v in volumes) or row.trade_count is not None:
            raise KlineCanonicalError('derived volume/count semantics violated')
    elif row.trade_count != row.source_count:
        raise KlineCanonicalError('trade count must equal source count')
    if row.volume_semantics != ('structural_zero' if derived else 'traded'):
        raise KlineCanonicalError('volume semantics differ from descriptor family')


def _kline_ordered(rows: Iterable[KlineCanonicalRow]) -> tuple[KlineCanonicalRow, ...]:
    rows = tuple(rows)
    previous = None
    for row in rows:
        validate_kline_row(row)
        key = (row.series_id, row.event_ts)
        if previous is not None and key <= previous:
            raise KlineCanonicalError('canonical series/time keys must be strictly increasing')
        previous = key
    return rows


def build_kline_rows(
    parsed: KlineParseResult, *, ingestion_ts: int | None = None,
    archive_publication_ts: int | None = None,
) -> tuple[KlineCanonicalRow, ...]:
    """Only actual source observations; Kraken close is derived K + 1h - 1ms."""
    if type(parsed) is not KlineParseResult:
        raise KlineCanonicalError('expected KlineParseResult')
    try:
        start, end, _ = kline_bounds(parsed.archive)
    except (KlineParseError, SeriesDescriptorError):
        raise KlineCanonicalError('invalid archive selection') from None
    spec = SERIES_REGISTRY[parsed.archive.series_id]
    derived = spec.source_family in DERIVED_PRICE_FAMILIES
    if (type(parsed.source_rows) is not int or type(parsed.distinct_rows) is not int
            or type(parsed.duplicate_rows) is not int or type(parsed.source_ordered) is not bool
            or parsed.distinct_rows != len(parsed.rows) or parsed.duplicate_rows < 0
            or parsed.source_rows != parsed.distinct_rows + parsed.duplicate_rows):
        raise KlineCanonicalError('parse counts are inconsistent')
    rows = []
    for source in parsed.rows:
        if not start <= source.event_ts < end:
            raise KlineCanonicalError('source row outside selected period')
        rows.append(KlineCanonicalRow(
            spec.provider, spec.venue, spec.market_type,
            _kline_instrument(parsed.archive.series_id),
            spec.provider_symbol, parsed.archive.series_id, spec.observation_cadence,
            parsed.archive.member, parsed.source_sha256, source.event_ts, source.event_ts,
            source.interval_close_ts, None, archive_publication_ts, ingestion_ts,
            source.interval_close_ts + 1, None, spec.timestamp_role,
            source.open, source.high, source.low, source.close, source.volume, source.quote_volume,
            None if derived else source.source_count, source.taker_buy_volume,
            source.taker_buy_quote_volume, source.source_count, source.source_ignore,
            source.volume_semantics,
        ))
    return _kline_ordered(rows)


def kline_schema_fingerprint() -> str:
    payload = {
        'domain': 'quantara-kline-series-schema-v1', 'schema_version': KLINE_SCHEMA_VERSION,
        'columns': [{'index': i, 'name': n, 'type': t, 'nullable': null}
                    for i, (n, t, null) in enumerate(KLINE_COLUMNS)],
    }
    return hashlib.sha256(canonicalize(payload).encode('utf-8')).hexdigest()


def kline_content_hash(rows: Iterable[KlineCanonicalRow]) -> str:
    digest = hashlib.sha256(KLINE_CONTENT_HASH_DOMAIN.encode('ascii') + b'\0')
    digest.update(kline_schema_fingerprint().encode('ascii') + b'\n')
    for row in _kline_ordered(rows):
        digest.update(canonicalize(row.to_content_array()).encode('utf-8') + b'\n')
    return digest.hexdigest()


def write_kline_parquet(rows: Iterable[KlineCanonicalRow], path: Path) -> None:
    rows = _kline_ordered(rows)
    try:
        table = pa.Table.from_pylist([asdict(row) for row in rows], schema=KLINE_PARQUET_SCHEMA)
        with pq.ParquetWriter(path, KLINE_PARQUET_SCHEMA, **KLINE_WRITER_CONFIG) as writer:
            writer.write_table(table)
    except Exception:
        raise KlineParquetFailure('kline Parquet write failed') from None
    reconcile_kline_parquet(rows, path)


def read_kline_rows(path: Path) -> tuple[KlineCanonicalRow, ...]:
    try:
        with pq.ParquetFile(Path(path)) as source:
            if not source.schema_arrow.equals(KLINE_PARQUET_SCHEMA, check_metadata=True):
                raise KlineParquetFailure('stored kline schema differs from frozen schema')
            table = source.read().cast(KLINE_PARQUET_SCHEMA, safe=True)
        return _kline_ordered(KlineCanonicalRow(**values) for values in table.to_pylist())
    except KlineParquetFailure:
        raise
    except Exception:
        raise KlineParquetFailure('kline Parquet read-back failed') from None


def reconcile_kline_parquet(rows: Iterable[KlineCanonicalRow], path: Path) -> None:
    expected, actual = _kline_ordered(rows), read_kline_rows(path)
    if len(expected) != len(actual):
        raise KlineReconciliationMismatch('kline row count differs')
    for position, (left, right) in enumerate(zip(expected, actual, strict=True)):
        if left.to_content_array() != right.to_content_array():
            raise KlineReconciliationMismatch(f'kline row {position} differs')


GAP_SCHEMA_VERSION = 'quantara.kline-gap-manifest/v1'
GAP_HASH_DOMAIN = 'quantara-kline-gap-manifest-content-v1'
GAP_COLUMNS = (
    ('series_id', 'string', False),
    ('interval_open_ts', 'int64', False),
    ('interval_close_ts', 'int64', False),
    ('enumeration_basis', 'string', False),
    ('exclusion_reason', 'null', True),
)
GAP_MANIFEST_FIELDS = (
    ('schema_version', 'string'), ('schema_fingerprint', 'string'),
    ('series_id', 'string'), ('period', 'string'), ('source_file', 'string'),
    ('source_sha256', 'string'), ('period_start_ts', 'int64'), ('period_end_ts', 'int64'),
    ('native_step_ms', 'int64'), ('expected_slots', 'int64'), ('present_slots', 'int64'),
    ('gap_count', 'int64'), ('gaps', 'array'),
)


def gap_schema_fingerprint() -> str:
    payload = {
        'domain': 'quantara-kline-gap-manifest-schema-v1', 'schema_version': GAP_SCHEMA_VERSION,
        'fields': [{'index': i, 'name': n, 'type': t}
                   for i, (n, t) in enumerate(GAP_MANIFEST_FIELDS)],
        'gap_columns': [{'index': i, 'name': n, 'type': t, 'nullable': null}
                        for i, (n, t, null) in enumerate(GAP_COLUMNS)],
    }
    return hashlib.sha256(canonicalize(payload).encode('utf-8')).hexdigest()


def build_gap_manifest(parsed: KlineParseResult) -> dict:
    """Evidence of native-grid absence, without D05 classification or approval.

    exclusion_reason remains null: the closed vocabulary's missing_native_interval
    describes an excluded lookback, and no candidate lookback is evaluated here.
    period_end_ts is exclusive; gap interval_close_ts is inclusive (derived for
    Kraken). Neither absence nor a zero gap count grants publication authority.
    """
    rows = build_kline_rows(parsed)
    start, end, step = kline_bounds(parsed.archive)
    present = {row.event_ts for row in rows}
    gaps = [
        {'series_id': parsed.archive.series_id, 'interval_open_ts': t,
         'interval_close_ts': t + step - 1, 'enumeration_basis': 'descriptor_period_native_grid',
         'exclusion_reason': None}
        for t in range(start, end, step) if t not in present
    ]
    return {
        'schema_version': GAP_SCHEMA_VERSION, 'schema_fingerprint': gap_schema_fingerprint(),
        'series_id': parsed.archive.series_id, 'period': parsed.archive.period,
        'source_file': parsed.archive.member, 'source_sha256': parsed.source_sha256,
        'period_start_ts': start, 'period_end_ts': end, 'native_step_ms': step,
        'expected_slots': (end - start) // step, 'present_slots': len(rows),
        'gap_count': len(gaps), 'gaps': gaps,
    }


def gap_manifest_bytes(manifest: dict) -> bytes:
    """Validate the closed evidence shape then serialize as UTF-8 JCS plus LF."""
    try:
        if type(manifest) is not dict or set(manifest) != {n for n, _ in GAP_MANIFEST_FIELDS}:
            raise KlineCanonicalError('gap manifest fields differ from frozen schema')
        for name, kind in GAP_MANIFEST_FIELDS:
            value = manifest[name]
            expected_type = {'string': str, 'int64': int, 'array': list}[kind]
            if type(value) is not expected_type:
                raise KlineCanonicalError('gap manifest field type differs')
            if kind == 'int64' and not 0 <= value < 2**63:
                raise KlineCanonicalError('gap manifest int64 out of range')
        archive = SeriesArchive(manifest['series_id'], manifest['period'])
        start, end, step = kline_bounds(archive)
        expected = {
            'schema_version': GAP_SCHEMA_VERSION, 'schema_fingerprint': gap_schema_fingerprint(),
            'source_file': archive.member, 'period_start_ts': start, 'period_end_ts': end,
            'native_step_ms': step, 'expected_slots': (end - start) // step,
        }
        if any(manifest[k] != v for k, v in expected.items()):
            raise KlineCanonicalError('gap manifest identity or grid differs')
        if not re.fullmatch(r'[0-9a-f]{64}', manifest['source_sha256']):
            raise KlineCanonicalError('gap source hash is invalid')
        gaps = manifest['gaps']
        if (manifest['gap_count'] != len(gaps)
                or manifest['present_slots'] + len(gaps) != manifest['expected_slots']):
            raise KlineCanonicalError('gap cardinality differs')
        previous = start - step
        for gap in gaps:
            if type(gap) is not dict or set(gap) != {n for n, _, _ in GAP_COLUMNS}:
                raise KlineCanonicalError('gap entry fields differ')
            t = gap['interval_open_ts']
            if (type(t) is not int or not start <= t < end or t % step or t <= previous
                    or type(gap['interval_close_ts']) is not int
                    or gap['interval_close_ts'] != t + step - 1
                    or gap['series_id'] != archive.series_id
                    or gap['enumeration_basis'] != 'descriptor_period_native_grid'
                    or gap['exclusion_reason'] is not None):
                raise KlineCanonicalError('invalid gap grid entry')
            previous = t
        return canonicalize(manifest).encode('utf-8') + b'\n'
    except KlineCanonicalError:
        raise
    except Exception:
        raise KlineCanonicalError('invalid gap manifest') from None


def gap_manifest_hash(manifest: dict) -> str:
    digest = hashlib.sha256(GAP_HASH_DOMAIN.encode('ascii') + b'\0')
    digest.update(gap_schema_fingerprint().encode('ascii') + b'\n')
    digest.update(gap_manifest_bytes(manifest))
    return digest.hexdigest()
