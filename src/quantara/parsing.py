"""Exact kline parsing and numeric policy.

Validates the exact ordered 12-name UTF-8 header contract (or, under the
2026-08-30 headerless-source amendment, verifies that a descriptor declaring
``source.csv_header: absent`` really has no header line and binds the same
frozen 12 field positions in the same order); parses unsigned
base-10 epoch-millisecond timestamps directly to integers; parses numeric
fields through decimal.Decimal only (binary floats are never constructed);
enforces the decimal128(38,18) representability budget exactly per spec §6.5
without rounding; keeps the source ignore field verbatim; and applies the
half-open period membership test to open times (spec §§3.3, 6.4–6.5).
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass

from quantara.descriptor import DatasetDescriptor
from quantara.errors import (
    DECIMAL_PRECISION_OR_SCALE_OVERFLOW,
    MALFORMED_NUMERIC_FIELD,
    MALFORMED_TIMESTAMP_FIELD,
    SOURCE_HEADER_MISMATCH,
    QuantaraError,
)

__all__ = [
    "HEADER",
    "DecimalOverflow",
    "MalformedNumeric",
    "MalformedTimestamp",
    "SourceHeaderMismatch",
    "SourceRow",
    "decode_member",
    "parse_numeric",
    "parse_rows",
    "parse_timestamp_ms",
]

HEADER = (
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "count",
    "taker_buy_volume",
    "taker_buy_quote_volume",
    "ignore",
)

NUMERIC_PATTERN = re.compile(r"^(0|[1-9][0-9]*)(\.[0-9]+)?$")
UNSIGNED_INT_PATTERN = re.compile(r"^[0-9]+$")
SIGNED_INT_PATTERN = re.compile(r"^-?[0-9]+$")

INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1

MAX_INTEGER_PLACES = 20
MAX_FRACTIONAL_PLACES = 18
MAX_TOTAL_FIXED_POINT_DIGITS = 38


class SourceHeaderMismatch(QuantaraError):
    error_id = SOURCE_HEADER_MISMATCH


class MalformedTimestamp(QuantaraError):
    error_id = MALFORMED_TIMESTAMP_FIELD


class MalformedNumeric(QuantaraError):
    error_id = MALFORMED_NUMERIC_FIELD


class DecimalOverflow(MalformedNumeric):
    error_id = DECIMAL_PRECISION_OR_SCALE_OVERFLOW


@dataclass(frozen=True)
class SourceRow:
    open_time: int
    close_time: int
    open: object
    high: object
    low: object
    close: object
    base_asset_volume: object
    quote_asset_volume: object
    trade_count: int
    taker_buy_base_volume: object
    taker_buy_quote_volume: object
    source_ignore: str


def decode_member(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        raise SourceHeaderMismatch("UTF-8 byte-order mark is forbidden")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourceHeaderMismatch(f"member is not valid UTF-8: {exc}") from exc


def parse_numeric(text: str):
    """Parse through exact decimal arithmetic only; floats never appear."""
    if not NUMERIC_PATTERN.fullmatch(text):
        raise MalformedNumeric(f"numeric text rejected by policy: {text!r}")
    integer_part, _, fractional_part = text.partition(".")
    integer_places = len(integer_part.lstrip("0"))
    trimmed_fraction = fractional_part.rstrip("0")
    if len(trimmed_fraction) > MAX_FRACTIONAL_PLACES:
        raise DecimalOverflow(
            f"{text!r} has {len(trimmed_fraction)} significant fractional digits; "
            f"max is {MAX_FRACTIONAL_PLACES}; rounding is never permitted"
        )
    if integer_places > MAX_INTEGER_PLACES:
        raise DecimalOverflow(
            f"{text!r} has {integer_places} integer places; max is {MAX_INTEGER_PLACES}"
        )
    total_digits = integer_places + len(fractional_part)
    if total_digits > MAX_TOTAL_FIXED_POINT_DIGITS:
        raise DecimalOverflow(
            f"{text!r} needs {total_digits} fixed-point digits; max is "
            f"{MAX_TOTAL_FIXED_POINT_DIGITS}"
        )
    from decimal import Decimal

    return Decimal(text)


def parse_timestamp_ms(text: str, field: str) -> int:
    """Unsigned base-10 epoch milliseconds only — no signs, dots, exponents."""
    if not UNSIGNED_INT_PATTERN.fullmatch(text):
        raise MalformedTimestamp(
            f"{field} must be an unsigned base-10 epoch-ms integer, got {text!r}"
        )
    return int(text)


def parse_rows(text: str, descriptor: DatasetDescriptor) -> list[SourceRow]:
    start_ms = int(descriptor.start_utc.timestamp() * 1000)
    end_ms = int(descriptor.end_utc.timestamp() * 1000)
    header_absent = bool(getattr(descriptor, "csv_header_absent", False))

    reader = csv.reader(io.StringIO(text, newline=""), delimiter=",")
    try:
        first = next(reader)
    except StopIteration as exc:
        raise SourceHeaderMismatch(
            "member has no data rows" if header_absent else "member has no header row"
        ) from exc

    if header_absent:
        # Amendment 2026-08-30: declared absence must actually be absence.
        # A first line that IS the frozen header means provider drift and
        # fails as loudly as the converse does on the default path.
        if tuple(first) == HEADER:
            raise SourceHeaderMismatch(
                "descriptor declares source.csv_header 'absent' but the member's "
                "first line is the exact 12-name header row"
            )
        first_data_row: list[str] | None = first
        first_line_number = 1
    else:
        if tuple(first) != HEADER:
            raise SourceHeaderMismatch(
                f"header mismatch: expected {HEADER}, got {tuple(first)}"
            )
        first_data_row = None
        first_line_number = 2

    def _data_rows():
        if first_data_row is not None:
            yield first_line_number, first_data_row
            offset = first_line_number + 1
        else:
            offset = first_line_number
        yield from enumerate(reader, start=offset)

    rows: list[SourceRow] = []
    for line_number, fields in _data_rows():
        if not fields:
            continue
        if len(fields) != len(HEADER):
            raise SourceHeaderMismatch(
                f"line {line_number}: expected {len(HEADER)} fields, got {len(fields)}"
            )
        (
            open_time,
            open_,
            high,
            low,
            close,
            volume,
            close_time,
            quote_volume,
            count,
            taker_buy_volume,
            taker_buy_quote_volume,
            ignore,
        ) = fields

        open_ms = parse_timestamp_ms(open_time, "open_time")
        close_ms = parse_timestamp_ms(close_time, "close_time")
        if close_ms != open_ms + 59_999:
            raise MalformedTimestamp(
                f"line {line_number}: close_time {close_ms} != open_time + 59999"
            )
        if not (start_ms <= open_ms < end_ms):
            raise MalformedTimestamp(
                f"line {line_number}: open_time {open_ms} outside [start, end)"
            )
        if not SIGNED_INT_PATTERN.fullmatch(count) or not (
            INT64_MIN <= int(count) <= INT64_MAX
        ):
            raise MalformedNumeric(f"line {line_number}: invalid count {count!r}")

        rows.append(
            SourceRow(
                open_time=open_ms,
                close_time=close_ms,
                open=parse_numeric(open_),
                high=parse_numeric(high),
                low=parse_numeric(low),
                close=parse_numeric(close),
                base_asset_volume=parse_numeric(volume),
                quote_asset_volume=parse_numeric(quote_volume),
                trade_count=int(count),
                taker_buy_base_volume=parse_numeric(taker_buy_volume),
                taker_buy_quote_volume=parse_numeric(taker_buy_quote_volume),
                source_ignore=ignore,
            )
        )
    return rows
