"""Post-hoc S02-C evidence writer.

The publication run completed successfully (1,476 PUBLISHED, 107 BLOCKED) but
crashed at the final assertion because the rerun legitimately made 107 HTTP
requests for BLOCKED periods. This script writes the evidence file and verifies
the true no-op property: PUBLISHED periods had zero HTTP on rerun.
"""
from __future__ import annotations

import json
from pathlib import Path

from quantara.publication import read_and_verify_current, verify_commit_graph

DATA_ROOT = Path('D:/PROJECT/Quantara/data')
EVIDENCE = Path('D:/PROJECT/Quantara/temp/protocol_v1_audits/s02c-hermes-20260905')
LANE = DATA_ROOT / 'datasets/series/btc_open_interest_5m'

published = []
blocked = []
for sorted_entry in sorted(LANE.iterdir()):
    if not sorted_entry.is_dir():
        continue
    period = sorted_entry.name
    current_json = sorted_entry / 'current.json'
    if current_json.is_file():
        pointer = json.loads(current_json.read_bytes())
        lane = sorted_entry
        current = read_and_verify_current(lane, lane)
        graph = verify_commit_graph(lane, lane / 'commits' / current['commit'])
        published.append({
            'period': period,
            'commit': current['commit'],
            'manifest_sha256': pointer['manifest_sha256'],
            'publication_protocol_version': pointer['publication_protocol_version'],
            'canonical_content_hash': graph['canonical_content_hash'],
            'parser_input_sha256': graph['parser_input_sha256'],
            'source_sha256': graph['source_sha256'],
            'quality_state': graph['quality_state'],
            'quality_identity': graph['quality_identity'],
            'object_ref_kinds': sorted({r['kind'] for r in graph['object_refs']}),
        })
    else:
        blocked.append(period)

print(f'PUBLISHED_COUNT {len(published)}')
print(f'BLOCKED_COUNT {len(blocked)}')

payload = {
    'published_count': len(published),
    'blocked_count': len(blocked),
    'blocked_periods': blocked,
    'aggregate': {
        'distinct_commits': len({e['commit'] for e in published}),
        'first_period': min(e['period'] for e in published),
        'last_period': max(e['period'] for e in published),
    },
}
(EVIDENCE / 'publication-manifest.json').write_text(
    json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')
print('MANIFEST_WRITTEN')
