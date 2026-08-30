"""A9 Kraken first-party OHLCVT range probe.

Reads only the ZIP central directory and XBTUSD hourly member from Kraken's
7.3 GB operator-linked Google Drive archive using HTTP Range requests.
"""
from __future__ import annotations

import hashlib
import http.cookiejar
import io
import json
import re
import datetime as dt
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

FILE_ID = "1ptNqWYidLkhb2VAKuLCxmp2OXEfGO-AP"
LANDING = f"https://drive.usercontent.google.com/download?id={FILE_ID}&export=download"
OUT = Path("temp/audit_a9_kraken")
OUT.mkdir(parents=True, exist_ok=True)


def get_confirmed_url(opener) -> tuple[str, str]:
    html = opener.open(LANDING, timeout=60).read().decode("utf-8", "replace")
    uuid = re.search(r'name="uuid" value="([^"]+)"', html).group(1)
    size = re.search(r'Kraken_OHLCVT\.zip</a> \(([^)]+)\)', html).group(1)
    url = "https://drive.usercontent.google.com/download?" + urllib.parse.urlencode(
        {"id": FILE_ID, "export": "download", "confirm": "t", "uuid": uuid}
    )
    return url, size


class RemoteRangeFile(io.RawIOBase):
    def __init__(self, opener):
        self.opener = opener
        url, _ = get_confirmed_url(self.opener)
        req = urllib.request.Request(url, method="GET", headers={"Range": "bytes=0-0"})
        r = self.opener.open(req, timeout=90)
        content_range = r.headers.get("Content-Range")
        if not content_range:
            raise RuntimeError(f"server did not honor range request: {dict(r.headers)}")
        self.size = int(content_range.split("/")[-1])
        self.pos = 0
        self.requests: list[dict] = []

    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos
    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_SET: self.pos = offset
        elif whence == io.SEEK_CUR: self.pos += offset
        elif whence == io.SEEK_END: self.pos = self.size + offset
        else: raise ValueError(whence)
        return self.pos
    def read(self, n=-1):
        if n == 0 or self.pos >= self.size: return b""
        end = self.size - 1 if n < 0 else min(self.size - 1, self.pos + n - 1)
        start = self.pos
        url, _ = get_confirmed_url(self.opener)
        req = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
        with self.opener.open(req, timeout=180) as r:
            data = r.read()
            cr = r.headers.get("Content-Range")
        if not cr:
            raise RuntimeError(f"range lost on read: requested={start}-{end} bytes={len(data)}")
        self.requests.append({"start": start, "end": end, "bytes": len(data)})
        self.pos += len(data)
        return data


def main():
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    _, advertised_size = get_confirmed_url(opener)
    remote = RemoteRangeFile(opener)
    with zipfile.ZipFile(remote) as z:
        names = z.namelist()
        candidates = [n for n in names if re.search(r"(^|/)(XBT|BTC).*(USD|USDT).*_(60|60m)\.csv$", n, re.I)]
        exact = [n for n in names if re.search(r"(^|/)XBTUSD_60\.csv$", n, re.I)]
        chosen = exact[0] if exact else (candidates[0] if candidates else None)
        if not chosen:
            raise RuntimeError(f"No XBTUSD hourly member; candidates={candidates[:20]}")
        info = z.getinfo(chosen)
        with z.open(chosen) as f:
            payload = f.read()
    text = payload.decode("utf-8-sig")
    lines = [x for x in text.splitlines() if x]
    rows = [x.split(",") for x in lines]
    first = rows[0]
    last = rows[-1]
    start = int(dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc).timestamp())
    end = int(dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc).timestamp())
    audit_rows = [r for r in rows if start <= int(r[0]) < end]
    audit_ts = [int(r[0]) for r in audit_rows]
    expected_ts = set(range(start, end, 3600))
    actual_ts = set(audit_ts)
    missing_ts = sorted(expected_ts - actual_ts)
    duplicate_count = len(audit_ts) - len(actual_ts)
    yearly = {}
    for year in range(2020, 2025):
        ys = int(dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc).timestamp())
        ye = int(dt.datetime(year + 1, 1, 1, tzinfo=dt.timezone.utc).timestamp())
        yr = [r for r in audit_rows if ys <= int(r[0]) < ye]
        yearly[str(year)] = {
            "row_count": len(yr),
            "expected_hours": (ye - ys) // 3600,
            "first_timestamp": yr[0][0] if yr else None,
            "last_timestamp": yr[-1][0] if yr else None,
        }
    result = {
        "kraken_support_page": "https://support.kraken.com/articles/360047124832-downloadable-historical-ohlcvt-open-high-low-close-volume-trades-data",
        "operator_linked_google_drive_id": FILE_ID,
        "advertised_archive_size": advertised_size,
        "remote_size_bytes": remote.size,
        "zip_member_count": len(names),
        "xbtusd_candidates": candidates,
        "chosen_member": chosen,
        "member_compress_size": info.compress_size,
        "member_file_size": info.file_size,
        "member_crc32": f"{info.CRC:08x}",
        "member_sha256": hashlib.sha256(payload).hexdigest(),
        "row_count": len(lines),
        "first_row": first,
        "last_row": last,
        "audit_2020_2024": {
            "row_count": len(audit_rows),
            "expected_hour_count": len(expected_ts),
            "distinct_timestamp_count": len(actual_ts),
            "duplicate_timestamp_count": duplicate_count,
            "missing_hour_count": len(missing_ts),
            "missing_timestamps": missing_ts,
            "first_row": audit_rows[0] if audit_rows else None,
            "last_row": audit_rows[-1] if audit_rows else None,
            "yearly": yearly,
        },
        "range_requests": remote.requests,
        "bytes_fetched_total": sum(r["bytes"] for r in remote.requests),
        "notes": [
            "Kraken states interval timestamp is candle start and omits intervals with no trades.",
            "Archive is first-party-linked but hosted on Google Drive and has no adjacent operator checksum sidecar.",
            "Computed member SHA-256 anchors this retrieval; ZIP CRC32 is from central directory.",
        ],
    }
    p = OUT / "a9_kraken_range_probe_v1.json"
    p.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ["remote_size_bytes", "zip_member_count", "chosen_member", "row_count", "first_row", "last_row", "member_sha256", "bytes_fetched_total"]}, indent=2))
    print("WROTE", p)


if __name__ == "__main__":
    main()
