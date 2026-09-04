"""Parsing and numeric-policy tests (spec §§3.3, 6.4–6.5, 15.4)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from conftest import (
    VALID_DESCRIPTOR_YAML,
    extended_year_1m_descriptor_text,
    write_text,
)
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


def make_headerless_descriptor(tmp_path, year: int = 2020):
    """Amendment 2026-08-30: an allow-listed year declaring csv_header absent."""
    text = extended_year_1m_descriptor_text(year).replace(
        "    - data.binance.vision",
        "    - data.binance.vision\n  csv_header: absent",
    )
    return load_descriptor(
        write_text(tmp_path / f"headerless-{year}", text, name=f"cfg-{year}.yaml")
    )


HEADERLESS_ROW_1 = (
    "1577836800000,7195.24,7196.25,7183.14,7186.68,74.55700000000000000,"
    "1577836859999,536101.14,318,26.80000000000000000,192674.13,0"
)
HEADERLESS_ROW_2 = (
    "1577836860000,7186.68,7191.00,7180.00,7188.00,51.20000000000000000,"
    "1577836919999,367920.55,201,20.10000000000000000,144480.10,0"
)


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





def test_scientific_notation_is_expanded_exactly() -> None:
    # Binance renders small funding rates as e.g. 8.4E-7. Scientific notation
    # is exact decimal notation and must be expanded, not treated as a float.
    assert parse_numeric("8.4E-7") == Decimal("8.4E-7")
    assert parse_numeric("1e5") == Decimal("100000")
    assert parse_numeric("1E+5") == Decimal("100000")
    assert parse_numeric("1.5E+3") == Decimal("1500")
    assert parse_numeric("0E0") == Decimal("0")


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
# ---------------------------------------------------------------------------
# Amendment 2026-08-30 (headerless source variant), governing spec §3.3.
# The 2020-01 … 2021-12 official monthly archives carry no header line. A v2
# descriptor may declare source.csv_header: absent for those two allow-listed
# identities; the first line is then a data row bound positionally to the same
# frozen 12 field names in the same order.
# ---------------------------------------------------------------------------


def headerless_csv(*rows: str) -> bytes:
    return ("\n".join(rows) + "\n").encode("utf-8")


def test_headerless_first_line_is_parsed_as_data(tmp_path) -> None:
    descriptor = make_headerless_descriptor(tmp_path)
    assert descriptor.csv_header_absent is True
    rows = parse_rows(
        decode_member(headerless_csv(HEADERLESS_ROW_1, HEADERLESS_ROW_2)), descriptor
    )
    assert len(rows) == 2
    assert rows[0].open_time == 1577836800000
    assert rows[1].open_time == 1577836860000


def test_headerless_binds_all_twelve_fields_positionally(tmp_path) -> None:
    descriptor = make_headerless_descriptor(tmp_path)
    row = parse_rows(decode_member(headerless_csv(HEADERLESS_ROW_1)), descriptor)[0]
    assert row.open_time == 1577836800000
    assert str(row.open) == "7195.24"
    assert str(row.high) == "7196.25"
    assert str(row.low) == "7183.14"
    assert str(row.close) == "7186.68"
    assert str(row.base_asset_volume) == "74.55700000000000000"
    assert row.close_time == 1577836859999
    assert str(row.quote_asset_volume) == "536101.14"
    assert row.trade_count == 318
    assert str(row.taker_buy_base_volume) == "26.80000000000000000"
    assert str(row.taker_buy_quote_volume) == "192674.13"
    assert row.source_ignore == "0"


def test_headerless_declared_but_header_present_is_rejected(tmp_path) -> None:
    """Declared absence that turns out to be presence must fail loudly."""
    descriptor = make_headerless_descriptor(tmp_path)
    with pytest.raises(SourceHeaderMismatch, match="first line is the exact"):
        parse_rows(decode_member(csv_text(HEADERLESS_ROW_1)), descriptor)


def test_headered_descriptor_still_requires_the_header(tmp_path) -> None:
    """The converse: an undeclared variant on headerless bytes is rejected."""
    descriptor = make_descriptor(tmp_path)
    assert descriptor.csv_header_absent is False
    with pytest.raises(SourceHeaderMismatch, match="header mismatch"):
        parse_rows(decode_member(headerless_csv(ROW_1)), descriptor)


def test_headerless_empty_member_is_rejected(tmp_path) -> None:
    descriptor = make_headerless_descriptor(tmp_path)
    with pytest.raises(SourceHeaderMismatch, match="no data rows"):
        parse_rows(decode_member(b""), descriptor)


def test_headerless_wrong_field_count_reports_line_one(tmp_path) -> None:
    """Line numbering starts at 1 on the headerless path, not 2."""
    descriptor = make_headerless_descriptor(tmp_path)
    truncated = ",".join(HEADERLESS_ROW_1.split(",")[:11])
    with pytest.raises(SourceHeaderMismatch, match="line 1: expected 12 fields"):
        parse_rows(decode_member(headerless_csv(truncated)), descriptor)


def test_headerless_second_line_wrong_field_count_reports_line_two(tmp_path) -> None:
    descriptor = make_headerless_descriptor(tmp_path)
    truncated = ",".join(HEADERLESS_ROW_2.split(",")[:11])
    with pytest.raises(SourceHeaderMismatch, match="line 2: expected 12 fields"):
        parse_rows(decode_member(headerless_csv(HEADERLESS_ROW_1, truncated)), descriptor)


def test_headerless_accepts_crlf_and_trailing_blank_lines(tmp_path) -> None:
    descriptor = make_headerless_descriptor(tmp_path)
    payload = headerless_csv(HEADERLESS_ROW_1, HEADERLESS_ROW_2).replace(b"\n", b"\r\n")
    rows = parse_rows(decode_member(payload) + "\n\n", descriptor)
    assert len(rows) == 2


def test_headerless_still_enforces_period_and_timestamp_invariants(tmp_path) -> None:
    descriptor = make_headerless_descriptor(tmp_path)
    outside = HEADERLESS_ROW_1.replace("1577836800000", "1609459200000", 1).replace(
        "1577836859999", "1609459259999", 1
    )  # 2021-01-01T00:00Z, outside the 2020 half-open period
    with pytest.raises(MalformedTimestamp):
        parse_rows(decode_member(headerless_csv(outside)), descriptor)
    bad_close = HEADERLESS_ROW_1.replace("1577836859999", "1577836860000")
    with pytest.raises(MalformedTimestamp):
        parse_rows(decode_member(headerless_csv(bad_close)), descriptor)


def test_headerless_rejects_bom_like_the_default_path(tmp_path) -> None:
    with pytest.raises(SourceHeaderMismatch):
        decode_member(b"\xef\xbb\xbf" + headerless_csv(HEADERLESS_ROW_1))


def test_headerless_2021_identity_is_also_allow_listed(tmp_path) -> None:
    descriptor = make_headerless_descriptor(tmp_path, year=2021)
    assert descriptor.csv_header_absent is True
    row_2021 = HEADERLESS_ROW_1.replace("1577836800000", "1609459200000", 1).replace(
        "1577836859999", "1609459259999", 1
    )
    rows = parse_rows(decode_member(headerless_csv(row_2021)), descriptor)
    assert rows[0].open_time == 1609459200000
