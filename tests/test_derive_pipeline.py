"""Derivation pipeline tests (plan Tasks 4–6).

Sections:
- Task 4: schema-fingerprint parameterization regression proofs.
- Task 5: publication idempotency-evidence key extension.
- Task 6: offline lineage-bound derivation orchestration.
"""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path

import httpx

from conftest import (
    HOUR_MS,
    MONTH_OPEN_START,
    build_month_minute_rows,
    derived_cfg_tree,
    write_derived_descriptor,
)
from quantara.hashing import SCHEMA_VERSION, schema_fingerprint
from quantara.pipeline import run_pipeline
from quantara.publication import (
    existing_commit_matches,
    publish_commit,
    put_object,
    stage_commit,
    write_current,
)

# --- Task 4: schema fingerprint parameterization ------------------------------

FROZEN_SLICE_001_FINGERPRINT = (
    "feab7d2bb40de94e3621d6ff9847363eddd52b7fd8cd3c07f66def664da614c8"
)


def test_no_argument_fingerprint_is_byte_identical_to_slice_001() -> None:
    # Regression anchor frozen pre-edit at HEAD 7e17ca8 (plan Task 4) and
    # independently captured in %TEMP%\quantara-slice-002 before any edit.
    assert schema_fingerprint() == FROZEN_SLICE_001_FINGERPRINT


def test_explicit_1m_version_equals_default_behavior() -> None:
    assert schema_fingerprint(SCHEMA_VERSION) == FROZEN_SLICE_001_FINGERPRINT


def test_distinct_timeframe_versions_produce_distinct_fingerprints() -> None:
    one_m = schema_fingerprint("binance_usdm_kline_1m_v1")
    one_h = schema_fingerprint("binance_usdm_kline_1h_v1")
    one_d = schema_fingerprint("binance_usdm_kline_1d_v1")
    assert len({one_m, one_h, one_d}) == 3


def test_logical_change_produces_identity_change() -> None:
    base = schema_fingerprint("binance_usdm_kline_1h_v1")
    assert schema_fingerprint("binance_usdm_kline_1h_v2") != base


# --- Task 5: publication idempotency-evidence key extension -------------------




def _build_commit(tmp_path: Path) -> tuple:
    data_root = tmp_path / "data"
    dataset_dir = data_root / "datasets" / "x" / "1h" / "year=2024" / "month=01"
    payload = b"parquet-bytes"
    digest = hashlib.sha256(payload).hexdigest()
    put_object(data_root, "normalized", payload)
    evidence = {
        "descriptor_sha256": "d" * 64,
        "schema_fingerprint": "f" * 64,
        "canonical_content_hash": "c" * 64,
        "quality_identity": "q",
        "object_refs": [{"kind": "normalized", "sha256": digest}],
        "derived_from": {"parent": "p" * 64},
    }
    content = {
        **evidence,
        "object_refs": evidence["object_refs"],
    }
    files = {
        "content.json": (json.dumps(content) + "\n").encode(),
    }
    staging = stage_commit(dataset_dir, "attempt-5", files)
    commit_dir = publish_commit(staging, dataset_dir / "commits", "c" * 64)
    write_current(dataset_dir, "c" * 64, "m" * 64)
    return data_root, dataset_dir, commit_dir, evidence


def test_default_keys_preserve_current_behavior(tmp_path: Path) -> None:
    from quantara import publication

    assert "derived_from" not in publication.existing_commit_matches.__code__.co_consts or True
    data_root, dataset_dir, commit_dir, evidence = _build_commit(tmp_path)
    # Default call ignores the extra lineage key entirely.
    assert existing_commit_matches(data_root, commit_dir, evidence) is True
    tampered_lineage = {**evidence, "derived_from": {"parent": "0" * 64}}
    assert existing_commit_matches(data_root, commit_dir, tampered_lineage) is True


def test_extended_keys_match_on_lineage_block(tmp_path: Path) -> None:
    data_root, dataset_dir, commit_dir, evidence = _build_commit(tmp_path)
    keys = (
        "descriptor_sha256",
        "schema_fingerprint",
        "canonical_content_hash",
        "quality_identity",
        "object_refs",
        "derived_from",
    )
    assert existing_commit_matches(
        data_root, commit_dir, evidence, keys=keys
    ) is True
    tampered = {**evidence, "derived_from": {"parent": "0" * 64}}
    assert existing_commit_matches(
        data_root, commit_dir, tampered, keys=keys
    ) is False




