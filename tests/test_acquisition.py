"""Acquisition tests: checksum grammar, verification, reuse, retries,
redirect allow-listing, size caps, and quarantine (spec §§4.1, 14.3, 14.4,
15.2). All network behavior is simulated offline via httpx.MockTransport."""

from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest

from conftest import VALID_DESCRIPTOR_YAML, write_text
from quantara.acquisition import (
    MAX_ATTEMPTS,
    Acquirer,
    ChecksumMismatch,
    DownloadFailed,
    InvalidChecksumDocument,
    NonAllowlistedHost,
    parse_checksum_document,
    transport_retry_kind,
)
from quantara.descriptor import load_descriptor

ARCHIVE_BYTES = b"fake-zip-bytes-" * 100
ARCHIVE_SHA = hashlib.sha256(ARCHIVE_BYTES).hexdigest()
CHECKSUM_DOC = f"{ARCHIVE_SHA}  BTCUSDT-1m-2024-01.zip\n"


@pytest.fixture()
def descriptor(tmp_path: Path):
    return load_descriptor(write_text(tmp_path / "cfg", VALID_DESCRIPTOR_YAML))


@pytest.fixture()
def good_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".CHECKSUM"):
            return httpx.Response(200, text=CHECKSUM_DOC)
        return httpx.Response(200, content=ARCHIVE_BYTES)

    return httpx.MockTransport(handler)


def make(tmp_path: Path, descriptor, transport, **kwargs) -> Acquirer:
    return Acquirer(
        descriptor=descriptor,
        data_root=tmp_path,
        attempt_id="20260824T000000Z-test",
        transport=transport,
        sleeper=lambda _seconds: None,
        **kwargs,
    )


def test_checksum_document_grammar_variants() -> None:
    assert parse_checksum_document(CHECKSUM_DOC, "BTCUSDT-1m-2024-01.zip") == ARCHIVE_SHA
    assert (
        parse_checksum_document(CHECKSUM_DOC.rstrip("\n"), "BTCUSDT-1m-2024-01.zip")
        == ARCHIVE_SHA
    )
    assert (
        parse_checksum_document(
            f"{ARCHIVE_SHA}  BTCUSDT-1m-2024-01.zip\r\n", "BTCUSDT-1m-2024-01.zip"
        )
        == ARCHIVE_SHA
    )


@pytest.mark.parametrize(
    "text",
    [
        f"{ARCHIVE_SHA}  WRONG-NAME.zip\n",
        f"{ARCHIVE_SHA.upper()}  BTCUSDT-1m-2024-01.zip\n",
        f"{ARCHIVE_SHA[:-1]}  BTCUSDT-1m-2024-01.zip\n",
        f"{ARCHIVE_SHA}x  BTCUSDT-1m-2024-01.zip\n",
        f"{ARCHIVE_SHA} BTCUSDT-1m-2024-01.zip\n",
        "",
        "garbage\n",
    ],
)
def test_invalid_checksum_documents(text: str) -> None:
    with pytest.raises(InvalidChecksumDocument):
        parse_checksum_document(text, "BTCUSDT-1m-2024-01.zip")


def test_successful_acquisition_promotes_objects(
    tmp_path: Path, descriptor, good_transport
) -> None:
    evidence = make(tmp_path, descriptor, good_transport).acquire()
    assert evidence.zip_sha256 == ARCHIVE_SHA
    assert evidence.reused_zip is False
    assert (tmp_path / "objects" / "raw" / "sha256" / ARCHIVE_SHA).read_bytes() == (
        ARCHIVE_BYTES
    )
    checksum_sha = hashlib.sha256(CHECKSUM_DOC.encode()).hexdigest()
    assert (tmp_path / "objects" / "checksum" / "sha256" / checksum_sha).exists()


