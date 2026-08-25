"""Canonical rows, row/sequence invariants, and Parquet persistence.

Assembles the fixed 23-column canonical rows from validated source rows plus
descriptor identity fields; derives nominal availability under the approved
temporal contract; detects source ordering state (complete-but-unordered
input sorts only while recording the finding); and exposes content arrays
with exactly-18-fractional-digit decimal strings for the hash contract.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from quantara.descriptor import DatasetDescriptor
from quantara.errors import DUPLICATE_OPEN_TIME, QuantaraError
from quantara.hashing import render_decimal_18
from quantara.parsing import SourceRow

__all__ = [
    "CanonicalRow",
    "DuplicateOpenTime",
    "assemble_canonical_rows",
    "build_canonical_row",
    "make_source_row",
]


class DuplicateOpenTime(QuantaraError):
    error_id = DUPLICATE_OPEN_TIME


@dataclass(frozen=True)
class CanonicalRow:
    identity: tuple[str, ...]  # ten identity strings, schema order
    open_time_ms: int
    close_time_ms: int
    nominal_available_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    base_asset_volume: Decimal
    quote_asset_volume: Decimal
    trade_count: int
    taker_buy_base_volume: Decimal
    taker_buy_quote_volume: Decimal
    source_ignore: str

    @property
    def instrument_id(self) -> str:
        return self.identity[2]

    def to_content_array(self) -> list[object]:
        """JSON-ready array in exact schema order; decimals carry 18 digits."""
        return [
            *self.identity,
            self.open_time_ms,
            self.close_time_ms,
            self.nominal_available_ms,
            render_decimal_18(self.open),
            render_decimal_18(self.high),
            render_decimal_18(self.low),
            render_decimal_18(self.close),
            render_decimal_18(self.base_asset_volume),
            render_decimal_18(self.quote_asset_volume),
            self.trade_count,
            render_decimal_18(self.taker_buy_base_volume),
            render_decimal_18(self.taker_buy_quote_volume),
            self.source_ignore,
        ]


def make_source_row(**kwargs) -> SourceRow:
    return SourceRow(
        open_time=kwargs["open_time"],
        close_time=kwargs["close_time"],
        open=kwargs["open"],
        high=kwargs["high"],
        low=kwargs["low"],
        close=kwargs["close"],
        base_asset_volume=kwargs["base_asset_volume"],
        quote_asset_volume=kwargs["quote_asset_volume"],
        trade_count=kwargs["trade_count"],
        taker_buy_base_volume=kwargs["taker_buy_base_volume"],
        taker_buy_quote_volume=kwargs["taker_buy_quote_volume"],
        source_ignore=kwargs["source_ignore"],
    )


def build_canonical_row(source: SourceRow, descriptor: DatasetDescriptor) -> CanonicalRow:
    identity = (
        descriptor.provider,
        descriptor.market_type,
        descriptor.instrument_id,
        descriptor.provider_symbol,
        descriptor.base_asset,
        descriptor.quote_asset,
        descriptor.settlement_asset,
        descriptor.contract_type,
        descriptor.interval,
        descriptor.schema_version,
    )
    return CanonicalRow(
        identity=identity,
        open_time_ms=source.open_time,
        close_time_ms=source.close_time,
        nominal_available_ms=source.open_time + 60_000,
        open=source.open,
        high=source.high,
        low=source.low,
        close=source.close,
        base_asset_volume=source.base_asset_volume,
        quote_asset_volume=source.quote_asset_volume,
        trade_count=source.trade_count,
        taker_buy_base_volume=source.taker_buy_base_volume,
        taker_buy_quote_volume=source.taker_buy_quote_volume,
        source_ignore=source.source_ignore,
    )


def assemble_canonical_rows(
    rows: list[SourceRow], descriptor: DatasetDescriptor
) -> tuple[list[CanonicalRow], bool]:
    """Build canonical rows; sort complete-but-unordered input while reporting
    that source order was invalid via the returned flag."""
    built = [build_canonical_row(row, descriptor) for row in rows]
    times = [row.open_time_ms for row in built]
    order_ok = all(a < b for a, b in itertools.pairwise(times))
    if not order_ok:
        unique_times = set(times)
        if len(unique_times) != len(times):
            seen: set[int] = set()
            duplicates = sorted({t for t in times if t in seen or seen.add(t)})
            raise DuplicateOpenTime(f"duplicate canonical open times: {duplicates}")
        built.sort(key=lambda row: row.open_time_ms)
    return built, order_ok


# ---------------------------------------------------------------------------
# Parquet write / read-back / reconciliation (spec §§9, 10 steps 15–17, §6.6)

import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from quantara.errors import (  # noqa: E402
    FAILED_PARQUET_WRITE_OR_READ_BACK,
    RECONCILIATION_MISMATCH,
)
from quantara.hashing import CANONICAL_COLUMNS  # noqa: E402

__all__ += [
    "PARQUET_SCHEMA",
    "WRITER_CONFIG",
    "read_canonical_rows",
    "reconcile_rows",
    "write_canonical_parquet",
]


class ReconciliationMismatch(QuantaraError):
    error_id = RECONCILIATION_MISMATCH


class ParquetFailure(QuantaraError):
    error_id = FAILED_PARQUET_WRITE_OR_READ_BACK


def _parquet_schema() -> pa.Schema:
    fields = []
    for name, ctype in CANONICAL_COLUMNS:
        if ctype == "utf8":
            arrow_type = pa.string()
        elif ctype == "timestamp_ms_utc":
            arrow_type = pa.timestamp("ms", tz="UTC")
        elif ctype == "decimal128_38_18":
            arrow_type = pa.decimal128(38, 18)
        elif ctype == "int64_nonnegative":
            arrow_type = pa.int64()
        else:  # pragma: no cover - schema constant is closed
            raise ParquetFailure(f"unknown canonical column type {ctype!r}")
        fields.append(pa.field(name, arrow_type, nullable=False))
    return pa.schema(fields)


PARQUET_SCHEMA = _parquet_schema()

# Fixed writer configuration recorded in manifests; changing it changes the
# Parquet byte hash but never the canonical-content identity.
WRITER_CONFIG = {
    "compression": "zstd",
    "version": "2.6",
    "data_page_version": "2.0",
    "store_schema": True,
}


def write_canonical_parquet(rows: list[CanonicalRow], path: Path) -> None:
    columns: list[list] = [
        [row.identity[i] for row in rows] for i in range(10)
    ]
    columns.append([row.open_time_ms for row in rows])
    columns.append([row.close_time_ms for row in rows])
    columns.append([row.nominal_available_ms for row in rows])
    for name in (
        "open",
        "high",
        "low",
        "close",
        "base_asset_volume",
        "quote_asset_volume",
    ):
        columns.append([getattr(row, name) for row in rows])
    columns.append([row.trade_count for row in rows])
    columns.append([row.taker_buy_base_volume for row in rows])
    columns.append([row.taker_buy_quote_volume for row in rows])
    columns.append([row.source_ignore for row in rows])

    arrays = [
        pa.array(values, type=PARQUET_SCHEMA.field(index).type)
        for index, values in enumerate(columns)
    ]
    table = pa.Table.from_arrays(arrays, schema=PARQUET_SCHEMA)
    try:
        with pq.ParquetWriter(path, PARQUET_SCHEMA, **WRITER_CONFIG) as writer:
            writer.write_table(table)
    except Exception as exc:  # pragma: no cover - defensive
        raise ParquetFailure(f"Parquet write failed for {path}: {exc}") from exc


def read_canonical_rows(path: Path) -> list[tuple]:
    """Read back through the approved explicit schema; decimals arrive as
    decimal.Decimal and timestamps as epoch-ms ints — never floats."""
    try:
        table = pq.read_table(Path(path))
    except Exception as exc:
        raise ParquetFailure(f"Parquet read-back failed for {path}: {exc}") from exc

    if table.schema != PARQUET_SCHEMA:
        raise ParquetFailure("read-back schema differs from approved canonical schema")
    try:
        columns = []
        for index in range(len(CANONICAL_COLUMNS)):
            column = table.column(index)
            if PARQUET_SCHEMA.field(index).type == pa.timestamp("ms", tz="UTC"):
                # Cast to raw epoch milliseconds; avoids materializing tz-aware
                # datetimes so no platform timezone database is required.
                values = column.cast(pa.int64()).to_pylist()
            else:
                values = column.to_pylist()
            columns.append(values)
    except ParquetFailure:
        raise
    except Exception as exc:
        raise ParquetFailure(f"Parquet decode failed for {path}: {exc}") from exc

    return list(zip(*columns, strict=True))


def reconcile_rows(
    source_rows: list[CanonicalRow], parquet_rows: list[tuple]
) -> None:
    """Exact field-by-field reconciliation via decimal strings/ints — binary
    floats are never constructed."""
    if len(source_rows) != len(parquet_rows):
        raise ReconciliationMismatch(
            f"row count mismatch: {len(source_rows)} source vs "
            f"{len(parquet_rows)} parquet"
        )
    for position, (source, persisted) in enumerate(
        zip(source_rows, parquet_rows, strict=True)
    ):
        expected = source.to_content_array()
        actual = list(persisted)
        rendered = [
            render_decimal_18(value) if isinstance(value, Decimal) else value
            for value in actual
        ]
        if expected != rendered:
            differing = [
                i
                for i, (e, a) in enumerate(zip(expected, rendered, strict=True))
                if e != a
            ]
            raise ReconciliationMismatch(
                f"row {position} differs at columns {differing}: "
                f"{[expected[i] for i in differing]} != "
                f"{[rendered[i] for i in differing]}"
            )
