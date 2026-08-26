"""Truthful attempt manifests and milestone invariant tests (Task T9).

Verifies:
- terminal results are one of PUBLISHED, VERIFIED_NO_OP, QUARANTINED, FAILED, BLOCKED;
- milestones always record lock_acquired, lock_released, attempt_staged,
  object_written, commit_renamed, pointer_replaced, discovery_verified, attempt_staging;
- commit_renamed is never True unless attempt_staged is True;
- pointer_replaced is never True unless commit_renamed is True (or lost_pointer_recovered);
- discovery_verified is never True unless pointer_replaced is True (or VERIFIED_NO_OP);
- staging directories are never left behind;
- dry run writes zero attempt manifests;
- corrupted quality blocks publication and writes truthful attempt manifest with
  failing check IDs in diagnostics.
"""

from __future__ import annotations

import json
from pathlib import Path

from quantara.evaluation_pipeline import run_evaluation_pipeline
from quantara.evaluation_quality import EvaluationQualityReport, Finding
from test_evaluation_pipeline import setup_offline_q1_parents

ALLOWED_TERMINAL_RESULTS = frozenset(
    {"PUBLISHED", "VERIFIED_NO_OP", "QUARANTINED", "FAILED", "BLOCKED"}
)


def test_attempt_manifest_milestone_invariants(tmp_path: Path) -> None:
    repo_root, data_root, eval_desc = setup_offline_q1_parents(tmp_path)

    # 1. Run publication
    code_pub = run_evaluation_pipeline(eval_desc, data_root, repo_root=repo_root)
    assert code_pub == 0

    # 2. Run no-op
    code_noop = run_evaluation_pipeline(eval_desc, data_root, repo_root=repo_root)
    assert code_noop == 0

    # 3. Trigger lost pointer recovery
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
    (eval_dir / "current.json").unlink()
    code_rec = run_evaluation_pipeline(eval_desc, data_root, repo_root=repo_root)
    assert code_rec == 0

    attempts_dir = data_root / "attempts" / "evaluation"
    manifests = [json.loads(p.read_text(encoding="utf-8")) for p in attempts_dir.glob("*.json")]
    assert len(manifests) == 3

    for man in manifests:
        # Check allowed terminal results
        assert man["terminal_result"] in ALLOWED_TERMINAL_RESULTS

        disps = man["artifact_dispositions"]
        # Required milestone keys
        for key in (
            "lock_acquired",
            "lock_released",
            "attempt_staged",
            "object_written",
            "commit_renamed",
            "pointer_replaced",
            "discovery_verified",
            "attempt_staging",
        ):
            assert key in disps, f"missing milestone {key} in {man['attempt_id']}"

        # Invariant 1: commit_renamed is never True unless attempt_staged is True
        if disps["commit_renamed"]:
            assert disps["attempt_staged"] is True

        # Invariant 2: pointer_replaced is never True unless commit_renamed is True
        # (except in lost_pointer_recovered)
        if disps["pointer_replaced"] and not disps.get("lost_pointer_recovered"):
            assert disps["commit_renamed"] is True

        # Invariant 3: discovery_verified is never True unless pointer_replaced is True
        # or VERIFIED_NO_OP
        if disps["discovery_verified"] and man["terminal_result"] != "VERIFIED_NO_OP":
            assert disps["pointer_replaced"] is True

        # Invariant 4: attempt staging is cleaned up
        if disps["attempt_staged"]:
            assert disps["attempt_staging"] == "discarded"

    # Invariant 5: No staging directories left behind
    assert not any((data_root / "staging").glob("attempt-*"))
    assert not any((eval_dir / "commits").glob(".staging-*"))


def test_dry_run_writes_zero_attempt_manifests(tmp_path: Path) -> None:
    repo_root, data_root, eval_desc = setup_offline_q1_parents(tmp_path)

    code = run_evaluation_pipeline(
        descriptor_path=eval_desc,
        data_root=data_root,
        repo_root=repo_root,
        dry_run=True,
    )
    assert code == 0

    attempts_dir = data_root / "attempts" / "evaluation"
    assert not attempts_dir.exists() or not list(attempts_dir.glob("*.json"))


def test_corrupted_quality_blocks_publication_and_records_truthful_manifest(
    tmp_path: Path, monkeypatch
) -> None:
    repo_root, data_root, eval_desc = setup_offline_q1_parents(tmp_path)

    from quantara import evaluation_pipeline as ep_module

    def failing_quality(**kwargs):
        findings = [
            Finding(
                check_id="numeric_domain",
                outcome="fail",
                severity="hard",
                count=2,
                evidence={"tampered_pearson": "NaN"},
            ),
            Finding(
                check_id="metric_bounds",
                outcome="fail",
                severity="hard",
                count=1,
                evidence={"out_of_bounds": "1.5"},
            ),
        ]
        return EvaluationQualityReport(findings)

    monkeypatch.setattr(ep_module, "evaluate_evaluation_quality", failing_quality)

    code = run_evaluation_pipeline(
        descriptor_path=eval_desc,
        data_root=data_root,
        repo_root=repo_root,
        dry_run=False,
    )
    assert code == 2

    attempts_dir = data_root / "attempts" / "evaluation"
    assert attempts_dir.is_dir()
    manifests = list(attempts_dir.glob("*.json"))
    assert len(manifests) == 1
    attempt = json.loads(manifests[0].read_text(encoding="utf-8"))

    assert attempt["terminal_result"] == "BLOCKED"
    assert "numeric_domain" in attempt["diagnostics"]
    assert "metric_bounds" in attempt["diagnostics"]
    disps = attempt["artifact_dispositions"]
    assert disps.get("commit_renamed") is not True
    assert disps.get("pointer_replaced") is not True
    assert disps.get("discovery_verified") is not True
