"""Digest parity between the Rust kernel and retained Python oracle."""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

import pytest
import quantara_kernel

from quantara import hashing
from quantara.jcs import canonicalize as jcs_canonicalize

GOLDEN_EXPECTED = Path(__file__).parent / "fixtures" / "golden" / "expected.json"
GOLDEN_DIGEST = "8f78cd55e6ada9539a5e88c4debcdea05cab7d7c1c5adb3d43944ef3d290feab"


def _join_reference(domain: str, fingerprint: str, rows: list[list[object]]) -> str:
    parts = [
        domain.encode("ascii"),
        b"\x00",
        fingerprint.lower().encode("ascii"),
        b"\n",
    ]
    for row in rows:
        parts.append(jcs_canonicalize(row).encode("utf-8"))
        parts.append(b"\n")
    return hashlib.sha256(b"".join(parts)).hexdigest()


def _canonical_rows(row_count: int, seed: int = 20260827) -> list[list[object]]:
    generator = random.Random(seed)
    rows: list[list[object]] = []
    identity = [
        "binance",
        "usd_m_futures",
        "binance:usd_m_futures:BTCUSDT:perpetual",
        "BTCUSDT",
        "BTC",
        "USDT",
        "USDT",
        "perpetual",
        "1m",
        "binance_usdm_kline_1m_v1",
    ]
    start_ms = 1_704_067_200_000
    for index in range(row_count):
        open_time = start_ms + index * 60_000
        price = 42_000 + generator.randrange(0, 1_000)
        rows.append(
            [
                *identity,
                open_time,
                open_time + 59_999,
                open_time + 60_000,
                f"{price}.123456789012345678",
                f"{price + 10}.000000000000000000",
                f"{price - 10}.000000000000000000",
                f"{price}.987654321098765432",
                f"{1 + index % 100}.000000000000000000",
                f"{100_000 + index}.000000000000000000",
                1 + generator.randrange(0, 10_000),
                f"{index % 10}.500000000000000000",
                f"{50_000 + index}.000000000000000000",
                "0",
            ]
        )
    return rows


def _research_rows(row_count: int, seed: int = 20260827) -> list[list[object]]:
    generator = random.Random(seed)
    rows: list[list[object]] = []
    start_ms = 1_704_067_200_000
    for index in range(row_count):
        decimal_value = f"{generator.randrange(-999, 1_000)}.{index % 10**18:018d}"
        rows.append(
            [
                start_ms + index * 3_600_000,
                None if index % 11 == 0 else decimal_value,
                decimal_value,
                None if index % 13 == 0 else decimal_value,
                decimal_value,
                None if index % 17 == 0 else decimal_value,
                None if index % 19 == 0 else (-1, 0, 1)[index % 3],
            ]
        )
    return rows


def _assert_rust_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QUANTARA_HASH_KERNEL", raising=False)
    assert hashing.active_hash_kernel() == "rust"


def test_golden_canonical_digest_under_kernel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = json.loads(GOLDEN_EXPECTED.read_text(encoding="utf-8"))
    rows = expected["rows"]
    fingerprint = expected["schema_fingerprint"]
    _assert_rust_mode(monkeypatch)

    assert hashing.canonical_content_hash(fingerprint, rows) == GOLDEN_DIGEST
    monkeypatch.setenv("QUANTARA_HASH_KERNEL", "python")
    assert hashing.canonical_content_hash(fingerprint, rows) == GOLDEN_DIGEST


def test_canonical_parity_seeded_corpus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _canonical_rows(300)
    fingerprint = hashing.schema_fingerprint().upper()
    reference = _join_reference(hashing.CONTENT_HASH_DOMAIN, fingerprint, rows)
    _assert_rust_mode(monkeypatch)

    kernel_digest = hashing.canonical_content_hash(fingerprint, rows)
    monkeypatch.setenv("QUANTARA_HASH_KERNEL", "python")
    python_digest = hashing.canonical_content_hash(fingerprint, rows)
    assert kernel_digest == python_digest == reference


def test_research_parity_seeded_corpus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _research_rows(300)
    fingerprint = hashing.research_schema_fingerprint()
    reference = _join_reference(hashing.RESEARCH_CONTENT_HASH_DOMAIN, fingerprint, rows)
    _assert_rust_mode(monkeypatch)

    kernel_digest = hashing.research_content_hash(fingerprint, rows)
    monkeypatch.setenv("QUANTARA_HASH_KERNEL", "python")
    python_digest = hashing.research_content_hash(fingerprint, rows)
    assert kernel_digest == python_digest == reference


def test_parity_randomized_property_battery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = random.Random(20260827)
    strings = [
        "",
        "plain",
        'quote"slash\\',
        "line\nfeed\tand\rreturn",
        "\x00\x01\b\f",
        "café 東京 🚀",
        "x" * 257,
    ]
    integers = [0, -1, 2**80, -(2**130), True, False]
    values: list[object] = [*strings, *integers]
    rows = [
        [generator.choice(values) for _ in range(len(hashing.CANONICAL_COLUMNS))]
        for _ in range(100)
    ]
    fingerprint = "FeAb7D2Bb40De94E3621D6Ff9847363EdDd52B7fD8Cd3C07F66DeF664Da614C8"
    _assert_rust_mode(monkeypatch)

    kernel_digest = hashing.canonical_content_hash(fingerprint, rows)
    monkeypatch.setenv("QUANTARA_HASH_KERNEL", "python")
    python_digest = hashing.canonical_content_hash(fingerprint, rows)
    assert kernel_digest == python_digest


def test_parity_large_streaming_corpus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _canonical_rows(30_000)
    fingerprint = hashing.schema_fingerprint()
    reference = _join_reference(hashing.CONTENT_HASH_DOMAIN, fingerprint, rows)
    _assert_rust_mode(monkeypatch)

    kernel_digest = hashing.canonical_content_hash(
        fingerprint, (row for row in rows)
    )
    monkeypatch.setenv("QUANTARA_HASH_KERNEL", "python")
    python_digest = hashing.canonical_content_hash(fingerprint, rows)
    assert kernel_digest == python_digest == reference


def test_kernel_domains_match_python_constants() -> None:
    assert quantara_kernel.CONTENT_HASH_DOMAIN == hashing.CONTENT_HASH_DOMAIN
    assert (
        quantara_kernel.RESEARCH_CONTENT_HASH_DOMAIN
        == hashing.RESEARCH_CONTENT_HASH_DOMAIN
    )
