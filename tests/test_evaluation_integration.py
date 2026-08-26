"""CLI end-to-end integration tests for feature_evaluation (Task T10).

Covers:
- full end-to-end execution of the CLI against the offline fixture;
- end-to-end dry-run via CLI with exact verification that zero files were created;
- end-to-end publication via CLI, verifying CAS object, commit directory,
  current.json, and attempt manifest;
- idempotent re-execution via CLI returning 0 and recording VERIFIED_NO_OP.
"""

from __future__ import annotations

import json
from pathlib import Path

from quantara.cli import main
from quantara.evaluation_pipeline import verify_evaluation_current_graph
from test_evaluation_pipeline import setup_offline_q1_parents


def test_cli_evaluation_integration_e2e(tmp_path: Path) -> None:
    repo_root, data_root, eval_desc = setup_offline_q1_parents(tmp_path)
    eval_dir = (
        data_root
        / "datasets"
        / "binance"
        / "usdm"
        / "evaluation"
        / "BTCUSDT"
        / "1h"
        / "year=2024"
        / "month=01"
    )

    # 1. Dry run via CLI
    exit_dry = main(
        [
            "--dataset-type",
            "feature_evaluation",
            "--descriptor",
            str(eval_desc),
            "--data-root",
            str(data_root),
            "--dry-run",
        ]
    )
    assert exit_dry == 0
    assert not eval_dir.exists()
    assert not (data_root / "attempts" / "evaluation").exists()

    # 2. Publication via CLI
    exit_pub = main(
        [
            "--dataset-type",
            "feature_evaluation",
            "--descriptor",
            str(eval_desc),
            "--data-root",
            str(data_root),
        ]
    )
    assert exit_pub == 0

    # Verify published graph via verify_evaluation_current_graph
    verified = verify_evaluation_current_graph(eval_dir, data_root)
    commit_id = verified["commit"]
    assert len(commit_id) == 64

    # Verify CAS object
    ref = verified["object_refs"][0]["sha256"]
    cas_file = data_root / "objects" / "normalized" / "sha256" / ref
    assert cas_file.is_file()

    # Verify attempt manifest
    attempts_dir = data_root / "attempts" / "evaluation"
    attempts = [json.loads(p.read_text(encoding="utf-8")) for p in attempts_dir.glob("*.json")]
    attempts.sort(key=lambda a: a["started_at_utc"])
    assert len(attempts) == 1
    assert attempts[0]["terminal_result"] == "PUBLISHED"
    assert attempts[0]["referenced_commit"] == commit_id

    # 3. Idempotent re-run via CLI
    exit_noop = main(
        [
            "--dataset-type",
            "feature_evaluation",
            "--descriptor",
            str(eval_desc),
            "--data-root",
            str(data_root),
        ]
    )
    assert exit_noop == 0

    attempts = [json.loads(p.read_text(encoding="utf-8")) for p in attempts_dir.glob("*.json")]
    attempts.sort(key=lambda a: a["started_at_utc"])
    assert len(attempts) == 2
    assert attempts[1]["terminal_result"] == "VERIFIED_NO_OP"
    assert attempts[1]["artifact_dispositions"]["evaluation_artifact"] == "already_published"
