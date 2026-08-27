"""Dispatch contract for the optional Rust canonical-hash kernel."""

from __future__ import annotations

import importlib
import random

import pytest

from quantara import hashing


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


def test_kernel_module_importable() -> None:
    kernel = importlib.import_module("quantara_kernel")

    for name in (
        "hash_canonical_rows",
        "hash_research_rows",
        "KernelHashPayloadError",
        "CONTENT_HASH_DOMAIN",
        "RESEARCH_CONTENT_HASH_DOMAIN",
    ):
        assert hasattr(kernel, name)


def test_default_mode_uses_kernel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QUANTARA_HASH_KERNEL", raising=False)

    assert hashing.active_hash_kernel() == "rust"


def test_forced_python_mode_matches_kernel_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _canonical_rows(50)
    fingerprint = hashing.schema_fingerprint()
    monkeypatch.delenv("QUANTARA_HASH_KERNEL", raising=False)
    kernel_digest = hashing.canonical_content_hash(fingerprint, rows)

    monkeypatch.setenv("QUANTARA_HASH_KERNEL", "python")
    assert hashing.active_hash_kernel() == "python"
    assert hashing.canonical_content_hash(fingerprint, rows) == kernel_digest


def test_explicit_rust_without_kernel_raises_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hashing, "_KERNEL_AVAILABLE", False)
    monkeypatch.setenv("QUANTARA_HASH_KERNEL", "rust")

    with pytest.raises(RuntimeError):
        hashing.canonical_content_hash(hashing.schema_fingerprint(), _canonical_rows(1))


def test_invalid_mode_value_falls_back_to_auto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUANTARA_HASH_KERNEL", "banana")

    assert hashing.active_hash_kernel() == "rust"
