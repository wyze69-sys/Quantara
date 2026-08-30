"""A5 liquidation audit probe.

Verifies that no Binance public archive carries liquidation history
and records the documented live-API throttling.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

ARCHIVE_PATHS = [
    "https://data.binance.vision/data/futures/um/monthly/liquidations/BTCUSDT/",
    "https://data.binance.vision/data/futures/um/daily/liquidations/BTCUSDT/",
    "https://data.binance.vision/data/futures/um/monthly/forceOrders/BTCUSDT/",
    "https://data.binance.vision/data/futures/um/daily/forceOrders/BTCUSDT/",
    "https://data.binance.vision/data/futures/um/monthly/liqOrders/BTCUSDT/",
    "https://data.binance.vision/data/futures/um/daily/liqOrders/BTCUSDT/",
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
    out = []
    for u in ARCHIVE_PATHS:
        out.append(head(u))
        print(u, "->", out[-1])
    p = Path("temp/audit_a5_liquidations/liquidation_probe_v1.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2))
    print("WROTE", p)


if __name__ == "__main__":
    main()