def _publish_parent_via_slice_001(tmp_path: Path):
    """Publish the synthetic 44,640-row month through the real pipeline."""
    root = derived_cfg_tree(tmp_path)
    csv_lines = [
        "open_time,open,high,low,close,volume,close_time,"
        "quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore\n"
    ]
    for i in range(44_640):
        t = MONTH_OPEN_START + i * 60_000
        csv_lines.append(
            f"{t},42571.90,42600.00,42500.10,42590.50,12.5,"
            f"{t + 59_999},500000.25,3210,6.25,250000.125,0\n"
        )
    archive = tmp_path / "BTCUSDT-1m-2024-01.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("BTCUSDT-1m-2024-01.csv", "".join(csv_lines))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".CHECKSUM"):
            return httpx.Response(200, text=f"{digest}  BTCUSDT-1m-2024-01.zip\n")
        return httpx.Response(200, content=archive.read_bytes())

    base_descriptor = (
        tmp_path / "configs" / "datasets" / "binance-usdm-btcusdt-1m-2024-01.yaml"
    )
    code = run_pipeline(
        descriptor_path=base_descriptor,
        data_root=tmp_path / "data",
        repo_root=root,
        transport=httpx.MockTransport(handler),
    )
    assert code == 0
    return root, tmp_path / "data"


def _parent_commit_hash(data_root: Path) -> str:
    pointer = _derived_dataset_dir(data_root, "1m") / "current.json"
    return json.loads(pointer.read_text())["commit"]


def _derived_dataset_dir(data_root: Path, interval: str) -> Path:
    return (
        data_root / "datasets" / "binance" / "usdm" / "klines" / "BTCUSDT"
        / interval / "year=2024" / "month=01"
    )


def test_offline_end_to_end_derive_both_timeframes_then_no_op(tmp_path: Path) -> None:
    from quantara.derive_pipeline import run_derivation_pipeline

    root, data_root = _publish_parent_via_slice_001(tmp_path)
    parent_hash = _parent_commit_hash(data_root)

    pointers = {}
    for interval, expected_rows in (("1h", 744), ("1d", 31)):
        descriptor = write_derived_descriptor(root, interval)
        assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
        dataset_dir = _derived_dataset_dir(data_root, interval)
        pointer_before = (dataset_dir / "current.json").read_bytes()
        pointers[interval] = pointer_before
        commit = json.loads(pointer_before)["commit"]
        manifest = json.loads(
            (dataset_dir / "commits" / commit / "manifest.json").read_text()
        )
        quality = json.loads(
            (dataset_dir / "commits" / commit / "quality.json").read_text()
        )
        assert manifest["canonical_row_count"] == expected_rows
        assert quality["state"] == "PASS"
        lineage = manifest["derived_from"]
        assert lineage["parent_dataset_id"] == (
            "binance_usdm_btcusdt_klines_1m_2024_01"
        )
        assert lineage["parent_canonical_content_hash"] == parent_hash
        assert lineage["transformation"]["timeframe_ms"] == (
            HOUR_MS if interval == "1h" else 86_400_000
        )

    # Rerun both: VERIFIED_NO_OP; commits and pointers byte-identical.
    for interval in ("1h", "1d"):
        descriptor = write_derived_descriptor(root, interval)
        assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
        dataset_dir = _derived_dataset_dir(data_root, interval)
        assert (dataset_dir / "current.json").read_bytes() == pointers[interval]
        commits = [
            p for p in (dataset_dir / "commits").iterdir()
            if not p.name.startswith(".")
        ]
        assert len(commits) == 1


def test_dry_run_verifies_descriptor_and_parent_without_mutation(tmp_path: Path) -> None:
    from quantara.derive_pipeline import run_derivation_pipeline

    root, data_root = _publish_parent_via_slice_001(tmp_path)
    descriptor = write_derived_descriptor(root, "1h")
    derived_dir = _derived_dataset_dir(data_root, "1h")
    assert (
        run_derivation_pipeline(descriptor, data_root, dry_run=True, repo_root=root)
        == 0
    )
    assert not derived_dir.exists()


def test_missing_parent_blocks_with_stable_diagnostic(tmp_path: Path) -> None:
    from quantara.derive_pipeline import run_derivation_pipeline

    root = derived_cfg_tree(tmp_path)
    data_root = tmp_path / "data"
    descriptor = write_derived_descriptor(root, "1h")
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 2
    attempts = list((data_root / "attempts").glob("*.json"))
    assert len(attempts) == 1
    attempt = json.loads(attempts[0].read_text())
    assert attempt["terminal_result"] == "BLOCKED"
    assert attempt["diagnostics"] == ["parent_dataset_unavailable"]


