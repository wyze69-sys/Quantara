"""Parsing and numeric-policy tests (spec §§3.3, 6.4–6.5, 15.4)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from conftest import VALID_DESCRIPTOR_YAML, write_text
from quantara.descriptor import load_descriptor
from quantara.parsing import (
    DecimalOverflow,
    MalformedNumeric,
    MalformedTimestamp,
    SourceHeaderMismatch,
    decode_member,
    parse_numeric,
    parse_rows,
)


def make_descriptor(tmp_path):
    return load_descriptor(write_text(tmp_path / "cfg", VALID_DESCRIPTOR_YAML))


def csv_text(*rows: str, header: str | None = None) -> bytes:
    head = (
        header
        if header is not None
        else "open_time,open,high,low,close,volume,close_time,"
        "quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore"
    )
    body = "\n".join((head, *rows)) + "\n"
    return body.encode("utf-8")


ROW_1 = (
    "1704067200000,42571.90,42600.00,42500.10,42590.50,12.345678901234567890,"
    "1704067259999,500000.25,3210,6.25,250000.125,0"
)


def test_decode_rejects_bom() -> None:
    with pytest.raises(SourceHeaderMismatch):
        decode_member(b"\xef\xbb\xbf" + csv_text())


def test_decode_accepts_utf8_and_crlf(tmp_path) -> None:
    text = decode_member(csv_text(ROW_1).replace(b"\n", b"\r\n"))
    rows = parse_rows(text, make_descriptor(tmp_path))
    assert len(rows) == 1
    assert rows[0].open_time == 1704067200000


@pytest.mark.parametrize(
    "header",
    [
        "open_time,open,high,low,close,volume,close_time,quote_volume,count",  # missing
        "open_time,open,high,low,close,volume,close_time,quote_volume,count,"
        "taker_buy_volume,taker_buy_quote_volume,ignore,extra",  # extra
        "open,open_time,high,low,close,volume,close_time,quote_volume,count,"
        "taker_buy_volume,taker_buy_quote_volume,ignore",  # reordered
        "open_time,open,high,low,close,volume,close_time,quote_volume,count,"
        "taker_buy_volume,taker_buy_quote_volume,ignore,ignore",  # duplicated
        "Open_time,open,high,low,close,volume,close_time,quote_volume,count,"
        "taker_buy_volume,taker_buy_quote_volume,ignore",  # case-changed
        "open_time;open;high;low;close;volume;close_time;quote_volume;count;"
        "taker_buy_volume;taker_buy_quote_volume;ignore",  # wrong delimiter
    ],
)
def test_header_contract_is_exact(header: str, tmp_path) -> None:
    with pytest.raises(SourceHeaderMismatch):
        parse_rows(decode_member(csv_text(ROW_1, header=header)), make_descriptor(tmp_path))


def test_rfc4180_quoting_in_ignore_field(tmp_path) -> None:
    quoted = ROW_1.replace(",0", ',"0"')
    rows = parse_rows(decode_member(csv_text(quoted)), make_descriptor(tmp_path))
    assert rows[0].source_ignore == "0"


@pytest.mark.parametrize(
    "bad",
    [
        "-1",
        "1.5",
        "+123",
        "1e9",
        "1704067200000.0",
        " 123 ",
        "0x10",
        "12345678901.2",
        "",
    ],
)
def test_malformed_timestamps_are_rejected(bad: str, tmp_path) -> None:
    row = ROW_1.replace("1704067200000", bad, 1)
    with pytest.raises(MalformedTimestamp):
        parse_rows(decode_member(csv_text(row)), make_descriptor(tmp_path))


def test_close_time_must_equal_open_plus_59999(tmp_path) -> None:
    row = ROW_1.replace("1704067259999", "1704067260000")
    with pytest.raises(MalformedTimestamp):
        parse_rows(decode_member(csv_text(row)), make_descriptor(tmp_path))


def test_open_time_outside_period_is_rejected(tmp_path) -> None:
    outside = ROW_1.replace("1704067200000", "1706745600000")  # 2024-02-01T00:00Z
    with pytest.raises(MalformedTimestamp):
        parse_rows(decode_member(csv_text(outside)), make_descriptor(tmp_path))


def test_parse_numeric_accepts_canonical_forms() -> None:
    assert parse_numeric("0") == Decimal("0")
    assert parse_numeric("42571.90") == Decimal("42571.90")
    assert parse_numeric("0.000000001") == Decimal("0.000000001")
    assert parse_numeric("98765432109876543210.123456789012345678") == (
        Decimal("98765432109876543210.123456789012345678")
    )


@pytest.mark.parametrize(
    "bad",
    ["-1", "+1", "1.", ".5", "01", "1e5", "NaN", "Infinity", "", " 1", "1_000", "１"],
)
def test_malformed_numerics_are_rejected(bad: str) -> None:
    with pytest.raises(MalformedNumeric):
        parse_numeric(bad)


@pytest.mark.parametrize(
    ("text",),
    [
        ("0.1234567890123456789",),  # 19 fractional places
        ("123456789012345678901.0",),  # 21 integer places
        ("12345678901234567890.12345678901234567890",),  # > 38 total digits
    ],
)
def test_decimal_budget_overflow_is_rejected_without_rounding(text: str) -> None:
    with pytest.raises(DecimalOverflow):
        parse_numeric(text)


def test_trailing_zeros_are_insignificant_for_the_budget() -> None:
    # 18 fractional places after trailing-zero trim: representable; the parsed
    # Decimal preserves source scale exactly.
    assert str(parse_numeric("0.100000000000000000")) == "0.100000000000000000"
    assert (
        str(parse_numeric("42571.900000000000000000")) == "42571.900000000000000000"
    )


def test_golden_value_survives_exactly(tmp_path) -> None:
    rows = parse_rows(decode_member(csv_text(ROW_1)), make_descriptor(tmp_path))
    assert str(rows[0].open) == "42571.90"
    assert str(rows[0].base_asset_volume) == "12.345678901234567890"
    assert str(rows[0].taker_buy_quote_volume) == "250000.125"


def test_full_row_mapping(tmp_path) -> None:
    rows = parse_rows(decode_member(csv_text(ROW_1)), make_descriptor(tmp_path))
    row = rows[0]
    assert row.open_time == 1704067200000
    assert row.close_time == 1704067259999
    assert row.trade_count == 3210
    assert row.source_ignore == "0"
    assert str(row.high) == "42600.00"


def test_wrong_field_count_is_rejected(tmp_path) -> None:
    truncated = ",".join(ROW_1.split(",")[:11])
    with pytest.raises(SourceHeaderMismatch):
        parse_rows(decode_member(csv_text(truncated)), make_descriptor(tmp_path))


def test_one_row_and_blank_lines(tmp_path) -> None:
    text = decode_member(csv_text(ROW_1)) + "\n\n"
    rows = parse_rows(text, make_descriptor(tmp_path))
    assert len(rows) == 1


def test_negative_trade_count_parses_but_is_preserved(tmp_path) -> None:
    row = ROW_1.replace(",3210,", ",-1,")
    rows = parse_rows(decode_member(csv_text(row)), make_descriptor(tmp_path))
    assert rows[0].trade_count == -1  # negativity is an invariant failure (Task 7)


def test_nonzero_ignore_is_kept_verbatim(tmp_path) -> None:
    row = ROW_1[::-1].replace("0"[::-1], "0", 1)[::-1]  # no-op guard
    del row
    patched = ROW_1[: ROW_1.rindex(",")] + ",7"
    rows = parse_rows(decode_member(csv_text(patched)), make_descriptor(tmp_path))
    assert rows[0].source_ignore == "7"
