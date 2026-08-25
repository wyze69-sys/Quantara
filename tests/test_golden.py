"""Golden offline transformation fixture (spec §15.6, plan Task 11).

The frozen expected values under tests/fixtures/golden/ were produced by an
independent stdlib-only generator script and reviewed; this test proves the
production parse -> assemble -> hash path reproduces them exactly, offline.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from conftest import VALID_DESCRIPTOR_YAML, write_text
from quantara.canonical import assemble_canonical_rows
from quantara.descriptor import load_descriptor
from quantara.hashing import canonical_content_hash, schema_fingerprint
from quantara.parsing import decode_member, parse_rows

FIXTURES = Path(__file__).parent / "fixtures" / "golden"


def test_golden_fixture_matches_independent_evidence(tmp_path) -> None:
    descriptor = load_descriptor(
        write_text(tmp_path / "cfg", VALID_DESCRIPTOR_YAML)
    )
    expected = json.loads((FIXTURES / "expected.json").read_text(encoding="utf-8"))
    member_text = decode_member((FIXTURES / "golden.csv").read_bytes())

    source_rows = parse_rows(member_text, descriptor)
    assembled, order_ok = assemble_canonical_rows(source_rows, descriptor)

    assert len(assembled) == expected["row_count"]
    assert schema_fingerprint() == expected["schema_fingerprint"]

    arrays = [row.to_content_array() for row in assembled]
    assert arrays == expected["rows"]

    assert canonical_content_hash(
        schema_fingerprint(), arrays
    ) == expected["canonical_content_hash"]


def test_golden_fixture_covers_required_cases() -> None:
    rows = json.loads((FIXTURES / "expected.json").read_text(encoding="utf-8"))["rows"]
    zero_volume = [
        r for r in rows if Decimal(r[17]) == 0 and Decimal(r[18]) == 0
    ]
    high_precision = [r for r in rows if r[10] == 1704067200000 + 120_000]
    large_count = [r for r in rows if r[19] == 2_000_000_000]
    first_boundary = [r for r in rows if r[10] == 1704067200000]
    assert zero_volume and high_precision and large_count and first_boundary
    # High-precision golden values survive in the canonical 18-digit rendering.
    assert high_precision[0][13] == "43000.000000000000001000"
    assert high_precision[0][15] == "42999.999999999999999000"
