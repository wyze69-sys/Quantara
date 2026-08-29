from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from conftest import write_synthetic_sidecar
from quantara.ic_stability_diagnostic import _run_ic_stability_report

pytestmark = pytest.mark.integration


def test_synthetic_sidecar_to_durable_report_then_cleanup(tmp_path: Path) -> None:
    sidecar = write_synthetic_sidecar(
        tmp_path / "per_fold_synthetic-attempt.json",
        [Decimal("0.5")] * 117,
    )
    report_path = tmp_path / "ic_stability_synthetic-attempt.json"

    report = _run_ic_stability_report(sidecar, report_path)

    assert not sidecar.exists()
    assert report_path.exists()
    assert json.loads(report_path.read_text(encoding="utf-8")) == report
    assert report["schema_version"] == "quantara.ic_stability_report/v1"
    assert report["attempt_id"] == "synthetic-attempt"
    assert report["code_revision"] == "f" * 40
    assert report["summary"] == {
        "mean": "0.500000000000000000",
        "median": "0.500000000000000000",
        "stdev": "0.000000000000000000",
        "p25": "0.500000000000000000",
        "p75": "0.500000000000000000",
        "min": "0.500000000000000000",
        "max": "0.500000000000000000",
        "count_positive": 117,
        "count_above_0_10": 117,
    }
    assert report["bootstrap_ci"] == [
        "0.500000000000000000",
        "0.500000000000000000",
    ]
    assert report["permutation_p_value"] == "0.000000000000000000"
    assert report["gate_verdict"] == "PROCEED"
    assert report["gate_reason"].startswith("per_fold_sd=0.000000000000000000")
    assert len(report["best_10_folds"]) == 10
    assert len(report["worst_10_folds"]) == 10
    assert len(report["time_series"]) == 117
