"""Behavior and memory acceptance for streaming Parquet reconciliation."""

from __future__ import annotations

import gc
import tracemalloc
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as pq
import pytest

import quantara.canonical as canonical_module
from quantara.canonical import (
    CanonicalRow,
    ParquetFailure,
    ReconciliationMismatch,
    build_canonical_row,
    make_source_row,
    read_canonical_rows,
    reconcile_rows,
    write_canonical_parquet,
)
from quantara.descriptor import load_descriptor

OPEN = 1_704_067_200_000


def _canonical_rows(valid_path: Path, row_count: int) -> list[CanonicalRow]:
    descriptor = load_descriptor(valid_path)
    rows = []
    for index in range(row_count):
        open_time = OPEN + index * 60_000
        source = make_source_row(
            open_time=open_time,
            close_time=open_time + 59_999,
            open=Decimal(f"{42_000 + index % 500}.123456789012345678"),
            high=Decimal("50000.000000000000000000"),
            low=Decimal("40000.000000000000000000"),
            close=Decimal(f"{42_000 + index % 500}.987654321098765432"),
            base_asset_volume=Decimal(f"{1 + index % 100}.500"),
            quote_asset_volume=Decimal(f"{100_000 + index}.250"),
            trade_count=1 + index % 10_000,
            taker_buy_base_volume=Decimal(f"{index % 10}.125"),
            taker_buy_quote_volume=Decimal(f"{50_000 + index}.125"),
            source_ignore="0",
        )
        rows.append(build_canonical_row(source, descriptor))
    return rows


def test_reconcile_parquet_round_trip_matches_legacy_pair(
    tmp_path: Path,
    valid_path: Path,
) -> None:
    for row_count in (1, 6, 7, 8, 13, 14):
        rows = _canonical_rows(valid_path, row_count)
        parquet_path = tmp_path / f"round-trip-{row_count}.parquet"
        write_canonical_parquet(rows, parquet_path)

        reconcile_rows(rows, read_canonical_rows(parquet_path))
        canonical_module.reconcile_parquet(rows, parquet_path, batch_size=7)


def test_reconcile_parquet_detects_field_mismatch(
    tmp_path: Path,
    valid_path: Path,
) -> None:
    persisted_rows = _canonical_rows(valid_path, 3)
    parquet_path = tmp_path / "field-mismatch.parquet"
    write_canonical_parquet(persisted_rows, parquet_path)
    source_rows = list(persisted_rows)
    victim = source_rows[1]
    source_rows[1] = CanonicalRow(
        identity=victim.identity,
        open_time_ms=victim.open_time_ms,
        close_time_ms=victim.close_time_ms,
        nominal_available_ms=victim.nominal_available_ms,
        open=victim.open,
        high=Decimal("49999.000000000000000000"),
        low=victim.low,
        close=victim.close,
        base_asset_volume=victim.base_asset_volume,
        quote_asset_volume=victim.quote_asset_volume,
        trade_count=victim.trade_count,
        taker_buy_base_volume=victim.taker_buy_base_volume,
        taker_buy_quote_volume=victim.taker_buy_quote_volume,
        source_ignore=victim.source_ignore,
    )

    with pytest.raises(ReconciliationMismatch):
        reconcile_rows(source_rows, read_canonical_rows(parquet_path))
    with pytest.raises(ReconciliationMismatch):
        canonical_module.reconcile_parquet(source_rows, parquet_path)


def test_reconcile_parquet_detects_count_mismatch(
    tmp_path: Path,
    valid_path: Path,
) -> None:
    source_rows = _canonical_rows(valid_path, 3)
    fewer_path = tmp_path / "fewer.parquet"
    extra_path = tmp_path / "extra.parquet"
    write_canonical_parquet(source_rows[:-1], fewer_path)
    write_canonical_parquet(_canonical_rows(valid_path, 4), extra_path)

    with pytest.raises(ReconciliationMismatch, match="row count"):
        canonical_module.reconcile_parquet(source_rows, fewer_path)
    with pytest.raises(ReconciliationMismatch, match="row count"):
        canonical_module.reconcile_parquet(source_rows, extra_path)


def test_reconcile_parquet_rejects_foreign_schema(
    tmp_path: Path,
    valid_path: Path,
) -> None:
    rows = _canonical_rows(valid_path, 3)
    approved_path = tmp_path / "approved.parquet"
    foreign_path = tmp_path / "foreign.parquet"
    write_canonical_parquet(rows, approved_path)
    table = pq.read_table(approved_path)
    pq.write_table(
        table.rename_columns(["foreign_provider", *table.column_names[1:]]),
        foreign_path,
    )

    with pytest.raises(ParquetFailure) as legacy_error:
        read_canonical_rows(foreign_path)
    with pytest.raises(ParquetFailure) as streaming_error:
        canonical_module.reconcile_parquet(rows, foreign_path)

    assert streaming_error.value.error_id == legacy_error.value.error_id


def test_reconcile_parquet_bounds_peak_memory(
    tmp_path: Path,
    valid_path: Path,
) -> None:
    rows = _canonical_rows(valid_path, 30_000)
    parquet_path = tmp_path / "memory.parquet"
    write_canonical_parquet(rows, parquet_path)

    gc.collect()
    tracemalloc.start()
    tracemalloc.reset_peak()
    try:
        persisted = read_canonical_rows(parquet_path)
        reconcile_rows(rows, persisted)
        legacy_peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    del persisted

    gc.collect()
    tracemalloc.start()
    tracemalloc.reset_peak()
    try:
        canonical_module.reconcile_parquet(rows, parquet_path)
        streaming_peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()

    assert streaming_peak <= legacy_peak * 0.5
