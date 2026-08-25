"""Derivation corruption and recovery scenarios (plan Task 9, correction 2).

Every fixture assembles a fully genuine parent graph — real descriptor hash,
real schema fingerprint, real canonical-content hash, real manifest digest —
through the publication primitives. Fabricated hashes are never accepted, by
the tests or by the production verifier. Each scenario asserts hard stops with
stable diagnostics and no discoverable partial graph, or documented recovery.
"""

from __future__ import annotations

import json
from pathlib import Path

from conftest import (
    BASE_DESCRIPTOR_NAME,
    build_month_minute_rows,
    derived_cfg_tree,
    make_minute_row,
    write_derived_descriptor,
)
from quantara.canonical import (
    read_canonical_rows,
    reconcile_rows,
    write_canonical_parquet,
)
from quantara.derive_pipeline import run_derivation_pipeline
from quantara.descriptor import load_descriptor
from quantara.hashing import (
    canonical_content_hash,
    descriptor_hash,
    schema_fingerprint,
    sha256_hex,
)
from quantara.manifests import PARSER_VERSION
from quantara.publication import (
    publish_commit,
    put_object,
    stage_commit,
    write_current,
)


def _parent_dir(data_root: Path) -> Path:
    return (
        data_root / "datasets" / "binance" / "usdm" / "klines" / "BTCUSDT"
        / "1m" / "year=2024" / "month=01"
    )


def _derived_dir(data_root: Path, interval: str = "1h") -> Path:
    return (
        data_root / "datasets" / "binance" / "usdm" / "klines" / "BTCUSDT"
        / interval / "year=2024" / "month=01"
    )


