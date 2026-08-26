"""Causal decimal feature engine tests (plan Task 3).

Hand-computed fixtures including a non-terminating quotient proving
single-rounding Q18 semantics, window-boundary fixtures for every column's
first-valid index, and the causality property test: perturbing any bar after
t leaves every feature value at rows <= t bit-identical.
"""

from __future__ import annotations

from decimal import Context, Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from conftest import HOUR_BAR_START, make_hour_bar
from quantara.features import (
    CLOSE_INDEX,
    VOLUME_INDEX,
    build_research_rows,
    compute_features,
    extract_series,
    one_bar_return,
    quantize_q18,
)

N = 80


def _bars(closes, volumes=None):
    volumes = volumes or ["12.5"] * len(closes)
    start = HOUR_BAR_START
    return [
        make_hour_bar(start + i * 3_600_000, closes[i], volumes[i]).to_content_array()
        for i in range(len(closes))
    ]


def _series(n=N):
    closes = [str(100 + i) for i in range(n)]
    volumes = [str(10 + (i % 7)) for i in range(n)]
    return _bars(closes, volumes)


# --- extract_series ------------------------------------------------------------


def test_extract_series_reads_positional_cells_and_forbids_floats() -> None:
    rows = _bars(["100", "101", "102"])
    closes, volumes = extract_series(rows)
    assert closes == [Decimal("100"), Decimal("101"), Decimal("102")]
    assert volumes[0] == Decimal("12.5")
    float_row = [None] * 23
    float_row[CLOSE_INDEX] = 100.5
    float_row[VOLUME_INDEX] = Decimal("1")
    with pytest.raises(ValueError):
        extract_series([float_row])


# --- hand-computed fixtures -----------------------------------------------------


def test_one_bar_return_exact_and_non_terminating_quotient() -> None:
    closes = [Decimal("3"), Decimal("1")]
    # 1/3 - 1 = -2/3, a non-terminating quotient held at prec=50.
    ret = one_bar_return(closes, 1)
    expected_prec50 = Context(prec=50).divide(Decimal(-2), Decimal(3))
    assert ret == expected_prec50
    # Single-rounding semantics: storage quantizes ONCE, HALF_EVEN, and the
    # result is the correctly-rounded -2/3 at 18 digits (-...667, not -...666).
    quantized = quantize_q18(ret)
    assert str(quantized) == "-0.666666666666666667"
    high_prec = Context(prec=90).divide(Decimal(-2), Decimal(3))
    assert quantize_q18(high_prec) == quantized


def test_ret_fixture_hand_computed() -> None:
    closes = [Decimal("100"), Decimal("101")]
    ret = one_bar_return(closes, 1)
    assert ret == Decimal("0.01")
    assert str(quantize_q18(ret)) == "0.010000000000000000"


def test_rvol_hand_computed_closed_form_45_over_76() -> None:
    closes = ["1", "2"] * 11  # returns alternate +1 and -1/2
    feats = compute_features(*extract_series(_bars(closes)))
    # Any complete 20-return window has 10 of each: mean 1/4, sum of squared
    # deviations 10*(3/4)^2*2 = 45/4, ddof=1 variance over 20 returns = 45/76.
    rvol = feats["f_rvol_20"][20]
    target = Decimal(45) / Decimal(76)
    assert (rvol * rvol - target).copy_abs() < Decimal("1e-46")
    reference = Context(prec=90).divide(Decimal(45), Decimal(76)).sqrt(Context(prec=90))
    assert quantize_q18(rvol) == quantize_q18(reference)


def test_volratio_window_mean_fixture() -> None:
    closes = [str(100 + i) for i in range(21)]
    volumes = ["10"] * 20 + ["30"]
    feats = compute_features(*extract_series(_bars(closes, volumes)))
    # At t=20 the trailing window is volumes[1..20]: nineteen 10s and one 30,
    # so the mean is exactly 11 and the ratio is the precise quotient 30/11.
    assert feats["f_volratio_20"][20] == Context(prec=50).divide(Decimal(30), Decimal(11))
    flat_closes = [str(100)] * 21
    flat_volumes = ["12"] * 21
    flat = compute_features(*extract_series(_bars(flat_closes, flat_volumes)))
    assert flat["f_volratio_20"][20] == Decimal("1")


def test_roc_fixture_hand_computed() -> None:
    closes = ["100"] * 60 + ["200"]
    feats = compute_features(*extract_series(_bars(closes)))
    assert feats["f_roc_60"][60] == Decimal("1")
    assert feats["f_roc_60"][59] is None


# --- window boundaries -----------------------------------------------------------


@pytest.mark.parametrize(
    ("column", "first_valid"),
    [
        ("f_ret_1", 1),
        ("f_roc_60", 60),
        ("f_rvol_20", 20),
        ("f_volratio_20", 19),
    ],
)
def test_first_valid_indices_match_designed_null_budgets(column: str, first_valid: int) -> None:
    feats = compute_features(*extract_series(_series()))
    column_values = feats[column]
    assert all(v is None for v in column_values[:first_valid])
    assert column_values[first_valid] is not None
    assert all(v is not None for v in column_values[first_valid:])


def test_build_research_rows_applies_storage_boundary_quantization() -> None:
    rows = build_research_rows(_series())
    assert len(rows) == N
    first = rows[0]
    assert first[0] == HOUR_BAR_START
    assert first[1] is None and first[2] is None  # ret/roc warm-up nulls
    third = rows[3]
    for value in third[1:6]:
        if value is not None:
            assert -value.as_tuple().exponent == 18  # exactly Q18
    assert rows[-1][5] is None and rows[-1][6] is None  # trailing label nulls


# --- causality property ----------------------------------------------------------


def _features_as_text(closes, volumes):
    feats = compute_features([Decimal(c) for c in closes], [Decimal(v) for v in volumes])
    return {
        name: [None if v is None else v.as_tuple() for v in values]
        for name, values in feats.items()
    }


_money = st.integers(min_value=100, max_value=10**9)


@settings(max_examples=25, deadline=None)
@given(
    data=st.data(),
    n=st.integers(min_value=85, max_value=110),
    t=st.integers(min_value=70, max_value=84),
)
def test_perturbing_bars_after_t_leaves_prior_features_bit_identical(data, n: int, t: int) -> None:
    closes = [str(data.draw(_money)) for _ in range(n)]
    volumes = [str(data.draw(_money)) for _ in range(n)]
    baseline = _features_as_text(closes, volumes)

    mutated_closes = list(closes)
    mutated_volumes = list(volumes)
    for i in range(t + 1, n):
        mutated_closes[i] = str(data.draw(_money))
        mutated_volumes[i] = str(data.draw(_money))

    perturbed = _features_as_text(mutated_closes, mutated_volumes)
    for name in baseline:
        assert baseline[name][: t + 1] == perturbed[name][: t + 1], (
            f"feature {name} leaked future information at t={t}"
        )
