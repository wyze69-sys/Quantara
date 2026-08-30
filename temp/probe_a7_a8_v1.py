"""A7/A8 first-party Binance archive audit.

A7 inventories ETHUSDT USD-M perpetual archives for 2020-2024 and
samples boundary files with checksum/schema/timestamp verification.
A8 downloads every BTCUSDT spot 1m month in 2020-2024 and verifies
checksums, coverage, row counts, and all timestamp gaps.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
HTTPS = "https://data.binance.vision/"
OUT = Path("temp/audit_a7_a8")
OUT.mkdir(parents=True, exist_ok=True)


def fetch(url: str, timeout: int = 60, attempts: int = 4) -> bytes:
    last = None
    for n in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Quantara-audit/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as exc:
            last = exc
            if n + 1 < attempts:
                time.sleep(1.5 * (n + 1))
    raise last  # type: ignore[misc]


def list_keys(prefix: str) -> list[dict]:
    token = None
    rows: list[dict] = []
    while True:
        q = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
        if token:
            q["continuation-token"] = token
        body = fetch(S3 + "?" + urllib.parse.urlencode(q))
        root = ET.fromstring(body)
        ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
        for c in root.findall("s3:Contents", ns):
            rows.append({
                "key": c.findtext("s3:Key", default="", namespaces=ns),
                "size": int(c.findtext("s3:Size", default="0", namespaces=ns)),
                "etag": c.findtext("s3:ETag", default="", namespaces=ns).strip('"'),
                "last_modified": c.findtext("s3:LastModified", default="", namespaces=ns),
            })
        if root.findtext("s3:IsTruncated", default="false", namespaces=ns) != "true":
            break
        token = root.findtext("s3:NextContinuationToken", namespaces=ns)
        if not token:
            raise RuntimeError(f"truncated listing without token: {prefix}")
    return rows


def months(start: str, end: str) -> list[str]:
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y += 1
            m = 1
    return out


def dates(start: str, end: str) -> list[str]:
    d = dt.date.fromisoformat(start)
    e = dt.date.fromisoformat(end)
    out = []
    while d <= e:
        out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def is_header(row: list[str]) -> bool:
    if not row:
        return True
    try:
        int(row[0])
        return False
    except ValueError:
        return True


def utc_ms(v: int) -> str:
    return dt.datetime.fromtimestamp(v / 1000, tz=dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_kline(zb: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(zb)) as z:
        member = z.namelist()[0]
        raw = z.read(member).decode("utf-8-sig")
    all_rows = list(csv.reader(io.StringIO(raw)))
    header_present = is_header(all_rows[0])
    header = all_rows[0] if header_present else None
    rows = all_rows[1:] if header_present else all_rows
    ts = [int(r[0]) for r in rows]
    diffs = [b - a for a, b in zip(ts, ts[1:])]
    gaps = []
    for a, b in zip(ts, ts[1:]):
        if b - a != 60_000:
            gaps.append({"after_ms": a, "after_utc": utc_ms(a), "before_ms": b,
                         "before_utc": utc_ms(b), "delta_ms": b - a,
                         "missing_minutes": max(0, (b - a) // 60_000 - 1)})
    return {
        "member": member,
        "header_present": header_present,
        "header": header,
        "column_count": len(rows[0]) if rows else 0,
        "row_count": len(rows),
        "first_ts_ms": ts[0] if ts else None,
        "first_ts_utc": utc_ms(ts[0]) if ts else None,
        "last_ts_ms": ts[-1] if ts else None,
        "last_ts_utc": utc_ms(ts[-1]) if ts else None,
        "gap_min_ms": min(diffs) if diffs else None,
        "gap_max_ms": max(diffs) if diffs else None,
        "non_60s_gap_count": len(gaps),
        "gaps": gaps,
        "sample_first_row": rows[0] if rows else None,
        "sample_last_row": rows[-1] if rows else None,
    }


def parse_funding(zb: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(zb)) as z:
        member = z.namelist()[0]
        raw = z.read(member).decode("utf-8-sig")
    all_rows = list(csv.reader(io.StringIO(raw)))
    hp = is_header(all_rows[0])
    rows = all_rows[1:] if hp else all_rows
    ts = [int(r[0]) for r in rows]
    diffs = [b - a for a, b in zip(ts, ts[1:])]
    return {"member": member, "header_present": hp,
            "header": all_rows[0] if hp else None, "column_count": len(rows[0]),
            "row_count": len(rows), "first_ts_utc": utc_ms(ts[0]),
            "last_ts_utc": utc_ms(ts[-1]), "interval_hours_values": sorted({r[1] for r in rows}),
            "gap_min_ms": min(diffs) if diffs else None, "gap_max_ms": max(diffs) if diffs else None,
            "sample_first_row": rows[0], "sample_last_row": rows[-1]}


def parse_metrics(zb: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(zb)) as z:
        member = z.namelist()[0]
        raw = z.read(member).decode("utf-8-sig")
    all_rows = list(csv.reader(io.StringIO(raw)))
    hp = is_header(all_rows[0])
    rows = all_rows[1:] if hp else all_rows
    distinct_rows = {tuple(r) for r in rows}
    timestamps = [r[0] for r in rows]
    return {"member": member, "header_present": hp,
            "header": all_rows[0] if hp else None, "column_count": len(rows[0]),
            "row_count": len(rows), "distinct_row_count": len(distinct_rows),
            "distinct_timestamp_count": len(set(timestamps)),
            "first_ts": timestamps[0], "last_ts": timestamps[-1],
            "sample_first_row": rows[0], "sample_last_row": rows[-1]}


def verify_file(key: str, parser) -> dict:
    url = HTTPS + key
    zb = fetch(url)
    digest = hashlib.sha256(zb).hexdigest()
    checksum_text = fetch(url + ".CHECKSUM").decode().strip()
    expected = checksum_text.split()[0]
    return {"key": key, "url": url, "zip_bytes": len(zb), "zip_sha256": digest,
            "checksum_text": checksum_text, "checksum_match": digest == expected,
            "parsed": parser(zb)}


def inventory_monthly(prefix: str, symbol: str, stem: str) -> dict:
    keys = list_keys(prefix)
    zip_names = {Path(x["key"]).name for x in keys if x["key"].endswith(".zip")}
    checksum_names = {Path(x["key"]).name for x in keys if x["key"].endswith(".zip.CHECKSUM")}
    expected = months("2020-01", "2024-12")
    expected_zips = {f"{symbol}-{stem}-{m}.zip" for m in expected}
    present = sorted(expected_zips & zip_names)
    missing = sorted(expected_zips - zip_names)
    missing_checksums = sorted(f + ".CHECKSUM" for f in present if f + ".CHECKSUM" not in checksum_names)
    return {"prefix": prefix, "object_count": len(keys), "first_key": keys[0]["key"] if keys else None,
            "last_key": keys[-1]["key"] if keys else None,
            "expected_2020_2024": len(expected_zips), "present_2020_2024": len(present),
            "missing_2020_2024": missing, "missing_checksum_sidecars": missing_checksums,
            "all_objects": keys}


def a7() -> dict:
    symbol = "ETHUSDT"
    configs = [
        ("traded_1m", f"data/futures/um/monthly/klines/{symbol}/1m/", "1m", parse_kline),
        ("funding", f"data/futures/um/monthly/fundingRate/{symbol}/", "fundingRate", parse_funding),
        ("mark_1m", f"data/futures/um/monthly/markPriceKlines/{symbol}/1m/", "1m", parse_kline),
        ("index_1m", f"data/futures/um/monthly/indexPriceKlines/{symbol}/1m/", "1m", parse_kline),
        ("premium_1m", f"data/futures/um/monthly/premiumIndexKlines/{symbol}/1m/", "1m", parse_kline),
    ]
    out: dict = {"retrieved_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "series": {}}
    sample_months = ["2019-12", "2020-01", "2020-09", "2020-12", "2021-01", "2021-12",
                     "2022-01", "2022-12", "2023-01", "2023-12", "2024-01", "2024-12"]
    for label, prefix, stem, parser in configs:
        inv = inventory_monthly(prefix, symbol, stem)
        samples = []
        available = {Path(x["key"]).name: x["key"] for x in inv["all_objects"] if x["key"].endswith(".zip")}
        for m in sample_months:
            name = f"{symbol}-{stem}-{m}.zip"
            if name in available:
                try:
                    samples.append(verify_file(available[name], parser))
                except Exception as exc:
                    samples.append({"key": available[name], "error": repr(exc)})
            else:
                samples.append({"expected_name": name, "present": False})
        inv.pop("all_objects")
        inv["samples"] = samples
        out["series"][label] = inv

    mprefix = f"data/futures/um/daily/metrics/{symbol}/"
    mkeys = list_keys(mprefix)
    zip_by_date = {}
    checksum_names = set()
    for x in mkeys:
        name = Path(x["key"]).name
        if name.endswith(".zip.CHECKSUM"):
            checksum_names.add(name)
        elif name.endswith(".zip"):
            date = name.removeprefix(f"{symbol}-metrics-").removesuffix(".zip")
            zip_by_date[date] = x["key"]
    sorted_dates = sorted(zip_by_date)
    expected_after_first = dates(max("2020-01-01", sorted_dates[0]), "2024-12-31") if sorted_dates else []
    missing = sorted(set(expected_after_first) - set(sorted_dates))
    sample_dates = ["2020-08-31", "2020-09-01", "2020-09-02", "2020-12-31", "2021-01-01",
                    "2021-12-31", "2022-01-01", "2022-12-31", "2023-01-01", "2023-12-31",
                    "2024-01-01", "2024-12-31"]
    msamples = []
    for d in sample_dates:
        if d in zip_by_date:
            try:
                msamples.append(verify_file(zip_by_date[d], parse_metrics))
            except Exception as exc:
                msamples.append({"key": zip_by_date[d], "error": repr(exc)})
        else:
            msamples.append({"date": d, "present": False})
    out["series"]["metrics_oi"] = {
        "prefix": mprefix, "object_count": len(mkeys),
        "first_available_date": sorted_dates[0] if sorted_dates else None,
        "last_available_date": sorted_dates[-1] if sorted_dates else None,
        "present_dates_2020_2024": sum("2020-01-01" <= d <= "2024-12-31" for d in sorted_dates),
        "missing_dates_after_first_through_2024": missing,
        "missing_checksum_sidecars": sorted(f"{symbol}-metrics-{d}.zip.CHECKSUM" for d in sorted_dates
                                             if f"{symbol}-metrics-{d}.zip.CHECKSUM" not in checksum_names),
        "samples": msamples,
    }
    return out


def a8() -> dict:
    symbol = "BTCUSDT"
    prefix = f"data/spot/monthly/klines/{symbol}/1m/"
    keys = list_keys(prefix)
    by_name = {Path(x["key"]).name: x["key"] for x in keys if x["key"].endswith(".zip")}
    wanted = [f"{symbol}-1m-{m}.zip" for m in months("2020-01", "2024-12")]
    missing = [n for n in wanted if n not in by_name]
    results = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(verify_file, by_name[n], parse_kline): n for n in wanted if n in by_name}
        for fut in as_completed(futures):
            n = futures[fut]
            try:
                results.append(fut.result())
            except Exception as exc:
                results.append({"name": n, "error": repr(exc)})
    results.sort(key=lambda x: x.get("key", x.get("name", "")))
    return {"retrieved_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "prefix": prefix,
            "object_count": len(keys), "expected_months": 60,
            "verified_months": sum("error" not in x for x in results),
            "missing_months": missing, "results": results}


def main() -> None:
    print("Running A7 ETHUSDT archive inventory and samples...")
    r7 = a7()
    (OUT / "a7_ethusdt_probe_v1.json").write_text(json.dumps(r7, indent=2), encoding="utf-8")
    print("A7 written")
    print("Running A8 BTCUSDT spot all-month verification...")
    r8 = a8()
    (OUT / "a8_btcusdt_spot_probe_v1.json").write_text(json.dumps(r8, indent=2), encoding="utf-8")
    print("A8 written", {"verified": r8["verified_months"], "missing": r8["missing_months"],
                         "errors": sum("error" in x for x in r8["results"])})


if __name__ == "__main__":
    main()
