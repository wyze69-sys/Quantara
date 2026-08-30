"""A3 mark-price / index-price klines audit probe.

Direct archive probes against data.binance.vision monthly mark- and
index-price klines zips for BTCUSDT USD-M.
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

BASE = "https://data.binance.vision/data/futures/um/monthly"
ARCHIVES = [
    ("mark", "markPriceKlines"),
    ("index", "indexPriceKlines"),
]


def fetch(url: str, timeout: int = 30) -> bytes:
    return urllib.request.urlopen(url, timeout=timeout).read()


def fetch_checksum(url: str) -> str:
    return fetch(url).decode("utf-8").strip()


def parse(zb: bytes) -> dict:
    z = zipfile.ZipFile(io.BytesIO(zb))
    name = z.namelist()[0]
    raw = z.read(name).decode("utf-8")
    lines = raw.splitlines()
    header = lines[0].split(",")
    rows = list(csv.reader(io.StringIO(raw)))[1:]
    if not rows:
        return {"member": name, "header": header, "row_count": 0}
    ts = [int(r[0]) for r in rows]
    diffs = [ts[i + 1] - ts[i] for i in range(len(ts) - 1)]
    return {
        "member": name,
        "header": header,
        "row_count": len(rows),
        "first_ts_ms": ts[0],
        "first_ts_utc": dt.datetime.utcfromtimestamp(ts[0] / 1000).isoformat() + "Z",
        "last_ts_ms": ts[-1],
        "last_ts_utc": dt.datetime.utcfromtimestamp(ts[-1] / 1000).isoformat() + "Z",
        "gap_min_ms": min(diffs) if diffs else None,
        "gap_max_ms": max(diffs) if diffs else None,
        "gap_mean_ms": (sum(diffs) / len(diffs)) if diffs else None,
        "sample_first_row": rows[0],
        "sample_last_row": rows[-1],
    }


def probe(label: str, archive_dir: str, month: str) -> dict:
    fname = f"BTCUSDT-1m-{month}.zip"
    url = f"{BASE}/{archive_dir}/BTCUSDT/1m/{fname}"
    out = {"series": label, "month": month, "url": url}
    try:
        z = fetch(url)
        out["zip_sha256"] = hashlib.sha256(z).hexdigest()
        out["zip_bytes"] = len(z)
        out["parsed"] = parse(z)
    except Exception as e:
        out["error"] = repr(e)
    try:
        out["checksum_file"] = fetch_checksum(url + ".CHECKSUM")
    except Exception as e:
        out["checksum_file_error"] = repr(e)
    return out


def main() -> None:
    out_dir = Path("temp/audit_a3_mark_index")
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for label, archive in ARCHIVES:
        # Test 2019 (should 404), 2020-01, 2020-06, 2020-12, 2021-01, 2021-12,
        # 2022-01, 2022-12, 2023-01, 2023-12, 2024-01, 2024-12
        for m in ["2019-12",
                  "2020-01", "2020-06", "2020-12",
                  "2021-01", "2021-12",
                  "2022-01", "2022-12",
                  "2023-01", "2023-12",
                  "2024-01", "2024-12"]:
            r = probe(label, archive, m)
            results.append(r)
            print(label, m, "->", {k: v for k, v in r.items()
                                    if k in ("zip_sha256", "error", "parsed",
                                             "checksum_file", "checksum_file_error")})
    p = out_dir / "mark_index_probe_v1.json"
    p.write_text(json.dumps(results, indent=2))
    print("WROTE", p)


if __name__ == "__main__":
    main()
