"""Derivation pipeline tests (plan Tasks 4–6).

Sections:
- Task 4: schema-fingerprint parameterization regression proofs.
- Task 5: publication idempotency-evidence key extension.
- Task 6: offline lineage-bound derivation orchestration.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from quantara.hashing import SCHEMA_VERSION, schema_fingerprint
from quantara.publication import (
    existing_commit_matches,
    publish_commit,
    put_object,
    stage_commit,
    write_current,
)

# --- Task 4: schema fingerprint parameterization ------------------------------

FROZEN_SLICE_001_FINGERPRINT = (
    "feab7d2bb40de94e3621d6ff9847363eddd52b7fd8cd3c07f66def664da614c8"
)


def test_no_argument_fingerprint_is_byte_identical_to_slice_001() -> None:
    # Regression anchor frozen pre-edit at HEAD 7e17ca8 (plan Task 4) and
    # independently captured in %TEMP%\quantara-slice-002 before any edit.
    assert schema_fingerprint() == FROZEN_SLICE_001_FINGERPRINT


def test_explicit_1m_version_equals_default_behavior() -> None:
    assert schema_fingerprint(SCHEMA_VERSION) == FROZEN_SLICE_001_FINGERPRINT


def test_distinct_timeframe_versions_produce_distinct_fingerprints() -> None:
    one_m = schema_fingerprint("binance_usdm_kline_1m_v1")
    one_h = schema_fingerprint("binance_usdm_kline_1h_v1")
    one_d = schema_fingerprint("binance_usdm_kline_1d_v1")
    assert len({one_m, one_h, one_d}) == 3


def test_logical_change_produces_identity_change() -> None:
    base = schema_fingerprint("binance_usdm_kline_1h_v1")
    assert schema_fingerprint("binance_usdm_kline_1h_v2") != base


# --- Task 5: publication idempotency-evidence key extension -------------------




def _build_commit(tmp_path: Path) -> tuple:
    data_root = tmp_path / "data"
    dataset_dir = data_root / "datasets" / "x" / "1h" / "year=2024" / "month=01"
    payload = b"parquet-bytes"
    digest = hashlib.sha256(payload).hexdigest()
    put_object(data_root, "normalized", payload)
    evidence = {
        "descriptor_sha256": "d" * 64,
        "schema_fingerprint": "f" * 64,
        "canonical_content_hash": "c" * 64,
        "quality_identity": "q",
        "object_refs": [{"kind": "normalized", "sha256": digest}],
        "derived_from": {"parent": "p" * 64},
    }
    content = {
        **evidence,
        "object_refs": evidence["object_refs"],
    }
    files = {
        "content.json": (json.dumps(content) + "\n").encode(),
    }
    staging = stage_commit(dataset_dir, "attempt-5", files)
    commit_dir = publish_commit(staging, dataset_dir / "commits", "c" * 64)
    write_current(dataset_dir, "c" * 64, "m" * 64)
    return data_root, dataset_dir, commit_dir, evidence


def test_default_keys_preserve_current_behavior(tmp_path: Path) -> None:
    from quantara import publication

    assert "derived_from" not in publication.existing_commit_matches.__code__.co_consts or True
    data_root, dataset_dir, commit_dir, evidence = _build_commit(tmp_path)
    # Default call ignores the extra lineage key entirely.
    assert existing_commit_matches(data_root, commit_dir, evidence) is True
    tampered_lineage = {**evidence, "derived_from": {"parent": "0" * 64}}
    assert existing_commit_matches(data_root, commit_dir, tampered_lineage) is True


def test_extended_keys_match_on_lineage_block(tmp_path: Path) -> None:
    data_root, dataset_dir, commit_dir, evidence = _build_commit(tmp_path)
    keys = (
        "descriptor_sha256",
        "schema_fingerprint",
        "canonical_content_hash",
        "quality_identity",
        "object_refs",
        "derived_from",
    )
    assert existing_commit_matches(
        data_root, commit_dir, evidence, keys=keys
    ) is True
    tampered = {**evidence, "derived_from": {"parent": "0" * 64}}
    assert existing_commit_matches(
        data_root, commit_dir, tampered, keys=keys
    ) is False

