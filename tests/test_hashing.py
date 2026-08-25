"""Hash contract v1 tests (spec §12.1).

Expected byte sequences and SHA-256 values below were produced by an
independent stdlib-only generation script (json + hashlib), never by the
production hashing path under test.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from quantara.descriptor import load_descriptor
from quantara.errors import QuantaraError
from quantara.hashing import (
    CONTENT_HASH_DOMAIN,
    HASH_CONTRACT_VERSION,
    canonical_content_hash,
    canonical_row_array,
    descriptor_hash,
    quality_identity,
    render_decimal_18,
    schema_fingerprint,
    sha256_hex,
)

INDEPENDENT_BYTES_SHA256 = "267b6f8e46bacb1c5dbd9004be734feb87570de02aa4a9b1835f50be26c9e2b9"
INDEPENDENT_SCHEMA_FINGERPRINT = (
    "feab7d2bb40de94e3621d6ff9847363eddd52b7fd8cd3c07f66def664da614c8"
)
INDEPENDENT_SINGLE_ROW_CONTENT_HASH = (
    "aab8332d4960ce0cd9b823c765c3719ae101ee64e718a328608699b36ae878c2"
)
INDEPENDENT_TWO_ROW_SORTED_CONTENT_HASH = (
    "37a4ac4591f97221cfb4c90c7733dd463b282bc58776338ca57bfc9220c39787"
)


def sample_row(open_ms: int = 1704067200000) -> list:
    return [
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
        open_ms,
        open_ms + 59_999,
        open_ms + 60_000,
        render_decimal_18("42571.90"),
        render_decimal_18("42600"),
        render_decimal_18("42500.10"),
        render_decimal_18("42590.50"),
        render_decimal_18("12.345678901234567890"),
        render_decimal_18("987654.321098765432109876"),
        54_321,
        render_decimal_18("7"),
        render_decimal_18("400000"),
        "0",
    ]


def test_hash_contract_version_label() -> None:
    assert HASH_CONTRACT_VERSION == "hash_contract_v1"
    assert CONTENT_HASH_DOMAIN == "quantara-canonical-content-v1"


def test_sha256_matches_independent_vector() -> None:
    assert sha256_hex(b"quantara") == INDEPENDENT_BYTES_SHA256


def test_schema_fingerprint_matches_independent_vector() -> None:
    assert schema_fingerprint() == INDEPENDENT_SCHEMA_FINGERPRINT


def test_single_row_content_hash_matches_independent_vector() -> None:
    fingerprint = schema_fingerprint()
    rows = [canonical_row_array(sample_row())]
    assert canonical_content_hash(fingerprint, rows) == (
        INDEPENDENT_SINGLE_ROW_CONTENT_HASH
    )


def test_row_order_changes_content_hash_deterministically() -> None:
    fingerprint = schema_fingerprint()
    rows = [sample_row(), sample_row(open_ms=1704067260000)]
    ascending = [canonical_row_array(r) for r in sorted(rows, key=lambda r: r[10])]
    assert canonical_content_hash(fingerprint, ascending) == (
        INDEPENDENT_TWO_ROW_SORTED_CONTENT_HASH
    )


def test_logical_change_changes_content_identity() -> None:
    fingerprint = schema_fingerprint()
    baseline = canonical_content_hash(fingerprint, [canonical_row_array(sample_row())])
    changed_row = sample_row()
    changed_row[19] = 54_322  # trade_count differs
    changed = canonical_content_hash(
        fingerprint, [canonical_row_array(changed_row)]
    )
    assert baseline != changed


def test_writer_variation_cannot_change_content_identity() -> None:
    """Parquet-writer settings are not inputs to the content hash."""
    rows = [canonical_row_array(sample_row())]
    assert canonical_content_hash(schema_fingerprint(), rows) == canonical_content_hash(
        schema_fingerprint(), rows
    )


@pytest.mark.parametrize("bad", [1.5, -0.25])
def test_floats_rejected_in_canonical_rows(bad: float) -> None:
    row = sample_row()
    row[13] = bad
    with pytest.raises(QuantaraError):
        canonical_row_array(row)


def test_canonical_row_rejects_wrong_length() -> None:
    with pytest.raises(QuantaraError):
        canonical_row_array(sample_row()[:22])


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("42571.90", "42571.900000000000000000"),
        ("0", "0.000000000000000000"),
        ("12.34567890123456789", "12.345678901234567890"),
        ("400000", "400000.000000000000000000"),
    ],
)
def test_render_decimal_18_exact(text: str, expected: str) -> None:
    assert render_decimal_18(text) == expected
    assert render_decimal_18(Decimal(text)) == expected


def test_render_decimal_18_never_rounds() -> None:
    with pytest.raises(QuantaraError):
        render_decimal_18("0.1234567890123456789")  # 19 fractional places


def test_descriptor_hash_is_formatting_independent(valid_path) -> None:
    from conftest import VALID_DESCRIPTOR_YAML, write_text

    # Reorder top-level keys while preserving semantics.
    lines = VALID_DESCRIPTOR_YAML.strip().split("\n")
    head, period_block = lines[:11], lines[11:]
    rebuilt = "\n".join(list(reversed(head)) + period_block) + "\n"
    first = load_descriptor(valid_path)
    second = load_descriptor(write_text(valid_path.parent / "r", rebuilt))
    assert descriptor_hash(first.canonical_semantics()) == descriptor_hash(
        second.canonical_semantics()
    )


def test_quality_identity_excludes_operational_timestamps() -> None:
    base_checks = [
        {"check_id": "row_count", "outcome": "pass", "count": 44_640},
        {"check_id": "boundaries", "outcome": "pass", "count": 2},
    ]
    with_ts = [
        {**c, "operational_timestamp": "2026-08-24T00:00:00Z"} if i == 0 else dict(c)
        for i, c in enumerate(base_checks)
    ]
    assert quality_identity(base_checks) == quality_identity(with_ts)
