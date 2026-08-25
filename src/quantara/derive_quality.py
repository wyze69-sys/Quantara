"""Derived-dataset quality evaluation (data slice 002).

Mirrors the slice 001 evaluator's Finding/QualityReport shapes with every
check id prefixed ``derived_`` (design §10): expected bucket count, exact
calendar boundaries, uniqueness, strict ascent, adjacency exactly timeframe_ms,
OHLC bounds, positive prices, non-negative volumes/counts, taker-buy bounds,
close-time relation, a defensive zero-volume-bucket warning, and the pipeline-
supplied reconciliation outcome. Policy v1: exactly PASS publishes; any warning
blocks; aggregate scores never gate alone.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from quantara.canonical import CanonicalRow
from quantara.hashing import quality_identity

QUALITY_POLICY_VERSION = "1"


@dataclass(frozen=True)
class Finding:
    check_id: str
    outcome: str  # "pass" | "warn" | "fail"
    severity: str  # "hard" | "warning"
    count: int
    evidence: dict


class DerivedQualityReport:
    def __init__(self, findings: list[Finding]) -> None:
        self.findings = findings
        has_fail = any(f.outcome == "fail" for f in findings)
        # Policy v1 strictness: any warning OR any check that could not be
        # evaluated blocks publication. Only checks that actually ran and
        # passed may contribute to a PASS state.
        blocking = ("warn", "not_evaluated")
        has_blocking_warning = any(f.outcome in blocking for f in findings)
        self.state = (
            "FAIL" if has_fail else ("WARN_BLOCKED" if has_blocking_warning else "PASS")
        )

    def identity(self) -> str:
        """Deterministic JCS identity; operational timestamps excluded."""
        return quality_identity(
            [
                {
                    "check_id": f.check_id,
                    "count": f.count,
                    "evidence": f.evidence,
                    "outcome": f.outcome,
                    "severity": f.severity,
                }
                for f in self.findings
            ]
        )


def evaluate_derived_quality(
    rows: Sequence[CanonicalRow],
    descriptor,
    expected_count: int | None = None,
    reconciliation_ok: bool = True,
) -> DerivedQualityReport:
    timeframe_ms = descriptor.timeframe_ms
    start_ms = int(descriptor.start_utc_open_ms)
    findings: list[Finding] = []

    def record(check_id: str, ok: bool, count: int = 0, **evidence) -> None:
        findings.append(
            Finding(
                check_id=check_id,
                outcome="pass" if ok else "fail",
                severity="hard",
                count=count,
                evidence=evidence or {"violations": count},
            )
        )

    def warn(check_id: str, count: int, **evidence) -> None:
        findings.append(
            Finding(
                check_id=check_id,
                outcome="warn" if count else "pass",
                severity="warning",
                count=count,
                evidence={**evidence, "occurrences": count},
            )
        )

    def not_evaluated(check_id: str, reason: str) -> None:
        """Explicit deterministic outcome for checks that could not run.
        Never represented as a pass; blocks under the strict policy."""
        findings.append(
            Finding(
                check_id=check_id,
                outcome="not_evaluated",
                severity="warning",
                count=0,
                evidence={"reason": reason},
            )
        )

    if expected_count is None:
        not_evaluated(
            "derived_row_count_matches_expected",
            "expected bucket count unavailable; row-count enforcement disabled",
        )
        complete_series = False
    else:
        complete_series = len(rows) == expected_count
        record("derived_row_count_matches_expected", complete_series, len(rows),
               approved_rows=expected_count, actual_rows=len(rows))

    if rows and complete_series:
        record("derived_first_boundary_exact",
               rows[0].open_time_ms == start_ms,
               observed_first_open=rows[0].open_time_ms,
               approved_first_open=start_ms)
        record("derived_last_boundary_exact",
               rows[-1].close_time_ms == start_ms + len(rows) * timeframe_ms - 1,
               observed_last_close=rows[-1].close_time_ms,
               approved_last_close=start_ms + len(rows) * timeframe_ms - 1)
    elif not rows:
        not_evaluated("derived_first_boundary_exact", "no rows")
        not_evaluated("derived_last_boundary_exact", "no rows")
    else:
        # Exact boundary equality is only decidable for the complete
        # calendar series; a partial fixture cannot pass these checks.
        not_evaluated("derived_first_boundary_exact",
                      "incomplete series; exact first boundary undecidable")
        not_evaluated("derived_last_boundary_exact",
                      "incomplete series; exact last boundary undecidable")

    times = [row.open_time_ms for row in rows]
    record("derived_unique_open_times", len(set(times)) == len(times),
           len(times) - len(set(times)))
    record(
        "derived_strictly_ascending_open_times",
        all(a < b for a, b in zip(times, times[1:], strict=False)),
    )
    record(
        "derived_adjacency_exactly_timeframe_ms",
        all(b - a == timeframe_ms for a, b in zip(times, times[1:], strict=False)),
    )

    ohlc_violations = 0
    price_violations = 0
    volume_violations = 0
    taker_violations = 0
    close_violations = 0
    zero_volume = 0
    for row in rows:
        if not (
            row.high >= row.open
            and row.high >= row.close
            and row.low <= row.open
            and row.low <= row.close
            and row.high >= row.low
        ):
            ohlc_violations += 1
        if not all(p > 0 for p in (row.open, row.high, row.low, row.close)):
            price_violations += 1
        if row.trade_count < 0 or not all(
            v >= 0
            for v in (
                row.base_asset_volume,
                row.quote_asset_volume,
                row.taker_buy_base_volume,
                row.taker_buy_quote_volume,
            )
        ):
            volume_violations += 1
        if not (
            row.taker_buy_base_volume <= row.base_asset_volume
            and row.taker_buy_quote_volume <= row.quote_asset_volume
        ):
            taker_violations += 1
        if row.close_time_ms != row.open_time_ms + timeframe_ms - 1:
            close_violations += 1
        if row.base_asset_volume == 0 and row.quote_asset_volume == 0:
            zero_volume += 1

    record("derived_ohlc_bounds_hold", ohlc_violations == 0, ohlc_violations)
    record("derived_prices_strictly_positive", price_violations == 0,
           price_violations)
    record("derived_volumes_and_counts_nonnegative", volume_violations == 0,
           volume_violations)
    record("derived_taker_buy_within_counterpart_volumes", taker_violations == 0,
           taker_violations)
    record("derived_close_time_relation", close_violations == 0,
           close_violations)
    warn("derived_zero_volume_bucket", zero_volume)
    record("derived_reconciliation_matches", reconciliation_ok,
           0 if reconciliation_ok else 1)

    return DerivedQualityReport(findings=findings)
