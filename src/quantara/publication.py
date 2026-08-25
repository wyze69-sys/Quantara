"""Publication protocol.

Content-addressed immutable object store under data/objects/{raw,checksum,
normalized}/sha256/, staged commit directories atomically renamed into
datasets/.../commits/<canonical-content-hash>/, a current.json pointer replaced
only after the committed directory independently verifies, and idempotent
VERIFIED_NO_OP detection. Readers never discover partial graphs; crash points
leave only safe orphans (spec §§9, 10, 12.3).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from quantara.errors import (
    ATOMIC_PROMOTION_FAILURE,
    MANIFEST_INCONSISTENCY,
    QuantaraError,
)

__all__ = [
    "PUBLICATION_PROTOCOL_VERSION",
    "InvalidPointer",
    "ObjectCollision",
    "PublicationError",
    "StoredObject",
    "existing_commit_matches",
    "put_object",
    "publish_commit",
    "read_and_verify_current",
    "stage_commit",
    "store_object",
    "verify_commit_graph",
    "write_current",
]

PUBLICATION_PROTOCOL_VERSION = "v1"
OBJECT_KINDS = ("raw", "checksum", "normalized")


class PublicationError(QuantaraError):
    error_id = ATOMIC_PROMOTION_FAILURE


class ObjectCollision(PublicationError):
    error_id = MANIFEST_INCONSISTENCY


class InvalidPointer(PublicationError):
    error_id = MANIFEST_INCONSISTENCY


def object_path(data_root: Path, kind: str, digest: str) -> Path:
    if kind not in OBJECT_KINDS:
        raise PublicationError(f"unknown object kind {kind!r}")
    return Path(data_root) / "objects" / kind / "sha256" / digest


@dataclass(frozen=True)
class StoredObject:
    """Result of one content-addressed object write: the address and whether
    THIS call created the object (False means an identical object was
    deduplicated and the stored bytes were left untouched)."""

    sha256: str
    created: bool


def store_object(
    data_root: Path, kind: str, payload: bytes, digest: str | None = None
) -> StoredObject:
    """Atomically create a content-addressed object and report ownership.

    A unique temporary file is fully written and synced before ``os.link``
    atomically claims the final path without replacement. If another publisher
    wins that claim, its retained bytes are authenticated before this call
    reports deduplication. A forced address remains collision-only on reuse,
    preserving the original ``put_object`` contract.
    """
    computed = hashlib.sha256(payload).hexdigest()
    address = digest or computed
    target = object_path(data_root, kind, address)
    target.parent.mkdir(parents=True, exist_ok=True)

    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target.parent,
            prefix=f".{address}.",
            suffix=".part",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

        try:
            os.link(temporary, target)
        except FileExistsError:
            if digest is None and target.read_bytes() == payload:
                return StoredObject(sha256=address, created=False)
            raise ObjectCollision(
                f"object address {address} already holds different bytes"
            ) from None
        return StoredObject(sha256=address, created=True)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def put_object(
    data_root: Path, kind: str, payload: bytes, digest: str | None = None
) -> str:
    """Write-once content-addressed storage; same bytes dedupe, different
    bytes forced under one address are a hard collision failure. Returns the
    content address."""
    return store_object(data_root, kind, payload, digest).sha256


def stage_commit(
    dataset_dir: Path, attempt_id: str, files: dict[str, bytes]
) -> Path:
    staging = dataset_dir / "commits" / f".staging-{attempt_id}"
    staging.mkdir(parents=True, exist_ok=True)
    for name, blob in files.items():
        target = staging / name
        with open(target, "wb") as handle:
            handle.write(blob)
            handle.flush()
            os.fsync(handle.fileno())
    return staging


def publish_commit(staging_dir: Path, commits_dir: Path, content_hash: str) -> Path:
    target = commits_dir / content_hash
    if target.exists():
        raise PublicationError(f"commit path already exists: {target}")
    marker = staging_dir / "COMMITTED"
    with open(marker, "wb") as handle:
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.rename(staging_dir, target)
    except OSError as exc:
        raise PublicationError(f"atomic rename failed: {exc}") from exc
    return target


@dataclass(frozen=True)
class CurrentPointer:
    dataset_id: str
    commit: str
    manifest_sha256: str


def write_current(dataset_dir: Path, commit_hash: str, manifest_digest: str) -> None:
    pointer = {
        "publication_protocol_version": PUBLICATION_PROTOCOL_VERSION,
        "commit": commit_hash,
        "manifest_sha256": manifest_digest,
    }
    dataset_dir.mkdir(parents=True, exist_ok=True)
    final = dataset_dir / "current.json"
    tmp = dataset_dir / "current.json.tmp"
    tmp.write_text(json.dumps(pointer, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, final)


def verify_commit_graph(data_root: Path, commit_dir: Path) -> dict:
    marker = commit_dir / "COMMITTED"
    content_path = commit_dir / "content.json"
    if not marker.exists() or not content_path.exists():
        raise PublicationError(f"incomplete commit directory: {commit_dir}")
    try:
        content = json.loads(content_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise PublicationError(f"invalid content.json: {exc}") from exc
    if not isinstance(content, dict):
        raise PublicationError("content.json must be a JSON object")
    refs = content.get("object_refs", [])
    if not isinstance(refs, list):
        raise PublicationError("content.json object_refs must be a list")
    for ref in refs:
        if (
            not isinstance(ref, dict)
            or set(ref) != {"kind", "sha256"}
            or not isinstance(ref["kind"], str)
            or not isinstance(ref["sha256"], str)
        ):
            raise PublicationError(
                'content.json object_refs entries must be {"kind", '
                '"sha256"} string mappings'
            )
    for ref in refs:
        path = object_path(Path(data_root), ref["kind"], ref["sha256"])
        if not path.exists():
            raise PublicationError(f"referenced object missing: {path}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != ref["sha256"]:
            raise PublicationError(
                f"object hash drift at {path}: {actual} != {ref['sha256']}"
            )
    return content


def read_and_verify_current(dataset_dir: Path, data_root: Path) -> dict:
    pointer_path = dataset_dir / "current.json"
    if not pointer_path.exists():
        raise InvalidPointer(f"no current.json under {dataset_dir}")
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise InvalidPointer(f"invalid current.json: {exc}") from exc
    if not isinstance(pointer, dict):
        raise InvalidPointer("current.json must be a JSON object")
    commit_dir = dataset_dir / "commits" / pointer.get("commit", "")
    if not pointer.get("commit") or not commit_dir.is_dir():
        raise InvalidPointer(
            f"current.json points to missing commit {pointer.get('commit')!r}"
        )
    content = verify_commit_graph(Path(data_root), commit_dir)
    return {"commit": pointer["commit"], **content}


def existing_commit_matches(
    data_root: Path, commit_dir: Path, evidence: dict, keys: tuple[str, ...] | None = None
) -> bool:
    """Idempotency check: every identity field must verify against the
    retained commit; any drift means this is NOT a no-op.

    ``keys`` optionally overrides the compared key set; the default preserves
    slice 001 behavior byte-for-byte. Derivation extends the keys with
    ``derived_from`` so a rerun also verifies the parent lineage binding.
    """
    if keys is None:
        keys = (
            "source_sha256",
            "descriptor_sha256",
            "schema_fingerprint",
            "parser_version",
            "canonical_content_hash",
            "quality_identity",
            "object_refs",
        )
    try:
        content = verify_commit_graph(Path(data_root), commit_dir)
    except QuantaraError:
        return False
    return all(content.get(key) == evidence.get(key) for key in keys)
