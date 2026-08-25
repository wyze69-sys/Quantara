"""Derivation corruption and recovery scenarios (plan Task 9).

Each scenario asserts hard stops with stable diagnostics and no discoverable
partial graph, or the documented recovery behavior, mirroring slice 001
recovery semantics.
"""

from __future__ import annotations

import json
from pathlib import Path

from conftest import (
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
from quantara.hashing import schema_fingerprint, sha256_hex
from quantara.publication import (
    publish_commit,
    put_object,
    stage_commit,
    write_current,
)

DAY_MS = 86_400_000


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


def _publish_parent(rows, tmp_path: Path, content_hash: str = "p" * 64):
    """Assemble a complete verified parent graph through publication primitives."""
    root = derived_cfg_tree(tmp_path)
    data_root = tmp_path / "data"
    staging = data_root / "staging" / "parent-build"
    staging.mkdir(parents=True, exist_ok=True)
    parquet_path = staging / "canonical.parquet"
    write_canonical_parquet(rows, parquet_path)
    persisted = read_canonical_rows(parquet_path)
    reconcile_rows(rows, persisted)
    parquet_bytes = parquet_path.read_bytes()
    parquet_sha = sha256_hex(parquet_bytes)
    normalized_ref = put_object(data_root, "normalized", parquet_bytes)
    content = {
        "descriptor_sha256": "d" * 64,
        "schema_fingerprint": schema_fingerprint(),
        "parser_version": "binance_kline_csv_v1",
        "canonical_content_hash": content_hash,
        "quality_identity": "q",
        "object_refs": [{"kind": "normalized", "sha256": normalized_ref}],
    }
    manifest = {"parquet_sha256": parquet_sha, "parquet_size": len(parquet_bytes)}
    staged = stage_commit(_parent_dir(data_root), "pb", {
        "content.json": (json.dumps(content) + "\n").encode(),
        "manifest.json": (json.dumps(manifest) + "\n").encode(),
    })
    publish_commit(staged, _parent_dir(data_root) / "commits", content_hash)
    write_current(_parent_dir(data_root), content_hash, "m" * 64)
    return root, data_root, parquet_sha


def _valid_parent(tmp_path: Path):
    return _publish_parent(build_month_minute_rows(), tmp_path)


def _assert_blocked_with(root, data_root, diagnostic, tmp_path: Path):
    descriptor = write_derived_descriptor(root, "1h")
    code = run_derivation_pipeline(descriptor, data_root, repo_root=root)
    assert code == 2
    attempts = list((data_root / "attempts").glob("*.json"))
    diagnostics = [
        json.loads(p.read_text())["diagnostics"] for p in attempts
    ]
    assert diagnostics == [[diagnostic]]


def test_missing_parent_current_json_blocks(tmp_path: Path) -> None:
    root, data_root, _ = _valid_parent(tmp_path)
    (_parent_dir(data_root) / "current.json").unlink()
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable", tmp_path)
    assert not _derived_dir(data_root).exists()


def test_invalid_parent_current_json_blocks(tmp_path: Path) -> None:
    root, data_root, _ = _valid_parent(tmp_path)
    (_parent_dir(data_root) / "current.json").write_text("{not json", encoding="utf-8")
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable", tmp_path)


def test_parent_object_drift_blocks_before_compute(tmp_path: Path) -> None:
    root, data_root, parquet_sha = _valid_parent(tmp_path)
    obj = data_root / "objects" / "normalized" / "sha256" / parquet_sha
    obj.write_bytes(b"tampered")  # drift the committed bytes
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable", tmp_path)
    # Nothing was computed or published for the derived dataset.
    assert not _derived_dir(data_root).exists()


def test_incomplete_parent_commit_graph_blocks(tmp_path: Path) -> None:
    root, data_root, _ = _valid_parent(tmp_path)
    commit = json.loads(
        (_parent_dir(data_root) / "current.json").read_text()
    )["commit"]
    (_parent_dir(data_root) / "commits" / commit / "COMMITTED").unlink()
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable", tmp_path)


def test_derived_pointer_to_missing_commit_recovers(tmp_path: Path) -> None:
    root, data_root, _ = _valid_parent(tmp_path)
    descriptor = write_derived_descriptor(root, "1h")
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    derived = _derived_dir(data_root)

    # Simulate pointer loss / dangling pointer: point at a missing commit.
    write_current(derived, "f" * 64, "m" * 64)
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    restored = json.loads((derived / "current.json").read_text())["commit"]
    assert (derived / "commits" / restored).is_dir()
    # Discovery verification passes and the graph holds exactly one commit.
    commits = [p for p in (derived / "commits").iterdir()
               if not p.name.startswith(".")]
    assert len(commits) == 1
    assert restored == commits[0].name


def test_pointer_loss_never_creates_partial_graph(tmp_path: Path) -> None:
    root, data_root, _ = _valid_parent(tmp_path)
    descriptor = write_derived_descriptor(root, "1h")
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    derived = _derived_dir(data_root)
    commit = json.loads((derived / "current.json").read_text())["commit"]

    # Injected failure after object write + commit rename but BEFORE the
    # pointer replacement: safe orphan, never canonical.
    (derived / "current.json").unlink()
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    assert json.loads((derived / "current.json").read_text())["commit"] == commit
    commits = sorted(p.name for p in (derived / "commits").iterdir()
                     if not p.name.startswith("."))
    assert commits == [commit]


def test_stale_staging_is_discarded(tmp_path: Path) -> None:
    root, data_root, _ = _valid_parent(tmp_path)
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
    root, data_root, _ = _publish_parent(rows, tmp_path)
    descriptor = write_derived_descriptor(root, "1h")
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    derived = _derived_dir(data_root)
    old_pointer = (derived / "current.json").read_bytes()
    old_commit = json.loads(old_pointer)["commit"]
    old_files = {
        p.relative_to(derived).as_posix(): sha256_hex(p.read_bytes())
        for p in derived.rglob("*") if p.is_file()
    }

    # Parent legitimately republished with different content.
    changed = list(rows)
    victim = changed[10]
    changed[10] = make_minute_row(
        victim.open_time_ms,
        o="42571.90", h="42600.00", lo="42500.10", c="99999.99",
        bv=victim.base_asset_volume, qv=victim.quote_asset_volume,
        n=3210, tbv=victim.taker_buy_base_volume,
        tqv=victim.taker_buy_quote_volume,
    )
    staging = data_root / "staging" / "repub"
    staging.mkdir(parents=True, exist_ok=True)
    parquet2 = staging / "canonical.parquet"
    write_canonical_parquet(changed, parquet2)
    parquet_bytes = parquet2.read_bytes()
    new_sha = sha256_hex(parquet_bytes)
    normalized_ref = put_object(data_root, "normalized", parquet_bytes)
    content = {
        "descriptor_sha256": "e" * 64,
        "schema_fingerprint": schema_fingerprint(),
        "parser_version": "binance_kline_csv_v1",
        "canonical_content_hash": "q" * 64,
        "quality_identity": "q2",
        "object_refs": [{"kind": "normalized", "sha256": normalized_ref}],
    }
    manifest = {"parquet_sha256": new_sha, "parquet_size": len(parquet_bytes)}
    staged = stage_commit(_parent_dir(data_root), "repub", {
        "content.json": (json.dumps(content) + "\n").encode(),
        "manifest.json": (json.dumps(manifest) + "\n").encode(),
    })
    publish_commit(staged, _parent_dir(data_root) / "commits", "q" * 64)
    write_current(_parent_dir(data_root), "q" * 64, "mm" * 32)

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
    current_files = {
        p.relative_to(derived).as_posix(): sha256_hex(p.read_bytes())
        for p in derived.rglob("*") if p.is_file()
        and old_commit in p.as_posix()
    }
    for rel, digest in old_files.items():
        if old_commit in f"/{rel}":
            assert current_files.get(rel) == digest
    commits = [p.name for p in (derived / "commits").iterdir()
               if not p.name.startswith(".")]
    assert sorted(commits) == sorted({old_commit, new_commit})

