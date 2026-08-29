from __future__ import annotations

import json
from pathlib import Path

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
