"""Strict quality warning approval loader and effective evaluation tests.

Tests cover §5.1, §5.3, §5.4, §5.5, and Task 1 requirements:
- strict YAML shape, types, and canonical self-hash;
- repository-contained path enforcement (no absolute or traversal paths);
- exact warning finding coverage and contextual bindings;
- raw PASS rejection of unnecessary approvals;
- raw FAIL hard non-overridability;
- policy 1 warning blocking;
- policy 2 exact authenticated approval to WARN_APPROVED;
- adversarial tamper/drift rejection.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from quantara.jcs import canonicalize
from quantara.quality import Finding, QualityReport
from quantara.quality_approval import (
    APPROVAL_SCHEMA,
    QualityApprovalError,
    canonical_finding_sha256,
    evaluate_effective_quality,
    load_approval_record,
    parse_approval_dict,
    validate_approval_path,
)

FROZEN_DATASET_ID = "binance_usdm_btcusdt_klines_1m_2024"
FROZEN_CONTENT_HASH = (
    "28137ac3d5bf2f46156caf0dc188bd33cb392f4d110d8353af759c21b8648db5"
)
FROZEN_SCHEMA_FINGERPRINT = (
    "f0d6a8dd92a1a4f1dcf29c4f9222c4ec7daa75a2e648ead6b4bfa453d347724a"
)
FROZEN_RAW_QUALITY_IDENTITY_SHA256 = (
    "10e100b458244a3d496666afaf37ef1518da15e8d8503d463abc632eccf343b8"
)
FROZEN_FINDING_SHA256 = (
    "6db969a652860d9fe74f6725e33f7aaad43c9cfe1b35fbeed7bfccecb24bcc68"
)
FROZEN_SOURCES = (
    "21eeac04a76a7a35b10467e5e752fb2f8cff77cdeb57df6b50a23ce8d69bb190",
    "1407acbf8ad99911bdf582805699b7e85fdbc346dbe12618ce8b6369f0d8058d",
    "040b8e448e4243072b88b0d9908dfebed91bba943b75f4e831fa5337a2e1dab9",
    "6a41f002da0c8e3f60bd46c841ea4ed766fb195764ad3b6b10e4f508d29c2eb7",
    "42de617ed643def54b5a2c3fceb7cd2edec91aafaa01104a097b2ded5c5122d4",
    "93499da4990fec5471bb0d73c91116e7d20a8b2697d7a4491665d6d1b8e85c85",
    "97f9cd5104a33828c5c2d8d03a2796d600102ab88737d1c6da515b9609540c3c",
    "f69dbcebfd7108dc97825bd6c35d8d9a51745082f66617cb69de888e867e8e89",
    "16fe2e13728236bfbd3efee99671612daadeea3b62dfd55d8874feae9faa4946",
    "aa8c79ad120a8d870e23276d1ad5966f99f59bc0a1886ef5927a3808a5efee36",
    "9c3dad038f4b043ec51d4200f57d15a0a07b3fc32b3ea3dca6a96543b9624941",
    "bfce141d2a152c2b94d85b797fe18ebfa195fa0e6091a7ccc06663ae1309466f",
)


def _make_valid_approval_payload() -> dict:
    semantics = {
        "schema": APPROVAL_SCHEMA,
        "record_id": "binance-usdm-btcusdt-1m-2024-zero-volume-v1",
        "dataset_id": FROZEN_DATASET_ID,
        "canonical_content_hash": FROZEN_CONTENT_HASH,
        "schema_fingerprint": FROZEN_SCHEMA_FINGERPRINT,
        "source_sha256": list(FROZEN_SOURCES),
        "quality_policy_version": "2",
        "quality_identity_sha256": FROZEN_RAW_QUALITY_IDENTITY_SHA256,
        "approved_findings": [
            {
                "check_id": "zero_volume_candle",
                "count": 89,
                "canonical_finding_sha256": FROZEN_FINDING_SHA256,
            }
        ],
        "approver": "258711354+wyze69-sys@users.noreply.github.com",
        "decision_time_utc": "2026-08-28T07:07:38Z",
        "rationale": (
            "official source contains 89 no-trade candles; rows are preserved, "
            "all hard invariants pass, and approval is internal-analysis-only."
        ),
        "scope": (
            "exact full-year BTCUSDT USD-M 1m canonical content only; "
            "no wildcard or future-data scope."
        ),
    }
    self_hash = hashlib.sha256(canonicalize(semantics).encode("utf-8")).hexdigest()
    return {**semantics, "record_sha256": self_hash}


def _make_sample_quality_report() -> QualityReport:
    findings = [
        Finding(
            check_id="row_count_matches_expected",
            outcome="pass",
            severity="hard",
            count=527040,
            evidence={"approved_rows": 527040, "actual_rows": 527040},
        ),
        Finding(
            check_id="first_boundary_exact",
            outcome="pass",
            severity="hard",
            count=0,
            evidence={
                "approved_start": 1704067200000,
                "observed_first_open": 1704067200000,
            },
        ),
        Finding(
            check_id="last_boundary_exact",
            outcome="pass",
            severity="hard",
            count=0,
            evidence={
                "approved_last_open": 1735689540000,
                "observed_last_open": 1735689540000,
            },
        ),
        Finding(
            check_id="unique_open_times",
            outcome="pass",
            severity="hard",
            count=0,
            evidence={"violations": 0},
        ),
        Finding(
            check_id="strictly_ascending_open_times",
            outcome="pass",
            severity="hard",
            count=0,
            evidence={"violations": 0},
        ),
        Finding(
            check_id="adjacency_exactly_60000ms",
            outcome="pass",
            severity="hard",
            count=0,
            evidence={"violations": 0},
        ),
        Finding(
            check_id="period_membership_respected",
            outcome="pass",
            severity="hard",
            count=0,
            evidence={"violations": 0},
        ),
        Finding(
            check_id="ohlc_bounds_hold",
            outcome="pass",
            severity="hard",
            count=0,
            evidence={"violations": 0},
        ),
        Finding(
            check_id="prices_strictly_positive",
            outcome="pass",
            severity="hard",
            count=0,
            evidence={"violations": 0},
        ),
        Finding(
            check_id="volumes_and_counts_nonnegative",
            outcome="pass",
            severity="hard",
            count=0,
            evidence={"violations": 0},
        ),
        Finding(
            check_id="close_time_equals_open_plus_59999",
            outcome="pass",
            severity="hard",
            count=0,
            evidence={"violations": 0},
        ),
        Finding(
            check_id="taker_buy_within_counterpart_volumes",
            outcome="pass",
            severity="hard",
            count=0,
            evidence={"violations": 0},
        ),
        Finding(
            check_id="source_order_invalid",
            outcome="pass",
            severity="warning",
            count=0,
            evidence={
                "note": "complete unique source rows required sorting",
                "occurrences": 0,
            },
        ),
        Finding(
            check_id="zero_volume_candle",
            outcome="warn",
            severity="warning",
            count=89,
            evidence={"occurrences": 89},
        ),
        Finding(
            check_id="nonzero_source_ignore",
            outcome="pass",
            severity="warning",
            count=0,
            evidence={"occurrences": 0},
        ),
    ]
    return QualityReport(findings=findings, state="WARN_BLOCKED")


def test_canonical_finding_sha256() -> None:
    finding = Finding(
        check_id="zero_volume_candle",
        outcome="warn",
        severity="warning",
        count=89,
        evidence={"occurrences": 89},
    )
    digest = canonical_finding_sha256(finding)
    assert digest == FROZEN_FINDING_SHA256


def test_load_valid_approval_record(tmp_path: Path) -> None:
    payload = _make_valid_approval_payload()
    record_file = tmp_path / "valid-approval.yaml"
    record_file.write_text(yaml.dump(payload), encoding="utf-8")

    record = load_approval_record(record_file, repo_root=tmp_path)
    assert record.schema == APPROVAL_SCHEMA
    assert record.record_id == "binance-usdm-btcusdt-1m-2024-zero-volume-v1"
    assert record.dataset_id == FROZEN_DATASET_ID
    assert record.quality_policy_version == "2"
    assert len(record.approved_findings) == 1
    assert record.approved_findings[0].check_id == "zero_volume_candle"
    assert record.approved_findings[0].count == 89
    assert record.approved_findings[0].canonical_finding_sha256 == FROZEN_FINDING_SHA256
    record.verify_self_hash()


def test_effective_quality_warn_approved_on_exact_match() -> None:
    payload = _make_valid_approval_payload()
    record = parse_approval_dict(payload)
    report = _make_sample_quality_report()

    decision = evaluate_effective_quality(
        raw_report=report,
        quality_policy_version="2",
        approval_record=record,
        dataset_id=FROZEN_DATASET_ID,
        canonical_content_hash=FROZEN_CONTENT_HASH,
        schema_fingerprint=FROZEN_SCHEMA_FINGERPRINT,
        source_sha256=FROZEN_SOURCES,
    )

    assert decision.effective_state == "WARN_APPROVED"
    assert decision.raw_state == "WARN_BLOCKED"
    assert decision.policy_version == "2"
    assert decision.raw_identity == report.identity()
    assert decision.raw_identity_sha256 == FROZEN_RAW_QUALITY_IDENTITY_SHA256
    assert decision.approval_record_id == record.record_id
    assert decision.approval_record_sha256 == record.record_sha256

    # Verify decision identity includes all required fields
    identity_dict = yaml.safe_load(decision.decision_identity())
    assert identity_dict == {
        "approval_record_id": record.record_id,
        "approval_record_sha256": record.record_sha256,
        "effective_state": "WARN_APPROVED",
        "policy_version": "2",
        "raw_identity_sha256": FROZEN_RAW_QUALITY_IDENTITY_SHA256,
    }


def test_effective_quality_blocked_on_missing_approval_under_policy_2() -> None:
    report = _make_sample_quality_report()
    decision = evaluate_effective_quality(
        raw_report=report,
        quality_policy_version="2",
        approval_record=None,
    )
    assert decision.effective_state == "WARN_BLOCKED"
    assert decision.raw_state == "WARN_BLOCKED"


def test_effective_quality_blocked_under_policy_1() -> None:
    payload = _make_valid_approval_payload()
    record = parse_approval_dict(payload)
    report = _make_sample_quality_report()

    decision = evaluate_effective_quality(
        raw_report=report,
        quality_policy_version="1",
        approval_record=record,
    )
    assert decision.effective_state == "WARN_BLOCKED"
    assert decision.raw_state == "WARN_BLOCKED"
    assert decision.policy_version == "1"


def test_raw_pass_rejects_unnecessary_approval() -> None:
    pass_report = QualityReport(
        findings=[Finding("check1", "pass", "hard", 0, {})],
        state="PASS",
    )
    payload = _make_valid_approval_payload()
    record = parse_approval_dict(payload)

    with pytest.raises(QualityApprovalError, match="cannot be attached to a raw PASS"):
        evaluate_effective_quality(
            raw_report=pass_report,
            quality_policy_version="2",
            approval_record=record,
        )

    clean_decision = evaluate_effective_quality(
        raw_report=pass_report,
        quality_policy_version="2",
        approval_record=None,
    )
    assert clean_decision.effective_state == "PASS"


def test_raw_fail_cannot_be_approved() -> None:
    fail_report = QualityReport(
        findings=[
            Finding("broken_ohlc_invariant", "fail", "hard", 1, {"violations": 1}),
            Finding("zero_volume_candle", "warn", "warning", 89, {"occurrences": 89}),
        ],
        state="FAIL",
    )
    payload = _make_valid_approval_payload()
    record = parse_approval_dict(payload)

    decision = evaluate_effective_quality(
        raw_report=fail_report,
        quality_policy_version="2",
        approval_record=record,
    )
    assert decision.effective_state == "FAIL"
    assert decision.raw_state == "FAIL"


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("dataset_id", "stale_dataset_id"),
        ("canonical_content_hash", "a" * 64),
        ("schema_fingerprint", "b" * 64),
        ("quality_identity_sha256", "c" * 64),
        ("quality_policy_version", "1"),
    ],
)
def test_stale_bindings_rejected(field: str, bad_value: str) -> None:
    payload = _make_valid_approval_payload()
    payload[field] = bad_value
    # Recalculate self-hash so the record itself is internally well-formed
    semantics = {k: v for k, v in payload.items() if k != "record_sha256"}
    payload["record_sha256"] = hashlib.sha256(
        canonicalize(semantics).encode("utf-8")
    ).hexdigest()
    record = parse_approval_dict(payload)
    report = _make_sample_quality_report()

    with pytest.raises(QualityApprovalError):
        evaluate_effective_quality(
            raw_report=report,
            quality_policy_version="2",
            approval_record=record,
            dataset_id=FROZEN_DATASET_ID,
            canonical_content_hash=FROZEN_CONTENT_HASH,
            schema_fingerprint=FROZEN_SCHEMA_FINGERPRINT,
            source_sha256=FROZEN_SOURCES,
        )


def test_stale_source_digests_rejected() -> None:
    payload = _make_valid_approval_payload()
    payload["source_sha256"] = list(FROZEN_SOURCES)[:-1] + ["0" * 64]
    semantics = {k: v for k, v in payload.items() if k != "record_sha256"}
    payload["record_sha256"] = hashlib.sha256(
        canonicalize(semantics).encode("utf-8")
    ).hexdigest()
    record = parse_approval_dict(payload)
    report = _make_sample_quality_report()

    with pytest.raises(QualityApprovalError, match="source_sha256"):
        evaluate_effective_quality(
            raw_report=report,
            quality_policy_version="2",
            approval_record=record,
            dataset_id=FROZEN_DATASET_ID,
            canonical_content_hash=FROZEN_CONTENT_HASH,
            schema_fingerprint=FROZEN_SCHEMA_FINGERPRINT,
            source_sha256=FROZEN_SOURCES,
        )


def test_finding_count_mismatch_rejected() -> None:
    payload = _make_valid_approval_payload()
    payload["approved_findings"][0]["count"] = 90
    semantics = {k: v for k, v in payload.items() if k != "record_sha256"}
    payload["record_sha256"] = hashlib.sha256(
        canonicalize(semantics).encode("utf-8")
    ).hexdigest()
    record = parse_approval_dict(payload)
    report = _make_sample_quality_report()

    with pytest.raises(QualityApprovalError, match="count"):
        evaluate_effective_quality(
            raw_report=report,
            quality_policy_version="2",
            approval_record=record,
            dataset_id=FROZEN_DATASET_ID,
            canonical_content_hash=FROZEN_CONTENT_HASH,
            schema_fingerprint=FROZEN_SCHEMA_FINGERPRINT,
            source_sha256=FROZEN_SOURCES,
        )


def test_finding_digest_mismatch_rejected() -> None:
    payload = _make_valid_approval_payload()
    payload["approved_findings"][0]["canonical_finding_sha256"] = "f" * 64
    semantics = {k: v for k, v in payload.items() if k != "record_sha256"}
    payload["record_sha256"] = hashlib.sha256(
        canonicalize(semantics).encode("utf-8")
    ).hexdigest()
    record = parse_approval_dict(payload)
    report = _make_sample_quality_report()

    with pytest.raises(QualityApprovalError, match="finding"):
        evaluate_effective_quality(
            raw_report=report,
            quality_policy_version="2",
            approval_record=record,
            dataset_id=FROZEN_DATASET_ID,
            canonical_content_hash=FROZEN_CONTENT_HASH,
            schema_fingerprint=FROZEN_SCHEMA_FINGERPRINT,
            source_sha256=FROZEN_SOURCES,
        )


def test_uncovered_warning_rejected() -> None:
    report = _make_sample_quality_report()
    report.findings.append(
        Finding("nonzero_source_ignore", "warn", "warning", 5, {"occurrences": 5})
    )
    payload = _make_valid_approval_payload()
    # Match the quality identity of the 2-warning report so we test the finding coverage check
    payload["quality_identity_sha256"] = hashlib.sha256(
        report.identity().encode("utf-8")
    ).hexdigest()
    semantics = {k: v for k, v in payload.items() if k != "record_sha256"}
    payload["record_sha256"] = hashlib.sha256(
        canonicalize(semantics).encode("utf-8")
    ).hexdigest()
    record = parse_approval_dict(payload)

    with pytest.raises(QualityApprovalError, match="uncovered warning"):
        evaluate_effective_quality(
            raw_report=report,
            quality_policy_version="2",
            approval_record=record,
            dataset_id=FROZEN_DATASET_ID,
            canonical_content_hash=FROZEN_CONTENT_HASH,
            schema_fingerprint=FROZEN_SCHEMA_FINGERPRINT,
            source_sha256=FROZEN_SOURCES,
        )


def test_extra_approved_finding_rejected() -> None:
    payload = _make_valid_approval_payload()
    payload["approved_findings"].append(
        {
            "check_id": "nonzero_source_ignore",
            "count": 1,
            "canonical_finding_sha256": "a" * 64,
        }
    )
    semantics = {k: v for k, v in payload.items() if k != "record_sha256"}
    payload["record_sha256"] = hashlib.sha256(
        canonicalize(semantics).encode("utf-8")
    ).hexdigest()
    record = parse_approval_dict(payload)
    report = _make_sample_quality_report()

    with pytest.raises(QualityApprovalError, match="extra approved"):
        evaluate_effective_quality(
            raw_report=report,
            quality_policy_version="2",
            approval_record=record,
            dataset_id=FROZEN_DATASET_ID,
            canonical_content_hash=FROZEN_CONTENT_HASH,
            schema_fingerprint=FROZEN_SCHEMA_FINGERPRINT,
            source_sha256=FROZEN_SOURCES,
        )


def test_tampered_self_hash_rejected() -> None:
    payload = _make_valid_approval_payload()
    payload["rationale"] = "tampered rationale text"

    with pytest.raises(QualityApprovalError, match="self-hash mismatch"):
        parse_approval_dict(payload)


@pytest.mark.parametrize(
    "bad_timestamp",
    [
        "2026-08-28 07:07:38",
        "2026-08-28T07:07:38",
        "2026-08-28T07:07:38.000Z",
        "invalid-time",
        "",
    ],
)
def test_malformed_decision_time_rejected(bad_timestamp: str) -> None:
    payload = _make_valid_approval_payload()
    payload["decision_time_utc"] = bad_timestamp
    semantics = {k: v for k, v in payload.items() if k != "record_sha256"}
    payload["record_sha256"] = hashlib.sha256(
        canonicalize(semantics).encode("utf-8")
    ).hexdigest()

    with pytest.raises(QualityApprovalError, match="decision_time_utc"):
        parse_approval_dict(payload)


@pytest.mark.parametrize(
    ("key", "wildcard_value"),
    [
        ("dataset_id", "binance_usdm_*"),
        ("rationale", "allow * zero volume"),
        ("scope", "all 2024?"),
    ],
)
def test_wildcards_rejected(key: str, wildcard_value: str) -> None:
    payload = _make_valid_approval_payload()
    payload[key] = wildcard_value
    semantics = {k: v for k, v in payload.items() if k != "record_sha256"}
    payload["record_sha256"] = hashlib.sha256(
        canonicalize(semantics).encode("utf-8")
    ).hexdigest()

    with pytest.raises(QualityApprovalError, match="wildcard"):
        parse_approval_dict(payload)


def test_unknown_keys_rejected() -> None:
    payload = _make_valid_approval_payload()
    payload["unknown_extra_field"] = "bad"
    semantics = {k: v for k, v in payload.items() if k != "record_sha256"}
    payload["record_sha256"] = hashlib.sha256(
        canonicalize(semantics).encode("utf-8")
    ).hexdigest()

    with pytest.raises(QualityApprovalError, match="unknown keys"):
        parse_approval_dict(payload)


def test_missing_required_keys_rejected() -> None:
    payload = _make_valid_approval_payload()
    del payload["approver"]

    with pytest.raises(QualityApprovalError, match="missing required keys"):
        parse_approval_dict(payload)


def test_duplicate_check_ids_rejected() -> None:
    payload = _make_valid_approval_payload()
    payload["approved_findings"].append(
        {
            "check_id": "zero_volume_candle",
            "count": 89,
            "canonical_finding_sha256": FROZEN_FINDING_SHA256,
        }
    )
    semantics = {k: v for k, v in payload.items() if k != "record_sha256"}
    payload["record_sha256"] = hashlib.sha256(
        canonicalize(semantics).encode("utf-8")
    ).hexdigest()

    with pytest.raises(QualityApprovalError, match="duplicate"):
        parse_approval_dict(payload)


def test_non_warning_finding_rejected() -> None:
    payload = _make_valid_approval_payload()
    payload["approved_findings"] = [
        {
            "check_id": "row_count_matches_expected",
            "count": 527040,
            "canonical_finding_sha256": "0" * 64,
        }
    ]
    semantics = {k: v for k, v in payload.items() if k != "record_sha256"}
    payload["record_sha256"] = hashlib.sha256(
        canonicalize(semantics).encode("utf-8")
    ).hexdigest()

    with pytest.raises(QualityApprovalError, match="not an approvable warning"):
        parse_approval_dict(payload)


@pytest.mark.parametrize(
    "bad_path",
    [
        "../outside.yaml",
        "foo/../../escape.yaml",
        "/etc/passwd",
        "C:\\absolute\\path.yaml",
    ],
)
def test_path_traversal_and_absolute_rejected(tmp_path: Path, bad_path: str) -> None:
    with pytest.raises(QualityApprovalError):
        validate_approval_path(bad_path, repo_root=tmp_path)


def test_formatting_only_yaml_equivalence(tmp_path: Path) -> None:
    payload = _make_valid_approval_payload()
    record1 = parse_approval_dict(payload)

    yaml_text = f"""\