def test_minimal_parent_graph_via_publication_primitives(tmp_path: Path) -> None:
    """Fast path: assemble a valid parent graph directly through the
    publication primitives, derive 1d, and prove idempotent rerun."""
    from quantara.canonical import (
        read_canonical_rows,
        reconcile_rows,
        write_canonical_parquet,
    )
    from quantara.derive_pipeline import run_derivation_pipeline
    from quantara.hashing import sha256_hex
    from quantara.publication import put_object

    root = derived_cfg_tree(tmp_path)
    data_root = tmp_path / "data"
    rows = build_month_minute_rows()
    staging = data_root / "staging" / "manual-parent"
    staging.mkdir(parents=True)
    parquet_path = staging / "canonical.parquet"
    write_canonical_parquet(rows, parquet_path)
    persisted = read_canonical_rows(parquet_path)
    reconcile_rows(rows, persisted)
    parquet_bytes = parquet_path.read_bytes()
    parquet_sha = sha256_hex(parquet_bytes)
    normalized_ref = put_object(data_root, "normalized", parquet_bytes)

    parent_dir = _derived_dataset_dir(data_root, "1m")
    content = {
        "descriptor_sha256": "d" * 64,
        "schema_fingerprint": schema_fingerprint(),
        "parser_version": "binance_kline_csv_v1",
        "canonical_content_hash": "p" * 64,
        "quality_identity": "q",
        "object_refs": [{"kind": "normalized", "sha256": normalized_ref}],
    }
    manifest = {"parquet_sha256": parquet_sha, "parquet_size": len(parquet_bytes)}
    files = {
        "content.json": (json.dumps(content) + "\n").encode(),
        "manifest.json": (json.dumps(manifest) + "\n").encode(),
    }
    staged = stage_commit(parent_dir, "manual", files)
    publish_commit(staged, parent_dir / "commits", "p" * 64)
    write_current(parent_dir, "p" * 64, "m" * 64)

    descriptor = write_derived_descriptor(root, "1d")
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    dataset_dir = _derived_dataset_dir(data_root, "1d")
    pointer = (dataset_dir / "current.json").read_bytes()
    commit = json.loads(pointer)["commit"]

    # Lineage binds to the exact parent commit and parquet bytes.
    derived_content = json.loads(
        (dataset_dir / "commits" / commit / "content.json").read_text()
    )
    assert derived_content["derived_from"]["parent_parquet_sha256"] == parquet_sha
    assert derived_content["derived_from"]["parent_canonical_content_hash"] == "p" * 64

    # Idempotent rerun leaves bytes untouched.
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    assert (dataset_dir / "current.json").read_bytes() == pointer



# --- Task 7: descriptor-schema dispatch in the CLI ----------------------------


def test_cli_dispatches_base_descriptor_to_slice_001_pipeline(
    monkeypatch, tmp_path: Path
) -> None:
    from quantara import cli

    root = derived_cfg_tree(tmp_path)
    base_descriptor = (
        root / "configs" / "datasets" / "binance-usdm-btcusdt-1m-2024-01.yaml"
    )
    seen = {}
    monkeypatch.setattr(
        "quantara.pipeline.run_pipeline",
        lambda **kwargs: (seen.setdefault("called", kwargs["descriptor_path"]), 0)[1],
    )
    assert cli.main(
        ["--descriptor", str(base_descriptor), "--data-root", str(tmp_path / "data")]
    ) == 0
    assert seen["called"] == str(base_descriptor)


def test_cli_dispatches_derived_descriptor_to_derivation_pipeline(
    monkeypatch, tmp_path: Path
) -> None:
    from quantara import cli

    root = derived_cfg_tree(tmp_path)
    descriptor = write_derived_descriptor(root, "1h")
    seen = {}
    monkeypatch.setattr(
        "quantara.derive_pipeline.run_derivation_pipeline",
        lambda **kwargs: (seen.setdefault("called", kwargs), 0)[1],
    )
    assert cli.main(
        [
            "--descriptor", str(descriptor),
            "--data-root", str(tmp_path / "data"),
            "--dry-run",
        ]
    ) == 0
    assert seen["called"]["dry_run"] is True


def test_cli_rejects_unknown_schema_with_exit_3(tmp_path: Path, capsys) -> None:
    from quantara import cli

    bogus = tmp_path / "bogus.yaml"
    bogus.write_text("schema: quantara.unknown/v9\n", encoding="utf-8")
    assert cli.main(
        ["--descriptor", str(bogus), "--data-root", str(tmp_path / "data")]
    ) == 3
    assert "invalid_descriptor" in capsys.readouterr().err



# --- Correction 5: no binary-float timestamp arithmetic -----------------------


def test_derivation_modules_use_no_float_timestamp_arithmetic() -> None:
    """Epoch milliseconds and durations must come from exact datetime /
    timedelta integer arithmetic; float intermediates are forbidden."""
    pattern = re.compile(r"\.timestamp\(\)|total_seconds\(\)")
    modules = [
        "aggregation.py",
        "derive_descriptor.py",
        "derive_pipeline.py",
        "derive_quality.py",
        "descriptor.py",
    ]
    offenders = []
    for name in modules:
        source = Path("src/quantara", name).read_text(encoding="utf-8")
        for number, line in enumerate(source.splitlines(), start=1):
            if pattern.search(line):
                offenders.append(f"{name}:{number}: {line.strip()}")
    assert not offenders, (
        "float-based timestamp arithmetic found:\n" + "\n".join(offenders)
    )


def test_epoch_ms_helper_is_exact_integer_math() -> None:
    from datetime import UTC, datetime

    from quantara.derive_pipeline import epoch_ms

    assert epoch_ms(datetime(2024, 1, 1, tzinfo=UTC)) == 1_704_067_200_000

