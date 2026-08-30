"""A10 correction probe for A3/A4 headerless BTC synthetic klines."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("probe", Path("temp/probe_a7_a8_v1.py"))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

families = {
    "mark": "data/futures/um/monthly/markPriceKlines/BTCUSDT/1m/",
    "index": "data/futures/um/monthly/indexPriceKlines/BTCUSDT/1m/",
    "premium": "data/futures/um/monthly/premiumIndexKlines/BTCUSDT/1m/",
}
months = ["2019-12", "2020-01", "2020-06", "2020-12", "2021-01", "2021-12",
          "2022-01", "2022-11", "2022-12", "2023-01", "2023-12", "2024-01", "2024-12"]
out = {}
for label, prefix in families.items():
    inv = p.inventory_monthly(prefix, "BTCUSDT", "1m")
    available = {Path(x["key"]).name: x["key"] for x in inv.pop("all_objects") if x["key"].endswith(".zip")}
    samples = []
    for month in months:
        name = f"BTCUSDT-1m-{month}.zip"
        if name in available:
            samples.append(p.verify_file(available[name], p.parse_kline))
        else:
            samples.append({"expected_name": name, "present": False})
    inv["samples"] = samples
    out[label] = inv
path = Path("temp/audit_a10_corrections/a3a4_reprobe_v2.json")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(out, indent=2), encoding="utf-8")
print("WROTE", path)
for label, data in out.items():
    print("\n", label, data["present_2020_2024"], "/", data["expected_2020_2024"])
    for x in data["samples"]:
        if "parsed" in x:
            q=x["parsed"]
            print(Path(x["key"]).name, q["row_count"], q["header_present"], q["first_ts_utc"], q["last_ts_utc"], q["non_60s_gap_count"], q["gap_max_ms"], x["checksum_match"])
        else: print(x)
