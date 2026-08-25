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
