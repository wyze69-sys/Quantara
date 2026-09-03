"""IR-2026-09-03-1 evidence: repo-wide value-blind scan for 2025-range values.

Walks every JSON under temp/ and reports any integer, digit-string, or ISO date
whose value falls in [2025-01-01, 2026-01-01) UTC. Method recorded in the
Stage 2 plan Incident log; run from repo root:

    .venv/Scripts/python.exe temp/scan_2025_exposure.py
"""

import glob
import json
import re

TH_LO, TH_HI = 1735689600, 1767225600  # [2025-01-01, 2026-01-01) UTC
ISO_2025 = re.compile(r"2025-\d{2}-\d{2}")


def walk(node, path, hits):
    if isinstance(node, dict):
        for k, v in node.items():
            walk(v, path + "." + str(k), hits)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            walk(v, f"{path}[{i}]", hits)
    elif isinstance(node, bool):
        return
    elif isinstance(node, int):
        if TH_LO <= node < TH_HI:
            hits.append((path, node))
    elif isinstance(node, str):
        if node.isdigit() and TH_LO <= int(node) < TH_HI:
            hits.append((path, int(node)))
        elif ISO_2025.search(node):
            hits.append((path, node[:40]))


for f in sorted(glob.glob("temp/**/*.json", recursive=True)):
    try:
        data = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    hits = []
    walk(data, "$", hits)
    if hits:
        print(f"{f}: {len(hits)} hit(s)")
        for p, v in hits:
            print(f"   {p} = {v}")
    else:
        print(f"{f}: clean")
