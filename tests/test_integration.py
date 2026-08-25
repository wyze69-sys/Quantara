"""Real-artifact integration: official January 2024 archive acceptance.

Networked and separately marked; invoked explicitly with ``uv run pytest -m
integration``. Phase order per plan Task 13: structural probe FIRST, then
end-to-end PUBLISHED, then VERIFIED_NO_OP rerun, then cross-run stability,
then proof that /data/ stays outside Git.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from quantara.acquisition import Acquirer
from quantara.archive import inspect_zip, read_member_bytes
from quantara.descriptor import load_descriptor
from quantara.hashing import sha256_hex
from quantara.manifests import attempt_id_now
from quantara.parsing import decode_member, parse_rows
from quantara.pipeline import run_pipeline
from quantara.publication import read_and_verify_current

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[1]
DESCRIPTOR_PATH = REPO_ROOT / "configs/datasets/binance-usdm-btcusdt-1m-2024-01.yaml"
DATA_ROOT = REPO_ROOT / "data"


def _dataset_dir() -> Path:
    return (
        DATA_ROOT / "datasets" / "binance" / "usdm" / "klines"
        / "BTCUSDT" / "1m" / "year=2024" / "month=01"
    )


def _commit_dir() -> Path:
    pointer = json.loads(
        (_dataset_dir() / "current.json").read_text(encoding="utf-8")
    )
    return _dataset_dir() / "commits" / pointer["commit"]


def _tree_digest(directory: Path) -> str:
    hasher = hashlib.sha256()
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        hasher.update(str(path.relative_to(directory)).encode())
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


def test_official_january_2024_archive_end_to_end() -> None:
    descriptor = load_descriptor(DESCRIPTOR_PATH)

    # ------------------------------------------------------------------
    # Phase 1: structural probe FIRST (plan Task 13 step 1).
    # ------------------------------------------------------------------
    acquirer = Acquirer(descriptor, DATA_ROOT, attempt_id_now())
    evidence = acquirer.acquire()
    spec = inspect_zip(evidence.zip_path, descriptor.member_pattern)
    member_text = decode_member(read_member_bytes(evidence.zip_path, spec))
    source_rows = parse_rows(member_text, descriptor)

    row_count = len(source_rows)
    zero_volume_count = sum(
        1
        for r in source_rows
        if r.base_asset_volume == 0 and r.quote_asset_volume == 0
    )
    nonzero_ignore_count = sum(1 for r in source_rows if r.source_ignore != "0")
    times = [r.open_time for r in source_rows]
    source_order_valid = all(
        a < b for a, b in zip(times, times[1:], strict=False)
    )

    print("\n[probe] row count:", row_count)
    print("[probe] first open:", times[0], "last open:", times[-1])
    print("[probe] zero-volume candles:", zero_volume_count)
    print("[probe] nonzero source_ignore rows:", nonzero_ignore_count)
    print("[probe] source ordering valid:", source_order_valid)

    # STOP CONDITION: any warning blocks acceptance (INCOMPLETE by policy).
    warnings_found = []
    if zero_volume_count:
        warnings_found.append(f"zero-volume candles: {zero_volume_count}")
    if nonzero_ignore_count:
        warnings_found.append(f"nonzero source_ignore rows: {nonzero_ignore_count}")
    if not source_order_valid:
        warnings_found.append("source rows unordered")
    assert not warnings_found, (
        "STRUCTURAL PROBE FOUND WARNINGS — golden-slice policy blocks "
        f"acceptance (INCOMPLETE): {warnings_found}"
    )

    assert row_count == descriptor.expected_row_count == 44_640
    start_ms = int(descriptor.start_utc.timestamp() * 1000)
    end_ms = int(descriptor.end_utc.timestamp() * 1000)
    assert times[0] == start_ms
    assert times[-1] == end_ms - 60_000
    assert len(set(times)) == row_count

    # ------------------------------------------------------------------
    # Phase 2: end-to-end PUBLISHED with quality exactly PASS.
    # ------------------------------------------------------------------
    assert run_pipeline(DESCRIPTOR_PATH, DATA_ROOT, repo_root=REPO_ROOT) == 0
    verified = read_and_verify_current(_dataset_dir(), DATA_ROOT)
    commit_dir = _commit_dir()
    manifest = json.loads((commit_dir / "manifest.json").read_text(encoding="utf-8"))
    quality = json.loads((commit_dir / "quality.json").read_text(encoding="utf-8"))
    print("[phase2] quality state:", quality["state"])
    print("[phase2] canonical content hash:", manifest["canonical_content_hash"])
    print("[phase2] parquet sha256:", manifest["parquet_sha256"])
    assert quality["state"] == "PASS"
    assert manifest["source_row_count"] == 44_640
    content_hash_first = manifest["canonical_content_hash"]
    parquet_sha_first = manifest["parquet_sha256"]
    assert verified["canonical_content_hash"] == content_hash_first

    pointer_before = (_dataset_dir() / "current.json").read_bytes()
    tree_before = _tree_digest(commit_dir)

    # ------------------------------------------------------------------
    # Phase 3: rerun must be VERIFIED_NO_OP and leave everything untouched.
    # ------------------------------------------------------------------
    assert run_pipeline(DESCRIPTOR_PATH, DATA_ROOT, repo_root=REPO_ROOT) == 0
    assert (_dataset_dir() / "current.json").read_bytes() == pointer_before
    assert _tree_digest(_commit_dir()) == tree_before
    results = [
        json.loads(p.read_text(encoding="utf-8"))["terminal_result"]
        for p in (DATA_ROOT / "attempts").glob("*.json")
    ]
    print("[phase3] attempt results observed:", sorted(results))
    assert "VERIFIED_NO_OP" in results
    commits = [
        p
        for p in (_dataset_dir() / "commits").iterdir()
        if not p.name.startswith(".")
    ]
    assert len(commits) == 1

    # ------------------------------------------------------------------
    # Phase 4: cross-run content-hash and Parquet-byte stability.
    # ------------------------------------------------------------------
    manifest_again = json.loads(
        (_commit_dir() / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest_again["canonical_content_hash"] == content_hash_first
    assert manifest_again["parquet_sha256"] == parquet_sha_first
    stored_parquet = (
        DATA_ROOT / "objects" / "normalized" / "sha256" / parquet_sha_first
    )
    assert sha256_hex(stored_parquet.read_bytes()) == parquet_sha_first

    # ------------------------------------------------------------------
    # Phase 5: /data/ is fully ignored by Git.
    # ------------------------------------------------------------------
    status = subprocess.run(
        ["git", "status", "--short"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    offending = [
        line for line in status.splitlines() if line[3:].startswith("data/")
    ]
    assert not offending, f"data directory leaked into git status: {offending}"
