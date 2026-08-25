"""Corruption and recovery scenario tests (spec §15.8)."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import httpx
import pytest
import yaml

from conftest import (
    VALID_DESCRIPTOR_YAML,
    build_month_csv,
    dataset_dir_for,
    rights_yaml_dict,
    write_text,
)
from quantara.archive import CorruptArchive, inspect_zip
from quantara.errors import QuantaraError
from quantara.pipeline import run_pipeline
from quantara.publication import InvalidPointer, read_and_verify_current


def make_env(tmp_path: Path):
    descriptor_path = write_text(
        tmp_path / "cfg", VALID_DESCRIPTOR_YAML, name="descriptor.yaml"
    )
    legal_dir = tmp_path / "configs" / "legal"
    legal_dir.mkdir(parents=True)
    (legal_dir / "binance-usdm-provider-rights.v1.yaml").write_text(
        yaml.safe_dump(rights_yaml_dict()), encoding="utf-8"
    )
    return descriptor_path, tmp_path / "data"


def build_zip(tmp_path: Path) -> tuple[Path, str]:
    archive = tmp_path / "BTCUSDT-1m-2024-01.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("BTCUSDT-1m-2024-01.csv", build_month_csv())
    return archive, hashlib.sha256(archive.read_bytes()).hexdigest()


def transport_for(archive: Path, digest: str):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".CHECKSUM"):
            return httpx.Response(200, text=f"{digest}  BTCUSDT-1m-2024-01.zip\n")
        return httpx.Response(200, content=archive.read_bytes())

    return httpx.MockTransport(handler)


@pytest.fixture()
def published(tmp_path: Path):
    descriptor_path, data_root = make_env(tmp_path)
    archive, digest = build_zip(tmp_path)
    assert (
        run_pipeline(
            descriptor_path,
            data_root,
            repo_root=tmp_path,
            transport=transport_for(archive, digest),
        )
        == 0
    )
    return {
        "descriptor_path": descriptor_path,
        "data_root": data_root,
        "archive": archive,
        "digest": digest,
        "dataset_dir": dataset_dir_for(data_root),
        "tmp_path": tmp_path,
    }


def rerun(env: dict) -> int:
    return run_pipeline(
        env["descriptor_path"],
        env["data_root"],
        repo_root=env["tmp_path"],
        transport=transport_for(env["archive"], env["digest"]),
    )


def test_truncated_staged_zip_is_a_hard_failure(tmp_path: Path) -> None:
    archive, _ = build_zip(tmp_path)
    blob = bytearray(archive.read_bytes())
    archive.write_bytes(bytes(blob[: len(blob) // 3]))
    with pytest.raises(CorruptArchive):
        inspect_zip(archive, r"^BTCUSDT-1m-2024-01\.csv$")


def test_checksum_altering_corruption_is_quarantined(tmp_path: Path) -> None:
    descriptor_path, data_root = make_env(tmp_path)
    corrupted = tmp_path / "corrupted.zip"
    with zipfile.ZipFile(corrupted, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("BTCUSDT-1m-2024-01.csv", b"small,different,content\n")
    official = hashlib.sha256(corrupted.read_bytes()).hexdigest()
    code = run_pipeline(
        descriptor_path,
        data_root,
        repo_root=tmp_path,
        transport=httpx.MockTransport(
            lambda request: (
                httpx.Response(200, text=f"{official}  BTCUSDT-1m-2024-01.zip\n")
                if request.url.path.endswith(".CHECKSUM")
                else httpx.Response(200, content=b"totally-different-bytes")
            )
        ),
    )
    assert code == 4  # QUARANTINED
    assert list((data_root / "quarantine").iterdir())


def test_pointer_loss_recovers_via_equivalent_rerun(published) -> None:
    # Crash point: after commit rename but before current.json replacement.
    (published["dataset_dir"] / "current.json").unlink()
    with pytest.raises(InvalidPointer):
        read_and_verify_current(published["dataset_dir"], published["data_root"])
    assert rerun(published) == 0
    verified = read_and_verify_current(
        published["dataset_dir"], published["data_root"]
    )
    assert verified["canonical_content_hash"]


def test_invalid_current_reference_is_never_discovered(published) -> None:
    pointer = published["dataset_dir"] / "current.json"
    pointer.write_text(json.dumps({"commit": "de" * 32}), encoding="utf-8")
    with pytest.raises(QuantaraError):
        read_and_verify_current(published["dataset_dir"], published["data_root"])
    assert rerun(published) == 0


def test_invalid_object_reference_fails_graph_verification(published) -> None:
    commit = json.loads(
        (published["dataset_dir"] / "current.json").read_text(encoding="utf-8")
    )["commit"]
    content_path = published["dataset_dir"] / "commits" / commit / "content.json"
    content = json.loads(content_path.read_text())
    content["object_refs"][0]["sha256"] = "aa" * 32  # dangling reference
    content_path.write_text(json.dumps(content))
    with pytest.raises(QuantaraError):
        read_and_verify_current(published["dataset_dir"], published["data_root"])


def test_stale_staging_is_discarded_on_rerun(published) -> None:
    commits = published["dataset_dir"] / "commits"
    stale = commits / ".staging-stale-attempt"
    stale.mkdir(parents=True)
    (stale / "junk.bin").write_bytes(b"x")
    assert rerun(published) == 0
    assert not stale.exists()
