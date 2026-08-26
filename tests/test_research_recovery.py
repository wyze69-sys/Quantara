"""Research corruption and recovery scenarios (plan Task 9).

Parent missing / unverifiable / corrupt; injected failures at object write,
commit rename, and pointer write (safe orphans only); stale ``.staging-*``
cleanup; legitimate parent republication yielding a new lineage-bound commit
while the old research commit stays immutable; undersized base BLOCKED before
any compute.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from conftest import (
    publish_month_via_slice_001,
    research_cfg_tree,
    write_derived_descriptor,
    write_research_descriptor,
)
from quantara.derive_pipeline import run_derivation_pipeline
from quantara.errors import QuantaraError
from quantara.research_pipeline import run_research_pipeline


def _research_dir(data_root):
    return (
        data_root
        / "datasets"
        / "binance"
        / "usdm"
        / "research"
        / "BTCUSDT"
        / "1h"
        / "year=2024"
        / "month=01"
    )


def _klines_dir(data_root, interval="1h"):
    return (
        data_root
        / "datasets"
        / "binance"
        / "usdm"
        / "klines"
        / "BTCUSDT"
        / interval
        / "year=2024"
        / "month=01"
    )


def _attempts(data_root):
    return {p.name for p in (data_root / "attempts").glob("*.json")}


def _latest_attempt(data_root, before):
    (name,) = _attempts(data_root) - before
    return json.loads((data_root / "attempts" / name).read_text())


@pytest.fixture(scope="module")
def chain(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("research_recovery")
    root, data_root = publish_month_via_slice_001(tmp)
    assert (
        run_derivation_pipeline(write_derived_descriptor(root, "1h"), data_root, repo_root=root)
        == 0
    )
    assert (
        run_research_pipeline(write_research_descriptor(root, "1h"), data_root, repo_root=root) == 0
    )
    return root, data_root


@pytest.fixture(scope="module")
def fresh_chain(tmp_path_factory):
    """A derived parent WITHOUT any prior research publication, so an
    injected mid-publication fault cannot be absorbed by the retained-
    equivalent recovery path."""
    tmp = tmp_path_factory.mktemp("research_recovery_fresh")
    root, data_root = publish_month_via_slice_001(tmp)
    assert (
        run_derivation_pipeline(write_derived_descriptor(root, "1h"), data_root, repo_root=root)
        == 0
    )
    return root, data_root


def _tree_digest(directory: Path) -> dict[str, str]:
    snapshot = {}
    for path in sorted(directory.rglob("*")):
        rel = path.relative_to(directory).as_posix()
        snapshot[rel] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "<dir>"
    return snapshot


# --- parent unavailability ------------------------------------------------------


def test_missing_parent_is_blocked(tmp_path) -> None:
    root = research_cfg_tree(tmp_path)
    descriptor = write_research_descriptor(root, "1h")
    assert run_research_pipeline(descriptor, tmp_path / "data", repo_root=root) == 2


def test_corrupt_parent_object_is_blocked(chain, monkeypatch) -> None:
    root, data_root = chain
    pointer = json.loads((_klines_dir(data_root) / "current.json").read_text())
    commit_dir = _klines_dir(data_root) / "commits" / pointer["commit"]
    manifest = json.loads((commit_dir / "manifest.json").read_text())
    object_path = data_root / "objects" / "normalized" / "sha256" / manifest["parquet_sha256"]
    original = object_path.read_bytes()
    try:
        object_path.write_bytes(original[:-1] + bytes([original[-1] ^ 0xFF]))
        before = _attempts(data_root)
        descriptor = write_research_descriptor(root, "1h")
        assert run_research_pipeline(descriptor, data_root, repo_root=root) == 2
        attempt = _latest_attempt(data_root, before)
        assert attempt["terminal_result"] == "BLOCKED"
    finally:
        object_path.write_bytes(original)
    # Restored parent verifies again.
    descriptor = write_research_descriptor(root, "1h")
    assert run_research_pipeline(descriptor, data_root, repo_root=root, dry_run=True) == 0


# --- injected failures: safe orphans only ----------------------------------------


def _inject(monkeypatch, target, boom):
    import quantara.research_pipeline as rp

    monkeypatch.setattr(rp, target, boom)


def test_object_write_failure_leaves_safe_orphans(chain, monkeypatch) -> None:
    root, data_root = chain
    dataset_dir = _research_dir(data_root)
    # A lost pointer forces the full publication path instead of the NO_OP
    # short-circuit, so the injection lands mid-publication.
    (dataset_dir / "current.json").unlink()
    commits_before = set((dataset_dir / "commits").iterdir())

    def boom(*args, **kwargs):
        raise QuantaraError("injected object write failure")

    _inject(monkeypatch, "store_object", boom)
    before = _attempts(data_root)
    descriptor = write_research_descriptor(root, "1h")
    assert run_research_pipeline(descriptor, data_root, repo_root=root) == 3
    attempt = _latest_attempt(data_root, before)
    assert attempt["terminal_result"] == "FAILED"
    assert attempt["diagnostics"] == ["quantara_error"]
    # Pointer still absent; no new commit dirs; no staging residue anywhere.
    assert not (dataset_dir / "current.json").exists()
    assert not set((dataset_dir / "commits").iterdir()) - commits_before
    assert not list((data_root / "staging").glob("*"))


def test_commit_rename_failure_leaves_safe_orphans(fresh_chain, monkeypatch) -> None:
    root, data_root = fresh_chain
    dataset_dir = _research_dir(data_root)
    descriptor = write_research_descriptor(root, "1h")

    def boom(staged, commits_dir, address):
        raise QuantaraError("injected rename failure")

    _inject(monkeypatch, "publish_commit", boom)
    before = _attempts(data_root)
    assert run_research_pipeline(descriptor, data_root, repo_root=root) == 3
    attempt = _latest_attempt(data_root, before)
    assert attempt["terminal_result"] == "FAILED"
    assert not (dataset_dir / "current.json").exists()
    after = {p.name for p in (dataset_dir / "commits").iterdir()}
    # No partial commit promoted; staged residue fully cleaned.
    assert not [p for p in after if not p.startswith(".staging-")]
    assert not [p for p in after if p.startswith(".staging-")]
    assert not list((data_root / "staging").glob("*"))


def test_pointer_write_failure_keeps_old_pointer(fresh_chain, monkeypatch) -> None:
    root, data_root = fresh_chain
    dataset_dir = _research_dir(data_root)
    descriptor = write_research_descriptor(root, "1h")

    def boom(dataset_directory, address, manifest_sha):
        raise QuantaraError("injected pointer write failure")

    _inject(monkeypatch, "write_current", boom)
    before = _attempts(data_root)
    assert run_research_pipeline(descriptor, data_root, repo_root=root) == 3
    attempt = _latest_attempt(data_root, before)
    assert attempt["terminal_result"] == "FAILED"
    # The renamed commit exists but the pointer was NOT written by this
    # failing invocation.
    assert not (dataset_dir / "current.json").exists()
    renamed = [
        p.name for p in (dataset_dir / "commits").iterdir() if not p.name.startswith(".staging-")
    ]
    assert len(renamed) == 1
    # Without the injected fault the same rerun recovers via the retained
    # equivalent commit (commit_renamed=False, pointer replaced).
    monkeypatch.undo()
    before = _attempts(data_root)
    assert run_research_pipeline(descriptor, data_root, repo_root=root) == 0
    attempt = _latest_attempt(data_root, before)
    dispositions = attempt["artifact_dispositions"]
    assert dispositions["commit_renamed"] is False
    assert dispositions["pointer_replaced"] is True
    assert dispositions["object_written"] is False
    assert (dataset_dir / "current.json").exists()


def test_stale_staging_directories_are_cleaned(chain) -> None:
    root, data_root = chain
    junk = _research_dir(data_root) / "commits" / ".staging-junk-leftover"
    junk.mkdir(parents=True, exist_ok=True)
    (junk / "leftover.txt").write_text("stale", encoding="utf-8")
    descriptor = write_research_descriptor(root, "1h")
    assert run_research_pipeline(descriptor, data_root, repo_root=root) == 0
    assert not junk.exists()


def test_parent_republication_binds_new_lineage_keeps_old_immutable(
    tmp_path_factory,
) -> None:
    tmp = tmp_path_factory.mktemp("research_reparent")
    root, data_root = publish_month_via_slice_001(tmp)
    derived = write_derived_descriptor(root, "1h")
    research_descriptor = write_research_descriptor(root, "1h")
    assert run_derivation_pipeline(derived, data_root, repo_root=root) == 0
    assert run_research_pipeline(research_descriptor, data_root, repo_root=root) == 0

    dataset_dir = _research_dir(data_root)
    old_pointer = json.loads((dataset_dir / "current.json").read_text())
    old_commit_digest = _tree_digest(dataset_dir / "commits" / old_pointer["commit"])

    # Legitimate parent correction flows through the real pipelines.
    publish_month_via_slice_001(tmp, price_offset=17)
    assert run_derivation_pipeline(derived, data_root, repo_root=root) == 0
    new_parent_pointer = json.loads((_klines_dir(data_root) / "current.json").read_text())
    assert new_parent_pointer["commit"] != old_pointer["commit"]
    assert run_research_pipeline(research_descriptor, data_root, repo_root=root) == 0

    new_pointer = json.loads((dataset_dir / "current.json").read_text())
    assert new_pointer["commit"] != old_pointer["commit"]
    content = json.loads(
        (dataset_dir / "commits" / new_pointer["commit"] / "content.json").read_text()
    )
    lineage = content["research_from"]
    assert lineage["base_commit_address"] == new_parent_pointer["commit"]

    # The old research commit remains byte-identical and discoverable.
    assert _tree_digest(dataset_dir / "commits" / old_pointer["commit"]) == old_commit_digest


def test_undersized_base_blocked_before_any_compute(tmp_path) -> None:
    root = research_cfg_tree(tmp_path)
    descriptor = write_research_descriptor(root, "1d")
    before = _attempts(tmp_path / "data")
    code = run_research_pipeline(descriptor, tmp_path / "data", repo_root=root)
    assert code == 2
    attempt = _latest_attempt(tmp_path / "data", before)
    assert attempt["terminal_result"] == "BLOCKED"
    assert attempt["diagnostics"] == ["undersized_base_dataset"]
    # Pre-compute: no objects, no datasets, no staging residue.
    assert not (tmp_path / "data" / "objects" / "normalized" / "sha256").exists()
    assert not (tmp_path / "data" / "datasets").exists()
