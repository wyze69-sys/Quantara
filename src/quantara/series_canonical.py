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
from quantara.series_descriptor import SeriesDescriptor, SeriesDescriptorError
from quantara.series_parsing import ScalarParseError, ScalarParseResult, require_scalar_decimal

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
