"""Real-parent integration acceptance (plan Task 10).

Invoked explicitly: ``uv run pytest -m integration``. Fails loudly (never
skips) if the retained parent artifacts are absent. Derives 1h and 1d through
the CLI entry point against the real verified January 2024 parent store,
proves idempotent reruns, and proves the parent graph is untouched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quantara.cli import main

pytestmark = [pytest.mark.integration]

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = REPO_ROOT / "data"
PARENT_COMMIT_HASH = (
    "9d7eee742d0a75612d0b37affcc0e4e40feee67c"
    "6f5e1d21f317a8821c9b448f"
)
PARENT_COMMIT_PREFIX = "9d7eee74"

DESCRIPTORS = {
    "1h": REPO_ROOT / "configs" / "datasets"
    / "binance-usdm-btcusdt-1h-2024-01-derived.yaml",
    "1d": REPO_ROOT / "configs" / "datasets"
    / "binance-usdm-btcusdt-1d-2024-01-derived.yaml",
}

EXPECTED_ROWS = {"1h": 744, "1d": 31}
TIMEFRAME_MS = {"1h": 3_600_000, "1d": 86_400_000}
MIDNIGHT = 1_704_067_200_000


def _require_parent() -> Path:
    parent = (
        DATA_ROOT / "datasets" / "binance" / "usdm" / "klines" / "BTCUSDT"
        / "1m" / "year=2024" / "month=01"
    )
    pointer = parent / "current.json"
    if not pointer.exists():  # fail loudly, never skip
        raise AssertionError(
            f"retained parent artifacts missing: {pointer} not found"
        )
    commit = json.loads(pointer.read_text())["commit"]
    assert commit.startswith(PARENT_COMMIT_PREFIX), (
        f"parent commit {commit} does not match frozen lineage prefix"
    )
    return parent


def _derived_dir(interval: str) -> Path:
    return (
        DATA_ROOT / "datasets" / "binance" / "usdm" / "klines" / "BTCUSDT"
        / interval / "year=2024" / "month=01"
    )


def _tree_digest(dataset_dir: Path) -> dict[str, str]:
    import hashlib

    snapshot = {}
    for path in sorted(dataset_dir.rglob("*")):
        rel = path.relative_to(dataset_dir.parent.parent).as_posix()
        if path.is_file():
            snapshot[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            snapshot[rel] = "<dir>"
    return snapshot


def _attempts() -> int:
    return len(list((DATA_ROOT / "attempts").glob("*.json")))


def test_real_parent_multi_timeframe_derivation_acceptance() -> None:
    parent_dir = _require_parent()

    # Parent immutability baseline (pointer + full committed directory).
    baseline = _tree_digest(parent_dir)
    attempts_before = _attempts()

    pointers: dict[str, bytes] = {}
    for interval in ("1h", "1d"):
        exit_code = main([
            "--descriptor", str(DESCRIPTORS[interval]),
            "--data-root", str(DATA_ROOT),
        ])
        assert exit_code == 0, f"{interval} derivation failed ({exit_code})"
        derived = _derived_dir(interval)
        pointer_bytes = (derived / "current.json").read_bytes()
        pointers[interval] = pointer_bytes
        commit = json.loads(pointer_bytes)["commit"]
        manifest = json.loads(
            (derived / "commits" / commit / "manifest.json").read_text()
        )
        quality = json.loads(
            (derived / "commits" / commit / "quality.json").read_text()
        )
        # Quality exactly PASS; exact calendar row counts and boundaries.
        assert quality["state"] == "PASS"
        tf_ms = TIMEFRAME_MS[interval]
        rows = EXPECTED_ROWS[interval]
        assert manifest["canonical_row_count"] == rows
        assert manifest["quality_state"] == "PASS"
        content = json.loads(
            (derived / "commits" / commit / "content.json").read_text()
        )
        lineage = content["derived_from"]
        assert lineage["parent_dataset_id"] == (
            "binance_usdm_btcusdt_klines_1m_2024_01"
        )
        assert (
            lineage["parent_canonical_content_hash"] == PARENT_COMMIT_HASH
        )
        # Calendar-derived first/last boundaries over the published rows.
        parquet_sha = manifest["parquet_sha256"]
        obj = DATA_ROOT / "objects" / "normalized" / "sha256" / parquet_sha
        assert obj.exists()
        from quantara.aggregation import rows_from_persisted
        from quantara.canonical import read_canonical_rows

        derived_rows = rows_from_persisted(read_canonical_rows(obj))
        assert len(derived_rows) == rows
        assert derived_rows[0].open_time_ms == MIDNIGHT
        assert derived_rows[-1].open_time_ms == MIDNIGHT + (rows - 1) * tf_ms
        assert derived_rows[-1].close_time_ms == MIDNIGHT + rows * tf_ms - 1
        assert lineage["transformation"]["timeframe_ms"] == tf_ms
        assert manifest["schema_version"] == f"binance_usdm_kline_{interval}_v1"

    # Rerun both: VERIFIED_NO_OP; byte-identical commits and pointers;
    # exactly two new attempt manifests total.
    attempts_after_publish = _attempts()
    for interval in ("1h", "1d"):
        assert main([
            "--descriptor", str(DESCRIPTORS[interval]),
            "--data-root", str(DATA_ROOT),
        ]) == 0
        derived = _derived_dir(interval)
        assert (derived / "current.json").read_bytes() == pointers[interval]
        commits = [p for p in (derived / "commits").iterdir()
                   if not p.name.startswith(".")]
        assert len(commits) == 1
    attempts_after_rerun = _attempts()
    rerun_results = []
    for p in sorted((DATA_ROOT / "attempts").glob("*.json"))[
        attempts_after_publish:attempts_after_rerun
    ]:
        rerun_results.append(json.loads(p.read_text())["terminal_result"])
    assert rerun_results == ["VERIFIED_NO_OP", "VERIFIED_NO_OP"], rerun_results
    assert attempts_after_rerun - attempts_before >= 2

    # Parent immutability proof: byte-for-byte unchanged by everything above.
    assert _tree_digest(parent_dir) == baseline

    # /data/ is ignored and nothing from it is staged in Git.
    import subprocess

    ls_files = subprocess.run(
        ["git", "ls-files", "data"], cwd=REPO_ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert ls_files == ""
    ignored = subprocess.run(
        ["git", "status", "--ignored", "--short", "data"], cwd=REPO_ROOT,
        capture_output=True, text=True, check=True,
    ).stdout
    assert "!! data/" in ignored
