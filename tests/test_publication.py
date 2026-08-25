"""Publication protocol tests (spec §§9–10, 12.3, 15.8)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from quantara.errors import QuantaraError
from quantara.publication import (
    PUBLICATION_PROTOCOL_VERSION,
    InvalidPointer,
    ObjectCollision,
    PublicationError,
    publish_commit,
    put_object,
    read_and_verify_current,
    stage_commit,
    verify_commit_graph,
    write_current,
)


def test_protocol_version() -> None:
    assert PUBLICATION_PROTOCOL_VERSION == "v1"


def test_put_object_addresses_by_content(tmp_path: Path) -> None:
    payload = b"immutable-bytes"
    digest = put_object(tmp_path, "raw", payload)
    assert digest == hashlib.sha256(payload).hexdigest()
    stored = tmp_path / "objects" / "raw" / "sha256" / digest
    assert stored.read_bytes() == payload


def test_put_object_dedupes_identical_bytes(tmp_path: Path) -> None:
    first = put_object(tmp_path, "normalized", b"same")
    second = put_object(tmp_path, "normalized", b"same")
    assert first == second


def test_collision_with_different_bytes_is_hard_failure(tmp_path: Path) -> None:
    digest = hashlib.sha256(b"original").hexdigest()
    target = tmp_path / "objects" / "checksum" / "sha256" / digest
    target.parent.mkdir(parents=True)
    target.write_bytes(b"original")
    # Simulate a corrupted pre-existing object addressed as b"original".
    real = hashlib.sha256(b"different").hexdigest()
    del real
    with pytest.raises(ObjectCollision):
        put_object(tmp_path, "checksum", b"corrupted-but-forced", digest=digest)


def test_staged_commit_publishes_atomically_once(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "datasets" / "d"
    files = {
        "manifest.json": json.dumps({"dataset": "d"}).encode(),
        "quality.json": json.dumps({"state": "PASS"}).encode(),
        "content.json": json.dumps(
            {"canonical_content_hash": "cafe" * 16}
        ).encode(),
    }
    staging = stage_commit(dataset_dir, "20260824T000000Z-a1", files)
    assert staging.name.startswith(".staging-")
    published = publish_commit(staging, dataset_dir / "commits", "ab" * 32)
    assert published == dataset_dir / "commits" / ("ab" * 32)
    assert (published / "COMMITTED").exists()
    # Publishing again into the same address is refused.
    staging2 = stage_commit(dataset_dir, "20260824T000000Z-a2", files)
    with pytest.raises(QuantaraError):
        publish_commit(staging2, dataset_dir / "commits", "ab" * 32)


def test_current_pointer_replacement_and_discovery(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "datasets" / "d"
    files = {"content.json": json.dumps({"refs": []}).encode()}
    staging = stage_commit(dataset_dir, "a", files)
    commit_hash = "cd" * 32
    publish_commit(staging, dataset_dir / "commits", commit_hash)
    write_current(dataset_dir, commit_hash, manifest_digest="ef" * 32)

    verified = read_and_verify_current(dataset_dir, tmp_path)
    assert verified["commit"] == commit_hash


def test_invalid_current_reference_never_discovers(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "datasets" / "d"
    write_current(dataset_dir, "ff" * 32, manifest_digest="00" * 32)
    with pytest.raises(InvalidPointer):
        read_and_verify_current(dataset_dir, tmp_path)


def test_tampered_object_fails_graph_verification(tmp_path: Path) -> None:
    payload = b"parquet-ish-bytes"
    digest = put_object(tmp_path, "normalized", payload)
    dataset_dir = tmp_path / "datasets" / "d"
    content = {
        "canonical_content_hash": "11" * 32,
        "object_refs": [{"kind": "normalized", "sha256": digest}],
        "source_sha256": "22" * 32,
        "descriptor_sha256": "33" * 32,
        "schema_fingerprint": "44" * 32,
        "parser_version": "v1",
        "quality_identity": "{}",
    }
    files = {"content.json": json.dumps(content).encode()}
    staging = stage_commit(dataset_dir, "a", files)
    commit_dir = publish_commit(staging, dataset_dir / "commits", "55" * 32)
    write_current(dataset_dir, "55" * 32, manifest_digest="66" * 32)

    assert verify_commit_graph(tmp_path, commit_dir)["canonical_content_hash"] == (
        "11" * 32
    )

    # Tamper with the immutable object after publication.
    obj = tmp_path / "objects" / "normalized" / "sha256" / digest
    obj.write_bytes(b"tampered!")
    with pytest.raises(QuantaraError):
        read_and_verify_current(dataset_dir, tmp_path)


def test_noop_verification_semantics(tmp_path: Path) -> None:
    from quantara.publication import existing_commit_matches

    payload = b"z" * 10
    digest = put_object(tmp_path, "normalized", payload)
    dataset_dir = tmp_path / "datasets" / "d"
    content = {
        "canonical_content_hash": "aa" * 32,
        "object_refs": [{"kind": "normalized", "sha256": digest}],
        "source_sha256": "bb" * 32,
        "descriptor_sha256": "cc" * 32,
        "schema_fingerprint": "dd" * 32,
        "parser_version": "v1",
        "quality_identity": "{\"checks\":[]}",
    }
    files = {"content.json": json.dumps(content).encode()}
    staging = stage_commit(dataset_dir, "a", files)
    commit_dir = publish_commit(staging, dataset_dir / "commits", "ee" * 32)

    assert existing_commit_matches(tmp_path, commit_dir, content) is True

    drifted = dict(content)
    drifted["source_sha256"] = "ff" * 32
    assert existing_commit_matches(tmp_path, commit_dir, drifted) is False


# --- final correction phase: JSON shape validation before use ------------------


def test_non_object_current_json_is_an_invalid_pointer(tmp_path: Path) -> None:
    """Syntactically valid non-object current.json is a controlled
    InvalidPointer, never a raw AttributeError."""
    dataset_dir = tmp_path / "datasets" / "d"
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "current.json").write_text("[]", encoding="utf-8")
    with pytest.raises(InvalidPointer):
        read_and_verify_current(dataset_dir, tmp_path)


def test_malformed_current_json_is_an_invalid_pointer(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "datasets" / "d"
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "current.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(InvalidPointer):
        read_and_verify_current(dataset_dir, tmp_path)


def test_non_object_content_json_fails_graph_verification(
    tmp_path: Path,
) -> None:
    """content.json containing [] fails graph verification as a controlled
    PublicationError and never discovers."""
    dataset_dir = tmp_path / "datasets" / "d"
    staging = stage_commit(dataset_dir, "a", {"content.json": b"[]\n"})
    commit_dir = publish_commit(staging, dataset_dir / "commits", "ab" * 32)
    with pytest.raises(PublicationError):
        verify_commit_graph(tmp_path, commit_dir)
    write_current(dataset_dir, "ab" * 32, manifest_digest="ef" * 32)
    with pytest.raises(QuantaraError):
        read_and_verify_current(dataset_dir, tmp_path)


def test_non_object_content_json_never_matches_as_no_op(tmp_path: Path) -> None:
    from quantara.publication import existing_commit_matches

    dataset_dir = tmp_path / "datasets" / "d"
    staging = stage_commit(dataset_dir, "a", {"content.json": b"[]\n"})
    commit_dir = publish_commit(staging, dataset_dir / "commits", "cd" * 32)
    assert existing_commit_matches(tmp_path, commit_dir, {}) is False


def test_non_mapping_object_refs_fail_verification(tmp_path: Path) -> None:
    """object_refs entries must be {kind, sha256} mappings; anything else is
    a controlled verification failure, never a raw TypeError."""
    dataset_dir = tmp_path / "datasets" / "d"
    content = {
        "canonical_content_hash": "11" * 32,
        "object_refs": ["not-a-mapping"],
    }
    staging = stage_commit(
        dataset_dir, "a", {"content.json": json.dumps(content).encode()}
    )
    publish_commit(staging, dataset_dir / "commits", "55" * 32)
    write_current(dataset_dir, "55" * 32, manifest_digest="66" * 32)
    with pytest.raises(PublicationError):
        read_and_verify_current(dataset_dir, tmp_path)
