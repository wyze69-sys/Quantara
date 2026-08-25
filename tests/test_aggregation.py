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
from quantara.hashing import canonical_content_hash, schema_fingerprint

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
    identity_1d = IDENTITY_1H[:8] + ("1d", "binance_usdm_kline_1d_v1")
    days = aggregate_timeframe(day_minutes, identity_1d, day_ms)

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



# --- Task 8: frozen golden multi-timeframe transformation fixture -------------
# GOLDEN below was produced by an independent out-of-repo generator script
# (transaction dir %TEMP%\\quantara-slice-002\\generate_golden.py) that
# reimplements JCS, 18-digit decimal rendering, schema fingerprints, content
# framing, aggregation arithmetic, and the §10 check sequence from the design
# text alone — reviewed, then frozen. The engine must reproduce it exactly.

DAY_MS = 86_400_000
GOLDEN_MIDNIGHT = 1_704_067_200_000  # 2024-01-01T00:00:00Z


def _golden_minute_rows():
    rows = []
    for t, o, h, lo, c, bv, qv, n, tbv, tqv in GOLDEN["minute_rows"]:
        rows.append(
            minute_row(t, o=o, h=h, lo=lo, c=c, bv=bv, qv=qv, n=n,
                       tbv=tbv, tqv=tqv)
        )
    return rows


def test_golden_hour_aggregates_and_content_hash_match_frozen() -> None:
    from quantara.aggregation import aggregate_timeframe
    bars = aggregate_timeframe(_golden_minute_rows(), IDENTITY_1H, HOUR_MS)
    assert len(bars) == 2
    for bar, expected in zip(bars, GOLDEN["expected_hour_bars"], strict=True):
        arr = bar.to_content_array()
        observed = [arr[10], arr[13], arr[14], arr[15], arr[16], arr[17],
                    arr[18], arr[19]]
        assert observed == expected
    fingerprint = schema_fingerprint("binance_usdm_kline_1h_v1")
    assert canonical_content_hash(
        fingerprint, [b.to_content_array() for b in bars]
    ) == GOLDEN["expected_hour_content_hash"]


def test_golden_hour_quality_identity_matches_frozen() -> None:
    from quantara.aggregation import aggregate_timeframe
    from quantara.derive_quality import evaluate_derived_quality

    class _View:
        timeframe_ms = HOUR_MS
        start_utc_open_ms = GOLDEN["fixture_start_ms"]

    bars = aggregate_timeframe(_golden_minute_rows(), IDENTITY_1H, HOUR_MS)
    report = evaluate_derived_quality(
        bars, _View(), expected_count=2, reconciliation_ok=True
    )
    assert report.state == "PASS"
    assert report.identity() == GOLDEN["expected_hour_quality_identity"]


def test_golden_day_aggregate_content_hash_and_identity_match_frozen() -> None:
    from quantara.aggregation import aggregate_timeframe
    from quantara.derive_quality import evaluate_derived_quality

    rows = []
    for rep in range(13):
        for record in GOLDEN["minute_rows"]:
            shifted_open = record[0] + rep * 2 * HOUR_MS
            if GOLDEN_MIDNIGHT <= shifted_open < GOLDEN_MIDNIGHT + DAY_MS:
                rows.append(minute_row(shifted_open, o=record[1], h=record[2],
                                       lo=record[3], c=record[4], bv=record[5],
                                       qv=record[6], n=record[7],
                                       tbv=record[8], tqv=record[9]))
    assert len(rows) == 1440  # one complete calendar day at the boundary
    bars = aggregate_timeframe(rows, (IDENTITY_1H[:8] + ("1d", "binance_usdm_kline_1d_v1")), DAY_MS)
    assert len(bars) == 1
    bar = bars[0]
    arr = bar.to_content_array()
    observed = [arr[10], arr[13], arr[14], arr[15], arr[16], arr[17], arr[18],
                arr[19]]
    assert observed == GOLDEN["expected_day_bar"]
    fingerprint = schema_fingerprint("binance_usdm_kline_1d_v1")
    assert canonical_content_hash(fingerprint, [arr]) == (
        GOLDEN["expected_day_content_hash"]
    )

    class _View:
        timeframe_ms = DAY_MS
        start_utc_open_ms = GOLDEN_MIDNIGHT

    report = evaluate_derived_quality(bars, _View(), expected_count=1,
                                      reconciliation_ok=True)
    assert report.state == "PASS"
    assert report.identity() == GOLDEN["expected_day_quality_identity"]


def test_golden_window_rejects_daily_aggregation_as_incomplete() -> None:
    from quantara.aggregation import aggregate_timeframe
    # The frozen 120-minute window cannot construct a daily bar; the engine's
    # frozen expectation for that misuse is a hard incomplete_group failure.
    identity_1d = (IDENTITY_1H[:8] + ("1d", "binance_usdm_kline_1d_v1"))
    with pytest.raises(QuantaraError):
        aggregate_timeframe(_golden_minute_rows(), identity_1d, DAY_MS)


