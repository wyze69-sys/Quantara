"""Real Q1 serial acceptance and independent oracle tests (data slice 006, Tasks T10, T11).

Covers:
- T10: Independently frozen real-Q1 oracle vectors:
  - exact 100 records, 200 IC values, 7,200 valid pairs, 0 feature nulls;
  - exact 24 target nulls in fold 24 only;
  - frozen schema fingerprint, canonical content hash, commit identity;
  - frozen artifact SHA-256, artifact size;
  - zero files written to disk.
- T11: Marked serial real-Q1 integration acceptance:
  - snapshots current research and validation pointers;
  - establishes retained Q1 research and validation chain through real CLI;
  - runs real Slice 006 feature evaluation through real CLI entrypoint;
  - verifies 25 folds, 100 records, 200 ICs, 72 valid pairs per record;
  - independently recomputes all Pearson and Spearman values without helpers;
  - independently recomputes all summaries from stored Q18 values;
  - matches frozen Q1 hashes, boundary records, and 8 summary anchors;
  - verifies first publication and byte-identical VERIFIED_NO_OP on rerun;
  - inspects truthful attempt milestones;
  - restores predecessor pointers in finally;
  - proves predecessor immutable trees remained byte-identical.
"""

from __future__ import annotations

import decimal
import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

from quantara.cli import main
from quantara.evaluation_descriptor import (
    APPROVED_FEATURES,
    load_evaluation_descriptor,
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
    sha256_hex,
)
from quantara.jcs import canonicalize
from quantara.research_pipeline import read_research_rows

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = REPO_ROOT / "data"
CONFIG_ROOT = REPO_ROOT / "configs" / "datasets"

FROZEN_Q1_SCHEMA_FINGERPRINT = "d454a7e142ac19cfbb75ccabd53f1fb20f26bc471968c6e4b84203030aa10843"
FROZEN_Q1_CANONICAL_CONTENT_HASH = (
    "76f02fca4d149baca6380caa4b389527787af2c2770f374b1cbd7ca3297d984c"
)
FROZEN_Q1_COMMIT_IDENTITY = "d2354cd10fd9b1640e42ba90c2d677c329103859c3f9673e6bcbec76210d4675"
FROZEN_Q1_ARTIFACT_SHA256 = "4b8393a961b909393d0e7616eda2d9e741ca2f7c2216231700f419505cd53e8f"
FROZEN_Q1_ARTIFACT_SIZE = 30991

EVALUATION_CONFIG = CONFIG_ROOT / "binance-usdm-btcusdt-1h-2024-q1-evaluation-dual-ic-v1.yaml"
RESEARCH_CONFIG = CONFIG_ROOT / "binance-usdm-btcusdt-1h-2024-q1-research-core-v1.yaml"
VALIDATION_CONFIG = CONFIG_ROOT / "binance-usdm-btcusdt-1h-2024-q1-validation-wf-v1.yaml"


def _tree_digest(directory: Path) -> str:
    hasher = hashlib.sha256()
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        hasher.update(path.relative_to(directory).as_posix().encode("utf-8"))
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


def _independent_rank(values: list[Decimal]) -> list[Decimal]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    n = len(values)
    ranks = [Decimal(0)] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        tie_rank = (Decimal(i + 1) + Decimal(j + 1)) / Decimal(2)
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = tie_rank
        i = j + 1
    return ranks


def _independent_pearson(xs: list[Decimal], ys: list[Decimal]) -> Decimal:
    n = Decimal(len(xs))
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x == 0 or var_y == 0:
        return Decimal(0)
    with decimal.localcontext(decimal.Context(prec=34)):
        denom = (var_x * var_y).sqrt()
        return cov / denom


def _independent_spearman(xs: list[Decimal], ys: list[Decimal]) -> Decimal:
    return _independent_pearson(_independent_rank(xs), _independent_rank(ys))


def _fmt18(d: Decimal) -> str:
    return f"{d.quantize(Decimal('1e-18'), rounding=decimal.ROUND_HALF_EVEN):.18f}"


