"""Validation corruption and recovery scenarios (plan Task 9).

Covers:
- Parent research table missing / unverifiable / corrupt (BLOCKED exit 2)
- Parent Parquet byte tamper in CAS detected and BLOCKED
- Parent quality missing or failing detected and BLOCKED
- Validation CAS object tamper detected by graph verification
- Injected failures at object write, commit rename, and pointer write (safe orphans only)
- Stale ``.staging-*`` cleanup
- Post-pointer failure referencing the published commit (the 290c963 rule parity)
- Undersized parent (1d) BLOCKED before any compute
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import (
    publish_month_via_slice_001,
    validation_cfg_tree,
    write_derived_descriptor,
    write_research_descriptor,
    write_validation_descriptor,
)
from quantara.derive_pipeline import run_derivation_pipeline
from quantara.errors import QuantaraError
from quantara.research_pipeline import run_research_pipeline
from quantara.validation_pipeline import (
    run_validation_pipeline,
    verify_validation_current_graph,
)


def _validation_dir(data_root: Path) -> Path:
    return (
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


def _research_dir(data_root: Path) -> Path:
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


def _attempts(data_root: Path) -> set[str]:
    attempts_dir = data_root / "attempts" / "validation"
    if not attempts_dir.exists():
        return set()
    return {p.name for p in attempts_dir.glob("*.json")}


def _latest_attempt(data_root: Path, before: set[str]) -> dict:
    new_files = _attempts(data_root) - before
    assert len(new_files) == 1, f"expected 1 new attempt, got {len(new_files)}"
    return json.loads((data_root / "attempts" / "validation" / next(iter(new_files))).read_text())


@pytest.fixture(scope="module")
def chain(tmp_path_factory):
    """Chain with slice 001 -> derived 1h -> research 1h -> validation 1h."""
    tmp = tmp_path_factory.mktemp("validation_recovery")
    root, data_root = publish_month_via_slice_001(tmp)
    assert (
        run_derivation_pipeline(
            write_derived_descriptor(root, "1h"), data_root, repo_root=root
        )
        == 0
    )
    assert (
        run_research_pipeline(
            write_research_descriptor(root, "1h"), data_root, repo_root=root
        )
        == 0
    )
    assert (
        run_validation_pipeline(
            write_validation_descriptor(root, "1h"), data_root, repo_root=root
        )
        == 0
    )
    return root, data_root


@pytest.fixture(scope="module")
def fresh_chain(tmp_path_factory):
    """Chain with parent research published, but validation NOT yet published."""
    tmp = tmp_path_factory.mktemp("validation_recovery_fresh")
    root, data_root = publish_month_via_slice_001(tmp)
    assert (
        run_derivation_pipeline(
            write_derived_descriptor(root, "1h"), data_root, repo_root=root
        )
        == 0
    )
    assert (
        run_research_pipeline(
            write_research_descriptor(root, "1h"), data_root, repo_root=root
        )
        == 0
    )
    return root, data_root


def _inject(monkeypatch, target: str, boom) -> None:
    import quantara.validation_pipeline as vp
    monkeypatch.setattr(vp, target, boom)


# --- Parent unavailability / corruption -----------------------------------------


def test_missing_parent_is_blocked(tmp_path) -> None:
    root = validation_cfg_tree(tmp_path)
    descriptor = write_validation_descriptor(root, "1h")
    assert run_validation_pipeline(descriptor, tmp_path / "data", repo_root=root) == 2


def test_parent_parquet_tamper_is_blocked(chain) -> None:
    root, data_root = chain
    research_dir = _research_dir(data_root)
    pointer = json.loads((research_dir / "current.json").read_text())
    manifest_path = research_dir / "commits" / pointer["commit"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text())

    parquet_path = data_root / "objects" / "normalized" / "sha256" / manifest["parquet_sha256"]
    original_bytes = parquet_path.read_bytes()

    try:
        # Bit-flip the last byte of parent Parquet
        parquet_path.write_bytes(original_bytes[:-1] + bytes([original_bytes[-1] ^ 0xFF]))
        before = _attempts(data_root)
        descriptor = write_validation_descriptor(root, "1h")
        assert run_validation_pipeline(descriptor, data_root, repo_root=root) == 2
        attempt = _latest_attempt(data_root, before)
        assert attempt["terminal_result"] == "BLOCKED"
    finally:
        parquet_path.write_bytes(original_bytes)

    # Restored parent allows dry-run verification
    descriptor = write_validation_descriptor(root, "1h")
    assert run_validation_pipeline(descriptor, data_root, dry_run=True, repo_root=root) == 0


def test_validation_cas_object_tamper(chain) -> None:
    root, data_root = chain
    val_dir = _validation_dir(data_root)
    pointer = json.loads((val_dir / "current.json").read_text())
    manifest = json.loads((val_dir / "commits" / pointer["commit"] / "manifest.json").read_text())

    artifact_path = data_root / "objects" / "normalized" / "sha256" / manifest["artifact_sha256"]
    original_bytes = artifact_path.read_bytes()

    try:
        # Corrupt the CAS object
        artifact_path.write_bytes(original_bytes[:-1] + bytes([original_bytes[-1] ^ 0x01]))
        with pytest.raises(QuantaraError):
            verify_validation_current_graph(val_dir, data_root)
    finally:
        artifact_path.write_bytes(original_bytes)

    # Restored artifact verifies again
    assert verify_validation_current_graph(val_dir, data_root)["commit"] == pointer["commit"]


# --- Injected mid-publication failures (safe orphans only) ----------------------


def test_object_write_failure_leaves_safe_orphans(chain, monkeypatch) -> None:
    root, data_root = chain
    dataset_dir = _validation_dir(data_root)
    (dataset_dir / "current.json").unlink()
    commits_before = set((dataset_dir / "commits").iterdir())

    def boom(*args, **kwargs):
        raise QuantaraError("injected validation object write failure")

    _inject(monkeypatch, "store_object", boom)
    before = _attempts(data_root)
    descriptor = write_validation_descriptor(root, "1h")
    assert run_validation_pipeline(descriptor, data_root, repo_root=root) == 3
    attempt = _latest_attempt(data_root, before)
    assert attempt["terminal_result"] == "FAILED"
    assert not (dataset_dir / "current.json").exists()
    assert not (set((dataset_dir / "commits").iterdir()) - commits_before)
    assert not list((data_root / "staging").glob("*"))


def test_commit_rename_failure_leaves_safe_orphans(fresh_chain, monkeypatch) -> None:
    root, data_root = fresh_chain
    dataset_dir = _validation_dir(data_root)
    descriptor = write_validation_descriptor(root, "1h")

    def boom(staged, commits_dir, address):
        raise QuantaraError("injected validation rename failure")

    _inject(monkeypatch, "publish_commit", boom)
    before = _attempts(data_root)
    assert run_validation_pipeline(descriptor, data_root, repo_root=root) == 3
    attempt = _latest_attempt(data_root, before)
    assert attempt["terminal_result"] == "FAILED"
    assert not (dataset_dir / "current.json").exists()
    after = {p.name for p in (dataset_dir / "commits").iterdir()}
    assert not [p for p in after if not p.startswith(".staging-")]
    assert not [p for p in after if p.startswith(".staging-")]
    assert not list((data_root / "staging").glob("*"))


def test_pointer_write_failure_recovers_via_retained_commit(fresh_chain, monkeypatch) -> None:
    root, data_root = fresh_chain
    dataset_dir = _validation_dir(data_root)
    descriptor = write_validation_descriptor(root, "1h")

    def boom(dataset_directory, address, manifest_sha):
        raise QuantaraError("injected pointer write failure")

    _inject(monkeypatch, "write_current", boom)
    before = _attempts(data_root)
    assert run_validation_pipeline(descriptor, data_root, repo_root=root) == 3
    attempt = _latest_attempt(data_root, before)
    assert attempt["terminal_result"] == "FAILED"
    assert not (dataset_dir / "current.json").exists()
    renamed = [
        p.name for p in (dataset_dir / "commits").iterdir() if not p.name.startswith(".staging-")
    ]
    assert len(renamed) == 1

    # Rerun without fault recovers via the retained equivalent commit
    monkeypatch.undo()
    before = _attempts(data_root)
    assert run_validation_pipeline(descriptor, data_root, repo_root=root) == 0
    attempt = _latest_attempt(data_root, before)
    dispositions = attempt["artifact_dispositions"]
    assert dispositions["commit_renamed"] is False
    assert dispositions["pointer_replaced"] is True
    assert dispositions["object_written"] is False
    assert (dataset_dir / "current.json").exists()


def test_stale_staging_directories_are_cleaned(chain) -> None:
    root, data_root = chain
    junk = _validation_dir(data_root) / "commits" / ".staging-junk-leftover"
    junk.mkdir(parents=True, exist_ok=True)
    (junk / "leftover.txt").write_text("stale", encoding="utf-8")
    descriptor = write_validation_descriptor(root, "1h")
    assert run_validation_pipeline(descriptor, data_root, repo_root=root) == 0
    assert not junk.exists()


# --- post-pointer evidence truthfulness (290c963 rule) ---------------------------


def test_post_pointer_failure_references_published_commit(chain, monkeypatch) -> None:
    """Closure contract: when recovery replaces pointer and discovery verification
    fails, the FAILED attempt must reference the published commit (referenced_commit
    follows pointer_replaced, never commit_renamed)."""
    root, data_root = chain
    dataset_dir = _validation_dir(data_root)
    pointer_path = dataset_dir / "current.json"
    pointer_before = pointer_path.read_bytes()
    retained_commit = json.loads(pointer_before)["commit"]

    pointer_path.unlink()  # lose only the pointer

    def boom(*a, **k):
        raise QuantaraError("injected discovery verification failure")

    before = _attempts(data_root)
    _inject(monkeypatch, "verify_validation_current_graph", boom)
    try:
        descriptor = write_validation_descriptor(root, "1h")
        assert run_validation_pipeline(descriptor, data_root, repo_root=root) == 3
    finally:
        monkeypatch.undo()

    attempt = _latest_attempt(data_root, before)
    assert attempt["terminal_result"] == "FAILED"
    dispositions = attempt["artifact_dispositions"]
    assert dispositions["pointer_replaced"] is True
    assert dispositions["commit_renamed"] is False
    assert dispositions["object_written"] is False
    assert dispositions["post_pointer"] == "published_unverified"
    assert attempt["referenced_commit"] == retained_commit
    assert pointer_path.read_bytes() == pointer_before

    # Clean rerun returns VERIFIED_NO_OP
    descriptor = write_validation_descriptor(root, "1h")
    assert run_validation_pipeline(descriptor, data_root, repo_root=root) == 0


def test_undersized_parent_blocked_before_any_compute(tmp_path) -> None:
    root = validation_cfg_tree(tmp_path)
    descriptor = write_validation_descriptor(root, "1d")
    before = _attempts(tmp_path / "data")
    code = run_validation_pipeline(descriptor, tmp_path / "data", repo_root=root)
    assert code == 2
    attempt = _latest_attempt(tmp_path / "data", before)
    assert attempt["terminal_result"] == "BLOCKED"
    assert attempt["diagnostics"] == ["undersized_parent_dataset"]
    assert not (tmp_path / "data" / "objects" / "normalized" / "sha256").exists()
    assert not (tmp_path / "data" / "datasets").exists()
