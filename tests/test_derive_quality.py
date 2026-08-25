"""Derived-dataset quality evaluator tests (plan Task 3, design §10)."""

from __future__ import annotations

from decimal import Decimal as D

import pytest

from quantara.canonical import CanonicalRow

HOUR_MS = 3_600_000


class FakeDescriptor:
    """Minimal descriptor surface the evaluator needs."""

    interval = "1h"
    timeframe_ms = HOUR_MS
    start_utc_open_ms = 1704067200000


def hour_bar(index: int, **overrides) -> CanonicalRow:
    open_ms = FakeDescriptor.start_utc_open_ms + index * HOUR_MS
    values = dict(
        o=D("100"), h=D("110"), lo=D("90"), c=D("105"),
        bv=D("1.5"), qv=D("150"), n=10, tbv=D("0.5"), tqv=D("50"),
        ignore="0",
    )
    values.update(overrides)
    return CanonicalRow(
        identity=("binance", "usd_m_futures", "i", "BTCUSDT", "BTC",
                  "USDT", "USDT", "perpetual", "1h", "sv"),
        open_time_ms=open_ms,
        close_time_ms=open_ms + HOUR_MS - 1,
        nominal_available_ms=open_ms + HOUR_MS,
        open=values["o"], high=values["h"], low=values["lo"],
        close=values["c"],
        base_asset_volume=values["bv"], quote_asset_volume=values["qv"],
        trade_count=values["n"],
        taker_buy_base_volume=values["tbv"],
        taker_buy_quote_volume=values["tqv"],
        source_ignore=values["ignore"],
    )


def evaluate(rows, expected_count=None, reconciliation_ok=True):
    from quantara.derive_quality import evaluate_derived_quality

    return evaluate_derived_quality(
        rows,
        FakeDescriptor(),
        expected_count=expected_count,
        reconciliation_ok=reconciliation_ok,
    )


def outcomes(report):
    return {f.check_id: f.outcome for f in report.findings}


def test_pass_report_for_a_clean_two_hour_series() -> None:
    report = evaluate([hour_bar(0), hour_bar(1)], expected_count=2)
    assert report.state == "PASS"
    found = outcomes(report)
    for check in (
        "derived_row_count_matches_expected",
        "derived_first_boundary_exact",
        "derived_last_boundary_exact",
        "derived_unique_open_times",
        "derived_strictly_ascending_open_times",
        "derived_adjacency_exactly_timeframe_ms",
        "derived_ohlc_bounds_hold",
        "derived_prices_strictly_positive",
        "derived_volumes_and_counts_nonnegative",
        "derived_close_time_relation",
        "derived_taker_buy_within_counterpart_volumes",
        "derived_reconciliation_matches",
    ):
        assert check in found, check
        assert found[check] == "pass", check


def test_every_check_id_is_prefixed_derived() -> None:
    report = evaluate([hour_bar(0)], expected_count=1)
    assert all(f.check_id.startswith("derived_") for f in report.findings)


def _assert_fail(rows, check_id, expected_count=None):
    report = evaluate(rows, expected_count=expected_count)
    assert report.state == "FAIL"
    assert outcomes(report)[check_id] == "fail"


def test_row_count_failure() -> None:
    report = evaluate([hour_bar(0), hour_bar(1)], expected_count=744)
    assert report.state == "FAIL"
    assert outcomes(report)["derived_row_count_matches_expected"] == "fail"


def test_first_and_last_boundary_failures() -> None:
    # A calendar-aligned single bar passes; a shifted one fails both.
    aligned = evaluate([hour_bar(0)], expected_count=1)
    found = outcomes(aligned)
    assert found["derived_first_boundary_exact"] == "pass"
    assert found["derived_last_boundary_exact"] == "pass"
    report = evaluate([hour_bar(3)], expected_count=1)
    assert report.state == "FAIL"
    shifted = outcomes(report)
    assert shifted["derived_first_boundary_exact"] == "fail"
    assert shifted["derived_last_boundary_exact"] == "fail"


def test_adjacency_failure() -> None:
    bars = [hour_bar(0), hour_bar(2)]  # one missing hour in between
    _assert_fail(bars, "derived_adjacency_exactly_timeframe_ms", expected_count=2)


def test_uniqueness_failure() -> None:
    bars = [hour_bar(0), hour_bar(0)]
    _assert_fail(bars, "derived_unique_open_times")


