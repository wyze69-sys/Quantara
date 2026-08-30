"""A2 open-interest audit probe.

Verifies (a) absence of any OI archive on data.binance.vision, and
(b) the documented 1-month retention of the live /openInterestHist endpoint.
The direct live-API probe is attempted but will not be a load-bearing
claim in this audit.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

LIVE_URLS = [
    "https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT",
    "https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=5m&limit=2",
    "https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=1d&limit=2",
]

ARCHIVE_PREFIXES = [
    "https://data.binance.vision/data/futures/um/monthly/openInterest/BTCUSDT/",
    "https://data.binance.vision/data/futures/um/daily/openInterest/BTCUSDT/",
    "https://data.binance.vision/data/futures/um/monthly/metrics/BTCUSDT/",
    "https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/",
]


def head(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, method="HEAD")
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return {"url": url, "status": r.status,
                "content_length": r.headers.get("Content-Length"),
                "last_modified": r.headers.get("Last-Modified"),
                "etag": r.headers.get("ETag")}
    except Exception as e:
        return {"url": url, "error": repr(e)}


def main() -> None:
    out = {"archive_probes": [], "live_probes": []}
    for u in ARCHIVE_PREFIXES:
        out["archive_probes"].append(head(u))
    for u in LIVE_URLS:
        out["live_probes"].append(head(u))
    p = Path("temp/audit_a2_oi/oi_probe_v1.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