def test_matching_retained_artifact_is_reused_byte_for_byte(
    tmp_path: Path, descriptor, good_transport
) -> None:
    raw_dir = tmp_path / "objects" / "raw" / "sha256"
    raw_dir.mkdir(parents=True)
    (raw_dir / ARCHIVE_SHA).write_bytes(ARCHIVE_BYTES)
    calls: list[str] = []

    def counting_handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path.endswith(".CHECKSUM"):
            return httpx.Response(200, text=CHECKSUM_DOC)
        return httpx.Response(200, content=ARCHIVE_BYTES)

    evidence = make(
        tmp_path, descriptor, httpx.MockTransport(counting_handler)
    ).acquire()
    assert evidence.reused_zip is True
    assert all(not url.endswith(".zip") for url in calls)  # zip never downloaded


def test_local_vs_official_mismatch_raises_and_quarantines(
    tmp_path: Path, descriptor
) -> None:
    def bad_zip_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".CHECKSUM"):
            return httpx.Response(200, text=CHECKSUM_DOC)
        return httpx.Response(200, content=b"different-bytes")

    with pytest.raises(ChecksumMismatch):
        make(tmp_path, descriptor, httpx.MockTransport(bad_zip_handler)).acquire()
    quarantined = list((tmp_path / "quarantine").iterdir())
    assert len(quarantined) == 1
    assert (quarantined[0] / "reason.json").exists()


def test_retry_only_for_eligible_transient_failures(tmp_path: Path, descriptor) -> None:
    state = {"zip_calls": 0}

    def flaky_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".CHECKSUM"):
            return httpx.Response(200, text=CHECKSUM_DOC)
        state["zip_calls"] += 1
        if state["zip_calls"] == 1:
            raise httpx.ConnectTimeout("transient")
        return httpx.Response(200, content=ARCHIVE_BYTES)

    evidence = make(tmp_path, descriptor, httpx.MockTransport(flaky_handler)).acquire()
    assert evidence.zip_sha256 == ARCHIVE_SHA
    assert state["zip_calls"] == 2
    assert any(r.kind == "connect_timeout" for r in evidence.retry_evidence)

def test_deterministic_failures_are_never_retried(tmp_path: Path, descriptor) -> None:
    calls: list[int] = []

    def not_found_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".CHECKSUM"):
            return httpx.Response(200, text=CHECKSUM_DOC)
        calls.append(1)
        return httpx.Response(404, text="nope")

    with pytest.raises(DownloadFailed):
        make(tmp_path, descriptor, httpx.MockTransport(not_found_handler)).acquire()
    assert len(calls) == 1


# D09: retry eligibility is decided by exception type, not by message wording.
# F-S01B-1 was a real 60-period backfill failure: httpx raises
# RemoteProtocolError("Server disconnected without sending a response.") when a
# server drops the connection, whose message contains no "reset", so the previous
# substring test gave it zero retries.
@pytest.mark.parametrize(
    ("exc", "kind"),
    [
        (httpx.RemoteProtocolError("Server disconnected without sending a response."),
         "dropped_connection"),
        (httpx.RemoteProtocolError("connection reset by peer"), "dropped_connection"),
        (httpx.ConnectError("connection refused"), "dropped_connection"),
        (httpx.ConnectTimeout("timed out"), "connect_timeout"),
        (httpx.ReadTimeout("timed out"), "connect_timeout"),
        (httpx.PoolTimeout("pool exhausted"), "connect_timeout"),
        (httpx.ReadError("connection reset"), "connection_reset"),
    ],
)
def test_transient_transport_failures_retry_regardless_of_message(
    tmp_path: Path, descriptor, exc: Exception, kind: str,
) -> None:
    state = {"zip_calls": 0}

    def flaky_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".CHECKSUM"):
            return httpx.Response(200, text=CHECKSUM_DOC)
        state["zip_calls"] += 1
        if state["zip_calls"] == 1:
            raise exc
        return httpx.Response(200, content=ARCHIVE_BYTES)

    evidence = make(tmp_path, descriptor, httpx.MockTransport(flaky_handler)).acquire()
    assert evidence.zip_sha256 == ARCHIVE_SHA
    assert state["zip_calls"] == 2, "a transient transport failure must be retried"
    assert any(r.kind == kind for r in evidence.retry_evidence)


