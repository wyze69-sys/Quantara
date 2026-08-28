"""Quality warning approval loader and policy-v2 effective quality evaluation.

Implements the quality-state model for Slice 010A:
- Loads and validates immutable quality approval records under schema
  `quantara.quality-warning-approval/v1`;
- Enforces strict shape, types, regex formats, and canonical self-hash;
- Evaluates effective quality decisions (PASS / WARN_BLOCKED / WARN_APPROVED / FAIL)
  without mutating the raw findings or raw quality identity;
- Restricts approval authentication to exact dataset, source, schema, canonical
  content, finding count, and finding digest bindings.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from quantara.errors import QuantaraError
from quantara.hashing import sha256_hex
from quantara.jcs import canonicalize
from quantara.quality import Finding, QualityReport

APPROVAL_SCHEMA = "quantara.quality-warning-approval/v1"

APPROVAL_TOP_LEVEL_KEYS = frozenset(
    {
        "schema",
        "record_id",
        "dataset_id",
        "canonical_content_hash",
        "schema_fingerprint",
        "source_sha256",
        "quality_policy_version",
        "quality_identity_sha256",
        "approved_findings",
        "approver",
        "decision_time_utc",
        "rationale",
        "scope",
        "record_sha256",
    }
)

APPROVED_FINDING_KEYS = frozenset(
    {"check_id", "count", "canonical_finding_sha256"}
)

APPROVABLE_WARNING_CHECK_IDS = frozenset(
    {
        "zero_volume_candle",
        "source_order_invalid",
        "nonzero_source_ignore",
        "transport_metadata_difference",
        # Slice 010B: the only derived warning check id in the codebase.
        "derived_zero_volume_bucket",
    }
)

SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")
UTC_TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class QualityApprovalError(QuantaraError):
    error_id = "quality_approval_rejected"


@dataclass(frozen=True)
class ApprovedFinding:
    check_id: str
    count: int
    canonical_finding_sha256: str


@dataclass(frozen=True)
class QualityApprovalRecord:
    schema: str
    record_id: str
    dataset_id: str
    canonical_content_hash: str
    schema_fingerprint: str
    source_sha256: tuple[str, ...]
    quality_policy_version: str
    quality_identity_sha256: str
    approved_findings: tuple[ApprovedFinding, ...]
    approver: str
    decision_time_utc: str
    rationale: str
    scope: str
    record_sha256: str

    def canonical_semantics(self) -> dict[str, Any]:
        """Return the dictionary of semantics excluding record_sha256."""
        return {
            "schema": self.schema,
            "record_id": self.record_id,
            "dataset_id": self.dataset_id,
            "canonical_content_hash": self.canonical_content_hash,
            "schema_fingerprint": self.schema_fingerprint,
            "source_sha256": list(self.source_sha256),
            "quality_policy_version": self.quality_policy_version,
            "quality_identity_sha256": self.quality_identity_sha256,
            "approved_findings": [
                {
                    "check_id": f.check_id,
                    "count": f.count,
                    "canonical_finding_sha256": f.canonical_finding_sha256,
                }
                for f in self.approved_findings
            ],
            "approver": self.approver,
            "decision_time_utc": self.decision_time_utc,
            "rationale": self.rationale,
            "scope": self.scope,
        }

    def canonical_semantics_json(self) -> str:
        return canonicalize(self.canonical_semantics())

    def verify_self_hash(self) -> None:
        computed = sha256_hex(self.canonical_semantics_json().encode("utf-8"))
        if computed != self.record_sha256:
            raise QualityApprovalError(
                f"approval record self-hash mismatch: computed {computed} != "
                f"committed {self.record_sha256}"
            )


@dataclass(frozen=True)
class EffectiveQualityDecision:
    effective_state: str
    raw_state: str
    policy_version: str
    raw_identity: str
    raw_identity_sha256: str
    approval_record_id: str | None = None
    approval_record_sha256: str | None = None

    def decision_identity(self) -> str:
        payload: dict[str, Any] = {
            "policy_version": self.policy_version,
            "raw_identity_sha256": self.raw_identity_sha256,
            "effective_state": self.effective_state,
        }
        if self.approval_record_id is not None:
            payload["approval_record_id"] = self.approval_record_id
        if self.approval_record_sha256 is not None:
            payload["approval_record_sha256"] = self.approval_record_sha256
        return canonicalize(payload)


def canonical_finding_sha256(finding: Finding | dict) -> str:
    """Return the SHA-256 digest of the complete JCS finding object.

    Accepts either a ``quality.Finding``/dict or any duck-typed finding
    (``derive_quality.Finding`` carries the same five attributes); the
    canonical payload is identical either way.
    """
    if isinstance(finding, dict):
        payload = {
            "check_id": finding["check_id"],
            "count": finding["count"],
            "evidence": finding["evidence"],
            "outcome": finding["outcome"],
            "severity": finding["severity"],
        }
    elif hasattr(finding, "check_id") and hasattr(finding, "outcome"):
        payload = {
            "check_id": finding.check_id,
            "count": finding.count,
            "evidence": finding.evidence,
            "outcome": finding.outcome,
            "severity": finding.severity,
        }
    else:
        raise TypeError(f"expected Finding or dict, got {type(finding)!r}")
    return sha256_hex(canonicalize(payload).encode("utf-8"))


def validate_approval_path(
    path: Path | str, repo_root: Path | str | None = None
) -> Path:
    """Enforce repository-contained path: relative, no traversal outside repo."""
    root = (Path(repo_root) if repo_root else Path.cwd()).resolve()
    if isinstance(path, str):
        path_str = path.replace("\\", "/")
        if ":" in path_str or path_str.startswith("/"):
            raise QualityApprovalError(
                f"approval record path must be repository-relative, got {path}"
            )
        raw_path = Path(path)
        if raw_path.is_absolute():
            raise QualityApprovalError(
                f"approval record path must be repository-relative, got absolute {path}"
            )
        resolved = (root / raw_path).resolve()
    else:
        resolved = (root / path).resolve() if not path.is_absolute() else path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise QualityApprovalError(
            f"approval record path {path} escapes repository root {root}"
        ) from exc
    return resolved


def parse_approval_dict(document: dict[str, Any]) -> QualityApprovalRecord:
    """Validate approval dictionary and return a verified QualityApprovalRecord."""
    if not isinstance(document, dict):
        raise QualityApprovalError("approval record must be a mapping")

    keys = set(document)
    missing = APPROVAL_TOP_LEVEL_KEYS - keys
    if missing:
        raise QualityApprovalError(f"missing required keys in approval record: {sorted(missing)}")
    unknown = keys - APPROVAL_TOP_LEVEL_KEYS
    if unknown:
        raise QualityApprovalError(f"unknown keys in approval record: {sorted(unknown)}")

    if document["schema"] != APPROVAL_SCHEMA:
        raise QualityApprovalError(
            f"approval record schema must be {APPROVAL_SCHEMA!r}, got {document['schema']!r}"
        )

    if isinstance(document.get("decision_time_utc"), datetime):
        document = dict(document)
        document["decision_time_utc"] = (
            document["decision_time_utc"].strftime("%Y-%m-%dT%H:%M:%SZ")
        )

    for field_name in (
        "record_id",
        "dataset_id",
        "approver",
        "decision_time_utc",
        "rationale",
        "scope",
        "quality_policy_version",
    ):
        val = document[field_name]
        if not isinstance(val, str) or not val.strip():
            raise QualityApprovalError(f"{field_name} must be a non-empty string")

    # Disallow wildcards in dataset_id, rationale, scope
    for field_name in ("dataset_id", "rationale", "scope"):
        val = document[field_name]
        if "*" in val or "?" in val:
            raise QualityApprovalError(
                f"wildcard patterns are forbidden in {field_name}: {val!r}"
            )

    if not UTC_TIMESTAMP_PATTERN.match(document["decision_time_utc"]):
        raise QualityApprovalError(
            "decision_time_utc must match strict ISO UTC format YYYY-MM-DDTHH:MM:SSZ, "
            f"got {document['decision_time_utc']!r}"
        )

    for hash_field in (
        "canonical_content_hash",
        "schema_fingerprint",
        "quality_identity_sha256",
        "record_sha256",
    ):
        val = document[hash_field]
        if not isinstance(val, str) or not SHA256_HEX_PATTERN.match(val):
            raise QualityApprovalError(
                f"{hash_field} must be a 64-character lowercase hex digest, got {val!r}"
            )

    sources = document["source_sha256"]
    if not isinstance(sources, list) or not sources:
        raise QualityApprovalError("source_sha256 must be a non-empty list")
    for s in sources:
        if not isinstance(s, str) or not SHA256_HEX_PATTERN.match(s):
            raise QualityApprovalError(
                f"source_sha256 entry must be a 64-character lowercase hex digest, got {s!r}"
            )

    raw_findings = document["approved_findings"]
    if not isinstance(raw_findings, list) or not raw_findings:
        raise QualityApprovalError("approved_findings must be a non-empty list")

    approved_findings: list[ApprovedFinding] = []
    seen_check_ids: set[str] = set()

    for item in raw_findings:
        if not isinstance(item, dict):
            raise QualityApprovalError("approved_findings entries must be mappings")
        f_keys = set(item)
        f_missing = APPROVED_FINDING_KEYS - f_keys
        if f_missing:
            raise QualityApprovalError(
                f"missing keys in approved_finding: {sorted(f_missing)}"
            )
        f_unknown = f_keys - APPROVED_FINDING_KEYS
        if f_unknown:
            raise QualityApprovalError(
                f"unknown keys in approved_finding: {sorted(f_unknown)}"
            )

        check_id = item["check_id"]
        if check_id not in APPROVABLE_WARNING_CHECK_IDS:
            raise QualityApprovalError(
                f"{check_id!r} is not an approvable warning finding"
            )
        if check_id in seen_check_ids:
            raise QualityApprovalError(
                f"duplicate check_id {check_id!r} in approved_findings"
            )
        seen_check_ids.add(check_id)

        count = item["count"]
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            raise QualityApprovalError(
                f"approved finding count must be a positive integer, got {count!r}"
            )

        f_sha = item["canonical_finding_sha256"]
        if not isinstance(f_sha, str) or not SHA256_HEX_PATTERN.match(f_sha):
            raise QualityApprovalError(
                "canonical_finding_sha256 must be a 64-character lowercase hex digest, "
                f"got {f_sha!r}"
            )

        approved_findings.append(
            ApprovedFinding(
                check_id=check_id,
                count=count,
                canonical_finding_sha256=f_sha,
            )
        )

    record = QualityApprovalRecord(
        schema=document["schema"],
        record_id=document["record_id"],
        dataset_id=document["dataset_id"],
        canonical_content_hash=document["canonical_content_hash"],
        schema_fingerprint=document["schema_fingerprint"],
        source_sha256=tuple(sources),
        quality_policy_version=document["quality_policy_version"],
        quality_identity_sha256=document["quality_identity_sha256"],
        approved_findings=tuple(approved_findings),
        approver=document["approver"],
        decision_time_utc=document["decision_time_utc"],
        rationale=document["rationale"],
        scope=document["scope"],
        record_sha256=document["record_sha256"],
    )
    record.verify_self_hash()
    return record


def load_approval_record(
    path: Path | str, repo_root: Path | str | None = None
) -> QualityApprovalRecord:
    """Load and strictly validate a quality approval YAML file."""
    resolved_path = validate_approval_path(path, repo_root=repo_root)
    try:
        content = resolved_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise QualityApprovalError(
            f"failed to read approval record at {path}: {exc}"
        ) from exc
    try:
        doc = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise QualityApprovalError(
            f"failed to parse approval record YAML at {path}: {exc}"
        ) from exc
    return parse_approval_dict(doc)


def evaluate_effective_quality(
    raw_report: QualityReport,
    quality_policy_version: str,
    approval_record: QualityApprovalRecord | None = None,
    dataset_id: str | None = None,
    canonical_content_hash: str | None = None,
    schema_fingerprint: str | None = None,
    source_sha256: Sequence[str] | str | None = None,
) -> EffectiveQualityDecision:
    """Compute the effective quality decision without mutating raw report."""
    raw_identity = raw_report.identity()
    raw_identity_sha = sha256_hex(raw_identity.encode("utf-8"))

    if raw_report.state == "FAIL":
        return EffectiveQualityDecision(
            effective_state="FAIL",
            raw_state="FAIL",
            policy_version=quality_policy_version,
            raw_identity=raw_identity,
            raw_identity_sha256=raw_identity_sha,
        )

    if raw_report.state == "PASS":
        if approval_record is not None:
            raise QualityApprovalError(
                "approval record cannot be attached to a raw PASS report"
            )
        return EffectiveQualityDecision(
            effective_state="PASS",
            raw_state="PASS",
            policy_version=quality_policy_version,
            raw_identity=raw_identity,
            raw_identity_sha256=raw_identity_sha,
        )

    # raw_report.state == "WARN_BLOCKED"
    if str(quality_policy_version) == "1":
        return EffectiveQualityDecision(
            effective_state="WARN_BLOCKED",
            raw_state="WARN_BLOCKED",
            policy_version="1",
            raw_identity=raw_identity,
            raw_identity_sha256=raw_identity_sha,
        )

    if str(quality_policy_version) != "2":
        raise QualityApprovalError(
            f"unsupported quality policy version: {quality_policy_version!r}"
        )

    if approval_record is None:
        return EffectiveQualityDecision(
            effective_state="WARN_BLOCKED",
            raw_state="WARN_BLOCKED",
            policy_version="2",
            raw_identity=raw_identity,
            raw_identity_sha256=raw_identity_sha,
        )

    # Policy 2 with approval record: authenticate all bindings
    approval_record.verify_self_hash()

    if approval_record.quality_policy_version != "2":
        raise QualityApprovalError(
            f"approval record quality policy version {approval_record.quality_policy_version!r} "
            "!= '2'"
        )

    if dataset_id is not None and approval_record.dataset_id != dataset_id:
        raise QualityApprovalError(
            f"approval record dataset_id {approval_record.dataset_id!r} != expected {dataset_id!r}"
        )

    if (
        canonical_content_hash is not None
        and approval_record.canonical_content_hash != canonical_content_hash
    ):
        raise QualityApprovalError(
            "approval record canonical_content_hash "
            f"{approval_record.canonical_content_hash!r} != expected {canonical_content_hash!r}"
        )

    if (
        schema_fingerprint is not None
        and approval_record.schema_fingerprint != schema_fingerprint
    ):
        raise QualityApprovalError(
            f"approval record schema_fingerprint {approval_record.schema_fingerprint!r} != "
            f"expected {schema_fingerprint!r}"
        )

    if source_sha256 is not None:
        expected_sources = (
            tuple(source_sha256)
            if isinstance(source_sha256, (list, tuple))
            else (source_sha256,)
        )
        if approval_record.source_sha256 != expected_sources:
            raise QualityApprovalError(
                f"approval record source_sha256 {approval_record.source_sha256!r} != "
                f"expected {expected_sources!r}"
            )

    if approval_record.quality_identity_sha256 != raw_identity_sha:
        raise QualityApprovalError(
            f"approval record quality_identity_sha256 {approval_record.quality_identity_sha256!r} "
            f"!= raw identity digest {raw_identity_sha!r}"
        )

    warnings = [f for f in raw_report.findings if f.outcome == "warn"]
    if len(approval_record.approved_findings) > len(warnings):
        raise QualityApprovalError("extra approved findings in approval record")
    if len(approval_record.approved_findings) < len(warnings):
        raise QualityApprovalError("uncovered warning findings in report")

    approved_map = {af.check_id: af for af in approval_record.approved_findings}
    for w in warnings:
        if w.check_id not in approved_map:
            raise QualityApprovalError(f"uncovered warning finding: {w.check_id}")
        af = approved_map[w.check_id]
        if af.count != w.count:
            raise QualityApprovalError(
                f"approved finding count {af.count} != warning count {w.count} for {w.check_id}"
            )
        w_digest = canonical_finding_sha256(w)
        if af.canonical_finding_sha256 != w_digest:
            raise QualityApprovalError(
                f"approved finding digest {af.canonical_finding_sha256!r} != warning digest "
                f"{w_digest!r} for {w.check_id}"
            )

    return EffectiveQualityDecision(
        effective_state="WARN_APPROVED",
        raw_state="WARN_BLOCKED",
        policy_version="2",
        raw_identity=raw_identity,
        raw_identity_sha256=raw_identity_sha,
        approval_record_id=approval_record.record_id,
        approval_record_sha256=approval_record.record_sha256,
    )
