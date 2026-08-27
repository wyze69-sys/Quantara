"""Acceptance tests for the deterministic canonical-stage benchmark harness."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.stage_baseline import build_corpus, main, run_baseline  # noqa: E402

from quantara.parsing import decode_member, parse_rows  # noqa: E402

EXPECTED_STAGES = {
    "parse",
    "assemble",
    "quality",
    "parquet_write",
    "verify_parquet",
    "content_hash",
}


def _assert_evidence_shape(evidence: dict) -> None:
    assert set(evidence) == {
        "harness_version",
        "row_count",
        "repeats",
        "stages",
        "environment",
    }
    assert set(evidence["stages"]) == EXPECTED_STAGES
    for result in evidence["stages"].values():
        assert set(result) == {
            "seconds_all",
            "seconds_median",
            "tracemalloc_peak_bytes",
        }
        assert isinstance(result["seconds_all"], list)
        assert isinstance(result["seconds_median"], float)
        assert result["seconds_median"] >= 0
        assert isinstance(result["tracemalloc_peak_bytes"], int)
        assert result["tracemalloc_peak_bytes"] >= 0


def test_synthetic_corpus_is_deterministic() -> None:
    first_text, first_descriptor = build_corpus(240, seed=20260827)
    second_text, second_descriptor = build_corpus(240, seed=20260827)

    assert first_text == second_text
    assert first_descriptor.canonical_semantics() == second_descriptor.canonical_semantics()


def test_baseline_evidence_shape(tmp_path: Path) -> None:
    evidence = run_baseline(row_count=240, repeats=1, workdir=tmp_path)

    json.dumps(evidence)
    _assert_evidence_shape(evidence)


def test_baseline_cli_emits_json(capsys) -> None:
    assert main(["--rows", "240", "--repeats", "1", "--json"]) == 0

    evidence = json.loads(capsys.readouterr().out)
    _assert_evidence_shape(evidence)


def test_parse_stage_corpus_passes_production_validation() -> None:
    row_count = 240
    corpus_text, descriptor = build_corpus(row_count)

    rows = parse_rows(decode_member(corpus_text.encode("utf-8")), descriptor)

    assert len(rows) == row_count
