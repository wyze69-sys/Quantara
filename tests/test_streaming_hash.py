"""Parity and memory acceptance for streaming row-framed content hashes."""

from __future__ import annotations

import hashlib
import json
import random
import tracemalloc
from pathlib import Path

import pytest

from quantara.hashing import (
    CONTENT_HASH_DOMAIN,
    RESEARCH_CONTENT_HASH_DOMAIN,
    HashPayloadError,
    canonical_content_hash,
    research_content_hash,
    research_schema_fingerprint,
    schema_fingerprint,
)
from quantara.jcs import canonicalize

GOLDEN_EXPECTED = Path(__file__).parent / "fixtures" / "golden" / "expected.json"


def _join_reference(domain: str, fingerprint: str, rows: list[list[object]]) -> str:
    parts = [
        domain.encode("ascii"),
        b"\x00",
        fingerprint.lower().encode("ascii"),
        b"\n",
    ]
    for row in rows:
        parts.append(canonicalize(row).encode("utf-8"))
        parts.append(b"\n")
    return hashlib.sha256(b"".join(parts)).hexdigest()


def _canonical_rows(row_count: int, seed: int = 20260827) -> list[list[object]]:
    generator = random.Random(seed)
    rows = []
    start_ms = 1_704_067_200_000
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
    rows = []
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


def test_canonical_streaming_matches_join_reference() -> None:
    fingerprint = schema_fingerprint()
    golden_rows = json.loads(GOLDEN_EXPECTED.read_text(encoding="utf-8"))["rows"]
    synthetic_rows = _canonical_rows(300)

    assert canonical_content_hash(fingerprint, golden_rows) == _join_reference(
        CONTENT_HASH_DOMAIN, fingerprint, golden_rows
    )
    assert canonical_content_hash(fingerprint, synthetic_rows) == _join_reference(
        CONTENT_HASH_DOMAIN, fingerprint, synthetic_rows
    )


def test_research_streaming_matches_join_reference() -> None:
    fingerprint = research_schema_fingerprint()
    rows = _research_rows(300)

    assert research_content_hash(fingerprint, rows) == _join_reference(
        RESEARCH_CONTENT_HASH_DOMAIN, fingerprint, rows
    )


def test_content_hash_accepts_lazy_iterators() -> None:
    canonical_rows = _canonical_rows(20)
    canonical_fingerprint = schema_fingerprint()
    canonical_expected = canonical_content_hash(canonical_fingerprint, canonical_rows)
    assert canonical_content_hash(
        canonical_fingerprint, (row for row in canonical_rows)
    ) == canonical_expected
    assert canonical_content_hash(
        canonical_fingerprint, iter(tuple(canonical_rows))
    ) == canonical_expected

    research_rows = _research_rows(20)
    research_fingerprint = research_schema_fingerprint()
    research_expected = research_content_hash(research_fingerprint, research_rows)
    assert research_content_hash(
        research_fingerprint, (row for row in research_rows)
    ) == research_expected
    assert research_content_hash(
        research_fingerprint, iter(tuple(research_rows))
    ) == research_expected


def test_malformed_row_mid_stream_raises_hash_payload_error() -> None:
    canonical_rows = _canonical_rows(9)
    canonical_rows[4][13] = 1.5
    research_rows = _research_rows(9)
    research_rows[4][1] = 1.5

    cases = (
        (canonical_content_hash, schema_fingerprint(), canonical_rows),
        (research_content_hash, research_schema_fingerprint(), research_rows),
    )
    for hash_function, fingerprint, rows in cases:
        for iterable in (rows, (row for row in rows)):
            with pytest.raises(HashPayloadError) as caught:
                hash_function(fingerprint, iterable)
            assert caught.value.error_id == "manifest_inconsistency"


def test_canonical_content_hash_bounds_peak_memory() -> None:
    rows = _canonical_rows(30_000)
    fingerprint = schema_fingerprint()

    tracemalloc.start()
    tracemalloc.reset_peak()
    try:
        digest = canonical_content_hash(fingerprint, (row for row in rows))
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()

    assert peak < 4_000_000
    assert digest == _join_reference(CONTENT_HASH_DOMAIN, fingerprint, rows)


def test_research_content_hash_bounds_peak_memory() -> None:
    rows = _research_rows(50_000)
    fingerprint = research_schema_fingerprint()

    tracemalloc.start()
    tracemalloc.reset_peak()
    try:
        digest = research_content_hash(fingerprint, (row for row in rows))
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()

    assert peak < 3_000_000
    assert digest == _join_reference(RESEARCH_CONTENT_HASH_DOMAIN, fingerprint, rows)
