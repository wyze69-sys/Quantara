"""Offline end-to-end pipeline orchestration tests (spec §10, plan Task 10)."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import httpx
import pytest
import yaml

from conftest import VALID_DESCRIPTOR_YAML, op, rights_yaml, write_text
from quantara.pipeline import run_pipeline

OPEN_START = 1704067200000
ROW_COUNT = 44_640


def build_month_csv() -> bytes:
    header = (
        "open_time,open,high,low,close,volume,close_time,"
        "quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore\n"
    )
    lines = [header]
    for i in range(ROW_COUNT):
        t = OPEN_START + i * 60_000
        lines.append(
            f"{t},42571.90,42600.00,42500.10,42590.50,12.5,"
            f"{t + 59_999},500000.25,3210,6.25,250000.125,0\n"
        )
    return "".join(lines).encode("utf-8")


def build_zip(tmp_path: Path) -> tuple[Path, str]:
    csv_bytes = build_month_csv()
    archive = tmp_path / "BTCUSDT-1m-2024-01.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("BTCUSDT-1m-2024-01.csv", csv_bytes)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    return archive, digest


@pytest.fixture()
def env(tmp_path: Path):
    descriptor_path = write_text(
        tmp_path / "cfg", VALID_DESCRIPTOR_YAML, name="descriptor.yaml"
    )
    legal_dir = tmp_path / "configs" / "legal"
    legal_dir.mkdir(parents=True)
    rights = rights_yaml(
        {
            "acquire_internal": op("OWNER_APPROVED_PENDING_COUNSEL"),
            "retain_raw_internal": op("OWNER_APPROVED_PENDING_COUNSEL"),
            "normalize_internal": op("OWNER_APPROVED_PENDING_COUNSEL"),
            "analyze_internal": op("UNKNOWN"),
            "model_train_internal": op("UNKNOWN"),
            "commercial_production_eligible": op("UNKNOWN"),
            "customer_display": op("UNKNOWN"),
            "raw_redistribution": op("UNKNOWN"),
        }
    )
    (legal_dir / "binance-usdm-provider-rights.v1.yaml").write_text(
        yaml.safe_dump(rights), encoding="utf-8"
    )
    data_root = tmp_path / "data"
    return descriptor_path, data_root


def fake_transport(archive: Path, checksum_text: str):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".CHECKSUM"):
            return httpx.Response(200, text=checksum_text)
        return httpx.Response(200, content=archive.read_bytes())

    return httpx.MockTransport(handler)


def dataset_dir_for(data_root: Path) -> Path:
    return (
        data_root
        / "datasets"
        / "binance"
        / "usdm"
        / "klines"
        / "BTCUSDT"
        / "1m"
        / "year=2024"
        / "month=01"
    )


def test_offline_end_to_end_publish_then_verified_no_op(env, tmp_path: Path) -> None:
    descriptor_path, data_root = env
    archive, zip_digest = build_zip(tmp_path)
    transport = fake_transport(archive, f"{zip_digest}  BTCUSDT-1m-2024-01.zip\n")

    exit_code = run_pipeline(
        descriptor_path=descriptor_path,
        data_root=data_root,
        repo_root=tmp_path,
        transport=transport,
    )
    assert exit_code == 0

    dataset_dir = dataset_dir_for(data_root)
    pointer_before = (dataset_dir / "current.json").read_bytes()
    commit_hash = json.loads(pointer_before)["commit"]
    manifest = json.loads(
        (dataset_dir / "commits" / commit_hash / "manifest.json").read_text()
    )
    quality = json.loads(
        (dataset_dir / "commits" / commit_hash / "quality.json").read_text()
    )
    assert manifest["source_row_count"] == ROW_COUNT == 44_640
    assert quality["state"] == "PASS"

    # Rerun: VERIFIED_NO_OP, pointer and commit untouched.
    exit_code2 = run_pipeline(
        descriptor_path=descriptor_path,
        data_root=data_root,
        repo_root=tmp_path,
        transport=transport,
    )
    assert exit_code2 == 0
    assert (dataset_dir / "current.json").read_bytes() == pointer_before
    commits = [
        p for p in (dataset_dir / "commits").iterdir() if not p.name.startswith(".")
    ]
    assert len(commits) == 1

    attempts = list((data_root / "attempts").glob("*.json"))
    results = sorted(json.loads(p.read_text())["terminal_result"] for p in attempts)
    assert results == ["PUBLISHED", "VERIFIED_NO_OP"]


def test_legal_gate_blocks_without_network(env, tmp_path: Path) -> None:
    descriptor_path, data_root = env

    def no_network(request):  # pragma: no cover - must never be called
        raise AssertionError("network access attempted despite legal block")

    legal = tmp_path / "configs" / "legal" / "binance-usdm-provider-rights.v1.yaml"
    record = yaml.safe_load(legal.read_text())
    record["operations"]["acquire_internal"]["state"] = "UNKNOWN"
    legal.write_text(yaml.safe_dump(record), encoding="utf-8")

    exit_code = run_pipeline(
        descriptor_path=descriptor_path,
        data_root=data_root,
        repo_root=tmp_path,
        transport=httpx.MockTransport(no_network),
    )
    assert exit_code == 2


def test_checksum_mismatch_quarantines_with_exit_4(env, tmp_path: Path) -> None:
    descriptor_path, data_root = env
    archive, _ = build_zip(tmp_path)
    wrong_digest = hashlib.sha256(b"not-the-archive").hexdigest()
    transport = fake_transport(archive, f"{wrong_digest}  BTCUSDT-1m-2024-01.zip\n")
    exit_code = run_pipeline(
        descriptor_path=descriptor_path,
        data_root=data_root,
        repo_root=tmp_path,
        transport=transport,
    )
    assert exit_code == 4
    assert list((data_root / "quarantine").iterdir())


def test_dry_run_makes_no_mutation_or_network(env, tmp_path: Path) -> None:
    descriptor_path, data_root = env

    def no_network(request):  # pragma: no cover - must never be called
        raise AssertionError("network access attempted in dry-run")

    assert (
        run_pipeline(
            descriptor_path=descriptor_path,
            data_root=data_root,
            repo_root=tmp_path,
            transport=httpx.MockTransport(no_network),
            dry_run=True,
        )
        == 0
    )
