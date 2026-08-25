"""Canonical-row assembly, row/sequence invariants, and quality tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from conftest import VALID_DESCRIPTOR_YAML, write_text
from quantara.canonical import (
    CanonicalRow,
    assemble_canonical_rows,
    build_canonical_row,
    make_source_row,
)
from quantara.descriptor import load_descriptor
from quantara.quality import QUALITY_POLICY_VERSION, evaluate_quality

OPEN = 1704067200000


def good_source(**overrides):
    fields = dict(
        open_time=OPEN,
        close_time=OPEN + 59_999,
        open=Decimal("42571.90"),
        high=Decimal("42600.00"),
        low=Decimal("42500.10"),
        close=Decimal("42590.50"),
        base_asset_volume=Decimal("12.5"),
        quote_asset_volume=Decimal("500000.25"),
        trade_count=3210,
        taker_buy_base_volume=Decimal("6.25"),
        taker_buy_quote_volume=Decimal("250000.125"),
        source_ignore="0",
    )
    # Keep the temporal contract intact when shifting open times.
    if "open_time" in overrides and "close_time" not in overrides:
        overrides = {**overrides, "close_time": overrides["open_time"] + 59_999}
    fields.update(overrides)
    return fields


@pytest.fixture()
def descriptor(tmp_path):
    return load_descriptor(write_text(tmp_path / "cfg", VALID_DESCRIPTOR_YAML))


def test_build_canonical_row_shape_and_nominal_time(descriptor) -> None:
    row = build_canonical_row(make_source_row(**good_source()), descriptor)
    assert isinstance(row, CanonicalRow)
    assert row.nominal_available_ms == OPEN + 60_000
    assert row.identity[0] == "binance"
    assert row.instrument_id == "binance:usd_m_futures:BTCUSDT:perpetual"
    arr = row.to_content_array()
    assert len(arr) == 23
    assert arr[10] == OPEN
    assert arr[13] == "42571.900000000000000000"


def test_complete_month_sequence_passes(descriptor) -> None:
    rows = [
        make_source_row(**good_source(open_time=OPEN + i * 60_000))
        for i in range(3)
    ]
    assembled, order_ok = assemble_canonical_rows(rows, descriptor)
    assert order_ok is True
    report = evaluate_quality(assembled, descriptor, source_order_valid=order_ok)
    del report


def test_unordered_but_complete_input_sorts_with_warning(descriptor) -> None:
    rows = [
        make_source_row(**good_source(open_time=OPEN + i * 60_000))
        for i in (2, 0, 1)
    ]
    assembled, order_ok = assemble_canonical_rows(rows, descriptor)
    assert order_ok is False
    assert [r.open_time_ms for r in assembled] == [OPEN, OPEN + 60_000, OPEN + 120_000]
    report = evaluate_quality(assembled, descriptor, source_order_valid=order_ok)
    assert report.state == "WARN_BLOCKED"
    ids = {f.check_id for f in report.findings if f.outcome == "warn"}
    assert "source_order_invalid" in ids


def test_duplicate_open_time_is_hard_failure(descriptor) -> None:
    rows = [
        make_source_row(**good_source(open_time=OPEN)),
        make_source_row(**good_source(open_time=OPEN)),
        make_source_row(**good_source(open_time=OPEN + 60_000)),
    ]
    from quantara.errors import QuantaraError

    with pytest.raises(QuantaraError, match="duplicate"):
        assemble_canonical_rows(rows, descriptor)


def test_gap_in_minute_sequence_is_hard_failure(descriptor) -> None:
    rows = [make_source_row(**good_source(open_time=OPEN))]
    rows.append(make_source_row(**good_source(open_time=OPEN + 120_000)))
    assembled, _ = assemble_canonical_rows(rows, descriptor)
    report = evaluate_quality(
        assembled, descriptor, source_order_valid=True, expected_count=None
    )
    assert report.state == "FAIL"


@pytest.mark.parametrize(
    "overrides",
    [
        {"high": Decimal("42500.00")},  # high < open
        {"low": Decimal("42591.00")},  # low > open
        {"high": Decimal("42580.00"), "low": Decimal("42585.00")},  # high < low
        {"open": Decimal("0")},  # price not positive
        {"base_asset_volume": Decimal("-1")},  # negative volume
        {"trade_count": -3},  # negative count
        {"taker_buy_base_volume": Decimal("13.0")},  # taker base > base volume
        {"taker_buy_quote_volume": Decimal("600000.0")},  # taker quote too big
    ],
)
def test_each_row_invariant_has_failing_regression_example(
    overrides, descriptor
) -> None:
    rows = [make_source_row(**good_source(**overrides))]
    assembled, _ = assemble_canonical_rows(rows, descriptor)
    report = evaluate_quality(
        assembled, descriptor, source_order_valid=True, expected_count=None
    )
    assert report.state == "FAIL"


def test_zero_volume_candle_is_warning_not_failure(descriptor) -> None:
    rows = [
        make_source_row(**good_source()),
        make_source_row(
            **good_source(
                open_time=OPEN + 60_000,
                base_asset_volume=Decimal("0"),
                quote_asset_volume=Decimal("0"),
                taker_buy_base_volume=Decimal("0"),
                taker_buy_quote_volume=Decimal("0"),
            )
        ),
    ]
    assembled, _ = assemble_canonical_rows(rows, descriptor)
    report = evaluate_quality(
        assembled, descriptor, source_order_valid=True, expected_count=None
    )
    assert report.state == "WARN_BLOCKED"
    zero = next(f for f in report.findings if f.check_id == "zero_volume_candle")
    assert zero.count == 1


def test_nonzero_source_ignore_is_warning(descriptor) -> None:
    rows = [make_source_row(**good_source(source_ignore="1"))]
    assembled, _ = assemble_canonical_rows(rows, descriptor)
    report = evaluate_quality(
        assembled, descriptor, source_order_valid=True, expected_count=None
    )
    assert report.state == "WARN_BLOCKED"


def test_wrong_row_count_is_hard_failure(descriptor) -> None:
    rows = [make_source_row(**good_source())]
    assembled, _ = assemble_canonical_rows(rows, descriptor)
    report = evaluate_quality(
        assembled, descriptor, source_order_valid=True, expected_count=3
    )
    assert report.state == "FAIL"
    by_id = {f.check_id: f for f in report.findings}
    assert by_id["row_count_matches_expected"].outcome == "fail"


def test_descriptor_row_count_enforced_for_full_month(descriptor) -> None:
    rows = [make_source_row(**good_source())]
    assembled, _ = assemble_canonical_rows(rows, descriptor)
    report = evaluate_quality(
        assembled,
        descriptor,
        source_order_valid=True,
        expected_count=descriptor.expected_row_count,
    )
    by_id = {f.check_id: f for f in report.findings}
    assert by_id["row_count_matches_expected"].count == 1
    assert by_id["row_count_matches_expected"].evidence["approved_rows"] == 44_640
    assert report.state == "FAIL"


def test_boundary_mismatch_is_hard_failure(descriptor) -> None:
    first = OPEN - 60_000  # one minute before the approved start boundary
    rows = [make_source_row(**good_source(open_time=first))]
    assembled, _ = assemble_canonical_rows(rows, descriptor)
    report = evaluate_quality(
        assembled, descriptor, source_order_valid=True, expected_count=None
    )
    assert report.state == "FAIL"


def test_policy_version_and_pass_state(descriptor) -> None:
    rows = [make_source_row(**good_source())]
    assembled, _ = assemble_canonical_rows(rows, descriptor)
    report = evaluate_quality(
        assembled, descriptor, source_order_valid=True, expected_count=None
    )
    assert QUALITY_POLICY_VERSION == "1"
    assert report.state == "PASS"
