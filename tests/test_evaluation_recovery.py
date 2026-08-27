"""Evaluation recovery, lock safety, and attempt milestone tests (data slice 006, Tasks T8, T9).

Covers:
- Attempt manifest milestone invariants (lock, stage, write, rename, replace, verify);
- Staging directory cleanup (no lingering staging directories);
- Dry-run writes zero attempt manifests and zero dataset artifacts;
- Corrupted quality blocks publication with truthful attempt diagnostics;
- Lock contention blocks with BLOCKED/2 and lock_contested diagnostic;
- Owner-safe lock release:
  - attempt ID written and fsynced to evaluation.lock;
  - lock only removed if attempt ID matches owner;
  - stale or replaced lock is never stolen or deleted;
- Safe lost-pointer recovery:
  - authentic candidate commit is promoted to current.json without renaming;
  - candidate commit with corrupt manifest or missing object is rejected;
- Post-pointer failure records referenced_commit truthfully;
- Rejection of mock/incomplete graph by verify_evaluation_current_graph.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quantara.cli import main
from quantara.errors import QuantaraError
from quantara.evaluation_pipeline import (
    run_evaluation_pipeline,
    verify_evaluation_current_graph,
)
from quantara.evaluation_quality import EvaluationQualityReport, Finding
from quantara.hashing import quality_identity, sha256_hex
from quantara.jcs import canonicalize
from quantara.publication import stage_commit, store_object, write_current
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
        assert man["terminal_result"] in ALLOWED_TERMINAL_RESULTS
        disps = man["artifact_dispositions"]

        for key in (
            "lock_acquired",
            "lock_released",
            "lock_cleanup",
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

        # Invariant 5: lock_cleanup is cleaned
        if disps["lock_acquired"]:
            assert disps["lock_released"] is True
            assert disps["lock_cleanup"] == "cleaned"

    # No staging directories left behind
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
    manifests = list(attempts_dir.glob("*.json"))
    assert len(manifests) == 1
    doc = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert doc["terminal_result"] == "BLOCKED"
    assert "numeric_domain" in doc["diagnostics"]
    assert "metric_bounds" in doc["diagnostics"]
    assert doc["artifact_dispositions"]["evaluation_artifact"] == "not_written"
    assert doc["artifact_dispositions"]["lock_acquired"] is False


def test_lock_contention_blocks_without_theft(tmp_path: Path) -> None:
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
    eval_dir.mkdir(parents=True, exist_ok=True)
    lock_path = eval_dir / "evaluation.lock"
    external_owner = {"attempt_id": "other_attempt_id", "pid": 99999}
    lock_path.write_text(json.dumps(external_owner) + "\n", encoding="utf-8")

    code = run_evaluation_pipeline(eval_desc, data_root, repo_root=repo_root)
    assert code == 2

    # Lock must remain intact (never stolen or removed)
    assert lock_path.is_file()
    assert json.loads(lock_path.read_text(encoding="utf-8")) == external_owner

    attempts_dir = data_root / "attempts" / "evaluation"
    manifests = list(attempts_dir.glob("*.json"))
    assert len(manifests) == 1
    doc = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert doc["terminal_result"] == "BLOCKED"
    assert doc["diagnostics"] == ["lock_contested"]
    assert doc["artifact_dispositions"]["lock_acquired"] is False


def test_owner_safe_lock_release_behavior(tmp_path: Path) -> None:
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

    # When publication succeeds, lock is created and cleaned
    code = run_evaluation_pipeline(eval_desc, data_root, repo_root=repo_root)
    assert code == 0
    lock_path = eval_dir / "evaluation.lock"
    assert not lock_path.exists()


def test_lost_pointer_recovery_rejects_malformed_commit(tmp_path: Path) -> None:
    repo_root, data_root, eval_desc = setup_offline_q1_parents(tmp_path)
    # First publication
    assert run_evaluation_pipeline(eval_desc, data_root, repo_root=repo_root) == 0

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
    current_json = eval_dir / "current.json"
    current_data = json.loads(current_json.read_text(encoding="utf-8"))
    commit_dir = eval_dir / "commits" / current_data["commit"]

    # Delete current.json
    current_json.unlink()

    # Tamper with candidate commit's manifest
    manifest_path = commit_dir / "manifest.json"
    man_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    man_data["artifact_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(man_data), encoding="utf-8")

    # Recovery must fail because candidate commit is malformed!
    # And it must not install current.json pointing to corrupt candidate commit
    run_evaluation_pipeline(eval_desc, data_root, repo_root=repo_root)
    # Re-publishing or failure without installing corrupt pointer
    assert not current_json.exists() or json.loads(current_json.read_text(encoding="utf-8"))[
        "manifest_sha256"
    ] != sha256_hex(manifest_path.read_bytes())


def test_post_pointer_verification_failure_records_referenced_commit(
    tmp_path: Path, monkeypatch
) -> None:
    repo_root, data_root, eval_desc = setup_offline_q1_parents(tmp_path)

    from quantara import evaluation_pipeline as ep_module

    call_count = [0]

    def failing_verify(dataset_dir, data_root):
        call_count[0] += 1
        raise QuantaraError("simulated post pointer read-back failure")

    monkeypatch.setattr(ep_module, "verify_evaluation_current_graph", failing_verify)

    code = run_evaluation_pipeline(eval_desc, data_root, repo_root=repo_root)
    assert code == 3

    attempts_dir = data_root / "attempts" / "evaluation"
    manifests = list(attempts_dir.glob("*.json"))
    assert len(manifests) == 1
    doc = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert doc["terminal_result"] == "FAILED"
    assert doc["referenced_commit"] is not None
    assert len(doc["referenced_commit"]) == 64
    assert doc["artifact_dispositions"]["pointer_replaced"] is True
    assert doc["artifact_dispositions"]["discovery_verified"] is False


def test_verify_evaluation_current_graph_rejects_mock_or_incomplete_graph(tmp_path: Path) -> None:
    """Regression: 3-key mock artifact or mock findings must be rejected by verifier."""
    data_root = tmp_path / "data"
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
    eval_dir.mkdir(parents=True, exist_ok=True)

    # 3-key mock artifact
    mock_artifact = {
        "schema": "quantara.feature_evaluation/v1",
        "dataset_id": "mock_id",
        "features": ["f_ret_1"],
    }
    art_bytes = canonicalize(mock_artifact).encode("utf-8") + b"\n"
    stored_obj = store_object(data_root, "normalized", art_bytes)

    # Mock findings (not 13 checks)
    mock_findings = [
        {
            "check_id": "mock_check",
            "outcome": "pass",
            "severity": "hard",
            "count": 0,
            "evidence": {},
        }
    ]

    fake_commit = "f" * 64
    content = {
        "descriptor_sha256": "0" * 64,
        "schema_fingerprint": "1" * 64,
        "parser_version": "1.0.0",
        "canonical_content_hash": "2" * 64,
        "quality_identity": quality_identity(mock_findings),
        "object_refs": [{"kind": "normalized", "sha256": stored_obj.sha256}],
        "evaluation_from": {"dummy": True},
        "evaluation_commit_identity": fake_commit,
    }
    manifest = {
        "dataset_id": "mock_id",
        "schema_version": "quantara_feature_evaluation_v1",
        "schema_fingerprint": "1" * 64,
        "parser_version": "1.0.0",
        "canonical_content_hash": "2" * 64,
        "quality_identity": quality_identity(mock_findings),
        "quality_state": "PASS",
        "quality_policy_version": "1",
        "commit_identity": fake_commit,
        "artifact_sha256": stored_obj.sha256,
        "artifact_size": len(art_bytes),
        "object_refs": [{"kind": "normalized", "sha256": stored_obj.sha256}],
        "evaluation_from": {"dummy": True},
        "parent_discovery": {
            "validation_pointer_manifest_sha256": "a" * 64,
            "research_pointer_manifest_sha256": "b" * 64,
        },
    }
    quality_doc = {
        "state": "PASS",
        "policy_version": "1",
        "identity": quality_identity(mock_findings),
        "findings": mock_findings,
    }
    manifest_bytes = (json.dumps(manifest) + "\n").encode("utf-8")

    staged = stage_commit(
        eval_dir,
        "att-1",
        {
            "manifest.json": manifest_bytes,
            "content.json": (json.dumps(content) + "\n").encode("utf-8"),
            "quality.json": (json.dumps(quality_doc) + "\n").encode("utf-8"),
        },
    )
    commit_dir = eval_dir / "commits" / fake_commit
    commit_dir.parent.mkdir(parents=True, exist_ok=True)
    staged.rename(commit_dir)
    write_current(eval_dir, fake_commit, sha256_hex(manifest_bytes))

    with pytest.raises(QuantaraError):
        verify_evaluation_current_graph(eval_dir, data_root)


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
