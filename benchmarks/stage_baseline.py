"""Deterministic offline timings for the canonical data path."""

from __future__ import annotations

import argparse
import json
import pathlib
import platform
import random
import sys
import tempfile
import time
import tracemalloc

import quantara.canonical as canonical
import quantara.descriptor as descriptor
import quantara.hashing as hashing
import quantara.parsing as parsing
import quantara.quality as quality

harness_version = "quantara-stage-baseline/1"

_START_EPOCH_SECONDS = 1_704_067_200
_HEADER_TEXT = ",".join(parsing.HEADER)


def _utc_text(epoch_seconds: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch_seconds))


def _descriptor_text(row_count: int) -> str:
    end = _utc_text(_START_EPOCH_SECONDS + row_count * 60)
    return f"""\
schema: quantara.dataset-descriptor/v1
dataset_id: binance_usdm_btcusdt_klines_1m_2024_01
provider: binance
market_type: usd_m_futures
instrument_id: binance:usd_m_futures:BTCUSDT:perpetual
provider_symbol: BTCUSDT
base_asset: BTC
quote_asset: USDT
settlement_asset: USDT
contract_type: perpetual
dataset_type: klines
interval: 1m
period:
  start: "2024-01-01T00:00:00Z"
  end: "{end}"
source:
  archive_url: https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01.zip
  checksum_url: https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01.zip.CHECKSUM
  allowed_hosts:
    - data.binance.vision
  member_pattern: "^BTCUSDT-1m-2024-01\\\\.csv$"
schema_version: binance_usdm_kline_1m_v1
timestamp_semantics: closed_interval_v1
quality_policy_version: "1"
legal_record: configs/legal/binance-usdm-provider-rights.v1.yaml
"""


def _price_text(integer: int, fraction: int, *, full_precision: bool) -> str:
    if full_precision:
        return f"{integer}.{fraction:018d}"
    return f"{integer}.{fraction % 100:02d}"


def build_corpus(
    row_count: int,
    seed: int = 20260827,
) -> tuple[str, descriptor.DatasetDescriptor]:
    """Build deterministic, production-valid one-minute CSV and descriptor."""
    if row_count <= 0:
        raise ValueError("row_count must be positive")

    generator = random.Random(seed)
    lines = [_HEADER_TEXT + "\n"]
    start_ms = _START_EPOCH_SECONDS * 1_000
    for index in range(row_count):
        open_time = start_ms + index * 60_000
        price_integer = 42_000 + generator.randrange(0, 800)
        fraction = generator.randrange(0, 10**18)
        full_precision = index % 97 == 0
        open_price = _price_text(
            price_integer,
            fraction,
            full_precision=full_precision,
        )
        close_price = _price_text(
            price_integer,
            fraction + 17,
            full_precision=full_precision,
        )
        base_volume = f"{1 + generator.randrange(0, 20)}.{generator.randrange(0, 1000):03d}"
        quote_volume = f"{100_000 + generator.randrange(0, 900_000)}.{index % 100:02d}"
        taker_base = f"{generator.randrange(0, 10)}.{generator.randrange(0, 1000):03d}"
        taker_quote = f"{50_000 + generator.randrange(0, 400_000)}.{index % 1000:03d}"
        fields = (
            str(open_time),
            open_price,
            "50000.000000000000000000",
            "40000.000000000000000000",
            close_price,
            base_volume,
            str(open_time + 59_999),
            quote_volume,
            str(1 + generator.randrange(0, 10_000)),
            taker_base,
            taker_quote,
            "0",
        )
        lines.append(",".join(fields) + "\n")

    with tempfile.TemporaryDirectory(prefix="quantara-stage-descriptor-") as scratch:
        descriptor_path = pathlib.Path(scratch) / "descriptor.yaml"
        descriptor_path.write_text(_descriptor_text(row_count), encoding="utf-8")
        loaded_descriptor = descriptor.load_descriptor(descriptor_path)

    return "".join(lines), loaded_descriptor


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[midpoint])
    return float((ordered[midpoint - 1] + ordered[midpoint]) / 2)


