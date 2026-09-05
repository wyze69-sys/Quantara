"""Verified artifact acquisition.

Streams the official ZIP and checksum documents into unique staging paths
under data/staging/<attempt_id>/ with a running SHA-256 and enforced size
caps; parses the checksum document against a strict grammar; verifies local
vs official hashes before any promotion; reuses matching retained artifacts
byte-for-byte; quarantines conflicting evidence with reason, hashes, and
timestamps; retries only eligible transient failures with bounded backoff;
and follows redirects hop-by-hop against the descriptor's allow-listed hosts.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx

from quantara.descriptor import DatasetDescriptor
from quantara.errors import (
    CHECKSUM_MISMATCH,
    DOWNLOAD_FAILED_AFTER_RETRIES,
    INVALID_CHECKSUM_DOCUMENT,
    NON_ALLOWLISTED_SOURCE,
    QuantaraError,
)
from quantara.hashing import sha256_hex

__all__ = [
    "Acquirer",
    "AcquisitionEvidence",
    "ChecksumMismatch",
    "DownloadFailed",
    "InvalidChecksumDocument",
    "NonAllowlistedHost",
    "QuarantineRecord",
    "parse_checksum_document",
    "quarantine",
    "transport_retry_kind",
]

MAX_ATTEMPTS = 3
MAX_REDIRECT_HOPS = 5
BACKOFF_SECONDS = (1.0, 2.0, 4.0)
DEFAULT_MAX_ZIP_BYTES = 256 * 1024 * 1024  # policy bound; real archive ≈ tens of MB
_CHUNK = 1 << 20
RETRYABLE_STATUS = frozenset({429, 502, 503, 504})


class InvalidChecksumDocument(QuantaraError):
    error_id = INVALID_CHECKSUM_DOCUMENT


class ChecksumMismatch(QuantaraError):
    error_id = CHECKSUM_MISMATCH


class DownloadFailed(QuantaraError):
    error_id = DOWNLOAD_FAILED_AFTER_RETRIES


class NonAllowlistedHost(QuantaraError):
    error_id = NON_ALLOWLISTED_SOURCE


def parse_checksum_document(text: str, filename: str) -> str:
    """Strict grammar: ^[0-9a-f]{64}  <filename>\r?\n?$ — nothing else."""
    pattern = re.compile(rf"^([0-9a-f]{{64}})  {re.escape(filename)}\r?\n?$", re.DOTALL)
    match = pattern.match(text)
    if match is None:
        raise InvalidChecksumDocument(
            f"checksum document does not match strict grammar for {filename}"
        )
    return match.group(1)


@dataclass(frozen=True)
class QuarantineRecord:
    directory: Path
    reason: str


def quarantine(
    data_root: Path,
    reason: str,
    payloads: dict[str, bytes],
    extra: dict | None = None,
) -> QuarantineRecord:
    """Retain diagnostic artifacts under data/quarantine/ with evidence."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = data_root / "quarantine" / f"{stamp}-{reason}"
    target.mkdir(parents=True, exist_ok=True)
    for name, blob in payloads.items():
        (target / name).write_bytes(blob)
    evidence = {
        "reason": reason,
        "timestamp_utc": stamp,
        "payloads": {name: sha256_hex(blob) for name, blob in payloads.items()},
        **(extra or {}),
    }
    (target / "reason.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8"
    )
    return QuarantineRecord(directory=target, reason=reason)


@dataclass(frozen=True)
class RetryEvidence:
    kind: str
    detail: str


@dataclass
class AcquisitionEvidence:
    zip_path: Path
    zip_sha256: str
    zip_size: int
    checksum_document_path: Path
    checksum_document_sha256: str
    official_digest: str
    reused_zip: bool
    reused_checksum: bool
    retry_evidence: list[RetryEvidence] = field(default_factory=list)
    redirect_hops: list[str] = field(default_factory=list)
    http_statuses: list[int] = field(default_factory=list)


_ELIGIBLE_TIMEOUTS = (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.PoolTimeout)

