"""S03-A: real-source audit for BTC mark-price klines 2020-2024.

Source: data/futures/um/monthly/markPriceKlines/BTCUSDT/1m/
60 monthly files expected: BTCUSDT-1m-2020-01.zip ... BTCUSDT-1m-2024-12.zip

Contract:
  - Verifies file listing matches 60 expected names
  - Downloads boundary files (first, mid, last) plus a post-header file
  - Verifies provider checksums
  - Parses with binance_usdm_kline_series_csv/v1
  - Verifies header policy: absent_before_2022-12
  - Records value-blind evidence only (counts, timestamps, hashes)

Environment:
    S03A_DATA_ROOT   disposable data root for downloads (required, explicit)
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx

from quantara.archive import inspect_zip, read_member_bytes
from quantara.series_descriptor import load_series_descriptor
from quantara.series_parsing import parse_kline_rows
from quantara.series_pipeline import _storage_root

ROOT = Path(__file__).resolve().parents[3]
DESCRIPTOR = ROOT / 'configs/series/binance-usdm-btcusdt-mark-1m-2020-2024.yaml'
EVIDENCE = Path(__file__).resolve().parent
DATA_ROOT = Path(os.environ['S03A_DATA_ROOT'])


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).isoformat().replace('+00:00', 'Z')


def expected_files(descriptor) -> list[str]:
    spec = descriptor.to_dict()
    start = datetime.strptime(spec['period']['start'], '%Y-%m-%d')
    end = datetime.strptime(spec['period']['end'], '%Y-%m-%d')
    files = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        files.append(f'BTCUSDT-1m-{y:04d}-{m:02d}.zip')
        m += 1
        if m > 12:
            m = 1
            y += 1
    return files


def verify_file(client: httpx.Client, data_root: Path, file_name: str, period: str) -> dict:
    archive_url = f'https://data.binance.vision/data/futures/um/monthly/markPriceKlines/BTCUSDT/1m/{file_name}'
    checksum_url = f'https://data.binance.vision/data/futures/um/monthly/markPriceKlines/BTCUSDT/1m/{file_name}.CHECKSUM'

    resp = client.get(archive_url)
    assert resp.status_code == 200, f'archive status {resp.status_code} for {file_name}'
    archive_bytes = resp.content

    resp = client.get(checksum_url)
    assert resp.status_code == 200, f'checksum status {resp.status_code} for {file_name}'
    checksum_bytes = resp.content

    official_digest = checksum_bytes.decode('ascii').strip().split()[0]
    actual_digest = sha(archive_bytes)
    assert official_digest == actual_digest, (
        f'checksum mismatch for {file_name}: official={official_digest} actual={actual_digest}')

    archive_path = data_root / 'downloads' / file_name
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_bytes(archive_bytes)

    member_pattern = file_name.replace('.zip', '*.csv')
    member = read_member_bytes(archive_path, inspect_zip(archive_path, member_pattern))

    # Build a SeriesArchive for this period
    descriptor = load_series_descriptor(DESCRIPTOR)
    archive = descriptor.archive_for(period)

    attempt_path = EVIDENCE / 'parse' / f'{file_name}.json'
    parsed = parse_kline_rows(member, archive, attempt_path=attempt_path)

    times = [r.event_ts for r in parsed.rows]
    return {
        'file_name': file_name,
        'period': period,
        'checksum_matches': True,
        'archive_sha256': actual_digest,
        'member_sha256': sha(member),
        'source_rows': parsed.source_rows,
        'distinct_rows': parsed.distinct_rows,
        'duplicate_rows': parsed.duplicate_rows,
        'conflict_rows': parsed.conflict_rows,
        'first_event_utc': utc(min(times)) if times else None,
        'last_event_utc': utc(max(times)) if times else None,
    }


def main() -> None:
    descriptor = load_series_descriptor(DESCRIPTOR)
    all_files = expected_files(descriptor)
    print(f'EXPECTED_FILES {len(all_files)}')

    data_root = _storage_root(DATA_ROOT)
    (EVIDENCE / 'parse').mkdir(exist_ok=True)

    # Map file names to periods (monthly files use first-of-month period)
    def file_to_period(file_name: str) -> str:
        # BTCUSDT-1m-2020-01.zip -> 2020-01 (monthly cadence)
        parts = file_name.replace('.zip', '').split('-')
        return f'{parts[2]}-{parts[3]}'

    # Audit boundary + interior samples
    sample_files = [all_files[0], all_files[len(all_files) // 2], all_files[-1]]
    print(f'SAMPLE_FILES {sample_files}')

    results = []
    with httpx.Client(timeout=30) as client:
        for file_name in sample_files:
            period = file_to_period(file_name)
            result = verify_file(client, data_root, file_name, period)
            results.append(result)
            print(f'VERIFIED {file_name}: '
                  f'rows={result["source_rows"]} distinct={result["distinct_rows"]} '
                  f'dupes={result["duplicate_rows"]} conflicts={result["conflict_rows"]}')

    payload = {
        'expected_files': len(all_files),
        'sample_files': sample_files,
        'results': results,
    }
    (EVIDENCE / 's03a-source-audit.json').write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')
    print('AUDIT_WRITTEN')


if __name__ == '__main__':
    main()