def _measure(stage, repeats: int) -> tuple[dict[str, object], object]:
    measurements: list[tuple[float, int]] = []
    latest = None
    for _ in range(repeats):
        tracemalloc.start()
        tracemalloc.reset_peak()
        started = time.perf_counter()
        try:
            latest = stage()
            seconds = time.perf_counter() - started
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        measurements.append((seconds, peak))

    ordered = sorted(measurements, key=lambda measurement: measurement[0])
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        median_peak = ordered[midpoint][1]
    else:
        median_peak = max(ordered[midpoint - 1][1], ordered[midpoint][1])
    seconds_all = [measurement[0] for measurement in measurements]
    return (
        {
            "seconds_all": seconds_all,
            "seconds_median": _median(seconds_all),
            "tracemalloc_peak_bytes": int(median_peak),
        },
        latest,
    )


def run_baseline(
    row_count: int,
    repeats: int,
    workdir: pathlib.Path | str,
) -> dict[str, object]:
    """Time each stable canonical-path stage in an isolated scratch directory."""
    if repeats <= 0:
        raise ValueError("repeats must be positive")

    corpus_text, loaded_descriptor = build_corpus(row_count)
    corpus_bytes = corpus_text.encode("utf-8")
    stages: dict[str, dict[str, object]] = {}

    def parse_stage():
        return parsing.parse_rows(
            parsing.decode_member(corpus_bytes),
            loaded_descriptor,
        )

    stages["parse"], parsed_rows = _measure(parse_stage, repeats)

    def assemble_stage():
        return canonical.assemble_canonical_rows(parsed_rows, loaded_descriptor)

    stages["assemble"], assembled_result = _measure(assemble_stage, repeats)
    assembled, source_order_valid = assembled_result

    def quality_stage():
        return quality.evaluate_quality(
            assembled,
            loaded_descriptor,
            source_order_valid=source_order_valid,
            expected_count=row_count,
        )

    stages["quality"], _ = _measure(quality_stage, repeats)

    pathlib.Path(workdir).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="quantara-stage-baseline-",
        dir=pathlib.Path(workdir),
    ) as scratch:
        parquet_path = pathlib.Path(scratch) / "canonical.parquet"

        def parquet_write_stage():
            return canonical.write_canonical_parquet(assembled, parquet_path)

        stages["parquet_write"], _ = _measure(parquet_write_stage, repeats)

        def verify_parquet_stage():
            reconcile_parquet = getattr(canonical, "reconcile_parquet", None)
            if reconcile_parquet is not None:
                return reconcile_parquet(assembled, parquet_path)
            persisted_rows = canonical.read_canonical_rows(parquet_path)
            return canonical.reconcile_rows(assembled, persisted_rows)

        stages["verify_parquet"], _ = _measure(verify_parquet_stage, repeats)

        fingerprint = hashing.schema_fingerprint()

        def content_hash_stage():
            return hashing.canonical_content_hash(
                fingerprint,
                (row.to_content_array() for row in assembled),
            )

        stages["content_hash"], _ = _measure(content_hash_stage, repeats)

    return {
        "harness_version": harness_version,
        "row_count": row_count,
        "repeats": repeats,
        "stages": stages,
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
    }


def _print_table(evidence: dict[str, object]) -> None:
    print(
        f"{evidence['harness_version']} rows={evidence['row_count']} "
        f"repeats={evidence['repeats']}"
    )
    print("stage             median_seconds  tracemalloc_peak_bytes")
    for name, result in evidence["stages"].items():
        print(
            f"{name:<17} {result['seconds_median']:>14.6f}  "
            f"{result['tracemalloc_peak_bytes']:>22}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=44_640)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args(argv)
    if arguments.rows <= 0:
        parser.error("--rows must be positive")
    if arguments.repeats <= 0:
        parser.error("--repeats must be positive")

    with tempfile.TemporaryDirectory(prefix="quantara-stage-cli-") as scratch:
        evidence = run_baseline(arguments.rows, arguments.repeats, scratch)
    if arguments.json:
        print(json.dumps(evidence, sort_keys=True))
    else:
        _print_table(evidence)
    return 0


if __name__ == "__main__":
    sys.exit(main())