def _write_parent_commit(root: Path, data_root: Path, rows, tag: str) -> tuple:
    """Publish one genuine parent commit; returns (parquet_sha, content_hash)."""
    staging = data_root / "staging" / f"parent-build-{tag}"
    staging.mkdir(parents=True, exist_ok=True)
    parquet_path = staging / "canonical.parquet"
    write_canonical_parquet(rows, parquet_path)
    persisted = read_canonical_rows(parquet_path)
    reconcile_rows(rows, persisted)
    parquet_bytes = parquet_path.read_bytes()
    parquet_sha = sha256_hex(parquet_bytes)

    base = load_descriptor(root / "configs" / "datasets" / BASE_DESCRIPTOR_NAME)
    fingerprint = schema_fingerprint(base.schema_version)
    content_hash_value = canonical_content_hash(
        fingerprint, [row.to_content_array() for row in rows]
    )
    put_object(data_root, "normalized", parquet_bytes)

    manifest = {
        "dataset_id": base.dataset_id,
        "instrument_id": base.instrument_id,
        "schema_version": base.schema_version,
        "schema_fingerprint": fingerprint,
        "timestamp_semantics": base.timestamp_semantics,
        "quality_policy_version": "1",
        "quality_state": "PASS",
        "source_row_count": len(rows),
        "canonical_row_count": len(rows),
        "canonical_content_hash": content_hash_value,
        "parquet_sha256": parquet_sha,
        "parquet_size": len(parquet_bytes),
        "object_refs": [{"kind": "normalized", "sha256": parquet_sha}],
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    content = {
        "descriptor_sha256": descriptor_hash(base.canonical_semantics()),
        "schema_fingerprint": fingerprint,
        "parser_version": PARSER_VERSION,
        "canonical_content_hash": content_hash_value,
        "quality_identity": "q-" + tag,
        "object_refs": [{"kind": "normalized", "sha256": parquet_sha}],
    }
    staged = stage_commit(_parent_dir(data_root), tag, {
        "content.json": (json.dumps(content) + "\n").encode(),
        "manifest.json": manifest_bytes,
    })
    publish_commit(staged, _parent_dir(data_root) / "commits", content_hash_value)
    write_current(
        _parent_dir(data_root), content_hash_value, sha256_hex(manifest_bytes)
    )
    return parquet_sha, content_hash_value


def _setup(tmp_path: Path):
    root = derived_cfg_tree(tmp_path)
    return root, tmp_path / "data"


def _publish_parent(rows, tmp_path: Path):
    root, data_root = _setup(tmp_path)
    parquet_sha, content_hash_value = _write_parent_commit(
        root, data_root, rows, "initial"
    )
    return root, data_root, parquet_sha, content_hash_value


def _valid_parent(tmp_path: Path):
    return _publish_parent(build_month_minute_rows(), tmp_path)


def _assert_blocked_with(root, data_root, diagnostic):
    descriptor = write_derived_descriptor(root, "1h")
    code = run_derivation_pipeline(descriptor, data_root, repo_root=root)
    assert code == 2
    attempts = list((data_root / "attempts").glob("*.json"))
    diagnostics = [json.loads(p.read_text())["diagnostics"] for p in attempts]
    assert diagnostics == [[diagnostic]]


# --- baseline rejection scenarios (retained from plan Task 9) -----------------


def test_missing_parent_current_json_blocks(tmp_path: Path) -> None:
    root, data_root, *_ = _valid_parent(tmp_path)
    (_parent_dir(data_root) / "current.json").unlink()
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")
    assert not _derived_dir(data_root).exists()


def test_invalid_parent_current_json_blocks(tmp_path: Path) -> None:
    root, data_root, *_ = _valid_parent(tmp_path)
    (_parent_dir(data_root) / "current.json").write_text(
        "{not json", encoding="utf-8"
    )
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")


def test_parent_object_drift_blocks_before_compute(tmp_path: Path) -> None:
    root, data_root, parquet_sha, *_ = _valid_parent(tmp_path)
    obj = data_root / "objects" / "normalized" / "sha256" / parquet_sha
    obj.write_bytes(b"tampered")  # drift the committed bytes
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")
    assert not _derived_dir(data_root).exists()


def test_incomplete_parent_commit_graph_blocks(tmp_path: Path) -> None:
    root, data_root, *_ = _valid_parent(tmp_path)
    commit = json.loads((_parent_dir(data_root) / "current.json").read_text())[
        "commit"
    ]
    (_parent_dir(data_root) / "commits" / commit / "COMMITTED").unlink()
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")


# --- correction 2 helpers ------------------------------------------------------


def _rewrite_manifest_consistently(data_root: Path, mutate) -> None:
    """Tamper the manifest and keep pointer digest consistent so ONLY the
    semantic check under test can reject the graph."""
    commit = json.loads((_parent_dir(data_root) / "current.json").read_text())[
        "commit"
    ]
    manifest_path = _parent_dir(data_root) / "commits" / commit / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    mutate(manifest)
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    manifest_path.write_bytes(manifest_bytes)
    pointer_path = _parent_dir(data_root) / "current.json"
    pointer = json.loads(pointer_path.read_text())
    pointer["manifest_sha256"] = sha256_hex(manifest_bytes)
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")


def _pointer_commit(data_root: Path) -> str:
    return json.loads((_parent_dir(data_root) / "current.json").read_text())[
        "commit"
    ]



# --- correction 2: fabricated or inconsistent evidence must block -------------


def test_malformed_pointer_structure_blocks(tmp_path: Path) -> None:
    root, data_root, *_ = _valid_parent(tmp_path)
    pointer_path = _parent_dir(data_root) / "current.json"
    pointer = json.loads(pointer_path.read_text())
    del pointer["manifest_sha256"]  # structurally incomplete pointer
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")


def test_wrong_pointer_protocol_version_blocks(tmp_path: Path) -> None:
    root, data_root, *_ = _valid_parent(tmp_path)
    pointer_path = _parent_dir(data_root) / "current.json"
    pointer = json.loads(pointer_path.read_text())
    pointer["publication_protocol_version"] = "v0"
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")


def test_manifest_digest_mismatch_blocks(tmp_path: Path) -> None:
    """manifest.json tampered after publication: current.json pins the digest."""
    root, data_root, *_ = _valid_parent(tmp_path)
    manifest_path = (
        _parent_dir(data_root) / "commits" / _pointer_commit(data_root)
        / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text())
    manifest["source_row_count"] = 1  # tamper
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")


def test_missing_required_manifest_field_blocks(tmp_path: Path) -> None:
    def drop_parquet_sha(manifest):
        del manifest["parquet_sha256"]

    root, data_root, *_ = _valid_parent(tmp_path)
    _rewrite_manifest_consistently(data_root, drop_parquet_sha)
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")


def test_parquet_size_mismatch_blocks(tmp_path: Path) -> None:
    def shrink_size(manifest):
        manifest["parquet_size"] -= 1

    root, data_root, *_ = _valid_parent(tmp_path)
    _rewrite_manifest_consistently(data_root, shrink_size)
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")



def test_canonical_content_identity_mismatch_blocks(tmp_path: Path) -> None:
    """content.json identity disagrees with the commit directory name: a
    fabricated graph object hashing alone cannot detect."""
    root, data_root, *_ = _valid_parent(tmp_path)
    content_path = (
        _parent_dir(data_root) / "commits" / _pointer_commit(data_root)
        / "content.json"
    )
    content = json.loads(content_path.read_text())
    content["canonical_content_hash"] = "a" * 64
    content_path.write_text(json.dumps(content) + "\n", encoding="utf-8")
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")


def test_committed_schema_evidence_mismatch_blocks(tmp_path: Path) -> None:
    """Manifest evidence internally consistent but contradicting the approved
    loaded base descriptor must be rejected."""
    def swap_schema(manifest):
        manifest["schema_version"] = "binance_usdm_kline_5m_v1"

    root, data_root, *_ = _valid_parent(tmp_path)
    _rewrite_manifest_consistently(data_root, swap_schema)
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")


def test_parent_quality_not_pass_blocks(tmp_path: Path) -> None:
    def degrade_quality(manifest):
        manifest["quality_state"] = "WARN_BLOCKED"

    root, data_root, *_ = _valid_parent(tmp_path)
    _rewrite_manifest_consistently(data_root, degrade_quality)
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")



# --- recovery behavior (retained from plan Task 9) -----------------------------


def test_derived_pointer_to_missing_commit_recovers(tmp_path: Path) -> None:
    root, data_root, *_ = _valid_parent(tmp_path)
    descriptor = write_derived_descriptor(root, "1h")
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    derived = _derived_dir(data_root)

    write_current(derived, "f" * 64, "m" * 64)  # dangling pointer
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    restored = json.loads((derived / "current.json").read_text())["commit"]
    assert (derived / "commits" / restored).is_dir()
    commits = [
        p for p in (derived / "commits").iterdir() if not p.name.startswith(".")
    ]
    assert len(commits) == 1
    assert restored == commits[0].name


def test_pointer_loss_never_creates_partial_graph(tmp_path: Path) -> None:
    root, data_root, *_ = _valid_parent(tmp_path)
    descriptor = write_derived_descriptor(root, "1h")
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    derived = _derived_dir(data_root)
    commit = json.loads((derived / "current.json").read_text())["commit"]

    # Failure after object write + commit rename but BEFORE pointer
    # replacement: safe orphan, never canonical.
    (derived / "current.json").unlink()
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    assert json.loads((derived / "current.json").read_text())["commit"] == commit
    commits = sorted(
        p.name for p in (derived / "commits").iterdir()
        if not p.name.startswith(".")
    )
    assert commits == [commit]


def test_stale_staging_is_discarded(tmp_path: Path) -> None:
    root, data_root, *_ = _valid_parent(tmp_path)
    derived = _derived_dir(data_root)
    stale = derived / "commits" / ".staging-stale-attempt"
    stale.mkdir(parents=True)
    (stale / "junk.bin").write_bytes(b"0")
    descriptor = write_derived_descriptor(root, "1h")
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    assert not list((derived / "commits").glob(".staging-*"))



def test_parent_republished_derived_rerun_publishes_new_lineage_commit(
    tmp_path: Path,
) -> None:
    rows = build_month_minute_rows()
    root, data_root = _setup(tmp_path)
    _, old_parent_cch = _write_parent_commit(root, data_root, rows, "gen1")
    descriptor = write_derived_descriptor(root, "1h")
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    derived = _derived_dir(data_root)
    old_pointer = (derived / "current.json").read_bytes()
    old_commit = json.loads(old_pointer)["commit"]
    old_files = {
        p.relative_to(derived).as_posix(): sha256_hex(p.read_bytes())
        for p in derived.rglob("*") if p.is_file()
    }

    # Parent legitimately republished with different content: fully genuine
    # second commit (changed close changes the affected hourly aggregates).
    changed = list(rows)
    victim = changed[10]
    changed[10] = make_minute_row(
        victim.open_time_ms,
        o="42571.90", h="42600.00", lo="42500.10", c="99999.99",
        bv=victim.base_asset_volume, qv=victim.quote_asset_volume,
        n=3210, tbv=victim.taker_buy_base_volume,
        tqv=victim.taker_buy_quote_volume,
    )
    new_sha, new_cch = _write_parent_commit(root, data_root, changed, "repub")
    assert new_cch != old_parent_cch

    # Derived rerun publishes a NEW lineage-bound commit.
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    new_pointer = (derived / "current.json").read_bytes()
    new_commit = json.loads(new_pointer)["commit"]
    assert new_commit != old_commit
    new_content = json.loads(
        (derived / "commits" / new_commit / "content.json").read_text()
    )
    assert new_content["derived_from"]["parent_parquet_sha256"] == new_sha

    # The old derived commit stays byte-identical (immutable history).
    for rel, digest in old_files.items():
        path = derived / rel
        if old_commit in path.as_posix():
            assert sha256_hex(path.read_bytes()) == digest
    commits = [
        p.name for p in (derived / "commits").iterdir()
        if not p.name.startswith(".")
    ]
    assert sorted(commits) == sorted({old_commit, new_commit})

