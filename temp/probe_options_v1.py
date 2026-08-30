"""A6 options audit probe.

Verifies the BVOLIndex and EOHSummary archives on data.binance.vision.
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

BVOL_BASE = "https://data.binance.vision/data/option/daily/BVOLIndex/BTCBVOLUSDT"
EOH_BASE = "https://data.binance.vision/data/option/daily/EOHSummary/BTCUSDT"


def fetch(url: str, timeout: int = 30) -> bytes:
    return urllib.request.urlopen(url, timeout=timeout).read()


def fetch_checksum(url: str) -> str:
    return fetch(url).decode("utf-8").strip()


def parse(zb: bytes) -> dict:
    z = zipfile.ZipFile(io.BytesIO(zb))
    name = z.namelist()[0]
    raw = z.read(name).decode("utf-8", errors="replace")
    lines = raw.splitlines()
    if not lines:
        return {"member": name, "row_count": 0}
    header = lines[0].split(",")
    rows = list(csv.reader(io.StringIO(raw)))[1:]
    return {
        "member": name,
        "header": header,
        "row_count": len(rows),
        "first_line": lines[0] if not rows else rows[0],
        "last_line": lines[-1] if not rows else rows[-1],
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
    out_dir = Path("temp/audit_a6_options")
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []

    # BVOL probe boundary days
    for m in ["2023-06-19", "2023-06-20", "2023-06-21",
              "2023-12-31", "2024-01-01", "2024-06-30", "2024-12-31"]:
        results.append(probe("BVOL", BVOL_BASE, f"BTCBVOLUSDT-BVOLIndex-{m}.zip"))
        print("BVOL", m, "->", {k: v for k, v in results[-1].items()
                                  if k in ("zip_sha256", "error", "parsed",
                                           "checksum_file", "checksum_file_error")})

    # EOH probe boundary days
    for m in ["2023-05-17", "2023-05-18", "2023-05-19", "2023-10-22", "2023-10-23", "2023-10-24"]:
        results.append(probe("EOH", EOH_BASE, f"BTCUSDT-EOHSummary-{m}.zip"))
        print("EOH", m, "->", {k: v for k, v in results[-1].items()
                                if k in ("zip_sha256", "error", "parsed",
                                         "checksum_file", "checksum_file_error")})

    p = out_dir / "options_probe_v1.json"
    p.write_text(json.dumps(results, indent=2))
    print("WROTE", p)


if __name__ == "__main__":
    main()
