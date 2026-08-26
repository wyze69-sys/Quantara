"""Research-table quality evaluation tests (plan Task 5).

Every design §7 invariant gets its own failing fixture; evaluator budgets are
derived from the actual parent count; ``quality_identity`` is deterministic.
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from conftest import HOUR_BAR_START
from quantara.features import build_research_rows
from quantara.research_quality import (
    designed_null_budgets,
    evaluate_research_quality,
)

N = 80


def _parent_rows(n=N):
    return [
        (
            HOUR_BAR_START + i * 3_600_000,
            *([None] * 22),
        )
        for i in range(n)
    ]


def _full_parent_and_table(n=N):
    closes = [Decimal(100 + i) for i in range(n)]
    volumes = [Decimal(10 + (i % 7)) for i in range(n)]
    parent_rows = []
    for i in range(n):
        row = [None] * 23
        row[0] = "x"  # placeholder identity slot, unused by engines
        row[10] = HOUR_BAR_START + i * 3_600_000
        row[16] = closes[i]
        row[17] = volumes[i]
        parent_rows.append(tuple(row))
    table = build_research_rows(parent_rows)
    open_times = [row[10] for row in parent_rows]
    return table, open_times


def test_designed_null_budgets_from_actual_parent_length() -> None:
    assert designed_null_budgets(744) == {
        "f_ret_1": 1,
        "f_roc_60": 60,
        "f_rvol_20": 20,
        "f_volratio_20": 19,
        "l_fwdret_24": 24,
        "l_fwddir_24": 24,
    }
    # Recomputed, never tunable: a shorter parent shrinks the budgets by the
    # definitions themselves.
    assert designed_null_budgets(30)["f_roc_60"] == 30
    assert designed_null_budgets(30)["l_fwddir_24"] == 24
    assert designed_null_budgets(10)["l_fwdret_24"] == 10


def test_complete_parent_passes_with_exact_budgets() -> None:
    table, open_times = _full_parent_and_table()
    report = evaluate_research_quality(table, open_times)
    assert report.state == "PASS"
    null_counts = {
        name: sum(1 for v in column_values if v is None)
        for name, column_values in _columns(table).items()
    }
    assert null_counts == designed_null_budgets(len(table))


def _columns(table):
    names = [
        "f_ret_1",
        "f_roc_60",
        "f_rvol_20",
        "f_volratio_20",
        "l_fwdret_24",
        "l_fwddir_24",
    ]
    return {name: [row[i + 1] for row in table] for i, name in enumerate(names)}


def test_identity_is_deterministic() -> None:
    table, open_times = _full_parent_and_table()
    first = evaluate_research_quality(table, open_times)
    second = evaluate_research_quality(table, open_times)
    assert first.identity() == second.identity()


def _mutated(mutator):
    table, open_times = _full_parent_and_table()
    table = [list(row) for row in table]
    mutator(table, open_times)
    return [tuple(row) for row in table], open_times


def test_row_count_mismatch_fails() -> None:
    table, open_times = _mutated(lambda t, o: t.pop(40))
    report = evaluate_research_quality(table, open_times)
    assert report.state != "PASS"
    assert "research_row_count_matches_parent" in report.failing_checks()


def test_open_times_must_match_parent() -> None:
    def bump(times, open_times):
        open_times[5] += 1

    table, open_times = _mutated(bump)
    report = evaluate_research_quality(table, open_times)
    assert "research_open_times_identical_to_parent" in report.failing_checks()


def test_unsorted_open_times_fail() -> None:
    table, open_times = _full_parent_and_table()
    table[10], table[11] = table[11], table[10]
    report = evaluate_research_quality(table, open_times[: len(table)])
    assert report.state != "PASS"
    assert "research_open_times_strictly_ascending" in report.failing_checks()


def test_duplicate_open_times_fail() -> None:
    table, open_times = _full_parent_and_table()
    rows = [list(row) for row in table]
    times = [row[0] for row in rows]
    times[7] = times[6]
    for row, time in zip(rows, times, strict=True):
        row[0] = time
    report = evaluate_research_quality([tuple(r) for r in rows], times)
    assert "research_unique_open_times" in report.failing_checks()


def test_extra_null_fails_budget() -> None:
    def nullify(table, open_times):
        assert table[70][2] is not None
        table[70][2] = None  # a valid f_roc_60 value becomes an extra null

    table, open_times = _mutated(nullify)
    report = evaluate_research_quality(table, open_times)
    assert "research_null_budget_f_roc_60" in report.failing_checks()


def test_missing_null_fails_budget() -> None:
    def fill(table, open_times):
        assert table[0][1] is None  # f_ret_1 warm-up null
        table[0][1] = Decimal("0.010000000000000000")

    table, open_times = _mutated(fill)
    report = evaluate_research_quality(table, open_times)
    assert "research_null_budget_f_ret_1" in report.failing_checks()


def test_scale_overflow_fails() -> None:
    def widen(table, open_times):
        table[30][3] = Decimal("0.1234567890123456789")  # 19 fractional digits

    table, open_times = _mutated(widen)
    report = evaluate_research_quality(table, open_times)
    assert "research_decimals_within_q18_scale" in report.failing_checks()


def test_zero_variance_rvol_fails_loudly() -> None:
    def flatten(table, open_times):
        assert table[25][3] is not None  # f_rvol_20
        table[25][3] = Decimal("0.000000000000000000")

    table, open_times = _mutated(flatten)
    report = evaluate_research_quality(table, open_times)
    assert "research_rvol_strictly_positive" in report.failing_checks()


def test_fwddir_inconsistency_fails_including_exact_zero() -> None:
    def flip(table, open_times):
        assert table[30][6] in (-1, 0, 1)
        table[30][6] = -table[30][6]

    table, open_times = _mutated(flip)
    report = evaluate_research_quality(table, open_times)
    assert "research_fwddir_sign_consistent" in report.failing_checks()

    def zero_ret_nonzero_dir(table, open_times):
        table[30][5] = Decimal("0.000000000000000000")  # exact zero return
        table[30][6] = 1

    table, open_times = _mutated(zero_ret_nonzero_dir)
    report = evaluate_research_quality(table, open_times)
    assert "research_fwddir_sign_consistent" in report.failing_checks()


def test_reconciliation_failure_blocks() -> None:
    table, open_times = _full_parent_and_table()
    report = evaluate_research_quality(table, open_times, reconciliation_ok=False)
    assert "research_reconciliation_matches" in report.failing_checks()
    assert report.state != "PASS"


_money = st.integers(min_value=100, max_value=10**9)


@settings(max_examples=15, deadline=None)
@given(data=st.data(), n=st.integers(min_value=85, max_value=120))
def test_property_generated_tables_pass(data, n: int) -> None:
    # Strictly increasing closes keep every rvol window non-degenerate (a
    # constant-price window is degenerate input the evaluator must fail).
    steps = [data.draw(_money) for _ in range(n)]
    closes = []
    total = Decimal(1000)
    for step in steps:
        closes.append(total)
        total += Decimal(step % 10_000) + 1
    volumes = [Decimal(data.draw(_money)) for _ in range(n)]
    parent_rows = []
    for i in range(n):
        row = [None] * 23
        row[0] = "x"
        row[10] = HOUR_BAR_START + i * 3_600_000
        row[16] = closes[i]
        row[17] = volumes[i]
        parent_rows.append(tuple(row))
    table = build_research_rows(parent_rows)
    report = evaluate_research_quality(table, [row[10] for row in parent_rows])
    assert report.state == "PASS", str(report.failing_checks())
