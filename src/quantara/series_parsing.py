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
from quantara.series_descriptor import SeriesArchive, SeriesDescriptor

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
