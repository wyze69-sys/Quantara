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
from quantara.training_metrics_logistic import (
    BASELINE_METRICS as LOGISTIC_BASELINE_METRICS,
)
from quantara.training_metrics_logistic import (
    BASELINES as LOGISTIC_BASELINES,
)
from quantara.training_metrics_logistic import (
    DIRECTION_INDEX as LOGISTIC_DIRECTION_INDEX,
)
from quantara.training_metrics_logistic import (
    METRICS as LOGISTIC_METRICS,
)
from quantara.training_metrics_logistic import (
    MINIMUM_USABLE_TRAIN_ROWS,
    brier,
    clamp_eta,
    climatology_probability,
    direction_ic_with_definition,
    log_loss,
    logistic_sigmoid,
)
from quantara.training_metrics_logistic import (
    quantize_q18 as logistic_quantize_q18,
)

TRAINING_ARTIFACT_SCHEMA = "quantara.model_training/v1"
LOGISTIC_ARTIFACT_SCHEMA = "quantara.model_training_logistic/v1"
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
LOGISTIC_CHECK_IDS = (*CHECK_IDS, "lane_kill_criteria")
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
LOGISTIC_ARTIFACT_KEYS = ARTIFACT_KEYS | {"training_parent", "kill_criteria"}
KILL_CRITERIA_BLOCK_KEYS = {"constants", "observed", "results", "all_passed"}
KILL_RESULT_KEYS = (
    "k1_directional_accuracy",
    "k2_direction_ic",
    "k3_log_loss",
    "k4_brier",
)


