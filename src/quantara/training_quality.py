"""PASS-only quality evidence for exact-decimal walk-forward training."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from quantara.hashing import quality_identity, sha256_hex
from quantara.jcs import canonicalize
from quantara.training_descriptor import TrainingDescriptor
from quantara.training_metrics import (
    BASELINES,
    DECIMAL_CONTEXT,
    DECIMAL_CONTRACT,
    FEATURE_INDICES,
    FEATURE_NAMES,
    TARGET_INDEX,
    quantize_q18,
)

TRAINING_ARTIFACT_SCHEMA = "quantara.model_training/v1"
DISCLAIMER = (
    "private internal research evidence; single-asset single-year walk-forward; "
    "no live trading, no performance claim, no commercial use"
)
QUALITY_POLICY_VERSION = "1"
CHECK_IDS = (
    "parents_authenticated",
    "lineage_binding",
    "descriptor_identity",
    "fold_alignment",
    "train_matrix",
    "numeric_domain",
    "solver_determinism",
    "metric_recomputation",
    "metric_bounds",
    "baseline_presence",
    "canonical_structure",
    "identity_contract",
)
Q18_PATTERN = re.compile(r"^-?\d+\.\d{18}$")
ARTIFACT_KEYS = {
    "schema",
    "dataset_id",
    "provider",
    "instrument_id",
    "period",
    "features",
    "target",
    "model",
    "training_set",
    "decimal_contract",
    "research_parent",
    "validation_parent",
    "records",
    "summaries",
    "baselines",
    "disclaimer",
}


def training_schema_fingerprint(parent_validation_fingerprint: str) -> str:
    payload = canonicalize(
        {
            "domain": "quantara-training-schema-fingerprint-v1",
            "parent_validation_fingerprint": parent_validation_fingerprint,
            "artifact_schema": TRAINING_ARTIFACT_SCHEMA,
            "decimal_contract": DECIMAL_CONTRACT,
        }
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def training_content_hash(schema_fingerprint: str, artifact_bytes: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(b"quantara-training-content-v1\0")
    digest.update(schema_fingerprint.encode("ascii"))
    digest.update(b"\0")
    digest.update(artifact_bytes)
    return digest.hexdigest()


def training_commit_identity(canonical_content_hash: str, training_from: dict) -> str:
    return hashlib.sha256(
        canonicalize(
            {
                "domain": "quantara-training-commit-identity-v1",
                "canonical_content_hash": canonical_content_hash,
                "training_from": training_from,
            }
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class Finding:
    check_id: str
    outcome: str
    severity: str
    count: int
    evidence: dict


class TrainingQualityReport:
    def __init__(self, findings: list[Finding]) -> None:
        self.findings = findings
        self.state = "FAIL" if any(item.outcome != "pass" for item in findings) else "PASS"

    def failing_checks(self) -> list[str]:
        return [item.check_id for item in self.findings if item.outcome != "pass"]

    def identity(self) -> str:
        return quality_identity(
            [
                {
                    "check_id": item.check_id,
                    "count": item.count,
                    "evidence": item.evidence,
                    "outcome": item.outcome,
                    "severity": item.severity,
                }
                for item in self.findings
            ]
        )


def _has_float(value: object) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(_has_float(key) or _has_float(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_has_float(item) for item in value)
    return False


def _is_q18(value: object) -> bool:
    return isinstance(value, str) and Q18_PATTERN.fullmatch(value) is not None


def _ctx_sum(values: Sequence[Decimal]) -> Decimal:
    total = Decimal(0)
    for value in values:
        total = DECIMAL_CONTEXT.add(total, value)
    return total


def _stored_pearson(predictions: Sequence[dict]) -> str:
    pairs = [(Decimal(item["prediction"]), Decimal(item["target"])) for item in predictions]
    count = Decimal(len(pairs))
    if len(pairs) < 2:
        return ""
    sx = sy = Decimal(0)
    for left, right in pairs:
        sx = DECIMAL_CONTEXT.add(sx, left)
        sy = DECIMAL_CONTEXT.add(sy, right)
    mx = DECIMAL_CONTEXT.divide(sx, count)
    my = DECIMAL_CONTEXT.divide(sy, count)
    numerator = vx = vy = Decimal(0)
    for left, right in pairs:
        dx = DECIMAL_CONTEXT.subtract(left, mx)
        dy = DECIMAL_CONTEXT.subtract(right, my)
        numerator = DECIMAL_CONTEXT.add(numerator, DECIMAL_CONTEXT.multiply(dx, dy))
        vx = DECIMAL_CONTEXT.add(vx, DECIMAL_CONTEXT.multiply(dx, dx))
        vy = DECIMAL_CONTEXT.add(vy, DECIMAL_CONTEXT.multiply(dy, dy))
    if vx.is_zero() or vy.is_zero():
        return ""
    denominator = DECIMAL_CONTEXT.sqrt(DECIMAL_CONTEXT.multiply(vx, vy))
    return format(
        quantize_q18(DECIMAL_CONTEXT.divide(numerator, denominator)),
        "f",
    )


def evaluate_training_quality(
    descriptor: TrainingDescriptor,
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
    training_from: dict,
    prospective_commit_identity: str,
) -> TrainingQualityReport:
    findings: list[Finding] = []

    def record(check_id: str, ok: bool, **evidence: object) -> None:
        findings.append(
            Finding(check_id, "pass" if ok else "fail", "hard", 0 if ok else 1, evidence)
        )

    validation_sha_ok = sha256_hex(validation_artifact_bytes) == validation_parent_info.get(
        "artifact_sha256"
    )
    parents_ok = (
        validation_quality_state == "PASS"
        and research_quality_state == "PASS"
        and validation_sha_ok
        and len(validation_artifact_bytes) == validation_parent_info.get("artifact_size")
        and isinstance(research_parent_info.get("parquet_sha256"), str)
        and isinstance(research_parent_info.get("parquet_size"), int)
    )
    record("parents_authenticated", parents_ok, validation_sha_match=validation_sha_ok)

    validation_to_research = (
        validation_lineage.get("parent_dataset_id") == research_parent_info.get("dataset_id")
        and validation_lineage.get("parent_commit_address")
        == research_parent_info.get("commit_address")
        and validation_lineage.get("parent_canonical_content_hash")
        == research_parent_info.get("canonical_content_hash")
        and validation_lineage.get("parent_parquet_sha256")
        == research_parent_info.get("parquet_sha256")
        and validation_lineage.get("parent_parquet_size")
        == research_parent_info.get("parquet_size")
    )
    training_to_parents = (
        training_from.get("validation_dataset_id") == validation_parent_info.get("dataset_id")
        and training_from.get("validation_commit_address")
        == validation_parent_info.get("commit_address")
        and training_from.get("validation_canonical_content_hash")
        == validation_parent_info.get("canonical_content_hash")
        and training_from.get("validation_artifact_sha256")
        == validation_parent_info.get("artifact_sha256")
        and training_from.get("validation_artifact_size")
        == validation_parent_info.get("artifact_size")
        and training_from.get("research_dataset_id") == research_parent_info.get("dataset_id")
        and training_from.get("research_commit_address")
        == research_parent_info.get("commit_address")
        and training_from.get("research_canonical_content_hash")
        == research_parent_info.get("canonical_content_hash")
        and training_from.get("research_parquet_sha256")
        == research_parent_info.get("parquet_sha256")
        and training_from.get("research_parquet_size")
        == research_parent_info.get("parquet_size")
    )
    record("lineage_binding", validation_to_research and training_to_parents)

    descriptor_ok = (
        artifact.get("dataset_id") == descriptor.dataset_id
        and artifact.get("provider") == descriptor.provider
        and artifact.get("instrument_id") == descriptor.instrument_id
        and tuple(artifact.get("features", ())) == descriptor.features
        and artifact.get("target") == descriptor.target
        and artifact.get("model") == descriptor.model
        and artifact.get("training_set") == descriptor.training_set
    )
    record("descriptor_identity", descriptor_ok)

    folds = validation_artifact.get("folds", [])
    records = artifact.get("records", [])
    fold_ok = len(folds) == len(records) and len(folds) == validation_artifact.get(
        "coverage", {}
    ).get("fold_count")
    if fold_ok:
        for index, (fold, item) in enumerate(zip(folds, records, strict=True)):
            train = fold.get("train_range")
            embargo = fold.get("embargo_range")
            test = fold.get("test_range")
            valid_ranges = all(
                isinstance(value, list)
                and len(value) == 2
                and all(isinstance(bound, int) and not isinstance(bound, bool) for bound in value)
                for value in (train, embargo, test)
            )
            if not valid_ranges:
                fold_ok = False
                break
            if not (
                fold.get("fold_id") == item.get("fold_id") == index
                and train[0] == 0
                and train[1] == embargo[0]
                and embargo[1] == test[0]
                and embargo[1] - embargo[0] == 24
                and train[1] <= test[0] - 24
                and 0 <= train[0] < train[1] <= test[0] < test[1] <= len(research_rows)
                and item.get("train_range") == train
                and item.get("embargo_range") == embargo
                and item.get("test_range") == test
            ):
                fold_ok = False
                break
    record("fold_alignment", fold_ok, fold_count=len(folds))

    matrix_ok = fold_ok
    if matrix_ok:
        for fold, item in zip(folds, records, strict=True):
            train_rows = research_rows[fold["train_range"][0] : fold["train_range"][1]]
            usable = sum(
                all(row[column] is not None for column in (*FEATURE_INDICES, TARGET_INDEX))
                for row in train_rows
            )
            if not (
                usable >= 200
                and item.get("usable_train_count") == usable
                and item.get("train_row_count") == len(train_rows)
                and item.get("excluded_train_count") == len(train_rows) - usable
                and item.get("predicted_count", -1) + item.get("excluded_test_count", -1)
                == item.get("test_row_count")
            ):
                matrix_ok = False
                break
    record("train_matrix", matrix_ok)

    numeric_ok = not _has_float(artifact)
    if numeric_ok:
        for item in records:
            q18_values = [
                item.get("intercept"),
                item.get("pearson_ic"),
                item.get("directional_accuracy"),
                item.get("mse"),
                *item.get("feature_means", {}).values(),
                *item.get("feature_stds", {}).values(),
                *item.get("coefficients", {}).values(),
            ]
            q18_values += [
                value
                for pred in item.get("predictions", [])
                for value in (pred.get("prediction"), pred.get("target"))
            ]
            numeric_ok = all(_is_q18(value) for value in q18_values)
            if not numeric_ok:
                break
    record("numeric_domain", numeric_ok)

    deterministic_ok = bool(records) and all(
        item.get("solver_deterministic") is True for item in records
    )
    record("solver_determinism", deterministic_ok)

    recomputation_ok = numeric_ok and fold_ok and bool(records)
    if recomputation_ok:
        first = records[0]
        recomputation_ok = _stored_pearson(first.get("predictions", [])) == first.get(
            "pearson_ic"
        )
        if recomputation_ok:
            train = folds[0]["train_range"]
            train_rows = [
                row
                for row in research_rows[train[0] : train[1]]
                if all(row[column] is not None for column in (*FEATURE_INDICES, TARGET_INDEX))
            ]
            means = []
            stds = []
            for column in FEATURE_INDICES:
                values = [Decimal(str(row[column])) for row in train_rows]
                mean = DECIMAL_CONTEXT.divide(_ctx_sum(values), Decimal(len(values)))
                variance = DECIMAL_CONTEXT.divide(
                    _ctx_sum(
                        [
                            DECIMAL_CONTEXT.multiply(
                                DECIMAL_CONTEXT.subtract(value, mean),
                                DECIMAL_CONTEXT.subtract(value, mean),
                            )
                            for value in values
                        ]
                    ),
                    Decimal(len(values)),
                )
                means.append(mean)
                stds.append(DECIMAL_CONTEXT.sqrt(variance))
            half_quantum = Decimal("0.0000000000000000005")
            for prediction in first["predictions"]:
                row = research_rows[prediction["row_index"]]
                approximate = Decimal(first["intercept"])
                bound_factor = Decimal(2)
                for index, column in enumerate(FEATURE_INDICES):
                    z = DECIMAL_CONTEXT.divide(
                        DECIMAL_CONTEXT.subtract(Decimal(str(row[column])), means[index]),
                        stds[index],
                    )
                    approximate = DECIMAL_CONTEXT.add(
                        approximate,
                        DECIMAL_CONTEXT.multiply(
                            Decimal(first["coefficients"][FEATURE_NAMES[index]]), z
                        ),
                    )
                    bound_factor = DECIMAL_CONTEXT.add(bound_factor, abs(z))
                tolerance = DECIMAL_CONTEXT.multiply(half_quantum, bound_factor)
                difference = abs(
                    DECIMAL_CONTEXT.subtract(
                        approximate, Decimal(prediction["prediction"])
                    )
                )
                if difference > tolerance:
                    recomputation_ok = False
                    break
    record("metric_recomputation", recomputation_ok)

    bounds_ok = numeric_ok
    if bounds_ok:
        for item in records:
            ic = Decimal(item["pearson_ic"])
            accuracy = Decimal(item["directional_accuracy"])
            mse = Decimal(item["mse"])
            if not (
                Decimal(-1) <= ic <= Decimal(1)
                and Decimal(0) <= accuracy <= Decimal(1)
                and mse >= 0
            ):
                bounds_ok = False
                break
    record("metric_bounds", bounds_ok)

    baselines_ok = bool(records) and all(
        set(item.get("baselines", {})) == set(BASELINES)
        and all(
            _is_q18(item["baselines"][name].get("directional_accuracy"))
            and Decimal(0) <= Decimal(item["baselines"][name]["directional_accuracy"]) <= Decimal(1)
            for name in BASELINES
        )
        for item in records
    ) and set(artifact.get("baselines", {})) == set(BASELINES)
    record("baseline_presence", baselines_ok)

    parent_keys_validation = {
        "dataset_id", "commit_address", "canonical_content_hash", "artifact_sha256", "artifact_size"
    }
    parent_keys_research = {
        "dataset_id", "commit_address", "canonical_content_hash", "parquet_sha256", "parquet_size"
    }
    try:
        canonical_bytes_ok = artifact_bytes == canonicalize(artifact).encode("utf-8") + b"\n"
    except Exception:
        canonical_bytes_ok = False
    canonical_ok = (
        set(artifact) == ARTIFACT_KEYS
        and artifact.get("schema") == TRAINING_ARTIFACT_SCHEMA
        and artifact.get("disclaimer") == DISCLAIMER
        and artifact.get("decimal_contract") == DECIMAL_CONTRACT
        and set(artifact.get("validation_parent", {})) == parent_keys_validation
        and set(artifact.get("research_parent", {})) == parent_keys_research
        and canonical_bytes_ok
    )
    record("canonical_structure", canonical_ok)

    expected_schema = training_schema_fingerprint(
        validation_parent_info.get("schema_fingerprint", "")
    )
    expected_content = training_content_hash(expected_schema, artifact_bytes)
    identity_ok = (
        schema_fingerprint == expected_schema
        and canonical_content_hash == expected_content
        and prospective_commit_identity
        == training_commit_identity(expected_content, training_from)
    )
    record("identity_contract", identity_ok)
    return TrainingQualityReport(findings)
