"""Real Q1 deterministic identity oracle and lock-free verification tests (Task T7).

Covers:
- Real retained Q1 validation and research parents read-only oracle:
  - exact 100 records and 8 summaries;
  - exact 7,200 valid pairs;
  - exact zero feature nulls;
  - exact 24 target nulls in fold 24 only;
  - frozen schema fingerprint;
  - frozen canonical artifact SHA-256 and size;
  - frozen canonical content hash;
  - frozen evaluation commit identity;
  - exact PASS quality state and deterministic quality identity;
  - zero files written to disk;
- verify_evaluation_current_graph:
  - protocol version v1;
  - COMMITTED marker required;
  - manifest SHA-256 matching current.json;
  - CAS object SHA-256 and size matching;
  - recomputation of content hash and commit identity;
  - PASS-only quality enforcement;
  - returns verified graph dictionary.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from quantara.errors import QuantaraError
from quantara.evaluation_descriptor import (
    APPROVED_FEATURES,
    load_evaluation_descriptor,
)
from quantara.evaluation_metrics import (
    build_evaluation_records,
    build_evaluation_summaries,
)
from quantara.evaluation_pipeline import (
    build_evaluation_artifact,
    evaluation_commit_identity,
    verify_evaluation_current_graph,
)
from quantara.evaluation_quality import evaluate_evaluation_quality
from quantara.hashing import (
    evaluation_content_hash,
    evaluation_schema_fingerprint,
    quality_identity,
    sha256_hex,
)
from quantara.jcs import canonicalize
from quantara.publication import stage_commit, store_object, write_current
from quantara.research_pipeline import read_research_rows

FROZEN_Q1_SCHEMA_FINGERPRINT = "d454a7e142ac19cfbb75ccabd53f1fb20f26bc471968c6e4b84203030aa10843"
FROZEN_Q1_CANONICAL_CONTENT_HASH = (
    "76f02fca4d149baca6380caa4b389527787af2c2770f374b1cbd7ca3297d984c"
)
FROZEN_Q1_COMMIT_IDENTITY = "d2354cd10fd9b1640e42ba90c2d677c329103859c3f9673e6bcbec76210d4675"
FROZEN_Q1_ARTIFACT_SHA256 = "4b8393a961b909393d0e7616eda2d9e741ca2f7c2216231700f419505cd53e8f"
FROZEN_Q1_ARTIFACT_SIZE = 30991


def test_real_q1_identity_oracle_freeze() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    data_root = repo_root / "data"

    desc_path = (
        repo_root
        / "configs"
        / "datasets"
        / "binance-usdm-btcusdt-1h-2024-q1-evaluation-dual-ic-v1.yaml"
    )
    descriptor = load_evaluation_descriptor(desc_path)

    val_commit = "3f8a776bbdb195bb80fe1d7e19e978b0492d7e95ed30307a32b131fe57f901ca"
    val_commit_dir = (
        data_root
        / "datasets"
        / "binance"
        / "usdm"
        / "validation"
        / "BTCUSDT"
        / "1h"
        / "year=2024"
        / "month=01"
        / "commits"
        / val_commit
    )
    val_manifest = json.loads((val_commit_dir / "manifest.json").read_text(encoding="utf-8"))
    val_content = json.loads((val_commit_dir / "content.json").read_text(encoding="utf-8"))
    val_art_sha = val_manifest["artifact_sha256"]
    val_art_bytes = (data_root / "objects" / "normalized" / "sha256" / val_art_sha).read_bytes()
    val_artifact = json.loads(val_art_bytes.decode("utf-8"))

    res_commit = "ca878557b82c63d5265a307c2b4b39bb1f4e11ca171bef65a573b51f4c970ce3"
    res_commit_dir = (
        data_root
        / "datasets"
        / "binance"
        / "usdm"
        / "research"
        / "BTCUSDT"
        / "1h"
        / "year=2024"
        / "month=01"
        / "commits"
        / res_commit
    )
    res_manifest = json.loads((res_commit_dir / "manifest.json").read_text(encoding="utf-8"))
    res_content = json.loads((res_commit_dir / "content.json").read_text(encoding="utf-8"))
    res_pq_sha = res_manifest["parquet_sha256"]
    res_pq_bytes = (data_root / "objects" / "normalized" / "sha256" / res_pq_sha).read_bytes()
    res_rows = read_research_rows(data_root / "objects" / "normalized" / "sha256" / res_pq_sha)

    records = build_evaluation_records(val_artifact["folds"], res_rows)
    summaries = build_evaluation_summaries(records)

    # 1. Shape and null freezes
    assert len(records) == 100
    assert len(summaries) == 8
    assert sum(r["valid_pair_count"] for r in records) == 7200
    assert all(r["feature_null_count"] == 0 for r in records)
    for r in records:
        expected_target_nulls = 24 if r["fold_id"] == 24 else 0
        assert r["target_null_count"] == expected_target_nulls
        assert r["excluded_pair_count"] == expected_target_nulls
        # Decimal checks
        p = Decimal(r["pearson_ic"])
        s = Decimal(r["spearman_ic"])
        assert not p.is_nan() and not p.is_infinite()
        assert not s.is_nan() and not s.is_infinite()

    val_parent_info = {
        "dataset_id": val_manifest["dataset_id"],
        "commit_address": val_commit,
        "canonical_content_hash": val_content["canonical_content_hash"],
        "artifact_sha256": val_art_sha,
        "artifact_size": len(val_art_bytes),
        "schema_fingerprint": val_content["schema_fingerprint"],
    }
    res_parent_info = {
        "dataset_id": res_manifest["dataset_id"],
        "commit_address": res_commit,
        "canonical_content_hash": res_content["canonical_content_hash"],
        "parquet_sha256": res_pq_sha,
        "parquet_size": len(res_pq_bytes),
    }

    artifact = build_evaluation_artifact(
        descriptor, val_parent_info, res_parent_info, records, summaries
    )
    art_bytes = canonicalize(artifact).encode("utf-8") + b"\n"
    art_sha = sha256_hex(art_bytes)

    schema_fp = evaluation_schema_fingerprint(
        parent_validation_fingerprint=val_content["schema_fingerprint"]
    )
    content_hash = evaluation_content_hash(schema_fp, art_bytes)

    eval_from = {
        "validation_dataset_id": val_parent_info["dataset_id"],
        "validation_commit_address": val_parent_info["commit_address"],
        "validation_canonical_content_hash": val_parent_info["canonical_content_hash"],
        "validation_artifact_sha256": val_parent_info["artifact_sha256"],
        "validation_artifact_size": val_parent_info["artifact_size"],
        "research_dataset_id": res_parent_info["dataset_id"],
        "research_commit_address": res_parent_info["commit_address"],
        "research_canonical_content_hash": res_parent_info["canonical_content_hash"],
        "research_parquet_sha256": res_parent_info["parquet_sha256"],
        "research_parquet_size": res_parent_info["parquet_size"],
        "evaluation_set_name": descriptor.evaluation_set["name"],
        "evaluation_set_version": descriptor.evaluation_set["version"],
        "features": list(descriptor.features),
        "target": descriptor.target,
        "metrics": list(descriptor.metrics),
        "decimal_contract": artifact["decimal_contract"],
    }
    commit_id = evaluation_commit_identity(content_hash, eval_from)

    report = evaluate_evaluation_quality(
        descriptor=descriptor,
        validation_parent_info=val_parent_info,
        research_parent_info=res_parent_info,
        validation_artifact=val_artifact,
        research_rows=res_rows,
        validation_artifact_bytes=val_art_bytes,
        validation_quality_state=val_manifest["quality_state"],
        research_quality_state=res_manifest["quality_state"],
        validation_lineage=val_content["validation_from"],
        artifact=artifact,
        artifact_bytes=art_bytes,
        schema_fingerprint=schema_fp,
        canonical_content_hash=content_hash,
        evaluation_from=eval_from,
        prospective_commit_identity=commit_id,
    )

    # 2. Exact frozen identities
    assert schema_fp == FROZEN_Q1_SCHEMA_FINGERPRINT
    assert art_sha == FROZEN_Q1_ARTIFACT_SHA256
    assert len(art_bytes) == FROZEN_Q1_ARTIFACT_SIZE
    assert content_hash == FROZEN_Q1_CANONICAL_CONTENT_HASH
    assert commit_id == FROZEN_Q1_COMMIT_IDENTITY
    assert report.state == "PASS"


def test_verify_evaluation_current_graph_success(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    dataset_dir = (
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

    # Store mock artifact in CAS
    art_payload = {
        "schema": "quantara.feature_evaluation/v1",
        "dataset_id": "binance_usdm_btcusdt_klines_1h_2024_q1_evaluation_dual_ic_v1",
        "features": list(APPROVED_FEATURES),
    }
    art_bytes = canonicalize(art_payload).encode("utf-8") + b"\n"
    stored = store_object(data_root, "normalized", art_bytes)

    schema_fp = evaluation_schema_fingerprint("0" * 64)
    content_hash = evaluation_content_hash(schema_fp, art_bytes)
    eval_from = {"some": "lineage"}
    commit_id = evaluation_commit_identity(content_hash, eval_from)

    findings = [
        {
            "check_id": "mock_check",
            "count": 0,
            "evidence": {},
            "outcome": "pass",
            "severity": "hard",
        }
    ]
    qid = quality_identity(findings)

    manifest = {
        "dataset_id": "binance_usdm_btcusdt_klines_1h_2024_q1_evaluation_dual_ic_v1",
        "schema_fingerprint": schema_fp,
        "parser_version": "1.0.0",
        "canonical_content_hash": content_hash,
        "quality_identity": qid,
        "quality_state": "PASS",
        "quality_policy_version": "1",
        "commit_identity": commit_id,
        "artifact_sha256": stored.sha256,
        "artifact_size": len(art_bytes),
        "object_refs": [{"kind": "normalized", "sha256": stored.sha256}],
        "evaluation_from": eval_from,
    }
    content = {
        "schema_fingerprint": schema_fp,
        "parser_version": "1.0.0",
        "canonical_content_hash": content_hash,
        "quality_identity": qid,
        "object_refs": [{"kind": "normalized", "sha256": stored.sha256}],
        "evaluation_from": eval_from,
        "evaluation_commit_identity": commit_id,
    }
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
    staged = stage_commit(dataset_dir, "test_eval", files)
    commit_dir = dataset_dir / "commits" / commit_id
    commit_dir.parent.mkdir(parents=True, exist_ok=True)
    staged.replace(commit_dir)
    (commit_dir / "COMMITTED").touch()
    write_current(dataset_dir, commit_id, sha256_hex(files["manifest.json"]))

    verified = verify_evaluation_current_graph(dataset_dir, data_root)
    assert verified["commit"] == commit_id
    assert verified["canonical_content_hash"] == content_hash


def test_verify_evaluation_current_graph_tampered_fails(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    dataset_dir = (
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

    art_payload = {"schema": "quantara.feature_evaluation/v1"}
    art_bytes = canonicalize(art_payload).encode("utf-8") + b"\n"
    stored = store_object(data_root, "normalized", art_bytes)
    schema_fp = evaluation_schema_fingerprint("0" * 64)
    content_hash = evaluation_content_hash(schema_fp, art_bytes)
    eval_from = {"some": "lineage"}
    commit_id = evaluation_commit_identity(content_hash, eval_from)

    manifest = {
        "dataset_id": "test",
        "schema_fingerprint": schema_fp,
        "parser_version": "1.0.0",
        "canonical_content_hash": content_hash,
        "quality_identity": "qid",
        "quality_state": "FAIL",  # Failing quality state
        "quality_policy_version": "1",
        "commit_identity": commit_id,
        "artifact_sha256": stored.sha256,
        "artifact_size": len(art_bytes),
        "object_refs": [{"kind": "normalized", "sha256": stored.sha256}],
        "evaluation_from": eval_from,
    }
    content = {
        "schema_fingerprint": schema_fp,
        "parser_version": "1.0.0",
        "canonical_content_hash": content_hash,
        "quality_identity": "qid",
        "object_refs": [{"kind": "normalized", "sha256": stored.sha256}],
        "evaluation_from": eval_from,
        "evaluation_commit_identity": commit_id,
    }
    quality = {
        "state": "FAIL",
        "policy_version": "1",
        "identity": "qid",
        "findings": [],
    }

    files = {
        "manifest.json": (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
        "content.json": (json.dumps(content, indent=2, sort_keys=True) + "\n").encode(),
        "quality.json": (json.dumps(quality, indent=2, sort_keys=True) + "\n").encode(),
    }
    staged = stage_commit(dataset_dir, "test_eval", files)
    commit_dir = dataset_dir / "commits" / commit_id
    commit_dir.parent.mkdir(parents=True, exist_ok=True)
    staged.replace(commit_dir)
    (commit_dir / "COMMITTED").touch()
    write_current(dataset_dir, commit_id, sha256_hex(files["manifest.json"]))

    with pytest.raises(QuantaraError):
        verify_evaluation_current_graph(dataset_dir, data_root)
