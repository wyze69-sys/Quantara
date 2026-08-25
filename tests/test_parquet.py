"""Parquet persistence tests: exact write, read-back, reconciliation."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from conftest import VALID_DESCRIPTOR_YAML, write_text
from quantara.canonical import (
    WRITER_CONFIG,
    CanonicalRow,
    build_canonical_row,
    make_source_row,
    read_canonical_rows,
    reconcile_rows,
    write_canonical_parquet,
)
from quantara.descriptor import load_descriptor
from quantara.errors import QuantaraError
from quantara.hashing import render_decimal_18

OPEN = 1704067200000


@pytest.fixture()
def descriptor(tmp_path):
    return load_descriptor(write_text(tmp_path / "cfg", VALID_DESCRIPTOR_YAML))


def sample_rows(n: int = 3):
    out = []
    for i in range(n):
        open_ms = OPEN + i * 60_000
        out.append(
            make_source_row(
                open_time=open_ms,
                close_time=open_ms + 59_999,
                open=Decimal("42571.90"),
                high=Decimal("42600.00"),
                low=Decimal("42500.10"),
                close=Decimal("42590.50"),
                base_asset_volume=Decimal("12.345678901234567890"),
                quote_asset_volume=Decimal("987654.321098765432109876"),
                trade_count=54_321,
                taker_buy_base_volume=Decimal("7"),
                taker_buy_quote_volume=Decimal("400000"),
                source_ignore="0",
            )
        )
    return out


def canonical(descriptor, n: int = 3) -> list[CanonicalRow]:
    return [
        build_canonical_row(src, descriptor) for src in sample_rows(n)
    ]


def test_writer_config_is_pinned() -> None:
    assert WRITER_CONFIG == {
        "compression": "zstd",
        "version": "2.6",
        "data_page_version": "2.0",
        "store_schema": True,
    }


def test_round_trip_preserves_exact_decimals(tmp_path: Path, descriptor) -> None:
    target = tmp_path / "canonical.parquet"
    rows = canonical(descriptor)
    write_canonical_parquet(rows, target)
    back = read_canonical_rows(target)
    assert len(back) == len(rows)
    first = back[0]
    # Structural proof: no binary floats anywhere in the read-back row.
    for value in first:
        assert not isinstance(value, float)
    assert isinstance(first[13], Decimal)
    assert str(first[13]) == "42571.900000000000000000"
    assert str(first[17]) == "12.345678901234567890"
    assert str(first[18]) == "987654.321098765432109876"
    assert first[10] == OPEN
    assert first[19] == 54_321


def test_reconciliation_passes_for_identical_data(tmp_path: Path, descriptor) -> None:
    target = tmp_path / "canonical.parquet"
    rows = canonical(descriptor)
    write_canonical_parquet(rows, target)
    back = read_canonical_rows(target)
    reconcile_rows(rows, back)


def test_reconciliation_fails_on_any_value_change(tmp_path: Path, descriptor) -> None:
    target = tmp_path / "canonical.parquet"
    rows = canonical(descriptor)
    write_canonical_parquet(rows, target)
    back = read_canonical_rows(target)
    tampered = list(back[1])
    tampered[14] = Decimal("1.000000000000000000")  # high changed
    mutated = [back[0], tuple(tampered), back[2]]
    with pytest.raises(QuantaraError, match="differs"):
        reconcile_rows(rows, mutated)


def test_truncated_parquet_is_a_hard_failure(tmp_path: Path, descriptor) -> None:
    target = tmp_path / "canonical.parquet"
    write_canonical_parquet(canonical(descriptor), target)
    blob = target.read_bytes()
    target.write_bytes(blob[: len(blob) // 2])
    with pytest.raises(QuantaraError):
        read_canonical_rows(target)


def test_garbage_file_is_a_hard_failure(tmp_path: Path) -> None:
    target = tmp_path / "garbage.parquet"
    target.write_bytes(b"not parquet at all")
    with pytest.raises(QuantaraError):
        read_canonical_rows(target)


def test_read_back_matches_content_arrays(tmp_path: Path, descriptor) -> None:
    """Reconciliation compares the same 18-digit decimal strings used for
    canonical-content hashing."""

    target = tmp_path / "canonical.parquet"
    rows = canonical(descriptor)
    write_canonical_parquet(rows, target)
    back = read_canonical_rows(target)
    for original, persisted in zip(rows, back, strict=True):
        # Render persisted Decimals exactly as the content hash does; the
        # comparison then proves value-level identity without binary floats.
        rendered = [
            render_decimal_18(v) if isinstance(v, Decimal) else v for v in persisted
        ]
        assert rendered == original.to_content_array()