def test_persistent_dropped_connection_exhausts_max_attempts(
    tmp_path: Path, descriptor,
) -> None:
    calls: list[int] = []

    def dropping_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".CHECKSUM"):
            return httpx.Response(200, text=CHECKSUM_DOC)
        calls.append(1)
        raise httpx.RemoteProtocolError("Server disconnected without sending a response.")

    acquirer = make(tmp_path, descriptor, httpx.MockTransport(dropping_handler))
    with pytest.raises(DownloadFailed):
        acquirer.acquire()
    assert len(calls) == MAX_ATTEMPTS
    assert sum(r.kind == "dropped_connection" for r in acquirer.retry_evidence) == MAX_ATTEMPTS


def test_unrecognised_transport_error_is_still_not_retried(
    tmp_path: Path, descriptor,
) -> None:
    """Widening eligibility must not turn every transport error into a retry."""
    for exc in (
        httpx.UnsupportedProtocol("scheme not supported"),
        httpx.ProxyError("bad proxy"),
        httpx.ReadError("some other read problem"),
    ):
        calls: list[int] = []

        def unsupported_handler(
            request: httpx.Request, exc=exc, calls=calls,
        ) -> httpx.Response:
            if request.url.path.endswith(".CHECKSUM"):
                return httpx.Response(200, text=CHECKSUM_DOC)
            calls.append(1)
            raise exc

        acquirer = make(tmp_path / type(exc).__name__, descriptor,
                        httpx.MockTransport(unsupported_handler))
        with pytest.raises(DownloadFailed):
            acquirer.acquire()
        assert len(calls) == 1, f"{type(exc).__name__} must not be retried"
        assert acquirer.retry_evidence == []


def test_series_and_dataset_acquirers_share_one_retry_classifier() -> None:
    """F-S01B-1 existed twice: both call sites must use the same function."""
    from quantara import series_acquisition

    assert series_acquisition.transport_retry_kind is transport_retry_kind
    assert transport_retry_kind(
        httpx.RemoteProtocolError("Server disconnected without sending a response.")
    ) == "dropped_connection"
    assert transport_retry_kind(httpx.UnsupportedProtocol("nope")) is None
    assert transport_retry_kind(ValueError("not a transport error")) is None


def test_redirect_to_non_allowlisted_host_hard_fails(
    tmp_path: Path, descriptor
) -> None:
    def redirecting_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".CHECKSUM"):
            return httpx.Response(200, text=CHECKSUM_DOC)
        if request.url.host == "data.binance.vision":
            return httpx.Response(
                302, headers={"Location": "https://evil.example.com/payload"}
            )
        return httpx.Response(200, content=ARCHIVE_BYTES)

    with pytest.raises(NonAllowlistedHost):
        make(tmp_path, descriptor, httpx.MockTransport(redirecting_handler)).acquire()


def test_allowed_host_redirect_is_followed(tmp_path: Path, descriptor) -> None:
    state = {"zip_calls": 0}

    def redirecting_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".CHECKSUM"):
            return httpx.Response(200, text=CHECKSUM_DOC)
        state["zip_calls"] += 1
        if state["zip_calls"] == 1:
            return httpx.Response(
                302,
                headers={
                    "Location": "https://data.binance.vision/mirror/BTCUSDT-1m-2024-01.zip"
                },
            )
        return httpx.Response(200, content=ARCHIVE_BYTES)

    evidence = make(
        tmp_path, descriptor, httpx.MockTransport(redirecting_handler)
    ).acquire()
    assert evidence.zip_sha256 == ARCHIVE_SHA
    assert len(evidence.redirect_hops) == 1


def test_excessive_redirects_are_capped(tmp_path: Path, descriptor) -> None:
    def always_redirect_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".CHECKSUM"):
            return httpx.Response(200, text=CHECKSUM_DOC)
        return httpx.Response(
            302, headers={"Location": "https://data.binance.vision/loop"}
        )

    with pytest.raises(DownloadFailed):
        make(
            tmp_path, descriptor, httpx.MockTransport(always_redirect_handler)
        ).acquire()


def test_size_cap_enforced_during_transfer(
    tmp_path: Path, descriptor, good_transport
) -> None:
    with pytest.raises(DownloadFailed):
        make(
            tmp_path,
            descriptor,
            good_transport,
            max_zip_bytes=len(ARCHIVE_BYTES) - 1,
        ).acquire()
