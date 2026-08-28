"""Training publication, no-op, rights, pointer, and CLI tests."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from conftest import rights_v2_yaml_dict, write_training_descriptor
from quantara.hashing import quality_identity, sha256_hex, validation_content_hash
from quantara.jcs import canonicalize
from quantara.publication import stage_commit, store_object, write_current
from quantara.training_pipeline import run_training_pipeline, verify_training_current_graph
from quantara.validation_pipeline import validation_commit_identity
from test_evaluation_pipeline import setup_offline_q1_parents


def _setup(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo_root, data_root, _ = setup_offline_q1_parents(tmp_path)
    descriptor = write_training_descriptor(repo_root)
    validation_dir = (
        data_root
        / "datasets"
        / "binance"
        / "usdm"
        / "validation"
        / "BTCUSDT"
        / "1h"
        / "year=2024"
        / "month=01"
    )
    pointer = json.loads((validation_dir / "current.json").read_text(encoding="utf-8"))
    old_dir = validation_dir / "commits" / pointer["commit"]
    manifest = json.loads((old_dir / "manifest.json").read_text(encoding="utf-8"))
    content = json.loads((old_dir / "content.json").read_text(encoding="utf-8"))
    folds = []
    start = 360
    for fold_id in range(25):
        end = start + (96 if fold_id == 24 else 72)
        folds.append(
            {
                "fold_id": fold_id,
                "train_range": [0, start - 24],
                "embargo_range": [start - 24, start],
                "test_range": [start, end],
            }
        )
        start = end
    artifact = {
        "schema": "quantara.validation_folds/v1",
        "fold_set": "btcusdt_core_v1_wf72_v1",
        "scheme": "anchored_walkforward_v1",
        "parameters": {"test_size": 72, "min_train_size": 336, "embargo": 24},
        "parent_rows": 2184,
        "excluded_head_rows": 360,
        "folds": folds,
        "coverage": {"total_rows": 2184, "test_rows": 1824, "fold_count": 25},
    }
    artifact_bytes = canonicalize(artifact).encode("utf-8") + b"\n"
    stored = store_object(data_root, "normalized", artifact_bytes)
    fingerprint = manifest["schema_fingerprint"]
    content_hash = validation_content_hash(fingerprint, artifact_bytes)
    lineage = content["validation_from"]
    commit = validation_commit_identity(content_hash, lineage)
    findings = [
        {
            "check_id": "fold_coverage",
            "count": 0,
            "evidence": {"folds": 25},
            "outcome": "pass",
            "severity": "hard",
        }
    ]
    qid = quality_identity(findings)
    manifest.update(
        canonical_content_hash=content_hash,
        commit_identity=commit,
        artifact_sha256=stored.sha256,
        artifact_size=len(artifact_bytes),
        quality_identity=qid,
        object_refs=[{"kind": "normalized", "sha256": stored.sha256}],
    )
    content.update(
        canonical_content_hash=content_hash,
        validation_commit_identity=commit,
        quality_identity=qid,
        object_refs=[{"kind": "normalized", "sha256": stored.sha256}],
    )
    quality = {
        "state": "PASS",
        "policy_version": "1",
        "identity": qid,
        "findings": findings,
    }
    files = {
        "manifest.json": (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
        "content.json": (json.dumps(content, indent=2, sort_keys=True) + "\n").encode(),
        "quality.json": (json.dumps(quality, indent=2, sort_keys=True) + "\n").encode(),
    }
    staged = stage_commit(validation_dir, "training_val", files)
    commit_dir = validation_dir / "commits" / commit
    staged.replace(commit_dir)
    (commit_dir / "COMMITTED").touch()
    write_current(validation_dir, commit, sha256_hex(files["manifest.json"]))
    return repo_root, data_root, descriptor


def _training_dir(data_root: Path) -> Path:
    return (
        data_root
        / "datasets"
        / "binance"
        / "usdm"
        / "training"
        / "BTCUSDT"
        / "1h"
        / "year=2024"
        / "month=01"
    )


def test_rights_unknown_blocks_with_attempt(tmp_path: Path) -> None:
    repo_root, data_root, descriptor = _setup(tmp_path)
    rights = rights_v2_yaml_dict()
    rights["record_id"] = "synthetic-training-blocked"
    (repo_root / "configs" / "legal" / "binance-usdm-provider-rights.v3.yaml").write_text(
        yaml.safe_dump(rights, sort_keys=False), encoding="utf-8"
    )
    assert run_training_pipeline(descriptor, data_root, repo_root=repo_root) == 2
    attempts = list((data_root / "attempts" / "training").glob("*.json"))
    assert len(attempts) == 1
    assert json.loads(attempts[0].read_text())["terminal_result"] == "BLOCKED"


def test_publish_noop_pointer_identity_and_verifier(tmp_path: Path) -> None:
    repo_root, data_root, descriptor = _setup(tmp_path)
    validation_pointer = next(data_root.glob("datasets/binance/usdm/validation/**/current.json"))
    research_pointer = next(data_root.glob("datasets/binance/usdm/research/**/current.json"))
    parent_bytes = (validation_pointer.read_bytes(), research_pointer.read_bytes())
    assert run_training_pipeline(descriptor, data_root, repo_root=repo_root) == 0
    training_dir = _training_dir(data_root)
    graph = verify_training_current_graph(training_dir, data_root)
    assert len(graph["records"]) == 25
    pointer_before = (training_dir / "current.json").read_bytes()
    assert run_training_pipeline(descriptor, data_root, repo_root=repo_root) == 0
    assert (training_dir / "current.json").read_bytes() == pointer_before
    assert (validation_pointer.read_bytes(), research_pointer.read_bytes()) == parent_bytes
    attempts = sorted((data_root / "attempts" / "training").glob("*.json"))
    assert json.loads(attempts[-1].read_text())["terminal_result"] == "VERIFIED_NO_OP"


def test_cli_training_dispatch(tmp_path: Path) -> None:
    from quantara.cli import main

    repo_root, data_root, descriptor = _setup(tmp_path)
    assert main(
        [
            "--dataset-type",
            "model_training",
            "--descriptor",
            str(descriptor),
            "--data-root",
            str(data_root),
            "--dry-run",
        ]
    ) == 0
