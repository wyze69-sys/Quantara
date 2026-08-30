"""A4 perp-spot basis audit probe.

Probes both the `premiumIndexKlines` archive (Binance's native basis
series) and a 2020-01 spot kline (the other leg of perp - spot basis)
to confirm both archives can be joined at the same 1m grid.
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

PREMIUM_BASE = "https://data.binance.vision/data/futures/um/monthly/premiumIndexKlines/BTCUSDT/1m"
SPOT_BASE = "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1m"


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


def probe(label: str, base: str, fname: str) -> dict:
    url = f"{base}/{fname}"
    out = {"series": label, "url": url}
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
    out_dir = Path("temp/audit_a4_basis")
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []

    # Premium index: 2019-12 (should 404), 2020-01, 2020-06, 2020-12, 2021-01,
    # 2021-12, 2022-01, 2022-12, 2023-01, 2023-12, 2024-01, 2024-12
    for m in ["2019-12",
              "2020-01", "2020-06", "2020-12",
              "2021-01", "2021-12",
              "2022-01", "2022-12",
              "2023-01", "2023-12",
              "2024-01", "2024-12"]:
        results.append(probe("premium", PREMIUM_BASE, f"BTCUSDT-1m-{m}.zip"))
        print("premium", m, "->", {k: v for k, v in results[-1].items()
                                    if k in ("zip_sha256", "error", "parsed",
                                             "checksum_file", "checksum_file_error")})

    # Spot klines: 2019-12 (control: should 200), 2020-01 (key), 2020-06,
    # 2020-12, 2021-01, 2024-12
    for m in ["2019-12", "2020-01", "2020-06", "2020-12", "2021-01", "2024-12"]:
        results.append(probe("spot", SPOT_BASE, f"BTCUSDT-1m-{m}.zip"))
        print("spot", m, "->", {k: v for k, v in results[-1].items()
                                if k in ("zip_sha256", "error", "parsed",
                                         "checksum_file", "checksum_file_error")})

    p = out_dir / "basis_probe_v1.json"
    p.write_text(json.dumps(results, indent=2))
    print("WROTE", p)


if __name__ == "__main__":
    main()