def test_ascent_failure() -> None:
    bars = [hour_bar(1), hour_bar(0)]
    _assert_fail(bars, "derived_strictly_ascending_open_times")


@pytest.mark.parametrize(
    ("kwargs", "check"),
    [
        ({"h": D("120"), "o": D("130")}, "derived_ohlc_bounds_hold"),
        ({"h": D("80"), "lo": D("90")}, "derived_ohlc_bounds_hold"),
        ({"o": D("0"), "h": D("0"), "lo": D("0"), "c": D("0")},
         "derived_prices_strictly_positive"),
        ({"bv": D("-1")}, "derived_volumes_and_counts_nonnegative"),
        ({"n": -5}, "derived_volumes_and_counts_nonnegative"),
        ({"tbv": D("2"), "bv": D("1.5")},
         "derived_taker_buy_within_counterpart_volumes"),
    ],
)
def test_explicit_failing_fixtures(kwargs, check) -> None:
    bar = hour_bar(0, **kwargs)
    _assert_fail([bar], check)


def test_close_time_relation_failure() -> None:
    bad = hour_bar(0)
    broken = CanonicalRow(
        identity=bad.identity,
        open_time_ms=bad.open_time_ms,
        close_time_ms=bad.open_time_ms + 60_000,  # wrong: must be open+tf-1
        nominal_available_ms=bad.nominal_available_ms,
        open=bad.open, high=bad.high, low=bad.low, close=bad.close,
        base_asset_volume=bad.base_asset_volume,
        quote_asset_volume=bad.quote_asset_volume,
        trade_count=bad.trade_count,
        taker_buy_base_volume=bad.taker_buy_base_volume,
        taker_buy_quote_volume=bad.taker_buy_quote_volume,
        source_ignore="0",
    )
    _assert_fail([broken], "derived_close_time_relation")


def test_zero_volume_bucket_warns_and_blocks() -> None:
    report = evaluate(
        [hour_bar(0, bv=D("0"), qv=D("0"), tbv=D("0"), tqv=D("0"))],
        expected_count=1,
    )
    assert report.state == "WARN_BLOCKED"
    assert outcomes(report)["derived_zero_volume_bucket"] == "warn"


def test_reconciliation_failure_is_a_hard_fail() -> None:
    report = evaluate([hour_bar(0)], expected_count=1, reconciliation_ok=False)
    assert report.state == "FAIL"
    assert outcomes(report)["derived_reconciliation_matches"] == "fail"


def test_identity_is_deterministic_and_excludes_timestamps() -> None:
    a = evaluate([hour_bar(0)], expected_count=1)
    b = evaluate([hour_bar(0)], expected_count=1)
    assert a.identity() == b.identity()


# --- correction 6: unevaluated checks are never represented as passing --------


def test_disabled_row_count_check_is_not_evaluated_and_blocks() -> None:
    # expected_count=None disables count enforcement; the emitted finding must
    # carry an explicit non-pass outcome compatible with strict blocking.
    report = evaluate([hour_bar(0)])
    found = outcomes(report)
    assert found["derived_row_count_matches_expected"] == "not_evaluated"
    assert report.state == "WARN_BLOCKED"


def test_unverifiable_boundaries_on_partial_series_are_not_evaluated() -> None:
    # Two bars out of an approved 744: exact calendar boundaries cannot be
    # decided; they must not be recorded as passing.
    from quantara.derive_quality import evaluate_derived_quality

    bars = [hour_bar(0), hour_bar(1)]
    view = type("V", (), {"timeframe_ms": HOUR_MS,
                          "start_utc_open_ms": 1704067200000})()
    report = evaluate_derived_quality(bars, view, expected_count=744)
    found = outcomes(report)
    assert found["derived_first_boundary_exact"] == "not_evaluated"
    assert found["derived_last_boundary_exact"] == "not_evaluated"
    assert report.state == "FAIL"  # row-count failure dominates


def test_empty_series_yields_blocking_not_evaluated_boundaries() -> None:
    report = evaluate([], expected_count=744)
    found = outcomes(report)
    assert found["derived_first_boundary_exact"] == "not_evaluated"
    assert found["derived_last_boundary_exact"] == "not_evaluated"
    assert report.state != "PASS"


def test_not_evaluated_outcome_is_deterministic_in_identity() -> None:
    a = evaluate([hour_bar(0)])
    b = evaluate([hour_bar(0)])
    assert a.identity() == b.identity()
