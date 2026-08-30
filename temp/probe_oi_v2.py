"""A2 open-interest and related metrics audit probe.

Verifies the existence and format of the `metrics` archive on
data.binance.vision (the only public OI history Binance exposes) and
probes representative boundary and interior days across 2020-2024.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

BASE = "https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT"


def head(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, method="HEAD")
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return {"status": r.status,
                "content_length": r.headers.get("Content-Length"),
                "last_modified": r.headers.get("Last-Modified"),
                "etag": r.headers.get("ETag")}
    except Exception as e:
        return {"error": repr(e)}


def fetch(url: str, timeout: int = 30) -> bytes:
    return urllib.request.urlopen(url, timeout=timeout).read()


def fetch_checksum(url: str) -> str:
    return fetch(url).decode("utf-8").strip()


def parse_zip(zb: bytes) -> dict:
    z = zipfile.ZipFile(io.BytesIO(zb))
    name = z.namelist()[0]
    raw = z.read(name).decode("utf-8")
    lines = raw.splitlines()
    header = lines[0].split(",")
    rows = list(csv.reader(io.StringIO(raw)))[1:]
    distinct = Counter(r[0] for r in rows)
    dup_count = sum(1 for v in distinct.values() if v > 1)
    sample = rows[0]
    fields = {
        "header": header,
        "row_count_total": len(rows),
        "distinct_timestamps": len(distinct),
        "duplicate_timestamp_rows": dup_count,
        "sample_row": sample,
        "first_ts": rows[0][0],
        "last_ts": rows[-1][0],
    }
    return fields


def probe(day: str) -> dict:
    url = f"{BASE}/BTCUSDT-metrics-{day}.zip"
    cksum_url = f"{url}.CHECKSUM"
    out = {"date": day, "url": url}
    try:
        z = fetch(url)
        out["zip_sha256"] = hashlib.sha256(z).hexdigest()
        out["zip_bytes"] = len(z)
        out["parsed"] = parse_zip(z)
    except Exception as e:
        out["error"] = repr(e)
    try:
        out["checksum_file"] = fetch_checksum(cksum_url)
    except Exception as e:
        out["checksum_file_error"] = repr(e)
    return out


def main() -> None:
    out_dir = Path("temp/audit_a2_oi")
    out_dir.mkdir(parents=True, exist_ok=True)

    boundary_days = [
        "2020-08-31",  # day before earliest possible
        "2020-09-01",  # earliest possible
        "2020-09-02",  # +1
        "2020-12-31",  # 2020 boundary
        "2021-01-01",  # 2021 start
        "2021-12-31",  # 2021 boundary
        "2022-01-01",
        "2022-12-31",
        "2023-01-01",
        "2023-12-31",
        "2024-01-01",
        "2024-12-31",  # 2024 boundary
    ]

    results = {}
    for d in boundary_days:
        r = probe(d)
        results[d] = r
        print(d, "->", {k: v for k, v in r.items()
                        if k in ("zip_sha256", "error", "parsed",
                                 "checksum_file", "checksum_file_error")})

    out = out_dir / "oi_probe_v2.json"
    out.write_text(json.dumps(results, indent=2))
    print("WROTE", out)


if __name__ == "__main__":
    main()
