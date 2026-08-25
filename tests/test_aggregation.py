"""Aggregation engine tests: adapters, contracts, exactness (plan Task 2)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from conftest import MONTH_OPEN_START
from quantara.canonical import (
    CanonicalRow,
    DuplicateOpenTime,
    read_canonical_rows,
    write_canonical_parquet,
)
from quantara.errors import QuantaraError

IDENTITY_1H = (
    "binance",
    "usd_m_futures",
    "binance:usd_m_futures:BTCUSDT:perpetual",
    "BTCUSDT",
    "BTC",
    "USDT",
    "USDT",
    "perpetual",
    "1h",
    "binance_usdm_kline_1h_v1",
)

HOUR_MS = 3_600_000


def minute_row(
    open_time_ms: int,
    o="100",
    h="110",
    lo="90",
    c="105",
    bv="1.5",
    qv="150",
    n="10",
    tbv="0.5",
    tqv="50",
    ignore="0",
) -> CanonicalRow:
    d = Decimal
    return CanonicalRow(
        identity=("p", "m", "i", "s", "b", "q", "sa", "ct", "1m", "sv"),
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + 59_999,
        nominal_available_ms=open_time_ms + 60_000,
        open=d(o),
        high=d(h),
        low=d(lo),
        close=d(c),
        base_asset_volume=d(bv),
        quote_asset_volume=d(qv),
        trade_count=int(n),
        taker_buy_base_volume=d(tbv),
        taker_buy_quote_volume=d(tqv),
        source_ignore=ignore,
    )


def full_hour(start_ms: int) -> list[CanonicalRow]:
    return [minute_row(start_ms + i * 60_000) for i in range(60)]


# --- persisted-row adapter ---------------------------------------------------


def test_adapter_roundtrips_through_real_parquet(tmp_path) -> None:
    from quantara.aggregation import rows_from_persisted

    minutes = [minute_row(MONTH_OPEN_START + i * 60_000) for i in range(5)]
    path = tmp_path / "parent.parquet"
    write_canonical_parquet(minutes, path)
    persisted = read_canonical_rows(path)
    restored = rows_from_persisted(persisted)
    assert [r.to_content_array() for r in restored] == [
        r.to_content_array() for r in minutes
    ]


def test_adapter_rejects_wrong_tuple_width() -> None:
    from quantara.aggregation import rows_from_persisted

    with pytest.raises(QuantaraError, match="width"):
        rows_from_persisted([tuple(range(22))])


def test_adapter_rejects_float_instances() -> None:
    from quantara.aggregation import rows_from_persisted

    row = list(minute_row(MONTH_OPEN_START).to_content_array())
    row[13] = 42571.9  # binary float contaminating an exact decimal slot
    with pytest.raises(QuantaraError, match="float"):
        rows_from_persisted([tuple(row)])


# --- input contract ----------------------------------------------------------


def test_duplicate_open_times_raise() -> None:
    from quantara.aggregation import aggregate_timeframe

    minutes = full_hour(MONTH_OPEN_START)
    minutes[5] = minute_row(minutes[4].open_time_ms)
    with pytest.raises(DuplicateOpenTime):
        aggregate_timeframe(minutes, IDENTITY_1H, HOUR_MS)


def test_unordered_input_is_rejected_not_sorted() -> None:
    from quantara.aggregation import UnorderedMinuteInput, aggregate_timeframe

    minutes = full_hour(MONTH_OPEN_START)
    minutes[10], minutes[20] = minutes[20], minutes[10]
    with pytest.raises(UnorderedMinuteInput):
        aggregate_timeframe(minutes, IDENTITY_1H, HOUR_MS)



# --- exact aggregation -------------------------------------------------------


def test_ordinary_hour_aggregates_exactly() -> None:
    from quantara.aggregation import aggregate_timeframe

    bars = aggregate_timeframe(full_hour(MONTH_OPEN_START), IDENTITY_1H, HOUR_MS)
    assert len(bars) == 1
    bar = bars[0]
    assert bar.identity == IDENTITY_1H
    assert bar.open_time_ms == MONTH_OPEN_START
    assert bar.close_time_ms == MONTH_OPEN_START + HOUR_MS - 1
    assert bar.nominal_available_ms == MONTH_OPEN_START + HOUR_MS
    # hand-computed: open of earliest, close of latest, max high, min low.
    assert (bar.open, bar.high, bar.low, bar.close) == (
        Decimal("100"),
        Decimal("110"),
        Decimal("90"),
        Decimal("105"),
    )
    assert bar.base_asset_volume == Decimal("90.0")  # 1.5 * 60
    assert bar.quote_asset_volume == Decimal("9000")  # 150 * 60
    assert bar.trade_count == 600  # 10 * 60
    assert (bar.taker_buy_base_volume, bar.taker_buy_quote_volume) == (
        Decimal("30.0"),
        Decimal("3000"),
    )


def test_incomplete_group_raises_incomplete_group_error() -> None:
    from quantara.aggregation import IncompleteGroup, aggregate_timeframe

    minutes = full_hour(MONTH_OPEN_START)[:-1]  # one missing minute
    with pytest.raises(IncompleteGroup) as excinfo:
        aggregate_timeframe(minutes, IDENTITY_1H, HOUR_MS)
    assert excinfo.value.error_id == "incomplete_group"


def test_nonzero_source_ignore_rejects_the_group() -> None:
    from quantara.aggregation import NonzeroSourceIgnoreInGroup, aggregate_timeframe

    minutes = full_hour(MONTH_OPEN_START)
    minutes[30] = minute_row(MONTH_OPEN_START + 30 * 60_000, ignore="1")
    with pytest.raises(NonzeroSourceIgnoreInGroup) as excinfo:
        aggregate_timeframe(minutes, IDENTITY_1H, HOUR_MS)
    assert excinfo.value.error_id == "nonzero_source_ignore_in_group"

def test_hour_boundary_and_day_boundary_selection() -> None:
    from quantara.aggregation import aggregate_timeframe

    # Two minutes of one hour + the rest of the next hour must fail the first
    # bucket's completeness gate, while a full day yields one daily bar.
    start = MONTH_OPEN_START + HOUR_MS - 120_000
    partial = [
        minute_row(start, o="50", h="55", lo="45", c="52"),
        minute_row(start + 60_000, o="51", h="200", lo="44", c="53"),
    ]
    with pytest.raises(QuantaraError):
        aggregate_timeframe(partial, IDENTITY_1H, HOUR_MS)

    day_ms = 86_400_000
    day_minutes = [
        minute_row(MONTH_OPEN_START + i * 60_000, bv="0.25") for i in range(1440)
    ]
    hours = aggregate_timeframe(day_minutes, IDENTITY_1H, HOUR_MS)
    assert len(hours) == 24
    days = aggregate_timeframe(day_minutes, IDENTITY_1H[:9] + ("1d",), day_ms)
    assert len(days) == 1
    assert days[0].open_time_ms == MONTH_OPEN_START  # midnight boundary
    assert days[0].close_time_ms == MONTH_OPEN_START + day_ms - 1
    assert days[0].nominal_available_ms == MONTH_OPEN_START + day_ms
    assert days[0].base_asset_volume == Decimal("360")  # 0.25 * 1440


def test_extreme_selection_across_minutes() -> None:
    from quantara.aggregation import aggregate_timeframe

    minutes = full_hour(MONTH_OPEN_START)
    minutes[7] = minute_row(MONTH_OPEN_START + 7 * 60_000, h="999")
    minutes[42] = minute_row(MONTH_OPEN_START + 42 * 60_000, lo="0.5")
    bar = aggregate_timeframe(minutes, IDENTITY_1H, HOUR_MS)[0]
    assert bar.high == Decimal("999") and bar.low == Decimal("0.5")


def test_high_precision_decimal_sums_exercise_trailing_zero_rendering() -> None:
    from quantara.aggregation import aggregate_timeframe
    from quantara.hashing import render_decimal_18

    total = Decimal(0)
    minutes = []
    for i in range(60):
        t = MONTH_OPEN_START + i * 60_000
        addend = Decimal(f"0.{i:02d}0000000000000123")
        total += addend
        minutes.append(minute_row(t, bv=f"0.{i:02d}0000000000000123"))
    bar = aggregate_timeframe(minutes, IDENTITY_1H, HOUR_MS)[0]
    assert bar.base_asset_volume == total
    # Exact rendering carries all 18 fractional digits, never rounded.
    assert render_decimal_18(bar.base_asset_volume) == (
        f"{total.quantize(Decimal(1).scaleb(-18)):f}"
    )


def test_naive_independent_reference_on_a_fixed_hour() -> None:
    """Fixed-seed deterministic cross-check against a test-local reference."""
    from quantara.aggregation import aggregate_timeframe

    minutes = [minute_row(MONTH_OPEN_START + i * 60_000) for i in range(60)]
    bars = aggregate_timeframe(minutes, IDENTITY_1H, HOUR_MS)
    d = Decimal
    ref_open, ref_close = minutes[0].open, minutes[-1].close
    ref_high = max(r.high for r in minutes)
    ref_low = min(r.low for r in minutes)
    ref_bv = sum((r.base_asset_volume for r in minutes), d(0))
    ref_qv = sum((r.quote_asset_volume for r in minutes), d(0))
    ref_n = sum(r.trade_count for r in minutes)
    ref_tbv = sum((r.taker_buy_base_volume for r in minutes), d(0))
    ref_tqv = sum((r.taker_buy_quote_volume for r in minutes), d(0))
    bar = bars[0]
    assert (bar.open, bar.close, bar.high, bar.low) == (
        ref_open, ref_close, ref_high, ref_low)
    assert bar.base_asset_volume == ref_bv and bar.quote_asset_volume == ref_qv
    assert bar.trade_count == ref_n
    assert (bar.taker_buy_base_volume, bar.taker_buy_quote_volume) == (ref_tbv,
                                                                       ref_tqv)


# --- hypothesis: generated valid hours equal the naive reference --------------


@settings(max_examples=25, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=99),
            st.integers(min_value=1, max_value=500),
            st.integers(min_value=0, max_value=100),
            st.integers(min_value=0, max_value=10_000),
            st.integers(min_value=0, max_value=5000),
        ),
        min_size=60,
        max_size=60,
    )
)
def test_property_generated_hour_equals_naive_reference(sixties) -> None:
    from quantara.aggregation import aggregate_timeframe

    base = MONTH_OPEN_START
    rows: list[CanonicalRow] = []
    d = Decimal
    for i, (low_int, height, close_off, vol_cents, count) in enumerate(sixties):
        t = base + i * 60_000
        low = d(low_int)
        high = low + d(height)
        open_ = low
        close = min(open_ + d(close_off), high)
        rows.append(
            CanonicalRow(
                identity=("p", "m", "i", "s", "b", "q", "sa", "ct", "1m", "sv"),
                open_time_ms=t,
                close_time_ms=t + 59_999,
                nominal_available_ms=t + 60_000,
                open=open_,
                high=high,
                low=low,
                close=close,
                base_asset_volume=d(vol_cents) / d(100),
                quote_asset_volume=d(vol_cents) * 137 / d(100),
                trade_count=count,
                taker_buy_base_volume=d(vol_cents) / d(200),
                taker_buy_quote_volume=d(vol_cents) * 137 / d(200),
                source_ignore="0",
            )
        )
    engine = aggregate_timeframe(rows, IDENTITY_1H, HOUR_MS)[0]
    first_open = rows[0].open
    last_close = rows[-1].close
    assert engine.open == first_open and engine.close == last_close
    assert engine.high == max(r.high for r in rows)
    assert engine.low == min(r.low for r in rows)
    assert engine.base_asset_volume == sum(
        (r.base_asset_volume for r in rows), d(0))
    assert engine.quote_asset_volume == sum(
        (r.quote_asset_volume for r in rows), d(0))
    assert engine.trade_count == sum(r.trade_count for r in rows)

