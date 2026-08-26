"""Validation pipeline tests (plan Task 6).

Offline lineage-bound orchestration: a synthetic month is published through
slice 001, derived to 1h through slice 002, researched through slice 003b,
then validation folds published:
- Dry-run verification-only parity (writes nothing)
- End-to-end publication with lineage binding and CAS artifact storage
- Idempotent VERIFIED_NO_OP detection
- Lost-pointer recovery with truthful milestones
- analyze_internal legal gate enforcement
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from conftest import (
    publish_month_via_slice_001,
    rights_v2_yaml_dict,
    validation_cfg_tree,
    write_derived_descriptor,
    write_research_descriptor,
    write_validation_descriptor,
)
from quantara.derive_pipeline import run_derivation_pipeline
from quantara.research_pipeline import run_research_pipeline
from quantara.validation_pipeline import (
    run_validation_pipeline,
    validation_commit_identity,
)


def _validation_dataset_dir(data_root: Path) -> Path:
    return (
        data_root
        / "datasets"
        / "binance"
        / "usdm"
        / "validation"
        / "BTCUSDT"
        / "1h"
        / "year=2024"
        / "month=01"
    )


def _attempts(data_root: Path) -> set[str]:
    attempts_dir = data_root / "attempts" / "validation"
    if not attempts_dir.exists():
        return set()
    return {p.name for p in attempts_dir.glob("*.json")}


@pytest.fixture(scope="module")
def chain(tmp_path_factory):
    """Synthetic parent chain: slice 001 -> derived 1h -> research 1h."""
    tmp = tmp_path_factory.mktemp("validation_e2e")
    root, data_root = publish_month_via_slice_001(tmp)
    assert (
        run_derivation_pipeline(
            write_derived_descriptor(root, "1h"), data_root, repo_root=root
        )
        == 0
    )
    assert (
        run_research_pipeline(
            write_research_descriptor(root, "1h"), data_root, repo_root=root
        )
        == 0
    )
    return root, data_root


def test_dry_run_verifies_without_any_mutation(chain) -> None:
    root, data_root = chain
    descriptor = write_validation_descriptor(root, "1h")
    assert (
        run_validation_pipeline(
            descriptor, data_root, dry_run=True, repo_root=root
        )
        == 0
    )
    assert not _validation_dataset_dir(data_root).exists()


def test_offline_end_to_end_publication_with_lineage_binding(chain) -> None:
    root, data_root = chain
    descriptor = write_validation_descriptor(root, "1h")
    assert run_validation_pipeline(descriptor, data_root, repo_root=root) == 0

    dataset_dir = _validation_dataset_dir(data_root)
    pointer_bytes = (dataset_dir / "current.json").read_bytes()
    commit = json.loads(pointer_bytes)["commit"]

    content = json.loads((dataset_dir / "commits" / commit / "content.json").read_text())
    manifest = json.loads((dataset_dir / "commits" / commit / "manifest.json").read_text())
    quality = json.loads((dataset_dir / "commits" / commit / "quality.json").read_text())

    # Lineage binds to parent research table
    parent_pointer = json.loads(
        (
            data_root
            / "datasets"
            / "binance"
            / "usdm"
            / "research"
            / "BTCUSDT"
            / "1h"
            / "year=2024"
            / "month=01"
            / "current.json"
        ).read_text()
    )
    lineage = content["validation_from"]
    assert lineage["parent_commit_address"] == parent_pointer["commit"]
    assert lineage["fold_set_name"] == "btcusdt_core_v1_wf72_v1"
    assert lineage["fold_set_version"] == "1"
    assert lineage["scheme"] == "anchored_walkforward_v1"
    assert lineage["parameters"] == {"test_size": 72, "min_train_size": 336}
    assert lineage["embargo"] == 24

    # Address equation
    content_hash = content["canonical_content_hash"]
    assert validation_commit_identity(content_hash, lineage) == commit

    # Quality and manifest agreement
    assert quality["state"] == "PASS"
    assert manifest["quality_state"] == "PASS"
    assert manifest["parent_row_count"] == 744
    assert manifest["fold_count"] == 5

    # CAS analytical object verification
    stored_sha = manifest["artifact_sha256"]
    artifact_path = data_root / "objects" / "normalized" / "sha256" / stored_sha
    assert artifact_path.exists()
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["schema"] == "quantara.validation_folds/v1"
    assert artifact["fold_set"] == "btcusdt_core_v1_wf72_v1"
    assert artifact["scheme"] == "anchored_walkforward_v1"
    assert artifact["parent_rows"] == 744
    assert artifact["excluded_head_rows"] == 360
    assert len(artifact["folds"]) == 5
    assert artifact["coverage"]["role_counts"]["TEST"] == 384
    assert artifact["coverage"]["role_counts"]["EXCLUDED"] == 360

    # Idempotent rerun: VERIFIED_NO_OP, pointer identical, 1 commit retained
    before = _attempts(data_root)
    assert run_validation_pipeline(descriptor, data_root, repo_root=root) == 0
    assert (dataset_dir / "current.json").read_bytes() == pointer_bytes
    assert len(list((dataset_dir / "commits").iterdir())) == 1
    new_attempts = _attempts(data_root) - before
    assert len(new_attempts) == 1
    attempt_manifest = json.loads(
        (data_root / "attempts" / "validation" / next(iter(new_attempts))).read_text()
    )
    assert attempt_manifest["terminal_result"] == "VERIFIED_NO_OP"
    dispositions = attempt_manifest["artifact_dispositions"]
    assert dispositions["validation_artifact"] == "already_published"


def test_lost_pointer_recovery_reports_truthful_milestones(chain) -> None:
    root, data_root = chain
    dataset_dir = _validation_dataset_dir(data_root)
    pointer_before = (dataset_dir / "current.json").read_bytes()

    # Lose the pointer; commit stays in place
    (dataset_dir / "current.json").unlink()
    before = _attempts(data_root)
    descriptor = write_validation_descriptor(root, "1h")
    assert run_validation_pipeline(descriptor, data_root, repo_root=root) == 0

    new_attempts = _attempts(data_root) - before
    assert len(new_attempts) == 1
    attempt = json.loads(
        (data_root / "attempts" / "validation" / next(iter(new_attempts))).read_text()
    )
    assert attempt["terminal_result"] == "PUBLISHED"
    dispositions = attempt["artifact_dispositions"]
    assert dispositions["object_written"] is False
    assert dispositions["commit_renamed"] is False
    assert dispositions["pointer_replaced"] is True
    assert (dataset_dir / "current.json").read_bytes() == pointer_before


def test_analyze_internal_gate_blocks_before_any_compute(tmp_path) -> None:
    root = validation_cfg_tree(tmp_path)
    blocked_rights = rights_v2_yaml_dict()
    unknown = blocked_rights["operations"]["analyze_internal"].copy()
    unknown["state"] = "UNKNOWN"
    blocked_rights["operations"]["analyze_internal"] = unknown
    (root / "configs" / "legal" / "binance-usdm-provider-rights.v2.yaml").write_text(
        yaml.safe_dump(blocked_rights), encoding="utf-8"
    )
    descriptor = write_validation_descriptor(root, "1h")
    code = run_validation_pipeline(descriptor, tmp_path / "data", repo_root=root)
    assert code == 2


def test_cli_validation_schema_dispatch(chain) -> None:
    from quantara.cli import main as cli_main

    root, data_root = chain
    descriptor = write_validation_descriptor(root, "1h")
    assert (
        cli_main(
            [
                "--descriptor",
                str(descriptor),
                "--data-root",
                str(data_root),
            ]
        )
        == 0
    )


# --- Task 8: frozen golden validation fold fixture ------------------------------

GOLDEN_VALIDATION_DIR = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "golden_validation"
)


def test_golden_validation_folds_equality(chain) -> None:
    root, _ = chain
    descriptor_path = write_validation_descriptor(root, "1h")

    parent_json = json.loads((GOLDEN_VALIDATION_DIR / "parent_table.json").read_text())
    expected_artifact = json.loads(
        (GOLDEN_VALIDATION_DIR / "expected_artifact.json").read_text()
    )

    from quantara.fold_stats import compute_fold_stats
    from quantara.folds import build_walkforward_folds
    from quantara.jcs import canonicalize
    from quantara.validation_descriptor import load_validation_descriptor
    from quantara.validation_pipeline import build_validation_artifact

    descriptor = load_validation_descriptor(descriptor_path)
    parent_rows = parent_json["rows"]

    partition = build_walkforward_folds(
        len(parent_rows),
        test_size=descriptor.parameters["test_size"],
        min_train_size=descriptor.parameters["min_train_size"],
        embargo=descriptor.embargo,
    )
    stats_list = [
        compute_fold_stats(
            parent_rows,
            fold.test_range,
            total_parent_rows=len(parent_rows),
            parameters=descriptor.parent_descriptor.parameters,
        )
        for fold in partition.folds
    ]

    artifact = build_validation_artifact(descriptor, partition, stats_list)

    # Byte-exact equality between independently generated fixture and production code
    assert artifact == expected_artifact
    assert canonicalize(artifact) == canonicalize(expected_artifact)
