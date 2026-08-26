"""Research pipeline tests (plan Task 6).

Offline lineage-bound orchestration: a synthetic month is published through
the REAL slice 001 pipeline, derived to 1h through the real derivation
pipeline, then researched: dry-run verification-only parity, end-to-end
publication with lineage binding, idempotent VERIFIED_NO_OP, lost-pointer
recovery with truthful milestones, and the analyze_internal legal gate.
"""

from __future__ import annotations

import json

import pytest
import yaml

from conftest import (
    publish_month_via_slice_001,
    research_cfg_tree,
    rights_v2_yaml_dict,
    write_derived_descriptor,
    write_research_descriptor,
)
from quantara.cli import BASE_SCHEMA, RESEARCH_SCHEMA
from quantara.cli import main as cli_main
from quantara.derive_pipeline import run_derivation_pipeline
from quantara.research_pipeline import run_research_pipeline


def _research_dataset_dir(data_root):
    return (
        data_root
        / "datasets"
        / "binance"
        / "usdm"
        / "research"
        / "BTCUSDT"
        / "1h"
        / "year=2024"
        / "month=01"
    )


def _attempts(data_root):
    return {p.name for p in (data_root / "attempts").glob("*.json")}


@pytest.fixture(scope="module")
def chain(tmp_path_factory):
    """Synthetic parent published via real run_pipeline, then derived 1h."""
    tmp = tmp_path_factory.mktemp("research_e2e")
    root, data_root = publish_month_via_slice_001(tmp)
    assert (
        run_derivation_pipeline(write_derived_descriptor(root, "1h"), data_root, repo_root=root)
        == 0
    )
    return root, data_root


def test_dry_run_verifies_without_any_mutation(chain) -> None:
    root, data_root = chain
    descriptor = write_research_descriptor(root, "1h")
    assert run_research_pipeline(descriptor, data_root, dry_run=True, repo_root=root) == 0
    assert not _research_dataset_dir(data_root).exists()


def test_offline_end_to_end_publication_with_lineage_binding(chain) -> None:
    root, data_root = chain
    descriptor = write_research_descriptor(root, "1h")
    assert run_research_pipeline(descriptor, data_root, repo_root=root) == 0

    dataset_dir = _research_dataset_dir(data_root)
    pointer = (dataset_dir / "current.json").read_bytes()
    commit = json.loads(pointer)["commit"]

    content = json.loads((dataset_dir / "commits" / commit / "content.json").read_text())
    manifest = json.loads((dataset_dir / "commits" / commit / "manifest.json").read_text())

    # Lineage binds to the exact parent commit and parquet bytes.
    parent_pointer = json.loads(
        (
            data_root
            / "datasets"
            / "binance"
            / "usdm"
            / "klines"
            / "BTCUSDT"
            / "1h"
            / "year=2024"
            / "month=01"
            / "current.json"
        ).read_text()
    )
    lineage = content["research_from"]
    assert lineage["base_dataset_id"] == "binance_usdm_btcusdt_klines_1h_2024_01"
    assert lineage["base_commit_address"] == parent_pointer["commit"]
    assert lineage["parameters"] == {
        "roc_window": 60,
        "vol_window": 20,
        "volume_window": 20,
        "label_horizon": 24,
    }
    assert manifest["quality_state"] == "PASS"
    assert manifest["canonical_row_count"] == manifest["source_row_count"] == 744
    assert manifest["feature_set"] == {"name": "btcusdt_core_v1", "version": "1"}
    assert manifest["designed_null_budgets"] == {
        "f_ret_1": 1,
        "f_roc_60": 60,
        "f_rvol_20": 20,
        "f_volratio_20": 19,
        "l_fwdret_24": 24,
        "l_fwddir_24": 24,
    }
    # Address equation: the commit address is the domain-separated binding of
    # content hash and lineage.
    from quantara.research_pipeline import research_commit_identity

    assert research_commit_identity(content["canonical_content_hash"], lineage) == commit
    # The published table decodes to exactly 744 rows.
    from quantara.canonical import read_canonical_rows  # noqa: F401 - sanity
    from quantara.research_pipeline import read_research_rows

    object_path = data_root / "objects" / "normalized" / "sha256" / manifest["parquet_sha256"]
    rows = read_research_rows(object_path)
    assert len(rows) == 744
    assert rows[0][0] == 1704067200000
    assert rows[0][1] is None and rows[60][1] is not None
    assert rows[-1][5] is None and rows[-1][6] is None

    # Idempotent rerun: VERIFIED_NO_OP, bytes untouched, one commit only.
    before = _attempts(data_root)
    assert run_research_pipeline(descriptor, data_root, repo_root=root) == 0
    assert (dataset_dir / "current.json").read_bytes() == pointer
    assert len(list((dataset_dir / "commits").iterdir())) == 1
    new_attempts = _attempts(data_root) - before
    assert len(new_attempts) == 1
    attempt = json.loads((data_root / "attempts" / next(iter(new_attempts))).read_text())
    assert attempt["terminal_result"] == "VERIFIED_NO_OP"
    dispositions = attempt["artifact_dispositions"]
    assert dispositions["normalized_parquet"] == "already_published"