GOLDEN = {
 "fixture_start_ms": 1704063600000,
 "minute_rows": [
  [
   1704063600000,
   "91",
   "110",
   "90",
   "91",
   "1.23E-16",
   "100",
   5,
   "6.15E-17",
   "50"
  ],
  [
   1704063660000,
   "93",
   "121",
   "91",
   "94",
   "0.010000000000000123",
   "101",
   6,
   "0.0050000000000000615",
   "50.5"
  ],
  [
   1704063720000,
   "95",
   "132",
   "92",
   "97",
   "0.020000000000000123",
   "102",
   7,
   "0.0100000000000000615",
   "51"
  ],
  [
   1704063780000,
   "94",
   "143",
   "93",
   "97",
   "0.030000000000000123",
   "103",
   8,
   "0.0150000000000000615",
   "51.5"
  ],
  [
   1704063840000,
   "96",
   "154",
   "94",
   "100",
   "0.040000000000000123",
   "104",
   9,
   "0.0200000000000000615",
   "52"
  ],
  [
   1704063900000,
   "98",
   "115",
   "95",
   "103",
   "0.050000000000000123",
   "105",
   10,
   "0.0250000000000000615",
   "52.5"
  ],
  [
   1704063960000,
   "97",
   "126",
   "96",
   "103",
   "0.060000000000000123",
   "106",
   11,
   "0.0300000000000000615",
   "53"
  ],
  [
   1704064020000,
   "92",
   "130",
   "90",
   "99",
   "0.070000000000000123",
   "107",
   12,
   "0.0350000000000000615",
   "53.5"
  ],
  [
   1704064080000,
   "94",
   "141",
   "91",
   "102",
   "0.080000000000000123",
   "108",
   13,
   "0.0400000000000000615",
   "54"
  ],
  [
   1704064140000,
   "93",
   "152",
   "92",
   "102",
   "0.090000000000000123",
   "109",
   5,
   "0.0450000000000000615",
   "54.5"
  ],
  [
   1704064200000,
   "95",
   "113",
   "93",
   "105",
   "0.100000000000000123",
   "110",
   6,
   "0.0500000000000000615",
   "55"
  ],
  [
   1704064260000,
   "97",
   "124",
   "94",
   "97",
   "0.110000000000000123",
   "111",
   7,
   "0.0550000000000000615",
   "55.5"
  ],
  [
   1704064320000,
   "96",
   "135",
   "95",
   "97",
   "0.120000000000000123",
   "112",
   8,
   "0.0600000000000000615",
   "56"
  ],
  [
   1704064380000,
   "98",
   "146",
   "96",
   "100",
   "0.130000000000000123",
   "113",
   9,
   "0.0650000000000000615",
   "56.5"
  ],
  [
   1704064440000,
   "93",
   "150",
   "90",
   "96",
   "0.140000000000000123",
   "114",
   10,
   "0.0700000000000000615",
   "57"
  ],
  [
   1704064500000,
   "92",
   "111",
   "91",
   "96",
   "0.150000000000000123",
   "115",
   11,
   "0.0750000000000000615",
   "57.5"
  ],
  [
   1704064560000,
   "94",
   "122",
   "92",
   "99",
   "0.160000000000000123",
   "116",
   12,
   "0.0800000000000000615",
   "58"
  ],
  [
   1704064620000,
   "96",
   "133",
   "93",
   "102",
   "0.170000000000000123",
   "117",
   13,
   "0.0850000000000000615",
   "58.5"
  ],
  [
   1704064680000,
   "95",
   "144",
   "94",
   "102",
   "0.180000000000000123",
   "118",
   5,
   "0.0900000000000000615",
   "59"
  ],
  [
   1704064740000,
   "97",
   "155",
   "95",
   "105",
   "0.190000000000000123",
   "119",
   6,
   "0.0950000000000000615",
   "59.5"
  ],
  [
   1704064800000,
   "99",
   "116",
   "96",
   "108",
   "0.200000000000000123",
   "120",
   7,
   "0.1000000000000000615",
   "60"
  ],
  [
   1704064860000,
   "91",
   "120",
   "90",
   "101",
   "0.210000000000000123",
   "121",
   8,
   "0.1050000000000000615",
   "60.5"
  ],
  [
   1704064920000,
   "93",
   "131",
   "91",
   "93",
   "0.220000000000000123",
   "122",
   9,
   "0.1100000000000000615",
   "61"
  ],
  [
   1704064980000,
   "95",
   "142",
   "92",
   "96",
   "0.230000000000000123",
   "123",
   10,
   "0.1150000000000000615",
   "61.5"
  ],
  [
   1704065040000,
   "94",
   "153",
   "93",
   "96",
   "0.240000000000000123",
   "124",
   11,
   "0.1200000000000000615",
   "62"
  ],
  [
   1704065100000,
   "96",
   "114",
   "94",
   "99",
   "0.250000000000000123",
   "125",
   12,
   "0.1250000000000000615",
   "62.5"
  ],
  [
   1704065160000,
   "98",
   "125",
   "95",
   "102",
   "0.260000000000000123",
   "126",
   13,
   "0.1300000000000000615",
   "63"
  ],
  [
   1704065220000,
   "97",
   "136",
   "96",
   "102",
   "0.270000000000000123",
   "127",
   5,
   "0.1350000000000000615",
   "63.5"
  ],
  [
   1704065280000,
   "92",
   "140",
   "90",
   "98",
   "0.280000000000000123",
   "128",
   6,
   "0.1400000000000000615",
   "64"
  ],
  [
   1704065340000,
   "94",
   "151",
   "91",
   "101",
   "0.290000000000000123",
   "129",
   7,
   "0.1450000000000000615",
   "64.5"
  ],
  [
   1704065400000,
   "93",
   "112",
   "92",
   "101",
   "0.300000000000000123",
   "130",
   8,
   "0.1500000000000000615",
   "65"
  ],
  [
   1704065460000,
   "95",
   "123",
   "93",
   "104",
   "0.310000000000000123",
   "131",
   9,
   "0.1550000000000000615",
   "65.5"
  ],
  [
   1704065520000,
   "97",
   "134",
   "94",
   "107",
   "0.320000000000000123",
   "132",
   10,
   "0.1600000000000000615",
   "66"
  ],
  [
   1704065580000,
   "96",
   "145",
   "95",
   "96",
   "0.330000000000000123",
   "133",
   11,
   "0.1650000000000000615",
   "66.5"
  ],
  [
   1704065640000,
   "98",
   "156",
   "96",
   "99",
   "0.340000000000000123",
   "134",
   12,
   "0.1700000000000000615",
   "67"
  ],
  [
   1704065700000,
   "93",
   "110",
   "90",
   "95",
   "0.350000000000000123",
   "135",
   13,
   "0.1750000000000000615",
   "67.5"
  ],
  [
   1704065760000,
   "92",
   "121",
   "91",
   "95",
   "0.360000000000000123",
   "136",
   5,
   "0.1800000000000000615",
   "68"
  ],
  [
   1704065820000,
   "94",
   "132",
   "92",
   "98",
   "0.370000000000000123",
   "137",
   6,
   "0.1850000000000000615",
   "68.5"
  ],
  [
   1704065880000,
   "96",
   "143",
   "93",
   "101",
   "0.380000000000000123",
   "138",
   7,
   "0.1900000000000000615",
   "69"
  ],
  [
   1704065940000,
   "95",
   "154",
   "94",
   "101",
   "0.390000000000000123",
   "139",
   8,
   "0.1950000000000000615",
   "69.5"
  ],
  [
   1704066000000,
   "97",
   "115",
   "95",
   "104",
   "0.400000000000000123",
   "140",
   9,
   "0.2000000000000000615",
   "70"
  ],
  [
   1704066060000,
   "99",
   "126",
   "96",
   "107",
   "0.410000000000000123",
   "141",
   10,
   "0.2050000000000000615",
   "70.5"
  ],
  [
   1704066120000,
   "91",
   "130",
   "90",
   "100",
   "0.420000000000000123",
   "142",
   11,
   "0.2100000000000000615",
   "71"
  ],
  [
   1704066180000,
   "93",
   "141",
   "91",
   "103",
   "0.430000000000000123",
   "143",
   12,
   "0.2150000000000000615",
   "71.5"
  ],
  [
   1704066240000,
   "95",
   "152",
   "92",
   "95",
   "0.440000000000000123",
   "144",
   13,
   "0.2200000000000000615",
   "72"
  ],
  [
   1704066300000,
   "94",
   "113",
   "93",
   "95",
   "0.450000000000000123",
   "145",
   5,
   "0.2250000000000000615",
   "72.5"
  ],
  [
   1704066360000,
   "96",
   "124",
   "94",
   "98",
   "0.460000000000000123",
   "146",
   6,
   "0.2300000000000000615",
   "73"
  ],
  [
   1704066420000,
   "98",
   "135",
   "95",
   "101",
   "0.470000000000000123",
   "147",
   7,
   "0.2350000000000000615",
   "73.5"
  ],
  [
   1704066480000,
   "97",
   "146",
   "96",
   "101",
   "0.480000000000000123",
   "148",
   8,
   "0.2400000000000000615",
   "74"
  ],
  [
   1704066540000,
   "92",
   "150",
   "90",
   "97",
   "0.490000000000000123",
   "149",
   9,
   "0.2450000000000000615",
   "74.5"
  ],
  [
   1704066600000,
   "94",
   "111",
   "91",
   "100",
   "0.500000000000000123",
   "150",
   10,
   "0.2500000000000000615",
   "75"
  ],
  [
   1704066660000,
   "93",
   "122",
   "92",
   "100",
   "0.510000000000000123",
   "151",
   11,
   "0.2550000000000000615",
   "75.5"
  ],
  [
   1704066720000,
   "95",
   "133",
   "93",
   "103",
   "0.520000000000000123",
   "152",
   12,
   "0.2600000000000000615",
   "76"
  ],
  [
   1704066780000,
   "97",
   "144",
   "94",
   "106",
   "0.530000000000000123",
   "153",
   13,
   "0.2650000000000000615",
   "76.5"
  ],
  [
   1704066840000,
   "96",
   "155",
   "95",
   "106",
   "0.540000000000000123",
   "154",
   5,
   "0.2700000000000000615",
   "77"
  ],
  [
   1704066900000,
   "98",
   "116",
   "96",
   "98",
   "0.550000000000000123",
   "155",
   6,
   "0.2750000000000000615",
   "77.5"
  ],
  [
   1704066960000,
   "93",
   "120",
   "90",
   "94",
   "0.560000000000000123",
   "156",
   7,
   "0.2800000000000000615",
   "78"
  ],
  [
   1704067020000,
   "92",
   "131",
   "91",
   "94",
   "0.570000000000000123",
   "157",
   8,
   "0.2850000000000000615",
   "78.5"
  ],
  [
   1704067080000,
   "94",
   "142",
   "92",
   "97",
   "0.580000000000000123",
   "158",
   9,
   "0.2900000000000000615",
   "79"
  ],
  [
   1704067140000,
   "96",
   "153",
   "93",
   "100",
   "0.590000000000000123",
   "159",
   10,
   "0.2950000000000000615",
   "79.5"
  ],
  [
   1704067200000,
   "95",
   "114",
   "94",
   "100",
   "0.600000000000000123",
   "160",
   11,
   "0.3000000000000000615",
   "80"
  ],
  [
   1704067260000,
   "97",
   "125",
   "95",
   "103",
   "0.610000000000000123",
   "161",
   12,
   "0.3050000000000000615",
   "80.5"
  ],
  [
   1704067320000,
   "99",
   "136",
   "96",
   "106",
   "0.620000000000000123",
   "162",
   13,
   "0.3100000000000000615",
   "81"
  ],
  [
   1704067380000,
   "91",
   "140",
   "90",
   "99",
   "0.630000000000000123",
   "163",
   5,
   "0.3150000000000000615",
   "81.5"
  ],
  [
   1704067440000,
   "93",
   "151",
   "91",
   "102",
   "0.640000000000000123",
   "164",
   6,
   "0.3200000000000000615",
   "82"
  ],
  [
   1704067500000,
   "95",
   "112",
   "92",
   "105",
   "0.650000000000000123",
   "165",
   7,
   "0.3250000000000000615",
   "82.5"
  ],
  [
   1704067560000,
   "94",
   "123",
   "93",
   "94",
   "0.660000000000000123",
   "166",
   8,
   "0.3300000000000000615",
   "83"
  ],
  [
   1704067620000,
   "96",
   "134",
   "94",
   "97",
   "0.670000000000000123",
   "167",
   9,
   "0.3350000000000000615",
   "83.5"
  ],
  [
   1704067680000,
   "98",
   "145",
   "95",
   "100",
   "0.680000000000000123",
   "168",
   10,
   "0.3400000000000000615",
   "84"
  ],
  [
   1704067740000,
   "97",
   "156",
   "96",
   "100",
   "0.690000000000000123",
   "169",
   11,
   "0.3450000000000000615",
   "84.5"
  ],
  [
   1704067800000,
   "92",
   "110",
   "90",
   "96",
   "0.700000000000000123",
   "170",
   12,
   "0.3500000000000000615",
   "85"
  ],
  [
   1704067860000,
   "94",
   "121",
   "91",
   "99",
   "0.710000000000000123",
   "171",
   13,
   "0.3550000000000000615",
   "85.5"
  ],
  [
   1704067920000,
   "93",
   "132",
   "92",
   "99",
   "0.720000000000000123",
   "172",
   5,
   "0.3600000000000000615",
   "86"
  ],
  [
   1704067980000,
   "95",
   "143",
   "93",
   "102",
   "0.730000000000000123",
   "173",
   6,
   "0.3650000000000000615",
   "86.5"
  ],
  [
   1704068040000,
   "97",
   "154",
   "94",
   "105",
   "0.740000000000000123",
   "174",
   7,
   "0.3700000000000000615",
   "87"
  ],
  [
   1704068100000,
   "96",
   "115",
   "95",
   "105",
   "0.750000000000000123",
   "175",
   8,
   "0.3750000000000000615",
   "87.5"
  ],
  [
   1704068160000,
   "98",
   "126",
   "96",
   "108",
   "0.760000000000000123",
   "176",
   9,
   "0.3800000000000000615",
   "88"
  ],
  [
   1704068220000,
   "93",
   "130",
   "90",
   "93",
   "0.770000000000000123",
   "177",
   10,
   "0.3850000000000000615",
   "88.5"
  ],
  [
   1704068280000,
   "92",
   "141",
   "91",
   "93",
   "0.780000000000000123",
   "178",
   11,
   "0.3900000000000000615",
   "89"
  ],
  [
   1704068340000,
   "94",
   "152",
   "92",
   "96",
   "0.790000000000000123",
   "179",
   12,
   "0.3950000000000000615",
   "89.5"
  ],
  [
   1704068400000,
   "96",
   "113",
   "93",
   "99",
   "0.800000000000000123",
   "180",
   13,
   "0.4000000000000000615",
   "90"
  ],
  [
   1704068460000,
   "95",
   "124",
   "94",
   "99",
   "0.810000000000000123",
   "181",
   5,
   "0.4050000000000000615",
   "90.5"
  ],
  [
   1704068520000,
   "97",
   "135",
   "95",
   "102",
   "0.820000000000000123",
   "182",
   6,
   "0.4100000000000000615",
   "91"
  ],
  [
   1704068580000,
   "99",
   "146",
   "96",
   "105",
   "0.830000000000000123",
   "183",
   7,
   "0.4150000000000000615",
   "91.5"
  ],
  [
   1704068640000,
   "91",
   "150",
   "90",
   "98",
   "0.840000000000000123",
   "184",
   8,
   "0.4200000000000000615",
   "92"
  ],
  [
   1704068700000,
   "93",
   "111",
   "91",
   "101",
   "0.850000000000000123",
   "185",
   9,
   "0.4250000000000000615",
   "92.5"
  ],
  [
   1704068760000,
   "95",
   "122",
   "92",
   "104",
   "0.860000000000000123",
   "186",
   10,
   "0.4300000000000000615",
   "93"
  ],
  [
   1704068820000,
   "94",
   "133",
   "93",
   "104",
   "0.870000000000000123",
   "187",
   11,
   "0.4350000000000000615",
   "93.5"
  ],
  [
   1704068880000,
   "96",
   "144",
   "94",
   "96",
   "0.880000000000000123",
   "188",
   12,
   "0.4400000000000000615",
   "94"
  ],
  [
   1704068940000,
   "98",
   "155",
   "95",
   "99",
   "0.890000000000000123",
   "189",
   13,
   "0.4450000000000000615",
   "94.5"
  ],
  [
   1704069000000,
   "97",
   "116",
   "96",
   "99",
   "0.900000000000000123",
   "190",
   5,
   "0.4500000000000000615",
   "95"
  ],
  [
   1704069060000,
   "92",
   "120",
   "90",
   "95",
   "0.910000000000000123",
   "191",
   6,
   "0.4550000000000000615",
   "95.5"
  ],
  [
   1704069120000,
   "94",
   "131",
   "91",
   "98",
   "0.920000000000000123",
   "192",
   7,
   "0.4600000000000000615",
   "96"
  ],
  [
   1704069180000,
   "93",
   "142",
   "92",
   "98",
   "0.930000000000000123",
   "193",
   8,
   "0.4650000000000000615",
   "96.5"
  ],
  [
   1704069240000,
   "95",
   "153",
   "93",
   "101",
   "0.940000000000000123",
   "194",
   9,
   "0.4700000000000000615",
   "97"
  ],
  [
   1704069300000,
   "97",
   "114",
   "94",
   "104",
   "0.950000000000000123",
   "195",
   10,
   "0.4750000000000000615",
   "97.5"
  ],
  [
   1704069360000,
   "96",
   "125",
   "95",
   "104",
   "0.960000000000000123",
   "196",
   11,
   "0.4800000000000000615",
   "98"
  ],
  [
   1704069420000,
   "98",
   "136",
   "96",
   "107",
   "0.970000000000000123",
   "197",
   12,
   "0.4850000000000000615",
   "98.5"
  ],
  [
   1704069480000,
   "93",
   "140",
   "90",
   "103",
   "0.980000000000000123",
   "198",
   13,
   "0.4900000000000000615",
   "99"
  ],
  [
   1704069540000,
   "92",
   "151",
   "91",
   "92",
   "0.990000000000000123",
   "199",
   5,
   "0.4950000000000000615",
   "99.5"
  ],
  [
   1704069600000,
   "94",
   "112",
   "92",
   "95",
   "0.1000000000000000123",
   "200",
   6,
   "0.05000000000000000615",
   "100"
  ],
  [
   1704069660000,
   "96",
   "123",
   "93",
   "98",
   "0.1010000000000000123",
   "201",
   7,
   "0.05050000000000000615",
   "100.5"
  ],
  [
   1704069720000,
   "95",
   "134",
   "94",
   "98",
   "0.1020000000000000123",
   "202",
   8,
   "0.05100000000000000615",
   "101"
  ],
  [
   1704069780000,
   "97",
   "145",
   "95",
   "101",
   "0.1030000000000000123",
   "203",
   9,
   "0.05150000000000000615",
   "101.5"
  ],
  [
   1704069840000,
   "99",
   "156",
   "96",
   "104",
   "0.1040000000000000123",
   "204",
   10,
   "0.05200000000000000615",
   "102"
  ],
  [
   1704069900000,
   "91",
   "110",
   "90",
   "97",
   "0.1050000000000000123",
   "205",
   11,
   "0.05250000000000000615",
   "102.5"
  ],
  [
   1704069960000,
   "93",
   "121",
   "91",
   "100",
   "0.1060000000000000123",
   "206",
   12,
   "0.05300000000000000615",
   "103"
  ],
  [
   1704070020000,
   "95",
   "132",
   "92",
   "103",
   "0.1070000000000000123",
   "207",
   13,
   "0.05350000000000000615",
   "103.5"
  ],
  [
   1704070080000,
   "94",
   "143",
   "93",
   "103",
   "0.1080000000000000123",
   "208",
   5,
   "0.05400000000000000615",
   "104"
  ],
  [
   1704070140000,
   "96",
   "154",
   "94",
   "106",
   "0.1090000000000000123",
   "209",
   6,
   "0.05450000000000000615",
   "104.5"
  ],
  [
   1704070200000,
   "98",
   "115",
   "95",
   "98",
   "0.1100000000000000123",
   "210",
   7,
   "0.05500000000000000615",
   "105"
  ],
  [
   1704070260000,
   "97",
   "126",
   "96",
   "98",
   "0.1110000000000000123",
   "211",
   8,
   "0.05550000000000000615",
   "105.5"
  ],
  [
   1704070320000,
   "92",
   "130",
   "90",
   "94",
   "0.1120000000000000123",
   "212",
   9,
   "0.05600000000000000615",
   "106"
  ],
  [
   1704070380000,
   "94",
   "141",
   "91",
   "97",
   "0.1130000000000000123",
   "213",
   10,
   "0.05650000000000000615",
   "106.5"
  ],
  [
   1704070440000,
   "93",
   "152",
   "92",
   "97",
   "0.1140000000000000123",
   "214",
   11,
   "0.05700000000000000615",
   "107"
  ],
  [
   1704070500000,
   "95",
   "113",
   "93",
   "100",
   "0.1150000000000000123",
   "215",
   12,
   "0.05750000000000000615",
   "107.5"
  ],
  [
   1704070560000,
   "97",
   "124",
   "94",
   "103",
   "0.1160000000000000123",
   "216",
   13,
   "0.05800000000000000615",
   "108"
  ],
  [
   1704070620000,
   "96",
   "135",
   "95",
   "103",
   "0.1170000000000000123",
   "217",
   5,
   "0.05850000000000000615",
   "108.5"
  ],
  [
   1704070680000,
   "98",
   "146",
   "96",
   "106",
   "0.1180000000000000123",
   "218",
   6,
   "0.05900000000000000615",
   "109"
  ],
  [
   1704070740000,
   "93",
   "150",
   "90",
   "102",
   "0.1190000000000000123",
   "219",
   7,
   "0.05950000000000000615",
   "109.5"
  ]
 ],
 "expected_hour_bars": [
  [
   1704063600000,
   "91.000000000000000000",
   "156.000000000000000000",
   "90.000000000000000000",
   "100.000000000000000000",
   "17.700000000000007380",
   "7770.000000000000000000",
   531
  ],
  [
   1704067200000,
   "95.000000000000000000",
   "156.000000000000000000",
   "90.000000000000000000",
   "102.000000000000000000",
   "33.990000000000005166",
   "11370.000000000000000000",
   540
  ]
 ],
 "expected_hour_content_hash": "58d5eb0682c09aa35c0d92fa19b953702b781d8001ac5d6b78c7c01585ad6f90",
 "expected_hour_quality_identity": "{\"checks\":[{\"check_id\":\"derived_row_count_matches_expected\",\"count\":2,\"evidence\":{\"actual_rows\":2,\"approved_rows\":2},\"outcome\":\"pass\",\"severity\":\"hard\"},{\"check_id\":\"derived_first_boundary_exact\",\"count\":0,\"evidence\":{\"approved_first_open\":1704063600000,\"observed_first_open\":1704063600000},\"outcome\":\"pass\",\"severity\":\"hard\"},{\"check_id\":\"derived_last_boundary_exact\",\"count\":0,\"evidence\":{\"approved_last_close\":1704070799999,\"observed_last_close\":1704070799999},\"outcome\":\"pass\",\"severity\":\"hard\"},{\"check_id\":\"derived_unique_open_times\",\"count\":0,\"evidence\":{\"violations\":0},\"outcome\":\"pass\",\"severity\":\"hard\"},{\"check_id\":\"derived_strictly_ascending_open_times\",\"count\":0,\"evidence\":{\"violations\":0},\"outcome\":\"pass\",\"severity\":\"hard\"},{\"check_id\":\"derived_adjacency_exactly_timeframe_ms\",\"count\":0,\"evidence\":{\"violations\":0},\"outcome\":\"pass\",\"severity\":\"hard\"},{\"check_id\":\"derived_ohlc_bounds_hold\",\"count\":0,\"evidence\":{\"violations\":0},\"outcome\":\"pass\",\"severity\":\"hard\"},{\"check_id\":\"derived_prices_strictly_positive\",\"count\":0,\"evidence\":{\"violations\":0},\"outcome\":\"pass\",\"severity\":\"hard\"},{\"check_id\":\"derived_volumes_and_counts_nonnegative\",\"count\":0,\"evidence\":{\"violations\":0},\"outcome\":\"pass\",\"severity\":\"hard\"},{\"check_id\":\"derived_taker_buy_within_counterpart_volumes\",\"count\":0,\"evidence\":{\"violations\":0},\"outcome\":\"pass\",\"severity\":\"hard\"},{\"check_id\":\"derived_close_time_relation\",\"count\":0,\"evidence\":{\"violations\":0},\"outcome\":\"pass\",\"severity\":\"hard\"},{\"check_id\":\"derived_zero_volume_bucket\",\"count\":0,\"evidence\":{\"occurrences\":0},\"outcome\":\"pass\",\"severity\":\"warning\"},{\"check_id\":\"derived_reconciliation_matches\",\"count\":0,\"evidence\":{\"violations\":0},\"outcome\":\"pass\",\"severity\":\"hard\"}]}",  # noqa: E501
 "expected_day_bar": [
  1704067200000,
  "95.000000000000000000",
  "156.000000000000000000",
  "90.000000000000000000",
  "100.000000000000000000",
  "620.280000000000150552",
  "229680.000000000000000000",
  12852
 ],
 "expected_day_content_hash": "a1c1f929310dd2212f1994253103e890d9053d241a2c235a0e4fa81c68c9af6e",
 "expected_day_quality_identity": "{\"checks\":[{\"check_id\":\"derived_row_count_matches_expected\",\"count\":1,\"evidence\":{\"actual_rows\":1,\"approved_rows\":1},\"outcome\":\"pass\",\"severity\":\"hard\"},{\"check_id\":\"derived_first_boundary_exact\",\"count\":0,\"evidence\":{\"approved_first_open\":1704067200000,\"observed_first_open\":1704067200000},\"outcome\":\"pass\",\"severity\":\"hard\"},{\"check_id\":\"derived_last_boundary_exact\",\"count\":0,\"evidence\":{\"approved_last_close\":1704153599999,\"observed_last_close\":1704153599999},\"outcome\":\"pass\",\"severity\":\"hard\"},{\"check_id\":\"derived_unique_open_times\",\"count\":0,\"evidence\":{\"violations\":0},\"outcome\":\"pass\",\"severity\":\"hard\"},{\"check_id\":\"derived_strictly_ascending_open_times\",\"count\":0,\"evidence\":{\"violations\":0},\"outcome\":\"pass\",\"severity\":\"hard\"},{\"check_id\":\"derived_adjacency_exactly_timeframe_ms\",\"count\":0,\"evidence\":{\"violations\":0},\"outcome\":\"pass\",\"severity\":\"hard\"},{\"check_id\":\"derived_ohlc_bounds_hold\",\"count\":0,\"evidence\":{\"violations\":0},\"outcome\":\"pass\",\"severity\":\"hard\"},{\"check_id\":\"derived_prices_strictly_positive\",\"count\":0,\"evidence\":{\"violations\":0},\"outcome\":\"pass\",\"severity\":\"hard\"},{\"check_id\":\"derived_volumes_and_counts_nonnegative\",\"count\":0,\"evidence\":{\"violations\":0},\"outcome\":\"pass\",\"severity\":\"hard\"},{\"check_id\":\"derived_taker_buy_within_counterpart_volumes\",\"count\":0,\"evidence\":{\"violations\":0},\"outcome\":\"pass\",\"severity\":\"hard\"},{\"check_id\":\"derived_close_time_relation\",\"count\":0,\"evidence\":{\"violations\":0},\"outcome\":\"pass\",\"severity\":\"hard\"},{\"check_id\":\"derived_zero_volume_bucket\",\"count\":0,\"evidence\":{\"occurrences\":0},\"outcome\":\"pass\",\"severity\":\"warning\"},{\"check_id\":\"derived_reconciliation_matches\",\"count\":0,\"evidence\":{\"violations\":0},\"outcome\":\"pass\",\"severity\":\"hard\"}]}"  # noqa: E501
}


