"""A1 funding-rate audit probe.

Direct archive probes against data.binance.vision monthly funding zips.
Outputs a small JSON sidecar for the audit report.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import urllib.request
import zipfile
from pathlib import Path

BASE = "https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def parse(zbytes: bytes) -> dict:
    z = zipfile.ZipFile(io.BytesIO(zbytes))
    name = z.namelist()[0]
    raw = z.read(name).decode("utf-8")
    lines = raw.splitlines()
    header = lines[0].split(",")
    rows = list(csv.reader(io.StringIO(raw)))[1:]
    ts = [int(r[0]) for r in rows]
    rates = [float(r[2]) for r in rows]
    intervals = sorted({int(r[1]) for r in rows})
    diffs = [ts[i + 1] - ts[i] for i in range(len(ts) - 1)]
    return {
        "member": name,
        "row_count": len(rows),
        "header": header,
        "first_ts_ms": ts[0],
        "first_ts_utc": dt.datetime.utcfromtimestamp(ts[0] / 1000).isoformat() + "Z",
        "last_ts_ms": ts[-1],
        "last_ts_utc": dt.datetime.utcfromtimestamp(ts[-1] / 1000).isoformat() + "Z",
        "interval_hours": intervals,
        "gap_min_ms": min(diffs) if diffs else None,
        "gap_max_ms": max(diffs) if diffs else None,
        "gap_mean_ms": (sum(diffs) / len(diffs)) if diffs else None,
        "rate_min": min(rates),
        "rate_max": max(rates),
        "rate_mean": sum(rates) / len(rates),
    }


def probe(month: str) -> dict:
    url = f"{BASE}/BTCUSDT-fundingRate-{month}.zip"
    zbytes = fetch(url)
    parsed = parse(zbytes)
    parsed["url"] = url
    parsed["zip_sha256"] = hashlib.sha256(zbytes).hexdigest()
    parsed["zip_bytes"] = len(zbytes)
    return parsed


def fetch_checksum(month: str) -> str:
    url = f"{BASE}/BTCUSDT-fundingRate-{month}.zip.CHECKSUM"
    return fetch(url).decode("utf-8").strip()


def main() -> None:
    out_dir = Path("temp/audit_a1_funding")
    out_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for m in ["2019-09", "2019-10", "2019-12",
              "2020-01", "2020-06", "2020-12",
              "2021-01", "2021-06", "2021-12",
              "2022-01", "2022-12",
              "2023-01", "2023-12",
              "2024-01", "2024-12"]:
        try:
            r = probe(m)
        except Exception as e:
            r = {"error": repr(e)}
        try:
            r["checksum_file"] = fetch_checksum(m)
        except Exception as e:
            r["checksum_file_error"] = repr(e)
        results[m] = r
        print(m, "->", {k: v for k, v in r.items() if k in
                        ("row_count", "first_ts_utc", "last_ts_utc",
                         "interval_hours", "gap_min_ms", "gap_max_ms",
                         "zip_sha256", "error", "checksum_file",
                         "checksum_file_error")})

    out = out_dir / "funding_probe_v1.json"
    out.write_text(json.dumps(results, indent=2))
    print("WROTE", out)


if __name__ == "__main__":
    main()