def test_lost_pointer_recovery_reports_truthful_milestones(chain) -> None:
    root, data_root = chain
    dataset_dir = _research_dataset_dir(data_root)
    pointer_before = (dataset_dir / "current.json").read_bytes()

    # Lose the pointer; the retained commit stays in place.
    (dataset_dir / "current.json").unlink()
    before = _attempts(data_root)
    descriptor = write_research_descriptor(root, "1h")
    assert run_research_pipeline(descriptor, data_root, repo_root=root) == 0

    new_attempts = _attempts(data_root) - before
    assert len(new_attempts) == 1
    attempt = json.loads((data_root / "attempts" / next(iter(new_attempts))).read_text())
    assert attempt["terminal_result"] == "PUBLISHED"
    dispositions = attempt["artifact_dispositions"]
    # Truthful recovery milestones per plan Task 6.
    assert dispositions["object_written"] is False
    assert dispositions["commit_renamed"] is False
    assert dispositions["pointer_replaced"] is True
    assert (dataset_dir / "current.json").read_bytes() == pointer_before


def test_analyze_internal_gate_blocks_before_any_compute(tmp_path) -> None:
    root = research_cfg_tree(tmp_path)
    blocked_rights = rights_v2_yaml_dict()
    unknown = blocked_rights["operations"]["analyze_internal"].copy()
    unknown["state"] = "UNKNOWN"
    blocked_rights["operations"]["analyze_internal"] = unknown
    (root / "configs" / "legal" / "binance-usdm-provider-rights.v2.yaml").write_text(
        yaml.safe_dump(blocked_rights), encoding="utf-8"
    )
    descriptor = write_research_descriptor(root, "1h")
    code = run_research_pipeline(descriptor, tmp_path / "data", repo_root=root)
    assert code == 2


# --- Task 7: CLI dispatch -------------------------------------------------------


def test_cli_research_schema_dispatch(chain) -> None:
    root, data_root = chain
    descriptor = write_research_descriptor(root, "1h")
    # The research table is already published by the earlier test in this
    # module; the CLI must dispatch to the research pipeline and report a
    # truthful idempotent no-op.
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
    # Dry-run parity through the same entry point.
    assert (
        cli_main(
            [
                "--descriptor",
                str(descriptor),
                "--data-root",
                str(data_root),
                "--dry-run",
            ]
        )
        == 0
    )


def test_cli_unknown_schema_is_invalid_descriptor(tmp_path) -> None:
    bogus = tmp_path / "bogus.yaml"
    bogus.write_text("schema: quantara.not-a-schema/v9\n", encoding="utf-8")
    assert cli_main(["--descriptor", str(bogus), "--data-root", str(tmp_path)]) == 3
    assert BASE_SCHEMA != RESEARCH_SCHEMA