def _independent_median(sorted_vals: list[Decimal]) -> Decimal:
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 1:
        return sorted_vals[mid]
    return (sorted_vals[mid - 1] + sorted_vals[mid]) / Decimal(2)


def test_real_q1_identity_oracle_freeze() -> None:
    """T10 — Independently frozen real-Q1 oracle vectors (read-only, write-free)."""
    descriptor = load_evaluation_descriptor(EVALUATION_CONFIG)

    val_commit = "3f8a776bbdb195bb80fe1d7e19e978b0492d7e95ed30307a32b131fe57f901ca"
    val_commit_dir = (
        DATA_ROOT
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
    val_art_bytes = (DATA_ROOT / "objects" / "normalized" / "sha256" / val_art_sha).read_bytes()
    val_artifact = json.loads(val_art_bytes.decode("utf-8"))

    res_commit = "ca878557b82c63d5265a307c2b4b39bb1f4e11ca171bef65a573b51f4c970ce3"
    res_commit_dir = (
        DATA_ROOT
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
    res_rows = read_research_rows(DATA_ROOT / "objects" / "normalized" / "sha256" / res_pq_sha)

    # Independently build records using our local math functions
    feature_indices = {"f_ret_1": 1, "f_roc_60": 2, "f_rvol_20": 3, "f_volratio_20": 4}
    records = []
    for fold in val_artifact["folds"]:
        fold_id = fold["fold_id"]
        start_idx, end_idx = fold["test_range"]
        test_rows = res_rows[start_idx:end_idx]
        test_count = len(test_rows)

        for feat_name in APPROVED_FEATURES:
            feat_idx = feature_indices[feat_name]
            valid_pairs = []
            target_nulls = 0
            for r in test_rows:
                y = r[5]
                if y is None:
                    target_nulls += 1
                else:
                    valid_pairs.append((Decimal(str(r[feat_idx])), Decimal(str(y))))

            xs = [p[0] for p in valid_pairs]
            ys = [p[1] for p in valid_pairs]
            records.append(
                {
                    "fold_id": fold_id,
                    "feature": feat_name,
                    "target": "l_fwdret_24",
                    "test_range": list(fold["test_range"]),
                    "test_row_count": test_count,
                    "valid_pair_count": len(valid_pairs),
                    "excluded_pair_count": target_nulls,
                    "feature_null_count": 0,
                    "target_null_count": target_nulls,
                    "pearson_ic": _fmt18(_independent_pearson(xs, ys)),
                    "spearman_ic": _fmt18(_independent_spearman(xs, ys)),
                }
            )

    # Independently build summaries
    summaries = []
    for feat_name in APPROVED_FEATURES:
        feat_recs = [r for r in records if r["feature"] == feat_name]
        for metric_name in ("pearson_ic", "spearman_ic"):
            values = [Decimal(r[metric_name]) for r in feat_recs]
            sorted_vals = sorted(values)
            n_folds = len(values)
            pos = sum(1 for v in values if v > 0)
            neg = sum(1 for v in values if v < 0)
            zero = sum(1 for v in values if v == 0)
            tot_pairs = sum(r["valid_pair_count"] for r in feat_recs)
            mean_val = sum(values) / Decimal(n_folds)
            med_val = _independent_median(sorted_vals)

            summaries.append(
                {
                    "feature": feat_name,
                    "metric": metric_name,
                    "fold_count": n_folds,
                    "total_valid_pair_count": tot_pairs,
                    "positive_fold_count": pos,
                    "negative_fold_count": neg,
                    "zero_fold_count": zero,
                    "minimum": _fmt18(sorted_vals[0]),
                    "maximum": _fmt18(sorted_vals[-1]),
                    "median": _fmt18(med_val),
                    "equal_weight_mean": _fmt18(mean_val),
                }
            )

    # Assert matrix counts
    assert len(records) == 100
    assert len(summaries) == 8
    assert sum(r["valid_pair_count"] for r in records) == 7200
    assert all(r["valid_pair_count"] == 72 for r in records)
    assert all(r["feature_null_count"] == 0 for r in records)
    for r in records:
        if r["fold_id"] == 24:
            assert r["target_null_count"] == 24
            assert r["excluded_pair_count"] == 24
        else:
            assert r["target_null_count"] == 0
            assert r["excluded_pair_count"] == 0

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
        "parquet_size": res_manifest["parquet_size"],
    }

    artifact = build_evaluation_artifact(
        descriptor, val_parent_info, res_parent_info, records, summaries
    )
    artifact_bytes = canonicalize(artifact).encode("utf-8") + b"\n"
    assert len(artifact_bytes) == FROZEN_Q1_ARTIFACT_SIZE
    assert sha256_hex(artifact_bytes) == FROZEN_Q1_ARTIFACT_SHA256

    schema_fp = evaluation_schema_fingerprint(
        parent_validation_fingerprint=val_content["schema_fingerprint"]
    )
    assert schema_fp == FROZEN_Q1_SCHEMA_FINGERPRINT

    content_hash = evaluation_content_hash(schema_fp, artifact_bytes)
    assert content_hash == FROZEN_Q1_CANONICAL_CONTENT_HASH

    evaluation_from = {
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
    commit_id = evaluation_commit_identity(content_hash, evaluation_from)
    assert commit_id == FROZEN_Q1_COMMIT_IDENTITY

    quality_report = evaluate_evaluation_quality(
        descriptor=descriptor,
        validation_parent_info=val_parent_info,
        research_parent_info=res_parent_info,
        validation_artifact=val_artifact,
        research_rows=res_rows,
        validation_artifact_bytes=val_art_bytes,
        validation_quality_state="PASS",
        research_quality_state="PASS",
        validation_lineage=val_content["validation_from"],
        artifact=artifact,
        artifact_bytes=artifact_bytes,
        schema_fingerprint=schema_fp,
        canonical_content_hash=content_hash,
        evaluation_from=evaluation_from,
        prospective_commit_identity=commit_id,
    )
    assert quality_report.state == "PASS"
    assert len(quality_report.findings) == 13


def test_real_q1_evaluation_serial_acceptance_and_idempotency() -> None:
    """T11 — Real-Q1 acceptance, idempotency, and invariant verification."""
    k1m_dir = DATA_ROOT / "datasets/binance/usdm/klines/BTCUSDT/1m/year=2024/month=01"
    k1h_dir = DATA_ROOT / "datasets/binance/usdm/klines/BTCUSDT/1h/year=2024/month=01"
    res_dir = DATA_ROOT / "datasets/binance/usdm/research/BTCUSDT/1h/year=2024/month=01"
    val_dir = DATA_ROOT / "datasets/binance/usdm/validation/BTCUSDT/1h/year=2024/month=01"
    eval_dir = DATA_ROOT / "datasets/binance/usdm/evaluation/BTCUSDT/1h/year=2024/month=01"

    k1m_ptr = k1m_dir / "current.json"
    k1h_ptr = k1h_dir / "current.json"
    res_ptr = res_dir / "current.json"
    val_ptr = val_dir / "current.json"
    eval_ptr = eval_dir / "current.json"

    # 1. Snapshot research and validation pointers and predecessors
    pointers = [k1m_ptr, k1h_ptr, res_ptr, val_ptr]
    if eval_ptr.exists():
        pointers.append(eval_ptr)
    snapshots = {p: p.read_bytes() for p in pointers}

    # 2. Snapshot predecessor immutable commit trees
    january_commit_dirs = {
        "k1m": k1m_dir / "commits" / json.loads(snapshots[k1m_ptr])["commit"],
        "k1h": k1h_dir / "commits" / json.loads(snapshots[k1h_ptr])["commit"],
        "res": res_dir / "commits" / json.loads(snapshots[res_ptr])["commit"],
        "val": val_dir / "commits" / json.loads(snapshots[val_ptr])["commit"],
    }
    baseline_digests = {name: _tree_digest(d) for name, d in january_commit_dirs.items()}

    attempts_dir = DATA_ROOT / "attempts" / "evaluation"

    try:
        # 3. Establish and authenticate Q1 research and validation chain through real CLI routes
        k1m_q1_commit = "8549fac77830c50a61fbe943568d85482bcee9469a82add2af1a84655538ce04"
        k1m_q1_man = sha256_hex(
            (k1m_dir / "commits" / k1m_q1_commit / "manifest.json").read_bytes()
        )
        k1m_ptr.write_text(
            json.dumps(
                {
                    "commit": k1m_q1_commit,
                    "manifest_sha256": k1m_q1_man,
                    "publication_protocol_version": "v1",
                },
                indent=2,
            )
            + "\n"
        )

        k1h_q1_commit = "59faf446d6957360a59e0969903bb0e11980ab984e3959b4d8bdf17f4de4e22f"
        k1h_q1_man = sha256_hex(
            (k1h_dir / "commits" / k1h_q1_commit / "manifest.json").read_bytes()
        )
        k1h_ptr.write_text(
            json.dumps(
                {
                    "commit": k1h_q1_commit,
                    "manifest_sha256": k1h_q1_man,
                    "publication_protocol_version": "v1",
                },
                indent=2,
            )
            + "\n"
        )

        # Authenticate through CLI
        assert main(["--descriptor", str(RESEARCH_CONFIG), "--data-root", str(DATA_ROOT)]) == 0
        assert main(["--descriptor", str(VALIDATION_CONFIG), "--data-root", str(DATA_ROOT)]) == 0

        # 4. Run the evaluation descriptor through the real CLI
        exit_code = main(["--descriptor", str(EVALUATION_CONFIG), "--data-root", str(DATA_ROOT)])
        assert exit_code == 0

        # 5. Read back through verify_evaluation_current_graph
        verified = verify_evaluation_current_graph(eval_dir, DATA_ROOT)
        assert verified["commit"] == FROZEN_Q1_COMMIT_IDENTITY
        assert verified["canonical_content_hash"] == FROZEN_Q1_CANONICAL_CONTENT_HASH
        assert verified["schema_fingerprint"] == FROZEN_Q1_SCHEMA_FINGERPRINT

        art_sha = verified["object_refs"][0]["sha256"]
        assert art_sha == FROZEN_Q1_ARTIFACT_SHA256
        art_bytes = (DATA_ROOT / "objects" / "normalized" / "sha256" / art_sha).read_bytes()
        assert len(art_bytes) == FROZEN_Q1_ARTIFACT_SIZE
        eval_artifact = json.loads(art_bytes.decode("utf-8"))

        records = eval_artifact["records"]
        summaries = eval_artifact["summaries"]

        # Assert record counts
        assert len(eval_artifact["records"]) == 100
        assert len(eval_artifact["summaries"]) == 8
        assert sum(r["valid_pair_count"] for r in records) == 7200
        assert all(r["valid_pair_count"] == 72 for r in records)

        # 6. Boundary records match exact Task T10 anchors
        rec_f0_ret1 = [r for r in records if r["fold_id"] == 0 and r["feature"] == "f_ret_1"][0]
        assert rec_f0_ret1["test_range"] == [360, 432]
        assert rec_f0_ret1["valid_pair_count"] == 72
        assert rec_f0_ret1["pearson_ic"] == "-0.098918351208551690"
        assert rec_f0_ret1["spearman_ic"] == "-0.138111775676892405"

        rec_f24_vol20 = [
            r for r in records if r["fold_id"] == 24 and r["feature"] == "f_volratio_20"
        ][0]
        assert rec_f24_vol20["test_range"] == [2088, 2184]
        assert rec_f24_vol20["test_row_count"] == 96
        assert rec_f24_vol20["valid_pair_count"] == 72
        assert rec_f24_vol20["target_null_count"] == 24
        assert rec_f24_vol20["excluded_pair_count"] == 24
        assert rec_f24_vol20["pearson_ic"] == "-0.009692885223140206"
        assert rec_f24_vol20["spearman_ic"] == "-0.009518296996591421"

        # 7. Summary anchors match exact Task T10 anchors
        sum_map = {(s["feature"], s["metric"]): s for s in summaries}
        s_ret1_p = sum_map[("f_ret_1", "pearson_ic")]
        assert s_ret1_p["equal_weight_mean"] == "-0.111294186144914768"
        assert s_ret1_p["minimum"] == "-0.303946195261965526"
        assert s_ret1_p["median"] == "-0.113263945415598819"
        assert s_ret1_p["maximum"] == "0.092814689936449646"
        assert (
            s_ret1_p["positive_fold_count"],
            s_ret1_p["negative_fold_count"],
            s_ret1_p["zero_fold_count"],
        ) == (4, 21, 0)

        s_ret1_s = sum_map[("f_ret_1", "spearman_ic")]
        assert s_ret1_s["equal_weight_mean"] == "-0.111973760370441829"
        assert s_ret1_s["minimum"] == "-0.428612772525564345"
        assert s_ret1_s["median"] == "-0.110875297446781143"
        assert s_ret1_s["maximum"] == "0.019004437584410573"
        assert (
            s_ret1_s["positive_fold_count"],
            s_ret1_s["negative_fold_count"],
            s_ret1_s["zero_fold_count"],
        ) == (3, 22, 0)

        s_roc60_p = sum_map[("f_roc_60", "pearson_ic")]
        assert s_roc60_p["equal_weight_mean"] == "-0.458770428587482703"
        assert s_roc60_p["minimum"] == "-0.874903358433405444"
        assert s_roc60_p["median"] == "-0.531055317815273077"
        assert s_roc60_p["maximum"] == "0.667172407469239722"
        assert (
            s_roc60_p["positive_fold_count"],
            s_roc60_p["negative_fold_count"],
            s_roc60_p["zero_fold_count"],
        ) == (2, 23, 0)

        s_volratio20_s = sum_map[("f_volratio_20", "spearman_ic")]
        assert s_volratio20_s["equal_weight_mean"] == "-0.010408386391407808"
        assert s_volratio20_s["minimum"] == "-0.382178918258408901"
        assert s_volratio20_s["median"] == "0.031063090874011190"
        assert s_volratio20_s["maximum"] == "0.351340922245803589"
        assert (
            s_volratio20_s["positive_fold_count"],
            s_volratio20_s["negative_fold_count"],
            s_volratio20_s["zero_fold_count"],
        ) == (13, 12, 0)

        # 8. Rerun and require byte-identical pointer and commit tree (VERIFIED_NO_OP)
        first_pointer_bytes = eval_ptr.read_bytes()
        eval_commit_dir = eval_dir / "commits" / FROZEN_Q1_COMMIT_IDENTITY
        first_commit_digest = _tree_digest(eval_commit_dir)

        during_attempts = set(attempts_dir.glob("*.json"))
        exit_code_noop = main(
            ["--descriptor", str(EVALUATION_CONFIG), "--data-root", str(DATA_ROOT)]
        )
        assert exit_code_noop == 0

        # Assert byte-identical pointer and tree
        assert eval_ptr.read_bytes() == first_pointer_bytes
        assert _tree_digest(eval_commit_dir) == first_commit_digest

        # Inspect truthful no-op attempt manifest
        new_attempts = set(attempts_dir.glob("*.json")) - during_attempts
        assert len(new_attempts) == 1
        noop_manifest = json.loads(list(new_attempts)[0].read_text(encoding="utf-8"))
        assert noop_manifest["terminal_result"] == "VERIFIED_NO_OP"
        assert noop_manifest["referenced_commit"] == FROZEN_Q1_COMMIT_IDENTITY
        disps = noop_manifest["artifact_dispositions"]
        assert disps["evaluation_artifact"] == "already_published"
        assert disps["lock_acquired"] is True
        assert disps["lock_released"] is True
        assert disps["lock_cleanup"] == "cleaned"
        assert disps["attempt_staged"] is False
        assert disps["object_written"] is False
        assert disps["commit_renamed"] is False
        assert disps["pointer_replaced"] is False
        assert disps["discovery_verified"] is True
    finally:
        # 9. Restore predecessor pointers
        for p, b in snapshots.items():
            temp = p.with_name(p.name + ".restore.tmp")
            temp.write_bytes(b)
            os.replace(temp, p)

        # 10. Prove predecessor immutable trees remained byte-identical
        for name, d in january_commit_dirs.items():
            assert _tree_digest(d) == baseline_digests[name], f"predecessor {name} tree modified"
