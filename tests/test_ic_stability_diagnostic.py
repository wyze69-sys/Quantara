from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from quantara.ic_stability_diagnostic import (
    GateVerdict,
    bootstrap_mean_ci,
    evaluate_ic_stability_gate,
    load_per_fold_ics,
    permutation_test,
    summarize_per_fold,
)
from quantara.training_pipeline import _write_per_fold_sidecar


def test_write_per_fold_sidecar_has_frozen_shape(tmp_path: Path) -> None:
    records = [
        {
            "fold_id": fold_index,
            "direction_ic": f"{fold_index / 1000:.18f}",
            "direction_ic_defined": True,
        }
        for fold_index in range(117)
    ]
    target = (
        tmp_path
        / "data"
        / "diagnostic"
        / "training"
        / "per_fold_synthetic-attempt.json"
    )

    _write_per_fold_sidecar(records, target)

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "quantara.ic_stability_sidecar/v1"
    assert payload["attempt_id"] == "synthetic-attempt"
    assert isinstance(payload["code_revision"], str)
    assert len(payload["records"]) == 117
    assert [record["fold_index"] for record in payload["records"]] == list(range(117))
    assert all("fold_id" not in record for record in payload["records"])
    assert all(
        isinstance(record["direction_ic"], str) and "." in record["direction_ic"]
        for record in payload["records"]
    )


def _write_sidecar(path: Path, ics: list[Decimal]) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "quantara.ic_stability_sidecar/v1",
                "attempt_id": "synthetic",
                "code_revision": "f" * 40,
                "records": [
                    {
                        "fold_index": fold_index,
                        "direction_ic": str(ic),
                        "direction_ic_defined": True,
                    }
                    for fold_index, ic in enumerate(ics)
                ],
            }
        ),
        encoding="utf-8",
    )


def test_load_per_fold_ics_validates_schema_count_and_order(tmp_path: Path) -> None:
    expected = [Decimal(index) / Decimal(1000) for index in range(117)]
    target = tmp_path / "sidecar.json"
    _write_sidecar(target, expected)
    assert load_per_fold_ics(target) == expected

    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["schema_version"] = "wrong"
    target.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="schema_version"):
        load_per_fold_ics(target)

    _write_sidecar(target, expected[:-1])
    with pytest.raises(ValueError, match="117"):
        load_per_fold_ics(target)

    _write_sidecar(target, expected)
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["records"][1]["fold_index"] = 99
    target.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="fold order"):
        load_per_fold_ics(target)


def test_summarize_per_fold_known_distribution() -> None:
    ics = [Decimal(index) / Decimal(1000) for index in range(117)]

    summary = summarize_per_fold(ics)

    assert summary["mean"] == Decimal("0.058000000000000000")
    assert summary["median"] == Decimal("0.058000000000000000")
    assert summary["stdev"] == Decimal("0.033919021212293258")
    assert summary["p25"] == Decimal("0.029000000000000000")
    assert summary["p75"] == Decimal("0.087000000000000000")
    assert summary["min"] == Decimal("0.000000000000000000")
    assert summary["max"] == Decimal("0.116000000000000000")
    assert summary["count_positive"] == 116
    assert summary["count_above_0_10"] == 16
    assert [item["fold_index"] for item in summary["worst_10"]] == list(range(10))
    assert [item["fold_index"] for item in summary["best_10"]] == list(
        range(107, 117)
    )
    assert summary["time_series"][29]["quarter"] == "2024-Q1"
    assert summary["time_series"][30]["quarter"] == "2024-Q2"
    assert summary["time_series"][60]["quarter"] == "2024-Q3"
    assert summary["time_series"][90]["quarter"] == "2024-Q4"


def test_bootstrap_mean_ci_is_deterministic_and_decimal_exact() -> None:
    ics = [Decimal(index) / Decimal(1000) for index in range(117)]
    assert bootstrap_mean_ci(ics) == (
        Decimal("0.051957051282051282"),
        Decimal("0.063940384615384615"),
    )


def test_permutation_test_is_deterministic_and_decimal_exact() -> None:
    ics = [Decimal(index) / Decimal(1000) for index in range(117)]
    assert permutation_test(ics) == Decimal("0.000000000000000000")


@pytest.mark.parametrize(
    ("ics", "expected"),
    [
        ([Decimal("0.5")] * 117, GateVerdict.PROCEED),
        (
            [Decimal("0.1") if index % 2 == 0 else Decimal("0.3") for index in range(117)],
            GateVerdict.PROCEED_WITH_CAVEAT,
        ),
        ([Decimal("0")] * 117, GateVerdict.STOP_PUBLISH_NEGATIVE),
        (
            [Decimal("0.5")] * 105 + [Decimal("-0.5")] * 12,
            GateVerdict.STOP_PUBLISH_NEGATIVE,
        ),
    ],
)
def test_evaluate_ic_stability_gate_all_branches(
    ics: list[Decimal], expected: GateVerdict
) -> None:
    verdict, reason = evaluate_ic_stability_gate(ics)
    assert verdict is expected
    assert reason.startswith("per_fold_sd=")
    assert " ci=(" in reason
    assert " permutation_p=" in reason
