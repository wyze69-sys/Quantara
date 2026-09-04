"""D03 exact scalar CSV parsing, with exclusive per-attempt evidence.

Inputs are already-acquired member bytes and a frozen archive selection. This
module performs no acquisition. Raw source SHA-256 covers the complete member;
raw records are compared byte-for-byte (including line endings) for duplicates.
Only identical records deduplicate. Every other same-timestamp record blocks,
including changes in ignored columns or in decimal spelling. No raw record or
ratio value is retained in the parsed rows or attempt JSON.

Physical grammar: UTF-8, no BOM, no quoting, and an exact ordered header.
LF or CRLF record terminators are compared as raw bytes.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from quantara.hashing import HashPayloadError, render_decimal_18
from quantara.parsing import MalformedNumeric, parse_numeric
from quantara.series_descriptor import SERIES_REGISTRY, SeriesArchive, SeriesDescriptor

FUNDING_HEADER = ('calc_time', 'funding_interval_hours', 'last_funding_rate')
OI_HEADER = (
    'create_time', 'symbol', 'sum_open_interest', 'sum_open_interest_value',
    'count_toptrader_long_short_ratio', 'sum_toptrader_long_short_ratio',
    'count_long_short_ratio', 'sum_taker_long_short_vol_ratio',
)
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_ROOT = Path(__file__).resolve().parents[2]
_FUNDING = frozenset(('btc_settled_funding', 'eth_settled_funding'))
_OI = frozenset(('btc_open_interest_5m', 'eth_open_interest_5m'))


class ScalarParseError(ValueError):
    """An unsupported source or invalid scalar record; no partial result."""


class FundingParseError(ScalarParseError):
    """Invalid settled-funding source."""


class OpenInterestParseError(ScalarParseError):
    """Invalid open-interest source."""


class DuplicateConflict(ScalarParseError):
    """Same observation key with nonidentical source bytes."""


class FundingDuplicateConflict(DuplicateConflict, FundingParseError):
    pass


class OpenInterestDuplicateConflict(DuplicateConflict, OpenInterestParseError):
    pass


def require_scalar_decimal(value: Decimal) -> Decimal:
    """Validate decimal128(38,18) exactly, independent of ambient context."""
    if type(value) is not Decimal or not value.is_finite():
        raise ScalarParseError('scalar numeric value must be a finite Decimal')
    if value and value.adjusted() >= 20:
        raise ScalarParseError('scalar exceeds 20 integer places')
    try:
        render_decimal_18(value)
    except (HashPayloadError, ValueError, ArithmeticError) as exc:
        raise ScalarParseError('scalar requires rounding at Q18') from exc
    return value


def _decimal(text: str, *, signed: bool = False) -> Decimal:
    # Legacy numeric grammar/budget is reused without modifying its unsigned
    # kline policy. Funding alone can carry a negative sign.
    negative = signed and text.startswith('-')
    try:
        value = parse_numeric(text[1:] if negative else text)
    except MalformedNumeric as exc:
        raise ScalarParseError('malformed or unrepresentable scalar decimal') from exc
    return require_scalar_decimal(value.copy_negate() if negative else value)


def _milliseconds(moment: datetime) -> int:
    delta = moment - _EPOCH
    return delta.days * 86_400_000 + delta.seconds * 1000 + delta.microseconds // 1000


def _bounds(archive: SeriesArchive) -> tuple[int, int]:
    start = datetime.fromisoformat(archive.period + ('-01' if len(archive.period) == 7 else ''))
    start = start.replace(tzinfo=UTC)
    if len(archive.period) == 7:
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    else:
        end = start + timedelta(days=1)
    return _milliseconds(start), _milliseconds(end)


def _timestamp(text: str, funding: bool) -> int:
    if funding:
        if not re.fullmatch(r'[0-9]{1,19}', text):
            raise ScalarParseError('calc_time must be unsigned epoch milliseconds')
        value = int(text)
        if value > 2**63 - 1:
            raise ScalarParseError('calc_time exceeds int64')
        return value
    if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}', text):
        raise ScalarParseError('create_time must use YYYY-MM-DD HH:MM:SS in UTC')
    try:
        return _milliseconds(datetime.strptime(text, '%Y-%m-%d %H:%M:%S').replace(tzinfo=UTC))
    except ValueError as exc:
        raise ScalarParseError('invalid create_time calendar timestamp') from exc


@dataclass(frozen=True, slots=True)
class ScalarSourceRow:
    event_ts: int
    last_funding_rate: Decimal | None = None
    funding_interval_hours: str | None = None
    sum_open_interest: Decimal | None = None
    sum_open_interest_value: Decimal | None = None


@dataclass(frozen=True, slots=True)
class ScalarParseResult:
    archive: SeriesArchive
    source_sha256: str
    rows: tuple[ScalarSourceRow, ...]
    source_rows: int
    distinct_rows: int
    duplicate_rows: int
    source_ordered: bool
    duplicate_hashes: tuple[str, ...]
    conflict_rows: int  # PARSED is always zero: conflicting attempts raise before return.


def parse_scalar_rows(
    data: bytes, archive: SeriesArchive, *, attempt_path: Path,
    repo_root: Path | str = _ROOT,
) -> ScalarParseResult:
    """Parse one closed archive and always retain terminal attempt evidence.

    The caller supplies a new attempt path under its scratch/staging directory.
    Existing attempts are never overwritten. Failure counts describe the consumed
    prefix and carry counts_complete=false; PARSED is not a D05 quality approval.
    Empty ratio cells are documented source nulls; nonempty cells must satisfy
    unsigned fixed-point grammar. All ratio cells are discarded after validation.
    """
    record = {
        'schema': 'quantara.scalar-parse-attempt/v1', 'status': 'BLOCKED',
        'source_rows': 0, 'distinct_rows': 0, 'duplicate_rows': 0,
        'duplicate_hashes': [],
        'conflict_rows': 0, 'counts_complete': False, 'source_ordered': True,
    }
    error = ScalarParseError
    with Path(attempt_path).open('x', encoding='utf-8', newline='\n') as evidence:
        try:
            if type(archive) is not SeriesArchive or archive.series_id not in _FUNDING | _OI:
                raise ScalarParseError('D03 supports only the four frozen scalar series')
            funding = archive.series_id in _FUNDING
            error = FundingParseError if funding else OpenInterestParseError
            record.update(series_id=archive.series_id, period=archive.period)
            descriptor = SeriesDescriptor(archive.series_id)
            if not descriptor.load_rights(repo_root).permits('normalize_internal'):
                raise error('normalization rights gate is closed')
            if type(data) is not bytes:
                raise error('source member must be bytes')
            digest = hashlib.sha256(data).hexdigest()
            record.update(source_file=archive.member, source_sha256=digest)
            header = FUNDING_HEADER if funding else OI_HEADER
            source = io.BytesIO(data)
            if data.startswith(b'\xef\xbb\xbf'):
                raise error('UTF-8 BOM is forbidden')
            if b'"' in data:
                raise error('quoting is not part of the frozen scalar grammar')
            actual_header = next(csv.reader([source.readline().decode('utf-8')], strict=True))
            if tuple(actual_header) != header:
                raise error('source header differs from exact ordered family header')
            start, end = _bounds(archive)
            unique: dict[int, tuple[bytes, ScalarSourceRow]] = {}
            previous = None
            for raw in source:
                record['source_rows'] += 1
                fields = next(csv.reader([raw.decode('utf-8')], strict=True))
                if len(fields) != len(header):
                    raise error('source row has wrong column count')
                timestamp = _timestamp(fields[0], funding)
                # Period selection is closed to the frozen window. No payload is
                # parsed until this timestamp passes archive membership.
                if not start <= timestamp < end:
                    raise error('observation is outside the selected archive period')
                if previous is not None and timestamp < previous:
                    record['source_ordered'] = False
                previous = timestamp
                if timestamp in unique:
                    if unique[timestamp][0] != raw:
                        record['conflict_rows'] += 1
                        conflict = (FundingDuplicateConflict if funding
                                    else OpenInterestDuplicateConflict)
                        raise conflict('nonidentical source rows share an observation key')
                    record['duplicate_rows'] += 1
                    record['duplicate_hashes'].append(hashlib.sha256(raw).hexdigest())
                    continue
                if funding:
                    interval = fields[1]
                    if not re.fullmatch(r'[0-9]{1,19}', interval) or not 0 < int(interval) < 2**63:
                        raise error('funding_interval_hours must be a positive integer')
                    row = ScalarSourceRow(timestamp, _decimal(fields[2], signed=True), interval)
                else:
                    if fields[1] != descriptor.to_dict()['provider_symbol']:
                        raise error('OI symbol differs from the frozen descriptor')
                    for ratio in fields[4:]:
                        if ratio:
                            _decimal(ratio)
                    row = ScalarSourceRow(
                        timestamp, sum_open_interest=_decimal(fields[2]),
                        sum_open_interest_value=_decimal(fields[3]),
                    )
                unique[timestamp] = (raw, row)
                record['distinct_rows'] += 1
            result = ScalarParseResult(
                archive, digest, tuple(unique[t][1] for t in sorted(unique)),
                record['source_rows'], record['distinct_rows'], record['duplicate_rows'],
                record['source_ordered'],
                tuple(record['duplicate_hashes']), record['conflict_rows'],
            )
            record.update(status='PARSED', counts_complete=True)
            return result
        except Exception as exc:
            record['error_type'] = type(exc).__name__
            if isinstance(exc, (error, DuplicateConflict)):
                raise
            # Never copy source values into the evidence JSON or error message.
            raise error('scalar source validation failed') from exc
        finally:
            json.dump(record, evidence, indent=2, sort_keys=True)
            evidence.write('\n')


# D04 is additive: none of the scalar grammar, result, or evidence contracts change.
KLINE_HEADER = (
    'open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time',
    'quote_volume', 'count', 'taker_buy_volume', 'taker_buy_quote_volume', 'ignore',
)
DERIVED_PRICE_FAMILIES = frozenset(('markPriceKlines', 'indexPriceKlines', 'premiumIndexKlines'))


class KlineParseError(ValueError):
    """Invalid D04 kline source; error text never includes source values."""


class OhlcvtParseError(KlineParseError):
    """Invalid Kraken OHLCVT source."""


class KlineDuplicateConflict(KlineParseError):
    """Same interval start with nonidentical raw record bytes."""


class OhlcvtDuplicateConflict(KlineDuplicateConflict, OhlcvtParseError):
    pass


def kline_bounds(archive: SeriesArchive) -> tuple[int, int, int]:
    """Closed descriptor window, exclusive upper bound, native step in UTC ms."""
    if type(archive) is not SeriesArchive:
        raise KlineParseError('expected a frozen archive selection')
    # Revalidate even a selection tampered with through object.__setattr__.
    SeriesArchive(archive.series_id, archive.period)
    spec = SERIES_REGISTRY[archive.series_id]
    if spec.canonical_value not in ('ohlcv', 'ohlcvt'):
        raise KlineParseError('D04 supports only frozen kline and OHLCVT series')
    if spec.source_family == 'kraken':
        return 1577836800000, 1735689600000, 3600000
    start, end = _bounds(archive)
    return start, end, 60000


@dataclass(frozen=True, slots=True)
class KlineSourceRow:
    event_ts: int
    interval_close_ts: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal | None
    source_count: int
    taker_buy_volume: Decimal | None
    taker_buy_quote_volume: Decimal | None
    source_ignore: str | None
    volume_semantics: str


@dataclass(frozen=True, slots=True)
class KlineParseResult:
    archive: SeriesArchive
    source_sha256: str
    rows: tuple[KlineSourceRow, ...]
    source_rows: int
    distinct_rows: int
    duplicate_rows: int
    source_ordered: bool
    duplicate_hashes: tuple[str, ...]
    conflict_rows: int  # PARSED is always zero: conflicting attempts raise before return.


def _kline_fields(raw: bytes) -> list[str]:
    # Remove only one record terminator. CR inside fields and RFC-4180 quoting
    # are forbidden; terminator bytes remain present in duplicate comparisons.
    body = raw[:-2] if raw.endswith(b'\r\n') else raw.removesuffix(b'\n')
    if b'\r' in body or b'"' in body or b'\xef\xbb\xbf' in body:
        raise KlineParseError('forbidden physical record encoding')
    return body.decode('utf-8').split(',')


def _kline_timestamp(text: str, *, seconds: bool = False) -> int:
    if not re.fullmatch(r'[0-9]{10}' if seconds else r'[0-9]{13}', text):
        raise KlineParseError('timestamp violates family epoch grammar')
    return int(text) * (1000 if seconds else 1)


def parse_kline_rows(
    data: bytes, archive: SeriesArchive, *, attempt_path: Path,
    repo_root: Path | str = _ROOT,
) -> KlineParseResult:
    """Parse bounded member bytes; retain value-blind, exclusive attempt evidence.

    Kraken callers supply only the frozen-window member selection. Any record
    outside that window blocks before payload parsing. SHA-256 binds all input
    bytes, not a claim that these bytes are the unbounded provider archive.
    Kraken interval close is derived as K + 3600000 - 1, never source-observed.
    """
    record = {
        'schema': 'quantara.kline-parse-attempt/v1', 'status': 'BLOCKED',
        'source_rows': 0, 'distinct_rows': 0, 'duplicate_rows': 0,
        'duplicate_hashes': [], 'conflict_rows': 0, 'counts_complete': False,
        'source_ordered': True,
    }
    error = KlineParseError
    with Path(attempt_path).open('x', encoding='utf-8', newline='\n') as evidence:
        try:
            if type(archive) is SeriesArchive and archive.series_id in SERIES_REGISTRY:
                if SERIES_REGISTRY[archive.series_id].source_family == 'kraken':
                    error = OhlcvtParseError
            start, end, step = kline_bounds(archive)
            spec = SERIES_REGISTRY[archive.series_id]
            kraken = spec.source_family == 'kraken'
            derived = spec.source_family in DERIVED_PRICE_FAMILIES
            record.update(series_id=archive.series_id, period=archive.period)
            rights = SeriesDescriptor(archive.series_id).load_rights(repo_root)
            if not rights.permits('normalize_internal'):
                raise error('normalization rights gate is closed')
            if type(data) is not bytes:
                raise error('source member must be bytes')
            digest = hashlib.sha256(data).hexdigest()
            record.update(source_file=archive.member, source_sha256=digest)
            source = io.BytesIO(data)
            if archive.csv_header == 'present':
                if tuple(_kline_fields(source.readline())) != KLINE_HEADER:
                    raise error('header differs from exact ordered family header')
            unique: dict[int, tuple[bytes, KlineSourceRow]] = {}
            previous = None
            for raw in source:
                record['source_rows'] += 1
                fields = _kline_fields(raw)
                if len(fields) != (7 if kraken else 12):
                    raise error('source row has wrong column count')
                timestamp = _kline_timestamp(fields[0], seconds=kraken)
                if not start <= timestamp < end:
                    raise error('observation is outside the selected archive period')
                if timestamp % step:
                    raise error('interval start is not aligned to native grid')
                if previous is not None and timestamp < previous:
                    record['source_ordered'] = False
                previous = timestamp
                if timestamp in unique:
                    if unique[timestamp][0] != raw:
                        record['conflict_rows'] += 1
                        conflict = OhlcvtDuplicateConflict if kraken else KlineDuplicateConflict
                        raise conflict('nonidentical source rows share an interval start')
                    record['duplicate_rows'] += 1
                    record['duplicate_hashes'].append(hashlib.sha256(raw).hexdigest())
                    continue
                close_ts = timestamp + step - 1 if kraken else _kline_timestamp(fields[6])
                if close_ts != timestamp + step - 1:
                    raise error('source bar span differs from native interval')
                prices = tuple(_decimal(field, signed=derived) for field in fields[1:5])
                opening, high, low, close = prices
                if low > min(opening, close) or high < max(opening, close) or high < low:
                    raise error('OHLC invariant failed')
                volume = _decimal(fields[5])
                quote, taker, taker_quote = ((None, None, None) if kraken else
                                            tuple(_decimal(fields[i]) for i in (7, 9, 10)))
                if derived and any(v != 0 for v in (volume, quote, taker, taker_quote)):
                    raise error('derived-price volumes must be structural zeros')
                count = fields[6 if kraken else 8]
                if not re.fullmatch(r'[0-9]{1,19}', count) or int(count) >= 2**63:
                    raise error('source count must be a nonnegative int64')
                row = KlineSourceRow(
                    timestamp, close_ts, *prices, volume, quote, int(count), taker,
                    taker_quote, None if kraken else fields[11],
                    'structural_zero' if derived else 'traded',
                )
                unique[timestamp] = (raw, row)
                record['distinct_rows'] += 1
            record.update(status='PARSED', counts_complete=True)
            return KlineParseResult(
                archive, digest, tuple(unique[t][1] for t in sorted(unique)),
                record['source_rows'], record['distinct_rows'], record['duplicate_rows'],
                record['source_ordered'],
                tuple(record['duplicate_hashes']), record['conflict_rows'],
            )
        except Exception as exc:
            record['error_type'] = type(exc).__name__
            if isinstance(exc, error):
                raise
            # Suppress chained legacy numeric exceptions, which contain values.
            raise error('kline source validation failed') from None
        finally:
            json.dump(record, evidence, indent=2, sort_keys=True)
            evidence.write('\n')
