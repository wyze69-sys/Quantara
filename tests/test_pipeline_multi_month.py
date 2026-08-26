"""Synthetic multi-month acquisition and seam invariants (data slice 005)."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import httpx
import pytest
import yaml

from conftest import (
    VALID_TWO_MONTH_DESCRIPTOR_YAML,
    build_range_month_csv,
    dataset_dir_for,
    rights_v2_yaml_dict,
    write_text,
)
from quantara.hashing import schema_fingerprint
from quantara.pipeline import run_pipeline


def _range_environment(
    tmp_path: Path,
    *,
    february_drop: frozenset[int] = frozenset(),
    february_duplicate: frozenset[int] = frozenset(),
) -> tuple[Path, Path, httpx.MockTransport]:
    descriptor_path = write_text(
        tmp_path / "configs" / "datasets",
        VALID_TWO_MONTH_DESCRIPTOR_YAML,
        name="range.yaml",
    )
    legal = tmp_path / "configs" / "legal"
    legal.mkdir(parents=True)
    rights = rights_v2_yaml_dict()
    rights["record_id"] = "binance-usdm-provider-rights.v2"
    (legal / "binance-usdm-provider-rights.v2.yaml").write_text(
        yaml.safe_dump(rights), encoding="utf-8"
    )

    archives: dict[str, bytes] = {}
    digests: dict[str, str] = {}
    for month in ("2024-01", "2024-02"):
        csv_bytes = build_range_month_csv(
            month,
            drop_indices=february_drop if month == "2024-02" else frozenset(),
            duplicate_indices=(
                february_duplicate if month == "2024-02" else frozenset()
            ),
        )
        archive = tmp_path / f"BTCUSDT-1m-{month}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr(f"BTCUSDT-1m-{month}.csv", csv_bytes)
        archives[month] = archive.read_bytes()
        digests[month] = hashlib.sha256(archives[month]).hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        month = "2024-02" if "2024-02" in request.url.path else "2024-01"
        filename = f"BTCUSDT-1m-{month}.zip"
        if request.url.path.endswith(".CHECKSUM"):
            return httpx.Response(200, text=f"{digests[month]}  {filename}\n")
        return httpx.Response(200, content=archives[month])

    return descriptor_path, tmp_path / "data", httpx.MockTransport(handler)


def _run_range(tmp_path: Path, **fixture_options) -> tuple[int, Path]:
    descriptor, data_root, transport = _range_environment(
        tmp_path, **fixture_options
    )
    code = run_pipeline(
        descriptor,
        data_root,
        repo_root=tmp_path,
        transport=transport,
    )
    return code, data_root


def test_cli_dispatches_v2_descriptor_to_base_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import quantara.pipeline
    from quantara.cli import main

    descriptor = write_text(
        tmp_path,
        VALID_TWO_MONTH_DESCRIPTOR_YAML,
        name="range.yaml",
    )
    calls: list[tuple[str, str, bool]] = []

    def fake_run_pipeline(*, descriptor_path, data_root, dry_run):
        calls.append((str(descriptor_path), str(data_root), dry_run))
        return 0

    monkeypatch.setattr(quantara.pipeline, "run_pipeline", fake_run_pipeline)
    data_root = tmp_path / "data"
    assert main(
        [
            "--descriptor",
            str(descriptor),
            "--data-root",
            str(data_root),
            "--dry-run",
        ]
    ) == 0
    assert calls == [(str(descriptor), str(data_root), True)]


def test_clean_two_month_seam_publishes(tmp_path: Path) -> None:
    code, data_root = _run_range(tmp_path)
    assert code == 0
    dataset_dir = dataset_dir_for(data_root)
    current = json.loads((dataset_dir / "current.json").read_text(encoding="utf-8"))
    manifest = json.loads(
        (dataset_dir / "commits" / current["commit"] / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["source_row_count"] == 86_400
    assert len(manifest["archive_url"]) == 2


@pytest.mark.parametrize(
    "fixture_options",
    [
        pytest.param(
            {"february_drop": frozenset({0})},
            id="gapped-month-seam",
        ),
        pytest.param(
            {"february_duplicate": frozenset({0})},
            id="duplicated-seam-bar",
        ),
        pytest.param(
            {"february_drop": frozenset({41_759})},
            id="segment-accounting-mismatch",
        ),
    ],
)
def test_range_invariant_failure_blocks_without_publication(
    tmp_path: Path, fixture_options: dict
) -> None:
    code, data_root = _run_range(tmp_path, **fixture_options)
    assert code == 2
    assert not (dataset_dir_for(data_root) / "current.json").exists()
    attempts = list((data_root / "attempts").glob("*.json"))
    assert len(attempts) == 1
    attempt = json.loads(attempts[0].read_text(encoding="utf-8"))
    assert attempt["terminal_result"] == "BLOCKED"
    assert attempt["diagnostics"] == ["multi_month_invariant_violation"]


def test_ordered_month_sets_have_distinct_fingerprints() -> None:
    month_sets = (
        ("2024-01", "2024-02"),
        ("2024-02", "2024-01"),
        ("2024-01", "2024-02", "2024-03"),
    )
    fingerprints = {schema_fingerprint(months=months) for months in month_sets}
    assert len(fingerprints) == len(month_sets)