# --- Correction 1: context-independent exact volume-family aggregation -------


def _context_free_scaled_int(dec: Decimal) -> int:
    """Independent reference mechanism: exact integer of dec × 10**18 built
    from the Decimal coefficient tuple — no arithmetic context involved."""
    sign, digits, exponent = dec.as_tuple()
    assert exponent == -18, f"reference expects scale 18, got {exponent}"
    value = 0
    for digit in digits:
        value = value * 10 + digit
    return -value if sign else value


def _reference_sum(decimals) -> Decimal:
    total = sum(_context_free_scaled_int(d) for d in decimals)
    negative = total < 0
    digit_tuple = tuple(int(ch) for ch in str(abs(total)))
    return Decimal((1 if negative else 0, digit_tuple, -18))


CONSTITUENT = Decimal("9999999999.123456789012345678")
EXACT_60_SUM = Decimal("599999999947.407407340740740680")


def test_hour_volume_sums_exact_beyond_ambient_decimal_context() -> None:
    from quantara.aggregation import aggregate_timeframe

    rows = []
    for i in range(60):
        t = MONTH_OPEN_START + i * 60_000
        rows.append(
            minute_row(t, o="100", h="110", lo="90", c="105",
                       bv=CONSTITUENT, qv=CONSTITUENT,
                       n=1, tbv=CONSTITUENT / 2, tqv=CONSTITUENT / 2)
        )
    bars = aggregate_timeframe(rows, IDENTITY_1H, HOUR_MS)
    assert len(bars) == 1
    bar = bars[0]
    # Exact sums, proven against a context-free integer reference.
    assert bar.base_asset_volume == EXACT_60_SUM == _reference_sum(
        [CONSTITUENT] * 60
    )
    assert bar.quote_asset_volume == EXACT_60_SUM
    assert bar.taker_buy_base_volume == _reference_sum([CONSTITUENT / 2] * 60)
    assert bar.taker_buy_quote_volume == _reference_sum([CONSTITUENT / 2] * 60)
    # The naive ambient-context sum would have rounded at 28 significant
    # digits; the persisted rendering must carry every exact digit.
    from quantara.hashing import render_decimal_18
    assert render_decimal_18(bar.base_asset_volume) == (
        "599999999947.407407340740740680"
    )


