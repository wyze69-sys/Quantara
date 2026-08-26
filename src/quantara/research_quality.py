"""Research-table quality evaluation (data slice 003b).

Mirrors the slice 001/002 evaluators' Finding/report shapes with every check
id prefixed ``research_`` (design §7): row count equals the parent count,
open times identical to the parent's / strictly ascending / unique, per-column
designed-null budgets recomputed from the actual parent length and asserted
exactly (extra or missing nulls are failures, never warnings), non-null
decimals within ``decimal128(38,18)`` scale, ``f_rvol_20`` strictly positive
where non-null (a zero-variance window fails loudly rather than publishing
zeros), ``l_fwddir_24`` consistent with the exact sign of ``l_fwdret_24``
including zero, and the pipeline-supplied independent cell-level
reconciliation outcome. Policy v1: exactly PASS publishes; any failure blocks.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from quantara.hashing import quality_identity
from quantara.research_descriptor import APPROVED_PARAMETERS

QUALITY_POLICY_VERSION = "1"

_VALUE_COLUMNS = (
    "f_ret_1",
    "f_roc_60",
    "f_rvol_20",
    "f_volratio_20",
    "l_fwdret_24",
    "l_fwddir_24",
)


@dataclass(frozen=True)
class Finding:
    check_id: str
    outcome: str  # "pass" | "fail"
    severity: str  # "hard"
    count: int
    evidence: dict


class ResearchQualityReport:
    def __init__(self, findings: list[Finding]) -> None:
        self.findings = findings
        self.state = "FAIL" if any(f.outcome != "pass" for f in findings) else "PASS"

    def failing_checks(self) -> list[str]:
        return [f.check_id for f in self.findings if f.outcome != "pass"]

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


def designed_null_budgets(
    row_count: int, parameters: dict[str, int] | None = None
) -> dict[str, int]:
    """Null counts implied by the definitions for a parent of ``row_count``
    bars — recomputed by the evaluator from the actual parent length, never
    tunable tolerances (design §5)."""
    params = parameters or APPROVED_PARAMETERS
    n = row_count
    return {
        "f_ret_1": min(1, n),
        "f_roc_60": min(params["roc_window"], n),
        "f_rvol_20": min(params["vol_window"], n),
        "f_volratio_20": min(params["volume_window"] - 1, n),
        "l_fwdret_24": min(params["label_horizon"], n),
        "l_fwddir_24": min(params["label_horizon"], n),
    }


def _within_q18_scale(value: Decimal) -> bool:
    return value.as_tuple().exponent >= -18


def evaluate_research_quality(
    rows: Sequence[Sequence],
    parent_open_times: Sequence[int],
    parameters: dict[str, int] | None = None,
    reconciliation_ok: bool = True,
) -> ResearchQualityReport:
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

    # Row count equals the parent count exactly.
    record(
        "research_row_count_matches_parent",
        len(rows) == len(parent_open_times),
        len(rows),
        parent_rows=len(parent_open_times),
        table_rows=len(rows),
    )

    times = [row[0] for row in rows]
    identical = list(times) == list(parent_open_times)
    record(
        "research_open_times_identical_to_parent",
        identical,
        sum(1 for a, b in zip(times, parent_open_times, strict=False) if a != b),
    )
    record(
        "research_open_times_strictly_ascending",
        all(a < b for a, b in zip(times, times[1:], strict=False)),
        sum(1 for a, b in zip(times, times[1:], strict=False) if not a < b),
    )
    record(
        "research_unique_open_times",
        len(set(times)) == len(times),
        len(times) - len(set(times)),
    )

    columns = {name: [row[i + 1] for row in rows] for i, name in enumerate(_VALUE_COLUMNS)}
    budgets = designed_null_budgets(len(rows), parameters)
    for name in _VALUE_COLUMNS:
        nulls = sum(1 for v in columns[name] if v is None)
        budget = budgets[name]
        record(
            f"research_null_budget_{name}",
            nulls == budget,
            abs(nulls - budget),
            designed_nulls=budget,
            actual_nulls=nulls,
        )

    scale_violations = 0
    for name in ("f_ret_1", "f_roc_60", "f_rvol_20", "f_volratio_20", "l_fwdret_24"):
        for value in columns[name]:
            if value is not None and not _within_q18_scale(value):
                scale_violations += 1
    record(
        "research_decimals_within_q18_scale",
        scale_violations == 0,
        scale_violations,
    )

    rvol_violations = sum(
        1 for value in columns["f_rvol_20"] if value is not None and not value > 0
    )
    record(
        "research_rvol_strictly_positive",
        rvol_violations == 0,
        rvol_violations,
        note="a zero-variance window is degenerate input and fails loudly",
    )

    sign_violations = 0
    fwdret_values = columns["l_fwdret_24"]
    fwddir_values = columns["l_fwddir_24"]
    for ret_value, dir_value in zip(fwdret_values, fwddir_values, strict=True):
        if (ret_value is None) != (dir_value is None):
            sign_violations += 1
            continue
        if ret_value is None:
            continue
        expected = 1 if ret_value > 0 else (-1 if ret_value < 0 else 0)
        if dir_value != expected:
            sign_violations += 1
    record(
        "research_fwddir_sign_consistent",
        sign_violations == 0,
        sign_violations,
        note="exact sign including exact zero",
    )

    record(
        "research_reconciliation_matches",
        reconciliation_ok,
        0 if reconciliation_ok else 1,
    )

    return ResearchQualityReport(findings)
