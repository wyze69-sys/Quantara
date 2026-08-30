from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(rel: str):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def main() -> None:
    a7 = load("temp/audit_a7_a8/a7_ethusdt_probe_v1.json")
    a8 = load("temp/audit_a7_a8/a8_btcusdt_spot_probe_v1.json")
    a9 = load("temp/audit_a9_kraken/a9_kraken_range_probe_v1.json")
    a10 = load("temp/audit_a10_corrections/a3a4_reprobe_v2.json")

    for family in ("traded_1m", "funding", "mark_1m", "index_1m", "premium_1m"):
        item = a7["series"][family]
        assert item["present_2020_2024"] == 60, family
        assert item["missing_2020_2024"] == [], family
        assert item["missing_checksum_sidecars"] == [], family
        samples = [x for x in item["samples"] if "parsed" in x]
        assert samples and all(x["checksum_match"] for x in samples), family
        assert not any("error" in x for x in item["samples"]), family

    oi = a7["series"]["metrics_oi"]
    assert oi["first_available_date"] == "2021-12-01"
    assert oi["present_dates_2020_2024"] == 1127
    assert oi["missing_dates_after_first_through_2024"] == []
    assert oi["missing_checksum_sidecars"] == []

    assert a8["verified_months"] == 60
    assert a8["missing_months"] == []
    assert len(a8["results"]) == 60
    assert all(x["checksum_match"] for x in a8["results"])
    gaps = [g for x in a8["results"] for g in x["parsed"]["gaps"]]
    assert len(gaps) == 15
    assert sum(g["missing_minutes"] for g in gaps) == 2325
    assert a8["results"][0]["zip_sha256"] == "02df6da44ed8145fbb9ed819858185d9e2f15eb025c5bec8a4ea2d8738cd0d19"
    assert a8["results"][-1]["zip_sha256"] == "58fef0b7c7abce7a0201efd04ed3732f236f607f3fcecf228fb8384cad1ae2c1"

    ka = a9["audit_2020_2024"]
    assert a9["chosen_member"] == "master_q4/XBTUSD_60.csv"
    assert a9["member_sha256"] == "b45e7ce94911d4c1d13bf5c2e270c9219b81631292f7c40bab27e81f7f3f8297"
    assert a9["member_crc32"] == "c351083a"
    assert ka["expected_hour_count"] == 43848
    assert ka["row_count"] == ka["distinct_timestamp_count"] == 43828
    assert ka["duplicate_timestamp_count"] == 0
    assert ka["missing_hour_count"] == len(ka["missing_timestamps"]) == 20

    for family in ("mark", "index", "premium"):
        item = a10[family]
        assert item["present_2020_2024"] == 60, family
        assert item["missing_2020_2024"] == [], family
        assert item["missing_checksum_sidecars"] == [], family
        assert all(x["checksum_match"] for x in item["samples"] if "parsed" in x), family

    expected_digests = {
        "temp/probe_a7_a8_v1.py": "2e06c9d74d3535eaf6f36887c8d638e778efba79979e4f8a65346fe505aa0f79",
        "temp/audit_a7_a8/a7_ethusdt_probe_v1.json": "42ceb787835603c83c1b8c69c0628b616c943274e4f9d890f57971b83585fbad",
        "temp/audit_a7_a8/a8_btcusdt_spot_probe_v1.json": "68136566f8352c37a80446db3a63db9e1d1b0a803e7c7162108c2b3aa4c8c54f",
        "temp/probe_a9_kraken_range_v1.py": "54af490a94023b458b0627acb09d0422c7865b879720071787338cc5e434182c",
        "temp/audit_a9_kraken/a9_kraken_range_probe_v1.json": "d90cadf07b59c113656518523c6dc257e5971c17ed50546e91d25a6c55a55f33",
        "temp/probe_a10_a3a4_correction_v2.py": "14916bafb03150d119009c650a600120dcebbde4dc750a647ff410330f722bb1",
        "temp/audit_a10_corrections/a3a4_reprobe_v2.json": "d8ac8449e0fa58280cc8ecb0be8607277dc1ccc3968c2b1810eebcd8b4db1213",
    }
    for rel, expected in expected_digests.items():
        assert digest(ROOT / rel) == expected, rel

    docs = [
        ROOT / "docs/superpowers/plans/2026-08-31-a7-ethusdt-perpetual.md",
        ROOT / "docs/superpowers/plans/2026-08-31-a8-btcusdt-spot.md",
        ROOT / "docs/superpowers/plans/2026-08-31-a9-second-btc-venue-kraken.md",
        ROOT / "docs/superpowers/plans/2026-08-31-a10-live-acquisition-consolidation.md",
    ]
    for path in docs:
        assert path.exists() and path.stat().st_size > 1000, path

    print("PASS: A7-A10 evidence, counts, checksums, gaps, hashes, and reports verified")


if __name__ == "__main__":
    main()