# Transient transport classes. A dropped connection is transient regardless of how
# the underlying library words the message: RemoteProtocolError covers "Server
# disconnected without sending a response", ConnectError covers refused/unreachable
# attempts that succeed on retry. Classification is by exception type, never by
# substring-matching a message, so wording changes cannot silently disable retries.
_ELIGIBLE_TRANSPORT = (httpx.RemoteProtocolError, httpx.ConnectError)


def transport_retry_kind(exc: BaseException) -> str | None:
    """Name the retry-eligible transport class, or None for a deterministic error.

    Complete classifier for every retry-eligible transport failure, so a caller
    with one combined ``except httpx.TransportError`` handler behaves the same as
    one with a separate timeout clause.
    """
    if not isinstance(exc, httpx.TransportError):
        return None
    if isinstance(exc, _ELIGIBLE_TIMEOUTS):
        return "connect_timeout"
    if isinstance(exc, _ELIGIBLE_TRANSPORT):
        return "dropped_connection"
    # Retain the historical reset path for TransportError subclasses outside the
    # eligible set; some backends surface a reset without a dedicated class.
    return "connection_reset" if "reset" in str(exc).lower() else None


class Acquirer:
    """Downloads and verifies the two official artifacts for one attempt."""

    def __init__(
        self,
        descriptor: DatasetDescriptor,
        data_root: Path,
        attempt_id: str,
        transport: httpx.BaseTransport | None = None,
        sleeper=None,
        max_zip_bytes: int = DEFAULT_MAX_ZIP_BYTES,
    ) -> None:
        self.descriptor = descriptor
        self.data_root = Path(data_root)
        self.attempt_id = attempt_id
        self.transport = transport
        self._sleep = sleeper if sleeper is not None else time.sleep
        self.max_zip_bytes = max_zip_bytes
        self.retry_evidence: list[RetryEvidence] = []
        self.redirect_hops: list[str] = []
        self.http_statuses: list[int] = []

    # ------------------------------------------------------------------ API

    def acquire(self) -> AcquisitionEvidence:
        staging = self.data_root / "staging" / self.attempt_id
        staging.mkdir(parents=True, exist_ok=True)
        archive_name = self.descriptor.archive_url.rsplit("/", 1)[-1]

        checksum_path = staging / f"{archive_name}.CHECKSUM"
        checksum_reused = checksum_path.exists()
        if not checksum_reused:
            self._download(self.descriptor.checksum_url, checksum_path)
        document_text = checksum_path.read_text(encoding="utf-8")
        official = parse_checksum_document(document_text, archive_name)

        raw_dir = self.data_root / "objects" / "raw" / "sha256"
        retained = raw_dir / official
        if retained.exists():
            retained_bytes = retained.read_bytes()
            actual = sha256_hex(retained_bytes)
            if actual != official:
                quarantine(
                    self.data_root,
                    "retained_artifact_corruption",
                    {"artifact": retained_bytes},
                    {"expected_sha256": official, "local_sha256": actual},
                )
                raise ChecksumMismatch(
                    f"retained artifact hash {actual} differs from official {official}"
                )
            zip_path, zip_sha, zip_size, reused = (
                retained,
                official,
                len(retained_bytes),
                True,
            )
        else:
            staged_zip = staging / archive_name
            zip_bytes = self._download(
                self.descriptor.archive_url, staged_zip
            )
            local_hash = sha256_hex(zip_bytes)
            if local_hash != official:
                quarantine(
                    self.data_root,
                    "checksum_mismatch",
                    {
                        archive_name: zip_bytes,
                        "checksum_document.txt": document_text.encode("utf-8"),
                    },
                    {"official_sha256": official, "local_sha256": local_hash},
                )
                raise ChecksumMismatch(
                    f"local SHA-256 {local_hash} differs from official {official}"
                )
            raw_dir.mkdir(parents=True, exist_ok=True)
            if retained.exists():
                if retained.read_bytes() == zip_bytes:
                    staged_zip.unlink()
                else:
                    raise DownloadFailed(
                        f"content-address collision with different bytes at {retained}"
                    )
            else:
                os.replace(staged_zip, retained)
            zip_path, zip_sha, zip_size, reused = (
                retained,
                local_hash,
                len(zip_bytes),
                False,
            )

        checksum_sha = sha256_hex(checksum_path.read_bytes())
        checksum_store = self.data_root / "objects" / "checksum" / "sha256"
        checksum_store.mkdir(parents=True, exist_ok=True)
        checksum_target = checksum_store / checksum_sha
        if not checksum_target.exists():
            os.replace(checksum_path, checksum_target)

        return AcquisitionEvidence(
            zip_path=zip_path,
            zip_sha256=zip_sha,
            zip_size=zip_size,
            checksum_document_path=checksum_target,
            checksum_document_sha256=checksum_sha,
            official_digest=official,
            reused_zip=reused,
            reused_checksum=checksum_reused,
            retry_evidence=list(self.retry_evidence),
            redirect_hops=list(self.redirect_hops),
            http_statuses=list(self.http_statuses),
        )

    # ------------------------------------------------------------- transport

    def _request_with_retries(self, url: str) -> httpx.Response:
        last_eligible: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                with httpx.Client(
                    transport=self.transport, follow_redirects=False, timeout=30.0
                ) as client:
                    response = client.get(url)
                self.http_statuses.append(response.status_code)
                if response.status_code in RETRYABLE_STATUS:
                    last_eligible = DownloadFailed(
                        f"{url} returned retryable status {response.status_code}"
                    )
                    if attempt < MAX_ATTEMPTS - 1:
                        self._backoff(attempt)
                        continue
                    raise last_eligible
                return response
            except _ELIGIBLE_TIMEOUTS as exc:
                self.retry_evidence.append(RetryEvidence("connect_timeout", str(exc)))
                last_eligible = exc
                if attempt < MAX_ATTEMPTS - 1:
                    self._backoff(attempt)
                    continue
            except httpx.TransportError as exc:
                kind = transport_retry_kind(exc)
                if kind is not None:
                    self.retry_evidence.append(RetryEvidence(kind, str(exc)))
                    last_eligible = exc
                    if attempt < MAX_ATTEMPTS - 1:
                        self._backoff(attempt)
                        continue
                raise DownloadFailed(f"{url}: {exc}") from exc
        raise DownloadFailed(
            f"{url}: exhausted {MAX_ATTEMPTS} attempts ({last_eligible})"
        )

    def _backoff(self, failed_attempt: int) -> None:
        delay = BACKOFF_SECONDS[failed_attempt] + random.uniform(0.0, 0.25)
        self.retry_evidence.append(RetryEvidence("backoff", f"{delay:.3f}s"))
        self._sleep(delay)

    def _download(self, url: str, destination: Path) -> bytes:
        is_zip = destination.suffix == ".zip"
        cap = self.max_zip_bytes if is_zip else DEFAULT_MAX_ZIP_BYTES
        hops: list[str] = [url]
        response = self._request_with_retries(url)
        while response.is_redirect:
            if len(hops) >= MAX_REDIRECT_HOPS:
                raise DownloadFailed(
                    f"{hops[0]}: exceeded {MAX_REDIRECT_HOPS} redirect hops"
                )
            location = response.headers.get("location", "")
            next_url = str(httpx.URL(url).join(location))
            parsed = httpx.URL(next_url)
            if (
                parsed.scheme != "https"
                or parsed.host not in self.descriptor.allowed_hosts
            ):
                raise NonAllowlistedHost(
                    f"redirect to non-allow-listed host blocked: {next_url}"
                )
            hops.append(next_url)
            response = self._request_with_retries(next_url)
            url = next_url
        if response.status_code != 200:
            raise DownloadFailed(f"{hops[0]}: HTTP {response.status_code}")
        hasher = hashlib.sha256()
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes(chunk_size=_CHUNK):
            total += len(chunk)
            if total > cap:
                raise DownloadFailed(
                    f"{hops[0]}: transfer exceeded size cap {cap} during streaming"
                )
            hasher.update(chunk)
            chunks.append(chunk)
        payload = b"".join(chunks)
        del hasher  # running hash verified by caller against the official digest
        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp = destination.with_name(destination.name + ".part")
        tmp.write_bytes(payload)
        os.replace(tmp, destination)
        self.redirect_hops.extend(hops[1:])
        return payload
