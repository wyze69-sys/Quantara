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
    VALID_TWO_MONTH_DESCRIPTOR_YAML,
    build_month_csv,
    build_range_month_csv,
    dataset_dir_for,
    rights_v2_yaml_dict,
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


# --- final correction phase: JSON shape validation (slice 001 paths) -----------


def test_non_object_current_json_rerun_is_controlled(published) -> None:
    """current.json containing [] must never surface a raw AttributeError;
    the rerun treats it as a lost pointer and recovers by equivalent
    republication."""
    pointer = published["dataset_dir"] / "current.json"
    pointer.write_text("[]", encoding="utf-8")
    assert rerun(published) == 0
    verified = read_and_verify_current(
        published["dataset_dir"], published["data_root"]
    )
    assert verified["canonical_content_hash"]
    attempts = sorted((published["data_root"] / "attempts").glob("*.json"))
    newest = json.loads(attempts[-1].read_text())
    assert newest["terminal_result"] == "PUBLISHED"


def test_dry_run_with_non_object_pointer_fails_controlled(published) -> None:
    """Dry-run discovery over a non-object current.json exits FAILED instead
    of crashing."""
    (published["dataset_dir"] / "current.json").write_text("[]", encoding="utf-8")
    assert (
        run_pipeline(
            published["descriptor_path"],
            published["data_root"],
            repo_root=published["tmp_path"],
            dry_run=True,
        )
        == 3
    )


# --- Data slice 005: second-archive all-or-nothing recovery ------------------


def _range_recovery_env(tmp_path: Path) -> dict:
    descriptor = write_text(
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
        target = tmp_path / f"BTCUSDT-1m-{month}.zip"
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr(
                f"BTCUSDT-1m-{month}.csv", build_range_month_csv(month)
            )
        archives[month] = target.read_bytes()
        digests[month] = hashlib.sha256(archives[month]).hexdigest()

    invalid = tmp_path / "BTCUSDT-1m-2024-02-invalid.zip"
    with zipfile.ZipFile(invalid, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("BTCUSDT-1m-2024-02.csv", b"invalid,header\n")
    invalid_bytes = invalid.read_bytes()

    return {
        "descriptor": descriptor,
        "data_root": tmp_path / "data",
        "archives": archives,
        "digests": digests,
        "invalid_february": invalid_bytes,
        "invalid_february_digest": hashlib.sha256(invalid_bytes).hexdigest(),
        "root": tmp_path,
    }


def _range_transport(
    env: dict, *, corrupt_checksum: bool = False, corrupt_parse: bool = False
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        month = "2024-02" if "2024-02" in request.url.path else "2024-01"
        filename = f"BTCUSDT-1m-{month}.zip"
        if request.url.path.endswith(".CHECKSUM"):
            if month == "2024-02" and corrupt_checksum:
                return httpx.Response(200, text="not-a-checksum-document\n")
            digest = (
                env["invalid_february_digest"]
                if month == "2024-02" and corrupt_parse
                else env["digests"][month]
            )
            return httpx.Response(200, text=f"{digest}  {filename}\n")
        payload = (
            env["invalid_february"]
            if month == "2024-02" and corrupt_parse
            else env["archives"][month]
        )
        return httpx.Response(200, content=payload)

    return httpx.MockTransport(handler)


def _assert_no_partial_range_publish(env: dict) -> None:
    dataset_dir = dataset_dir_for(env["data_root"])
    assert not (dataset_dir / "current.json").exists()
    commits = dataset_dir / "commits"
    assert not commits.exists() or not list(commits.iterdir())
    staging = env["data_root"] / "staging"
    assert not staging.exists() or not list(staging.iterdir())


def _healthy_range_rerun_publishes(env: dict) -> None:
    assert (
        run_pipeline(
            env["descriptor"],
            env["data_root"],
            repo_root=env["root"],
            transport=_range_transport(env),
        )
        == 0
    )
    assert (dataset_dir_for(env["data_root"]) / "current.json").exists()


def test_second_archive_checksum_corruption_precedes_all_parsing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _range_recovery_env(tmp_path)
    parse_calls = []

    def parsing_must_not_start(*args, **kwargs):
        parse_calls.append((args, kwargs))
        raise AssertionError("parsing started before every checksum was verified")

    import quantara.pipeline as pipeline_module

    original_parse_rows = pipeline_module.parse_rows
    monkeypatch.setattr(pipeline_module, "parse_rows", parsing_must_not_start)
    assert (
        run_pipeline(
            env["descriptor"],
            env["data_root"],
            repo_root=env["root"],
            transport=_range_transport(env, corrupt_checksum=True),
        )
        == 3
    )
    assert parse_calls == []
    _assert_no_partial_range_publish(env)

    monkeypatch.setattr(pipeline_module, "parse_rows", original_parse_rows)
    _healthy_range_rerun_publishes(env)


def test_second_archive_parse_failure_cleans_staging_and_recovers(
    tmp_path: Path,
) -> None:
    env = _range_recovery_env(tmp_path)
    assert (
        run_pipeline(
            env["descriptor"],
            env["data_root"],
            repo_root=env["root"],
            transport=_range_transport(env, corrupt_parse=True),
        )
        == 3
    )
    _assert_no_partial_range_publish(env)
    _healthy_range_rerun_publishes(env)
