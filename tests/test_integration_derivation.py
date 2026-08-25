"""Real-parent integration acceptance (plan Task 10).

Invoked explicitly: ``uv run pytest -m integration``. Fails loudly (never
skips) if the retained parent artifacts are absent. Derives 1h and 1d through
the CLI entry point against the real verified January 2024 parent store,
proves idempotent reruns, and proves the parent graph is untouched.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tempfile
import time
import zipfile
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import httpx
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


# --- Task 11: official-archive cross-check (independent evidence) -------------

ALLOWED_HOST = "data.binance.vision"
CHECKSUM_GRAMMAR = re.compile(r"^([0-9a-f]{64})  (BTCUSDT-(?:1h|1d)-2024-01\.zip)$")
VOLUME_TOLERANCE = Decimal("1e-8")


def _verified_download(url: str, retries: int = 3) -> bytes:
    """Allow-listed host, bounded exponential backoff for transient failures."""
    assert urlparse(url).hostname == ALLOWED_HOST, f"non-allowlisted host: {url}"
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = httpx.get(url, timeout=60.0)
            response.raise_for_status()
            return response.content
        except httpx.TransportError as exc:  # eligible transient failures only
            last_error = exc
            time.sleep(0.5 * (2**attempt))
    raise AssertionError(f"download failed after {retries} attempts: {last_error}")


def _official_rows(zip_bytes: bytes) -> list[list[str]]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        name = zf.namelist()[0]
        text = zf.read(name).decode("utf-8")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines[0].split(",")[0].strip().isdigit():
        lines = lines[1:]  # newer archives embed a header row
    return [line.split(",") for line in lines]


@pytest.mark.parametrize("interval", ["1h", "1d"])
def test_official_archive_cross_check(interval: str) -> None:
    base = (
        "https://data.binance.vision/data/futures/um/monthly/klines/"
        f"BTCUSDT/{interval}/BTCUSDT-{interval}-2024-01"
    )
    archive_bytes = _verified_download(base + ".zip")
    checksum_text = _verified_download(base + ".zip.CHECKSUM").decode("utf-8")

    # Strict CHECKSUM grammar, then digest equality over the exact bytes.
    match = CHECKSUM_GRAMMAR.match(checksum_text.strip())
    assert match, f"checksum document violates strict grammar: {checksum_text!r}"
    expected_digest, filename = match.group(1), match.group(2)
    assert filename == f"BTCUSDT-{interval}-2024-01.zip"
    assert hashlib.sha256(archive_bytes).hexdigest() == expected_digest

    official = _official_rows(archive_bytes)
    derived = _derived_dir(interval)
    pointer = json.loads((derived / "current.json").read_text())
    manifest = json.loads(
        (derived / "commits" / pointer["commit"] / "manifest.json").read_text()
    )
    from quantara.aggregation import rows_from_persisted
    from quantara.canonical import read_canonical_rows

    ours = rows_from_persisted(
        read_canonical_rows(
            DATA_ROOT / "objects" / "normalized" / "sha256" / manifest["parquet_sha256"]
        )
    )
    assert len(ours) == len(official) == EXPECTED_ROWS[interval]

    deltas = []
    mismatches = []
    for bar, row in zip(ours, official, strict=True):
        open_ms = int(row[0])
        o, h, lo, c = (Decimal(row[i]) for i in (1, 2, 3, 4))
        bv, qv = Decimal(row[5]), Decimal(row[7])
        n = int(row[8])
        tbv, tqv = Decimal(row[9]), Decimal(row[10])
        assert open_ms == bar.open_time_ms
        for field, ours_value, theirs in (
            ("open", bar.open, o), ("high", bar.high, h),
            ("low", bar.low, lo), ("close", bar.close, c),
        ):
            if ours_value != theirs:  # exact: endpoint/extreme selections
                mismatches.append((open_ms, field, str(ours_value), str(theirs)))
        if bar.trade_count != n:  # exact integer counts
            mismatches.append((open_ms, "count", bar.trade_count, n))
        for field, ours_value, theirs in (
            ("base_asset_volume", bar.base_asset_volume, bv),
            ("quote_asset_volume", bar.quote_asset_volume, qv),
            ("taker_buy_base_volume", bar.taker_buy_base_volume, tbv),
            ("taker_buy_quote_volume", bar.taker_buy_quote_volume, tqv),
        ):
            delta = abs(ours_value - theirs)
            deltas.append({
                "open_time_utc": open_ms, "field": field,
                "delta": str(delta),
                "within_tolerance": delta <= VOLUME_TOLERANCE,
            })
            assert delta <= VOLUME_TOLERANCE, (
                f"{field} drift {delta} at {open_ms} exceeds 1e-8"
            )

    # Every delta is printed and recorded — never hidden.
    max_delta = max((Decimal(d["delta"]) for d in deltas), default=Decimal(0))
    print(f"[{interval}] bars compared: {len(ours)}; "
          f"volume-family max |delta| = {max_delta}")
    for d in deltas:
        print(f"  {d['open_time_utc']} {d['field']}: |delta|={d['delta']}")
    assert not mismatches, f"exact-field mismatches: {mismatches}"

    results_path = (
        Path(os.environ.get("TEMP", tempfile.gettempdir()))
        / "quantara-slice-002" / f"crosscheck-results-{interval}.json"
    )
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps({
        "interval": interval,
        "bars_compared": len(ours),
        "exact_field_mismatches": len(mismatches),
        "max_volume_family_delta": str(max_delta),
        "tolerance": "1e-8",
        "deltas": deltas,
    }, indent=2), encoding="utf-8")