def test_daily_volume_sums_exact_for_1440_members() -> None:
    from quantara.aggregation import aggregate_timeframe

    day_ms = 86_400_000
    rows = []
    for i in range(1440):
        t = MONTH_OPEN_START + i * 60_000
        rows.append(
            minute_row(t, o="100", h="110", lo="90", c="105",
                       bv=CONSTITUENT, qv=CONSTITUENT,
                       n=1, tbv=CONSTITUENT / 2, tqv=CONSTITUENT / 2)
        )
    bars = aggregate_timeframe(rows, IDENTITY_1H[:8] + ("1d",
                                                        "binance_usdm_kline_1d_v1"),
                               day_ms)
    expected = _reference_sum([CONSTITUENT] * 1440)
    assert bars[0].base_asset_volume == expected
    assert bars[0].quote_asset_volume == expected


def test_unrepresentable_exact_aggregate_fails_deterministically() -> None:
    from quantara.aggregation import aggregate_timeframe
    from quantara.errors import DECIMAL_PRECISION_OR_SCALE_OVERFLOW

    # Each constituent fits decimal128(38,18) (19 integer digits), but the
    # exact 60-member sum needs 21 integer digits and can never be persisted.
    huge = Decimal("99999999999999999999.123456789012345678"[:20] + ".123456789012345678")
    assert len(huge.as_tuple().digits) <= 38
    rows = []
    for i in range(60):
        t = MONTH_OPEN_START + i * 60_000
        rows.append(minute_row(t, o="1", h="2", lo="0.5", c="1.5", bv=huge))
    with pytest.raises(QuantaraError) as excinfo:
        aggregate_timeframe(rows, IDENTITY_1H, HOUR_MS)
    assert excinfo.value.error_id == DECIMAL_PRECISION_OR_SCALE_OVERFLOW