def training_schema_fingerprint(
    parent_validation_fingerprint: str,
    artifact_schema: str = TRAINING_ARTIFACT_SCHEMA,
) -> str:
    payload = canonicalize(
        {
            "domain": "quantara-training-schema-fingerprint-v1",
            "parent_validation_fingerprint": parent_validation_fingerprint,
            "artifact_schema": artifact_schema,
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


# --- Slice 012 additive: logistic-family quality evidence --------------------

_LOGISTIC_PARENT_KEYS_VALIDATION = {
    "dataset_id",
    "commit_address",
    "canonical_content_hash",
    "artifact_sha256",
    "artifact_size",
}
_LOGISTIC_PARENT_KEYS_RESEARCH = {
    "dataset_id",
    "commit_address",
    "canonical_content_hash",
    "parquet_sha256",
    "parquet_size",
}
_LOGISTIC_PARENT_KEYS_TRAINING = {
    "dataset_id",
    "commit_address",
    "canonical_content_hash",
    "artifact_sha256",
    "artifact_size",
}


def _logistic_usable_train_rows(
    research_rows: Sequence[Sequence], train_range: Sequence[int]
) -> tuple[list[Sequence], int]:
    """Rows eligible for a logistic fit: complete features, non-null non-zero label."""
    usable: list[Sequence] = []
    zero_labels = 0
    for row in research_rows[train_range[0] : train_range[1]]:
        direction = row[LOGISTIC_DIRECTION_INDEX]
        if direction == 0:
            zero_labels += 1
        if direction in (None, 0):
            continue
        if any(row[column] is None for column in FEATURE_INDICES):
            continue
        usable.append(row)
    return usable, zero_labels


def _logistic_stored_metrics(item: dict) -> dict[str, str] | None:
    """Recompute a fold's scored metrics from its own stored predictions."""
    predictions = item.get("predictions")
    if not isinstance(predictions, list) or len(predictions) < 2:
        return None
    try:
        probabilities = [Decimal(entry["probability"]) for entry in predictions]
        labels = [entry["label"] for entry in predictions]
        predicted = [entry["predicted_direction"] for entry in predictions]
        actual = [entry["direction"] for entry in predictions]
    except (KeyError, TypeError, ArithmeticError):
        return None
    if any(label not in (0, 1) for label in labels):
        return None
    if any(value not in (-1, 1) for value in (*predicted, *actual)):
        return None
    correct = sum(
        1 for left, right in zip(predicted, actual, strict=True) if left == right
    )
    try:
        ic, defined = direction_ic_with_definition(probabilities, labels)
        return {
            "directional_accuracy": format(
                logistic_quantize_q18(
                    DECIMAL_CONTEXT.divide(Decimal(correct), Decimal(len(actual)))
                ),
                "f",
            ),
            "log_loss": format(
                logistic_quantize_q18(log_loss(probabilities, labels)), "f"
            ),
            "brier": format(logistic_quantize_q18(brier(probabilities, labels)), "f"),
            "direction_ic": format(logistic_quantize_q18(ic), "f"),
            "direction_ic_defined": defined,
        }
    except Exception:
        return None


def _logistic_stored_climatology(
    item: dict, research_rows: Sequence[Sequence], train_range: Sequence[int]
) -> dict[str, str] | None:
    """Recompute the causal climatology baseline from train-window labels only."""
    labels = [
        row[LOGISTIC_DIRECTION_INDEX]
        for row in research_rows[train_range[0] : train_range[1]]
        if row[LOGISTIC_DIRECTION_INDEX] is not None
    ]
    up_count = sum(1 for value in labels if value == 1)
    down_count = sum(1 for value in labels if value == -1)
    predictions = item.get("predictions")
    if not isinstance(predictions, list) or not predictions:
        return None
    try:
        probability = climatology_probability(up_count, down_count)
    except Exception:
        return None
    direction = 1 if probability >= Decimal("0.5") else -1
    scored_labels = [entry["label"] for entry in predictions]
    actual = [entry["direction"] for entry in predictions]
    correct = sum(1 for value in actual if value == direction)
    try:
        return {
            "probability": format(logistic_quantize_q18(probability), "f"),
            "predicted_direction": direction,
            "directional_accuracy": format(
                logistic_quantize_q18(
                    DECIMAL_CONTEXT.divide(Decimal(correct), Decimal(len(actual)))
                ),
                "f",
            ),
            "log_loss": format(
                logistic_quantize_q18(
                    log_loss([probability] * len(scored_labels), scored_labels)
                ),
                "f",
            ),
            "brier": format(
                logistic_quantize_q18(
                    brier([probability] * len(scored_labels), scored_labels)
                ),
                "f",
            ),
            "train_up_count": up_count,
            "train_down_count": down_count,
        }
    except Exception:
        return None


def _logistic_probability_recomputation_ok(
    item: dict, folds: Sequence[dict], research_rows: Sequence[Sequence]
) -> bool:
    """Independently re-derive fold 0 probabilities from the stored parameters."""
    usable, _ = _logistic_usable_train_rows(research_rows, folds[0]["train_range"])
    if len(usable) < 2:
        return False
    means: list[Decimal] = []
    stds: list[Decimal] = []
    for column in FEATURE_INDICES:
        values = [Decimal(str(row[column])) for row in usable]
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
        std = DECIMAL_CONTEXT.sqrt(variance)
        if std.is_zero():
            return False
        means.append(mean)
        stds.append(std)
    half_quantum = Decimal("0.0000000000000000005")
    for prediction in item.get("predictions", []):
        row = research_rows[prediction["row_index"]]
        eta = Decimal(item["intercept"])
        bound_factor = Decimal(2)
        for index, column in enumerate(FEATURE_INDICES):
            z = DECIMAL_CONTEXT.divide(
                DECIMAL_CONTEXT.subtract(Decimal(str(row[column])), means[index]),
                stds[index],
            )
            eta = DECIMAL_CONTEXT.add(
                eta,
                DECIMAL_CONTEXT.multiply(
                    Decimal(item["coefficients"][FEATURE_NAMES[index]]), z
                ),
            )
            bound_factor = DECIMAL_CONTEXT.add(bound_factor, abs(z))
        clamped, _ = clamp_eta(eta)
        approximate = logistic_sigmoid(clamped)
        # |dp/deta| <= 1/4, plus the stored Q18 rounding of the probability.
        tolerance = DECIMAL_CONTEXT.add(
            DECIMAL_CONTEXT.multiply(half_quantum, bound_factor), half_quantum
        )
        difference = abs(
            DECIMAL_CONTEXT.subtract(approximate, Decimal(prediction["probability"]))
        )
        if difference > tolerance:
            return False
        expected_direction = 1 if Decimal(prediction["probability"]) >= Decimal("0.5") else -1
        if prediction.get("predicted_direction") != expected_direction:
            return False
        if (prediction.get("label") == 1) != (prediction.get("direction") == 1):
            return False
    return True


def _logistic_expected_observed(artifact: dict) -> dict[str, str] | None:
    """The kill block's ``observed`` values as implied by the artifact itself."""
    summaries = artifact.get("summaries")
    baselines = artifact.get("baselines")
    if not isinstance(summaries, list) or not isinstance(baselines, dict):
        return None
    observed: dict[str, str] = {}
    for metric in LOGISTIC_METRICS:
        match = [item for item in summaries if item.get("metric") == metric]
        if len(match) != 1 or not isinstance(match[0].get("equal_weight_mean"), str):
            return None
        observed[f"{metric}_mean"] = match[0]["equal_weight_mean"]
    for baseline in LOGISTIC_BASELINES:
        for metric in LOGISTIC_BASELINE_METRICS[baseline]:
            block = baselines.get(baseline)
            if not isinstance(block, dict) or not isinstance(block.get(metric), dict):
                return None
            mean = block[metric].get("equal_weight_mean")
            if not isinstance(mean, str):
                return None
            observed[f"{baseline}_{metric}_mean"] = mean
    return observed


def evaluate_logistic_training_quality(
    descriptor: TrainingDescriptor,
    validation_parent_info: dict,
    research_parent_info: dict,
    training_parent_info: dict,
    validation_artifact: dict,
    research_rows: Sequence[Sequence],
    validation_artifact_bytes: bytes,
    validation_quality_state: str,
    research_quality_state: str,
    training_quality_state: str,
    validation_lineage: dict,
    artifact: dict,
    artifact_bytes: bytes,
    schema_fingerprint: str,
    canonical_content_hash: str,
    training_from: dict,
    prospective_commit_identity: str,
) -> TrainingQualityReport:
    """Ordered hard-check evidence for the logistic IRLS publish path."""
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
        and training_quality_state == "PASS"
        and validation_sha_ok
        and len(validation_artifact_bytes) == validation_parent_info.get("artifact_size")
        and isinstance(research_parent_info.get("parquet_sha256"), str)
        and isinstance(research_parent_info.get("parquet_size"), int)
        and isinstance(training_parent_info.get("artifact_sha256"), str)
        and isinstance(training_parent_info.get("artifact_size"), int)
        and isinstance(training_parent_info.get("commit_address"), str)
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
        and training_from.get("training_dataset_id") == training_parent_info.get("dataset_id")
        and training_from.get("training_commit_address")
        == training_parent_info.get("commit_address")
        and training_from.get("training_canonical_content_hash")
        == training_parent_info.get("canonical_content_hash")
        and training_from.get("training_artifact_sha256")
        == training_parent_info.get("artifact_sha256")
        and training_from.get("training_artifact_size")
        == training_parent_info.get("artifact_size")
        and artifact.get("training_parent") == dict(training_parent_info)
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
        and descriptor.model.get("family") == "logistic_irls"
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
            usable, zero_labels = _logistic_usable_train_rows(
                research_rows, fold["train_range"]
            )
            if not (
                len(usable) >= MINIMUM_USABLE_TRAIN_ROWS
                and item.get("usable_train_count") == len(usable)
                and item.get("train_row_count") == len(train_rows)
                and item.get("excluded_train_count") == len(train_rows) - len(usable)
                and item.get("zero_train_label_count") == zero_labels
                and item.get("predicted_count", -1) + item.get("excluded_test_count", -1)
                == item.get("test_row_count")
                and item.get("predicted_count") == len(item.get("predictions", []))
            ):
                matrix_ok = False
                break
    record("train_matrix", matrix_ok)

    numeric_ok = not _has_float(artifact)
    if numeric_ok:
        for item in records:
            q18_values = [
                item.get("intercept"),
                *(item.get(metric) for metric in LOGISTIC_METRICS),
                *item.get("feature_means", {}).values(),
                *item.get("feature_stds", {}).values(),
                *item.get("coefficients", {}).values(),
            ]
            q18_values += [
                value
                for pred in item.get("predictions", [])
                for value in (pred.get("probability"), pred.get("target"))
            ]
            baselines_block = item.get("baselines", {})
            for name in LOGISTIC_BASELINES:
                block = baselines_block.get(name, {})
                q18_values += [block.get(metric) for metric in LOGISTIC_BASELINE_METRICS[name]]
            q18_values.append(baselines_block.get("climatology_p", {}).get("probability"))
            numeric_ok = all(_is_q18(value) for value in q18_values)
            if not numeric_ok:
                break
    record("numeric_domain", numeric_ok)

    deterministic_ok = bool(records) and all(
        item.get("solver_deterministic") is True
        and isinstance(item.get("converged_iterations"), int)
        and not isinstance(item.get("converged_iterations"), bool)
        and 1 <= item["converged_iterations"] <= descriptor.model["max_iterations"]
        for item in records
    )
    record("solver_determinism", deterministic_ok)

    recomputation_ok = numeric_ok and fold_ok and matrix_ok and bool(records)
    if recomputation_ok:
        for fold, item in zip(folds, records, strict=True):
            expected = _logistic_stored_metrics(item)
            climatology = _logistic_stored_climatology(
                item, research_rows, fold["train_range"]
            )
            if expected is None or climatology is None:
                recomputation_ok = False
                break
            if any(item.get(name) != value for name, value in expected.items()):
                recomputation_ok = False
                break
            stored_climatology = item.get("baselines", {}).get("climatology_p", {})
            if any(
                stored_climatology.get(name) != value
                for name, value in climatology.items()
                if name in stored_climatology
            ) or set(climatology) - set(stored_climatology) - {
                "train_up_count",
                "train_down_count",
            }:
                recomputation_ok = False
                break
        if recomputation_ok:
            recomputation_ok = _logistic_probability_recomputation_ok(
                records[0], folds, research_rows
            )
    record("metric_recomputation", recomputation_ok)

    bounds_ok = numeric_ok and bool(records)
    if bounds_ok:
        for item in records:
            accuracy = Decimal(item["directional_accuracy"])
            loss = Decimal(item["log_loss"])
            score = Decimal(item["brier"])
            ic = Decimal(item["direction_ic"])
            return_ic = Decimal(item["pearson_ic"])
            if not (
                Decimal(0) <= accuracy <= Decimal(1)
                and loss >= 0
                and Decimal(0) <= score <= Decimal(1)
                and Decimal(-1) <= ic <= Decimal(1)
                and Decimal(-1) <= return_ic <= Decimal(1)
            ):
                bounds_ok = False
                break
            for prediction in item.get("predictions", []):
                probability = Decimal(prediction["probability"])
                if not (Decimal(0) < probability < Decimal(1)):
                    bounds_ok = False
                    break
            if not bounds_ok:
                break
    record("metric_bounds", bounds_ok)

    baselines_ok = bool(records) and all(
        set(item.get("baselines", {})) == set(LOGISTIC_BASELINES)
        and all(
            _is_q18(item["baselines"][name].get(metric))
            for name in LOGISTIC_BASELINES
            for metric in LOGISTIC_BASELINE_METRICS[name]
        )
        for item in records
    )
    if baselines_ok:
        artifact_baselines = artifact.get("baselines", {})
        baselines_ok = set(artifact_baselines) == set(LOGISTIC_BASELINES) and all(
            set(artifact_baselines[name]) == set(LOGISTIC_BASELINE_METRICS[name])
            for name in LOGISTIC_BASELINES
        )
    if baselines_ok:
        baselines_ok = [
            item.get("metric") for item in artifact.get("summaries", [])
        ] == list(LOGISTIC_METRICS)
    record("baseline_presence", baselines_ok)

    try:
        canonical_bytes_ok = artifact_bytes == canonicalize(artifact).encode("utf-8") + b"\n"
    except Exception:
        canonical_bytes_ok = False
    canonical_ok = (
        set(artifact) == LOGISTIC_ARTIFACT_KEYS
        and artifact.get("schema") == LOGISTIC_ARTIFACT_SCHEMA
        and artifact.get("disclaimer") == DISCLAIMER
        and artifact.get("decimal_contract") == DECIMAL_CONTRACT
        and set(artifact.get("validation_parent", {})) == _LOGISTIC_PARENT_KEYS_VALIDATION
        and set(artifact.get("research_parent", {})) == _LOGISTIC_PARENT_KEYS_RESEARCH
        and set(artifact.get("training_parent", {})) == _LOGISTIC_PARENT_KEYS_TRAINING
        and set(artifact.get("kill_criteria", {})) == KILL_CRITERIA_BLOCK_KEYS
        and canonical_bytes_ok
    )
    record("canonical_structure", canonical_ok)

    expected_schema = training_schema_fingerprint(
        validation_parent_info.get("schema_fingerprint", ""), LOGISTIC_ARTIFACT_SCHEMA
    )
    expected_content = training_content_hash(expected_schema, artifact_bytes)
    identity_ok = (
        schema_fingerprint == expected_schema
        and canonical_content_hash == expected_content
        and prospective_commit_identity
        == training_commit_identity(expected_content, training_from)
    )
    record("identity_contract", identity_ok)

    kill = artifact.get("kill_criteria")
    constants_match = False
    observed_match = False
    all_passed = False
    if isinstance(kill, dict) and set(kill) == KILL_CRITERIA_BLOCK_KEYS:
        constants = kill.get("constants")
        pinned = descriptor.kill_criteria
        constants_match = (
            isinstance(constants, dict)
            and isinstance(pinned, dict)
            and set(constants) == set(pinned)
            and all(Decimal(constants[name]) == Decimal(pinned[name]) for name in pinned)
        )
        expected_observed = _logistic_expected_observed(artifact)
        observed = kill.get("observed")
        observed_match = (
            isinstance(observed, dict)
            and expected_observed is not None
            and set(observed) == set(expected_observed)
            and all(
                Decimal(observed[name]) == Decimal(expected_observed[name])
                for name in expected_observed
            )
        )
        results = kill.get("results")
        booleans_ok = (
            isinstance(results, dict)
            and set(results) == set(KILL_RESULT_KEYS)
            and all(results[name] is True for name in KILL_RESULT_KEYS)
            and kill.get("all_passed") is True
        )
        criteria_ok = False
        if constants_match and observed_match and isinstance(results, dict):
            try:
                criteria_ok = (
                    (
                        Decimal(observed["directional_accuracy_mean"])
                        >= Decimal(constants["directional_accuracy_min"])
                    )
                    and (
                        Decimal(observed["direction_ic_mean"])
                        >= Decimal(constants["direction_ic_min"])
                    )
                    and (
                        Decimal(observed["log_loss_mean"])
                        <= Decimal(constants["log_loss_max"])
                    )
                    and (Decimal(observed["brier_mean"]) <= Decimal(constants["brier_max"]))
                )
            except (KeyError, ArithmeticError, TypeError):
                criteria_ok = False
        all_passed = bool(booleans_ok and criteria_ok)
    record(
        "lane_kill_criteria",
        constants_match and observed_match and all_passed,
        constants_match=constants_match,
        observed_match=observed_match,
        all_passed=all_passed,
    )
    return TrainingQualityReport(findings)

