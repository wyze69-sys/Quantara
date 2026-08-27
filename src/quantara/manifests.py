"""Manifest writer (component 4).

Immutable run evidence: dataset manifests recording source identity, hashes,
schema/parser identities, temporal bounds, row counts, output artifacts,
environment evidence, legal status, and quality results; attempt manifests
recording unique IDs (UTC basic timestamp + UUIDv4), artifact dispositions,
bounded retry evidence without secrets, and terminal results that never
participate in content equality (spec §§4.1, 13.1–13.2).
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

__all__ = [
    "PARSER_VERSION",
    "attempt_id_now",
    "build_dataset_manifest",
    "environment_evidence",
    "new_attempt_manifest",
    "write_json",
]

PARSER_VERSION = "binance_kline_csv_v1"
PUBLICATION_PROTOCOL_VERSION = "v1"
TERMINAL_RESULTS = ("PUBLISHED", "VERIFIED_NO_OP", "QUARANTINED", "FAILED", "BLOCKED")


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def attempt_id_now() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4()}"


def environment_evidence(repo_root: Path) -> dict:
    import pyarrow

    evidence = {
        "python": platform.python_version(),
        "pyarrow": pyarrow.__version__,
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
    }
    lock = Path(repo_root) / "uv.lock"
    if lock.exists():
        evidence["uv_lock_sha256"] = hashlib.sha256(lock.read_bytes()).hexdigest()
    try:
        import subprocess

        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        evidence["git_head"] = head
    except Exception:  # pragma: no cover - git may be unavailable
        evidence["git_head"] = None
    return evidence


def build_dataset_manifest(**fields) -> dict:
    manifest = dict(fields)
    manifest.update(
        {
            "hash_contract": "hash_contract_v1",
            "publication_protocol_version": PUBLICATION_PROTOCOL_VERSION,
            "parser_version": fields.get("parser_version", PARSER_VERSION),
            "written_at_utc": _utc_now(),
        }
    )
    return manifest


def new_attempt_manifest(
    *,
    terminal_result: str,
    artifact_dispositions: dict[str, str],
    retry_evidence: list[dict],
    http_statuses: list[int],
    referenced_commit: str | None,
    diagnostics: list[str],
    repo_root: Path,
    attempt_id: str | None = None,
) -> dict:
    """Build one immutable attempt manifest.

    ``attempt_id`` lets an owning pipeline propagate its single invocation
    identity (the same ID that names staging paths and lock ownership) into
    the written manifest. When omitted, a fresh ID is generated for backward
    compatibility with other pipeline callers.
    """
    if terminal_result not in TERMINAL_RESULTS:
        raise ValueError(f"unknown terminal result {terminal_result!r}")
    return {
        "attempt_id": attempt_id if attempt_id is not None else attempt_id_now(),
        "started_at_utc": _utc_now(),
        "finished_at_utc": _utc_now(),
        "terminal_result": terminal_result,
        "artifact_dispositions": artifact_dispositions,
        "retry_evidence": retry_evidence,
        "http_statuses": http_statuses,
        "referenced_commit": referenced_commit,
        "diagnostics": diagnostics,
        "code_revision": environment_evidence(repo_root).get("git_head"),
        "runtime": {"python": platform.python_version(), "executable": sys.executable},
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
