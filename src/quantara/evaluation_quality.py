"""Dual-IC feature evaluation quality evaluation (data slice 006).

Evaluates dual-IC evaluation records, cross-fold summaries, parent lineages,
and canonical serialization against the exact 13 ordered PASS-only quality gates
(spec §10, plan Task 5):
1. parents_authenticated
2. lineage_binding
3. descriptor_identity
4. fold_ranges
5. row_alignment
6. record_matrix
7. pair_counts
8. numeric_domain
9. metric_recomputation
10. metric_bounds
11. summary_recomputation
12. canonical_structure
13. identity_contract
Policy v1: exactly PASS publishes; any failure blocks publication.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from quantara.evaluation_descriptor import (
    APPROVED_FEATURES,
    APPROVED_TARGET,
    EvaluationDescriptor,
)
from quantara.evaluation_metrics import (
    DECIMAL_CONTRACT,
    FEATURE_COLUMN_INDICES,
    TARGET_COLUMN_INDEX,
    build_evaluation_summaries,
    evaluate_fold_feature,
)
from quantara.hashing import (
    evaluation_content_hash,
    evaluation_schema_fingerprint,
    quality_identity,
    sha256_hex,
)
from quantara.jcs import canonicalize

__all__ = [
    "CHECK_IDS",
    "DISCLAIMER",
    "EVALUATION_ARTIFACT_SCHEMA",
    "EvaluationQualityReport",
    "Finding",
    "QUALITY_POLICY_VERSION",
    "evaluate_evaluation_quality",
]

DISCLAIMER = (
    "internal descriptive analysis only; no model, signal, backtest, "
    "significance, or performance claim"
)
EVALUATION_ARTIFACT_SCHEMA = "quantara.feature_evaluation/v1"

QUALITY_POLICY_VERSION = "1"

CHECK_IDS: tuple[str, ...] = (
    "parents_authenticated",
    "lineage_binding",
    "descriptor_identity",
    "fold_ranges",
    "row_alignment",
    "record_matrix",
    "pair_counts",
    "numeric_domain",
    "metric_recomputation",
    "metric_bounds",
    "summary_recomputation",
    "canonical_structure",
    "identity_contract",
)

EXPECTED_ARTIFACT_KEYS: frozenset[str] = frozenset(
    {
        "schema",
        "dataset_id",
        "provider",
        "instrument_id",
        "period",
        "evaluation_set",
        "validation_parent",
        "research_parent",
        "features",
        "target",
        "metrics",
        "decimal_contract",
        "records",
        "summaries",
        "disclaimer",
    }
)

Q18_PATTERN = re.compile(r"^-?\d+\.\d{18}$")


@dataclass(frozen=True)
class Finding:
    check_id: str
    outcome: str  # "pass" | "fail"
    severity: str  # "hard"
    count: int
    evidence: dict


class EvaluationQualityReport:
    """Outcome of feature-evaluation quality evaluation."""

    def __init__(self, findings: list[Finding]) -> None:
        self.findings = findings
        self.state = "FAIL" if any(f.outcome != "pass" for f in findings) else "PASS"

    def failing_checks(self) -> list[str]:
        return [f.check_id for f in self.findings if f.outcome != "pass"]

    def identity(self) -> str:
        """Deterministic JCS identity over ordered findings; operational timestamps excluded."""
        return quality_identity(
            [
                {
                    "check_id": f.check_id,
                    "count": f.count,
                    "evidence": f.evidence,
                    "outcome": f.outcome,
                    "severity": f.severity,
                }
                for f in self.findings
            ]
        )


def evaluate_evaluation_quality(
    descriptor: EvaluationDescriptor,
    validation_parent_info: dict,
    research_parent_info: dict,
    validation_artifact: dict,
    research_rows: Sequence[Sequence],
    validation_artifact_bytes: bytes,
    validation_quality_state: str,
    research_quality_state: str,
    validation_lineage: dict,
    artifact: dict,
    artifact_bytes: bytes,
    schema_fingerprint: str,
    canonical_content_hash: str,
    evaluation_from: dict,
    prospective_commit_identity: str,
) -> EvaluationQualityReport:
    """Evaluate dual-IC evaluation records and artifact against PASS-only gates."""
    findings: list[Finding] = []

    def record(check_id: str, ok: bool, count: int = 0, **evidence) -> None:
        findings.append(
            Finding(
                check_id=check_id,
                outcome="pass" if ok else "fail",
                severity="hard",
                count=count,
                evidence=evidence,
            )
        )

    # 1. parents_authenticated
    val_sha = sha256_hex(validation_artifact_bytes)
    val_sha_ok = val_sha == validation_parent_info.get("artifact_sha256")
    val_size_ok = len(validation_artifact_bytes) == validation_parent_info.get("artifact_size")
    val_pass = validation_quality_state == "PASS"
    res_pass = research_quality_state == "PASS"
    res_sha = research_parent_info.get("parquet_sha256")
    res_sha_ok = isinstance(res_sha, str) and len(res_sha) == 64
    res_size = research_parent_info.get("parquet_size")
    res_size_ok = isinstance(res_size, int) and not isinstance(res_size, bool) and res_size > 0
    parents_ok = val_pass and res_pass and val_sha_ok and val_size_ok and res_sha_ok and res_size_ok
    record(
        "parents_authenticated",
        parents_ok,
        count=0 if parents_ok else 1,
        validation_quality=validation_quality_state,
        research_quality=research_quality_state,
        validation_sha_match=val_sha_ok,
        validation_size_match=val_size_ok,
    )

    # 2. lineage_binding
    lineage_dataset_ok = validation_lineage.get("parent_dataset_id") == research_parent_info.get(
        "dataset_id"
    )
    lineage_commit_ok = validation_lineage.get("parent_commit_address") == research_parent_info.get(
        "commit_address"
    )
    lineage_hash_ok = validation_lineage.get(
        "parent_canonical_content_hash"
    ) == research_parent_info.get("canonical_content_hash")
    lineage_parquet_sha_ok = validation_lineage.get(
        "parent_parquet_sha256"
    ) == research_parent_info.get("parquet_sha256")
    lineage_parquet_size_ok = validation_lineage.get(
        "parent_parquet_size"
    ) == research_parent_info.get("parquet_size")
    lineage_ok = (
        lineage_dataset_ok
        and lineage_commit_ok
        and lineage_hash_ok
        and lineage_parquet_sha_ok
        and lineage_parquet_size_ok
    )
    record(
        "lineage_binding",
        lineage_ok,
        count=0 if lineage_ok else 1,
        lineage_dataset_match=lineage_dataset_ok,
        lineage_commit_match=lineage_commit_ok,
        lineage_hash_match=lineage_hash_ok,
    )

    # 3. descriptor_identity
    parent_val = descriptor.parent_descriptor
    desc_id_ok = (
        descriptor.schema == "quantara.evaluation-descriptor/v1"
        and descriptor.dataset_id == artifact.get("dataset_id")
        and descriptor.provider == artifact.get("provider") == parent_val.provider
        and descriptor.instrument_id == artifact.get("instrument_id") == parent_val.instrument_id
        and descriptor.base_dataset_id == parent_val.base_dataset_id
        and descriptor.start_utc == parent_val.start_utc
        and descriptor.end_utc == parent_val.end_utc
        and descriptor.evaluation_set == artifact.get("evaluation_set")
        and descriptor.features == tuple(artifact.get("features", ()))
        and descriptor.target == artifact.get("target")
        and descriptor.metrics == tuple(artifact.get("metrics", ()))
        and descriptor.legal_record == "configs/legal/binance-usdm-provider-rights.v2.yaml"
    )
    record("descriptor_identity", desc_id_ok, count=0 if desc_id_ok else 1)

    # 4. fold_ranges
    folds = validation_artifact.get("folds", [])
    fold_ranges_ok = True
    if len(folds) != 25:
        fold_ranges_ok = False
    else:
        for idx, fold in enumerate(folds):
            if fold.get("fold_id") != idx:
                fold_ranges_ok = False
                break
            r = fold.get("test_range")
            if not isinstance(r, (list, tuple)) or len(r) != 2:
                fold_ranges_ok = False
                break
            start, end = r
            if idx == 0 and start != 360:
                fold_ranges_ok = False
                break
            if idx > 0 and start != folds[idx - 1]["test_range"][1]:
                fold_ranges_ok = False
                break
            expected_size = 96 if idx == 24 else 72
            if end - start != expected_size:
                fold_ranges_ok = False
                break
        if fold_ranges_ok and folds[-1]["test_range"][1] != len(research_rows):
            fold_ranges_ok = False
    record(
        "fold_ranges",
        fold_ranges_ok,
        count=0 if fold_ranges_ok else 1,
        fold_count=len(folds),
    )

    # 5. row_alignment
    n_rows = len(research_rows)
    parent_rows_match = validation_artifact.get("parent_rows") == n_rows == 2184
    time_strictly_increasing = n_rows == 2184 and all(
        isinstance(research_rows[i][0], int)
        and not isinstance(research_rows[i][0], bool)
        and research_rows[i][0] < research_rows[i + 1][0]
        for i in range(n_rows - 1)
    )
    time_hourly = n_rows == 2184 and all(
        research_rows[i + 1][0] - research_rows[i][0] == 3600000 for i in range(n_rows - 1)
    )
    row_align_ok = parent_rows_match and time_strictly_increasing and time_hourly
    record(
        "row_alignment",
        row_align_ok,
        count=0 if row_align_ok else 1,
        row_count=n_rows,
        parent_rows_match=parent_rows_match,
    )

    # 6. record_matrix
    records = artifact.get("records", [])
    matrix_ok = True
    if len(records) != 100:
        matrix_ok = False
    else:
        expected_matrix = [(fold_id, feat) for fold_id in range(25) for feat in APPROVED_FEATURES]
        actual_matrix = [(r.get("fold_id"), r.get("feature")) for r in records]
        if actual_matrix != expected_matrix:
            matrix_ok = False
        if not all(r.get("target") == APPROVED_TARGET for r in records):
            matrix_ok = False
    record(
        "record_matrix",
        matrix_ok,
        count=0 if matrix_ok else 1,
        record_count=len(records),
    )

    # 7. pair_counts
    pair_counts_ok = True
    total_valid = 0
    if not matrix_ok:
        pair_counts_ok = False
    else:
        for r in records:
            fold_id = r.get("fold_id")
            expected_test_rows = 96 if fold_id == 24 else 72
            expected_nulls = 24 if fold_id == 24 else 0
            if r.get("test_row_count") != expected_test_rows:
                pair_counts_ok = False
                break
            if r.get("valid_pair_count") != 72:
                pair_counts_ok = False
                break
            if r.get("feature_null_count") != 0:
                pair_counts_ok = False
                break
            if r.get("target_null_count") != expected_nulls:
                pair_counts_ok = False
                break
            if r.get("excluded_pair_count") != expected_nulls:
                pair_counts_ok = False
                break
            total_valid += r.get("valid_pair_count", 0)
        if pair_counts_ok and total_valid != 7200:
            pair_counts_ok = False
    record(
        "pair_counts",
        pair_counts_ok,
        count=0 if pair_counts_ok else 1,
        total_valid_pairs=total_valid,
    )

    # 8. numeric_domain
    numeric_ok = True
    for r in records:
        for metric_name in ("pearson_ic", "spearman_ic"):
            val_str = r.get(metric_name)
            if not isinstance(val_str, str) or not Q18_PATTERN.fullmatch(val_str):
                numeric_ok = False
                break
            try:
                dec = Decimal(val_str)
                if dec.is_nan() or dec.is_infinite():
                    numeric_ok = False
                    break
            except Exception:
                numeric_ok = False
                break
        if not numeric_ok:
            break

    summaries = artifact.get("summaries", [])
    if numeric_ok:
        for s in summaries:
            for field_name in ("minimum", "maximum", "median", "equal_weight_mean"):
                val_str = s.get(field_name)
                if not isinstance(val_str, str) or not Q18_PATTERN.fullmatch(val_str):
                    numeric_ok = False
                    break
                try:
                    dec = Decimal(val_str)
                    if dec.is_nan() or dec.is_infinite():
                        numeric_ok = False
                        break
                except Exception:
                    numeric_ok = False
                    break
            for count_field in (
                "fold_count",
                "total_valid_pair_count",
                "positive_fold_count",
                "negative_fold_count",
                "zero_fold_count",
            ):
                cnt = s.get(count_field)
                if not isinstance(cnt, int) or isinstance(cnt, bool) or cnt < 0:
                    numeric_ok = False
                    break
            if not numeric_ok:
                break
    record("numeric_domain", numeric_ok, count=0 if numeric_ok else 1)

    # 9. metric_recomputation
    metric_recomp_ok = True
    if not matrix_ok or not fold_ranges_ok:
        metric_recomp_ok = False
    else:
        for r in records:
            fold_id = r["fold_id"]
            feat = r["feature"]
            f_idx = FEATURE_COLUMN_INDICES[feat]
            test_range = r["test_range"]
            fold_rows = research_rows[test_range[0] : test_range[1]]
            rec_fresh = evaluate_fold_feature(
                fold_id=fold_id,
                feature=feat,
                target=APPROVED_TARGET,
                test_range=test_range,
                test_rows=fold_rows,
                feature_idx=f_idx,
                target_idx=TARGET_COLUMN_INDEX,
            )
            if (
                rec_fresh["pearson_ic"] != r["pearson_ic"]
                or rec_fresh["spearman_ic"] != r["spearman_ic"]
            ):
                metric_recomp_ok = False
                break
    record(
        "metric_recomputation",
        metric_recomp_ok,
        count=0 if metric_recomp_ok else 1,
    )

    # 10. metric_bounds
    bounds_ok = True
    minus_one = Decimal("-1")
    one = Decimal("1")
    if numeric_ok:
        for r in records:
            p = Decimal(r["pearson_ic"])
            s = Decimal(r["spearman_ic"])
            if not (minus_one <= p <= one and minus_one <= s <= one):
                bounds_ok = False
                break
        if bounds_ok:
            for s in summaries:
                for k in ("minimum", "maximum", "median", "equal_weight_mean"):
                    v = Decimal(s[k])
                    if not (minus_one <= v <= one):
                        bounds_ok = False
                        break
                if not bounds_ok:
                    break
    else:
        bounds_ok = False
    record("metric_bounds", bounds_ok, count=0 if bounds_ok else 1)

    # 11. summary_recomputation
    summary_recomp_ok = True
    if len(summaries) != 8:
        summary_recomp_ok = False
    elif matrix_ok and numeric_ok:
        expected_summaries = build_evaluation_summaries(records)
        if expected_summaries != summaries:
            summary_recomp_ok = False
    else:
        summary_recomp_ok = False
    record(
        "summary_recomputation",
        summary_recomp_ok,
        count=0 if summary_recomp_ok else 1,
        summary_count=len(summaries),
    )

    # 12. canonical_structure
    keys_ok = set(artifact.keys()) == EXPECTED_ARTIFACT_KEYS
    schema_ok = artifact.get("schema") == EVALUATION_ARTIFACT_SCHEMA
    disclaimer_ok = artifact.get("disclaimer") == DISCLAIMER
    contract_ok = artifact.get("decimal_contract") == DECIMAL_CONTRACT
    expected_bytes = canonicalize(artifact).encode("utf-8") + b"\n"
    bytes_ok = artifact_bytes == expected_bytes
    canonical_ok = keys_ok and schema_ok and disclaimer_ok and contract_ok and bytes_ok
    record("canonical_structure", canonical_ok, count=0 if canonical_ok else 1)

    # 13. identity_contract
    from quantara.evaluation_pipeline import evaluation_commit_identity

    parent_fp = validation_parent_info.get("schema_fingerprint")
    expected_schema_fp = evaluation_schema_fingerprint(parent_validation_fingerprint=parent_fp)
    schema_fp_ok = schema_fingerprint == expected_schema_fp
    expected_content_hash = evaluation_content_hash(schema_fingerprint, artifact_bytes)
    content_hash_ok = canonical_content_hash == expected_content_hash
    expected_commit_id = evaluation_commit_identity(canonical_content_hash, evaluation_from)
    commit_id_ok = prospective_commit_identity == expected_commit_id
    identity_ok = schema_fp_ok and content_hash_ok and commit_id_ok
    record(
        "identity_contract",
        identity_ok,
        count=0 if identity_ok else 1,
        schema_fingerprint_match=schema_fp_ok,
        content_hash_match=content_hash_ok,
        commit_identity_match=commit_id_ok,
    )

    return EvaluationQualityReport(findings)