# Quality Warning Approval Record
schema: {payload["schema"]}
record_id: {payload["record_id"]}
quality_policy_version: "{payload["quality_policy_version"]}"
dataset_id: {payload["dataset_id"]}
canonical_content_hash: {payload["canonical_content_hash"]}
schema_fingerprint: {payload["schema_fingerprint"]}
quality_identity_sha256: {payload["quality_identity_sha256"]}
approver: "{payload["approver"]}"
decision_time_utc: "{payload["decision_time_utc"]}"
rationale: "{payload["rationale"]}"
scope: "{payload["scope"]}"
approved_findings:
  - check_id: zero_volume_candle
    count: 89
    canonical_finding_sha256: {FROZEN_FINDING_SHA256}
source_sha256:
{yaml.dump(payload["source_sha256"], indent=2)}
record_sha256: {payload["record_sha256"]}
"""
    doc_path = tmp_path / "reordered.yaml"
    doc_path.write_text(yaml_text, encoding="utf-8")
    record2 = load_approval_record(doc_path, repo_root=tmp_path)

    assert record1.record_sha256 == record2.record_sha256
    assert record1.canonical_semantics() == record2.canonical_semantics()


# --- Slice 010B: derived-lane approval plumbing ---------------------------------

DERIVED_FROZEN_DATASET_ID = "binance_usdm_btcusdt_klines_1h_2024"
DERIVED_FROZEN_CONTENT_HASH = (
    "9129f9ac1a5ad2f21b8e74d4512ed334871d1cee22a1d99275ad8db74b29f39e"
)
DERIVED_FROZEN_SCHEMA_FINGERPRINT = (
    "2e2fb0f01e206d892fd5f2116d5ee206c5af27cf6fc9bdfb288b4ead0c6b13ff"
)
DERIVED_FROZEN_PARENT_PARQUET_SHA256 = (
    "4456d6a7b5693bac7bc4870affead2f5be79d52eba0593d9d235234e0b340726"
)
DERIVED_FROZEN_RAW_IDENTITY_SHA256 = (
    "14c8b656ab519f23b307149c243311e7d2337d6b79d77d39b2883ef48dd11f20"
)
DERIVED_FROZEN_FINDING_SHA256 = (
    "11db14d6d01bbe81bfefc89d20f0fc113e97f8991768c0007831d6a1b07ae05c"
)


def _make_derived_approval_payload() -> dict:
    semantics = {
        "schema": APPROVAL_SCHEMA,
        "record_id": "binance-usdm-btcusdt-1h-2024-derived-zero-volume-v1",
        "dataset_id": DERIVED_FROZEN_DATASET_ID,
        "canonical_content_hash": DERIVED_FROZEN_CONTENT_HASH,
        "schema_fingerprint": DERIVED_FROZEN_SCHEMA_FINGERPRINT,
        "source_sha256": [DERIVED_FROZEN_PARENT_PARQUET_SHA256],
        "quality_policy_version": "2",
        "quality_identity_sha256": DERIVED_FROZEN_RAW_IDENTITY_SHA256,
        "approved_findings": [
            {
                "check_id": "derived_zero_volume_bucket",
                "count": 1,
                "canonical_finding_sha256": DERIVED_FROZEN_FINDING_SHA256,
            }
        ],
        "approver": "258711354+wyze69-sys@users.noreply.github.com",
        "decision_time_utc": "2026-08-28T16:00:00Z",
        "rationale": (
            "the single zero-volume 1h bucket at 2024-10-28T20:00:00Z aggregates "
            "the 60-minute Binance USD-M maintenance window; rows are preserved, "
            "all hard invariants pass, approval is internal-analysis-only."
        ),
        "scope": (
            "exact full-year BTCUSDT USD-M 1h canonical content only; "
            "no wildcard or future-data scope."
        ),
    }
    self_hash = hashlib.sha256(
        canonicalize(semantics).encode("utf-8")
    ).hexdigest()
    return {**semantics, "record_sha256": self_hash}


def test_derived_zero_volume_bucket_is_appovable() -> None:
    """derived_zero_volume_bucket must be an approvable warning check id."""
    from quantara.quality_approval import APPROVABLE_WARNING_CHECK_IDS

    assert "derived_zero_volume_bucket" in APPROVABLE_WARNING_CHECK_IDS


def test_derived_approval_payload_roundtrip() -> None:
    payload = _make_derived_approval_payload()
    record = parse_approval_dict(payload)
    assert record.record_id == (
        "binance-usdm-btcusdt-1h-2024-derived-zero-volume-v1"
    )
    assert record.dataset_id == DERIVED_FROZEN_DATASET_ID
    assert record.source_sha256 == (DERIVED_FROZEN_PARENT_PARQUET_SHA256,)
    assert record.approved_findings[0].check_id == "derived_zero_volume_bucket"
    assert record.approved_findings[0].count == 1
    record.verify_self_hash()


def test_repository_derived_approval_record_loads() -> None:
    """The frozen repository record must load and self-authenticate."""
    repo_root = Path(__file__).resolve().parents[1]
    record = load_approval_record(
        "configs/quality/approvals/"
        "binance-usdm-btcusdt-1h-2024-derived-zero-volume.v1.yaml",
        repo_root=repo_root,
    )
    assert record.record_id == (
        "binance-usdm-btcusdt-1h-2024-derived-zero-volume-v1"
    )
    assert record.dataset_id == DERIVED_FROZEN_DATASET_ID
    assert record.canonical_content_hash == DERIVED_FROZEN_CONTENT_HASH
    assert record.schema_fingerprint == DERIVED_FROZEN_SCHEMA_FINGERPRINT
    assert record.source_sha256 == (DERIVED_FROZEN_PARENT_PARQUET_SHA256,)
    assert record.quality_policy_version == "2"
    assert record.quality_identity_sha256 == DERIVED_FROZEN_RAW_IDENTITY_SHA256
    assert record.approved_findings[0].check_id == "derived_zero_volume_bucket"
    assert record.approved_findings[0].count == 1
    assert (
        record.approved_findings[0].canonical_finding_sha256
        == DERIVED_FROZEN_FINDING_SHA256
    )
    assert record.approver == "258711354+wyze69-sys@users.noreply.github.com"
    record.verify_self_hash()


_FROZEN_DERIVED_FINDINGS_DATA = [
    ("derived_row_count_matches_expected", "pass", "hard", 8784,
     {"approved_rows": 8784, "actual_rows": 8784}),
    ("derived_first_boundary_exact", "pass", "hard", 0,
     {"observed_first_open": 1704067200000, "approved_first_open": 1704067200000}),
    ("derived_last_boundary_exact", "pass", "hard", 0,
     {"observed_last_close": 1735689599999, "approved_last_close": 1735689599999}),
    ("derived_unique_open_times", "pass", "hard", 0, {"violations": 0}),
    ("derived_strictly_ascending_open_times", "pass", "hard", 0, {"violations": 0}),
    ("derived_adjacency_exactly_timeframe_ms", "pass", "hard", 0, {"violations": 0}),
    ("derived_ohlc_bounds_hold", "pass", "hard", 0, {"violations": 0}),
    ("derived_prices_strictly_positive", "pass", "hard", 0, {"violations": 0}),
    ("derived_volumes_and_counts_nonnegative", "pass", "hard", 0, {"violations": 0}),
    ("derived_taker_buy_within_counterpart_volumes", "pass", "hard", 0,
     {"violations": 0}),
    ("derived_close_time_relation", "pass", "hard", 0, {"violations": 0}),
    ("derived_zero_volume_bucket", "warn", "warning", 1, {"occurrences": 1}),
    ("derived_reconciliation_matches", "pass", "hard", 0, {"violations": 0}),
]


def _frozen_derived_findings() -> list:
    """The exact 13 findings of the frozen full-year 1h derived evaluation."""
    from quantara.derive_quality import Finding as DFinding

    return [
        DFinding(
            check_id=check_id,
            outcome=outcome,
            severity=severity,
            count=count,
            evidence=dict(evidence),
        )
        for check_id, outcome, severity, count, evidence
        in _FROZEN_DERIVED_FINDINGS_DATA
    ]


def test_derived_effective_quality_warn_approved() -> None:
    """Policy 2 + derived approval over the exact frozen derived report."""
    from quantara.derive_quality import DerivedQualityReport

    report = DerivedQualityReport(findings=_frozen_derived_findings())

    record = parse_approval_dict(_make_derived_approval_payload())
    decision = evaluate_effective_quality(
        raw_report=report,
        quality_policy_version="2",
        approval_record=record,
        dataset_id=DERIVED_FROZEN_DATASET_ID,
        canonical_content_hash=DERIVED_FROZEN_CONTENT_HASH,
        schema_fingerprint=DERIVED_FROZEN_SCHEMA_FINGERPRINT,
        source_sha256=(DERIVED_FROZEN_PARENT_PARQUET_SHA256,),
    )
    assert decision.effective_state == "WARN_APPROVED"
    assert decision.raw_state == "WARN_BLOCKED"
    assert decision.policy_version == "2"
    assert decision.approval_record_id == (
        "binance-usdm-btcusdt-1h-2024-derived-zero-volume-v1"
    )
    assert decision.raw_identity_sha256 == DERIVED_FROZEN_RAW_IDENTITY_SHA256


def test_derived_effective_quality_blocks_without_record() -> None:
    from quantara.derive_quality import DerivedQualityReport

    report = DerivedQualityReport(findings=_frozen_derived_findings())
    decision = evaluate_effective_quality(
        raw_report=report,
        quality_policy_version="2",
        approval_record=None,
    )
    assert decision.effective_state == "WARN_BLOCKED"


# --- Amendment 2026-08-30: headerless-year approval records --------------------

# Observed at implementation time by reparsing the retained official archives
# under the headerless source variant. Frozen here so a silent drift in the
# 2020/2021 raw bytes, the parser path, or the quality identity cannot pass.
HEADERLESS_YEAR_APPROVALS = {
    2020: {
        "canonical_content_hash": (
            "429e7ad880aa15b9b11888c4a1b4ec386ad114cbd67bc1b935486d77c287bb38"
        ),
        "schema_fingerprint": (
            "e4f64e3ba5beec25fba9f8b83320a68b3ddf5b8f848a2229f54bb02730f5d551"
        ),
        "quality_identity_sha256": (
            "4dbe4fdf22eb4ee7fd1ff635f191fb2a05a06d5a817d685c56a9ae1b5c05668e"
        ),
        "count": 2,
        "canonical_finding_sha256": (
            "087f3e42d319788d75ab4e3d8d21507cbdca7d7a26418aa962e1abfae66625a7"
        ),
        "record_sha256": (
            "0089482c012568fac59ae7117f3fde30742db22d1baf5408e035bbb9e4130e27"
        ),
    },
    2021: {
        "canonical_content_hash": (
            "c6f03f939777151a5d989b9f8476bbff57fd780b28c63bd3489e742207fcf310"
        ),
        "schema_fingerprint": (
            "8e26376df705c7144895b9afedf65a5c7143007ad4f9551762f6fdda12adf482"
        ),
        "quality_identity_sha256": (
            "846e0fce09988e630184290a150c8abaab909e1bd7c6409548bc12bfd4d40ed1"
        ),
        "count": 59,
        "canonical_finding_sha256": (
            "557c6b7e3bbdb5eba2a5071d4831a4a98efa9b09ae8725fd9303c9b08253636c"
        ),
        "record_sha256": (
            "2e2e78eb88e7a971e781d425264b9b0fd19163ae25d32f8f28cb3c8abbc89130"
        ),
    },
}


@pytest.mark.parametrize("year", sorted(HEADERLESS_YEAR_APPROVALS))
def test_repository_headerless_year_approval_record_loads(year: int) -> None:
    """The 2020/2021 records must load, self-authenticate, and stay frozen."""
    expected = HEADERLESS_YEAR_APPROVALS[year]
    repo_root = Path(__file__).resolve().parents[1]
    record = load_approval_record(
        "configs/quality/approvals/"
        f"binance-usdm-btcusdt-1m-{year}-zero-volume.v1.yaml",
        repo_root=repo_root,
    )
    assert record.schema == APPROVAL_SCHEMA
    assert record.record_id == f"binance-usdm-btcusdt-1m-{year}-zero-volume-v1"
    assert record.dataset_id == f"binance_usdm_btcusdt_klines_1m_{year}"
    assert record.canonical_content_hash == expected["canonical_content_hash"]
    assert record.schema_fingerprint == expected["schema_fingerprint"]
    assert record.quality_identity_sha256 == expected["quality_identity_sha256"]
    assert record.quality_policy_version == "2"
    assert len(record.source_sha256) == 12
    assert len(record.approved_findings) == 1
    finding = record.approved_findings[0]
    assert finding.check_id == "zero_volume_candle"
    assert finding.count == expected["count"]
    assert finding.canonical_finding_sha256 == expected["canonical_finding_sha256"]
    assert record.approver == "258711354+wyze69-sys@users.noreply.github.com"
    assert record.record_sha256 == expected["record_sha256"]
    record.verify_self_hash()


@pytest.mark.parametrize("year", sorted(HEADERLESS_YEAR_APPROVALS))
def test_headerless_year_approval_is_not_consumed_by_the_dataset_config(
    year: int,
) -> None:
    """The record exists; the amendment does not activate it.

    The 2020/2021 dataset descriptors stay at quality_policy_version "1", so the
    pipeline never loads these records and both years remain WARN_BLOCKED. The
    amendment authorizes parseability, not publication -- this test is what makes
    that boundary fail loudly if someone flips the policy without a decision.
    """
    from quantara.descriptor import load_descriptor

    repo_root = Path(__file__).resolve().parents[1]
    descriptor = load_descriptor(
        repo_root / "configs" / "datasets" / f"binance-usdm-btcusdt-1m-{year}.yaml"
    )
    assert descriptor.quality_policy_version == "1"
    assert descriptor.quality_approval is None
