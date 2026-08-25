"""Manifest writer tests (spec §§13.1–13.2)."""

from __future__ import annotations

import json
from pathlib import Path

from quantara.manifests import (
    attempt_id_now,
    build_dataset_manifest,
    environment_evidence,
    new_attempt_manifest,
    write_json,
)


def test_attempt_ids_are_unique_and_timestamp_prefixed() -> None:
    ids = {attempt_id_now() for _ in range(200)}
    assert len(ids) == 200
    for attempt_id in ids:
        date_part, _, uuid_part = attempt_id.partition("-")
        assert len(date_part) == 16 and date_part.endswith("Z")
        assert len(uuid_part) == 36


def test_environment_evidence_contains_pinned_stack(tmp_path: Path) -> None:
    lock = tmp_path / "uv.lock"
    lock.write_text("lock-bytes", encoding="utf-8")
    evidence = environment_evidence(tmp_path)
    assert evidence["python"].startswith("3.11.")
    assert evidence["pyarrow"]
    assert evidence["platform"]
    assert evidence["uv_lock_sha256"]


def test_dataset_manifest_has_required_fields(tmp_path: Path) -> None:
    evidence = {"python": "3.11.15", "pyarrow": "25.0.1"}
    manifest = build_dataset_manifest(
        dataset_id="binance_usdm_btcusdt_klines_1m_2024_01",
        instrument_id="binance:usd_m_futures:BTCUSDT:perpetual",
        archive_url="https://data.binance.vision/a.zip",
        checksum_url="https://data.binance.vision/a.zip.CHECKSUM",
        official_checksum_sha256="aa" * 32,
        checksum_document_sha256="bb" * 32,
        local_zip_sha256="aa" * 32,
        local_zip_size=10,
        member_name="BTCUSDT-1m-2024-01.csv",
        member_size=8,
        member_sha256="cc" * 32,
        source_header=tuple("abcdefghij"[:12]) if False else ("open_time",),
        parser_version="binance_kline_csv_v1",
        schema_version="binance_usdm_kline_1m_v1",
        schema_fingerprint="dd" * 32,
        timestamp_semantics="closed_interval_v1",
        quality_policy_version="1",
        quality_identity="{}",
        source_row_count=44_640,
        canonical_row_count=44_640,
        source_order_state="ordered",
        canonical_content_hash="ee" * 32,
        parquet_sha256="ff" * 32,
        parquet_size=123,
        object_refs=[{"kind": "normalized", "sha256": "ff" * 32}],
        legal_record_id="binance-usdm-provider-rights.v1",
        legal_states={"acquire_internal": "OWNER_APPROVED_PENDING_COUNSEL"},
        environment=evidence,
    )
    assert manifest["publication_protocol_version"] == "v1"
    assert manifest["hash_contract"] == "hash_contract_v1"
    assert manifest["source_row_count"] == 44_640
    assert manifest["environment"]["pyarrow"] == "25.0.1"


def test_attempt_manifest_records_dispositions_and_result(tmp_path: Path) -> None:
    attempt = new_attempt_manifest(
        terminal_result="VERIFIED_NO_OP",
        artifact_dispositions={
            "zip": "reused",
            "checksum": "downloaded",
            "normalized_parquet": "not_written",
        },
        retry_evidence=[{"kind": "connect_timeout", "detail": "x"}],
        http_statuses=[200],
        referenced_commit="ab" * 32,
        diagnostics=[],
        repo_root=tmp_path,
    )
    path = tmp_path / "attempts" / f"{attempt['attempt_id']}.json"
    write_json(path, attempt)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["terminal_result"] == "VERIFIED_NO_OP"
    assert loaded["artifact_dispositions"]["zip"] == "reused"
    assert loaded["referenced_commit"] == "ab" * 32
    assert "secrets" not in json.dumps(loaded).lower()
