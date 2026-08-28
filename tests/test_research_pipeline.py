"""Research pipeline tests (plan Task 6).

Offline lineage-bound orchestration: a synthetic month is published through
the REAL slice 001 pipeline, derived to 1h through the real derivation
pipeline, then researched: dry-run verification-only parity, end-to-end
publication with lineage binding, idempotent VERIFIED_NO_OP, lost-pointer
recovery with truthful milestones, and the analyze_internal legal gate.
"""

from __future__ import annotations

import json
from pathlib import Path

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


# --- Task 8: frozen golden research table fixture -------------------------------

GOLDEN_DIR = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "golden_research"
)


def test_golden_research_table_equality() -> None:
    parent = json.loads((GOLDEN_DIR / "parent_bars.json").read_text())
    expected = json.loads((GOLDEN_DIR / "expected_table.json").read_text())

    from conftest import make_hour_bar
    from quantara.features import build_research_rows
    from quantara.hashing import research_content_hash, research_schema_fingerprint
    from quantara.research_pipeline import render_content_rows

    n = parent["bar_count"]
    parent_rows = [
        make_hour_bar(
            parent["first_open_time_ms"] + i * parent["interval_ms"],
            parent["closes"][i],
            parent["volumes"][i],
        ).to_content_array()
        for i in range(n)
    ]
    table = build_research_rows(parent_rows)

    # Byte-exact equality with the independently computed golden table.
    rendered = render_content_rows(table)
    assert rendered == expected["rows"]

    # Frozen identities.
    fingerprint = research_schema_fingerprint(expected["schema_version"])
    assert fingerprint == expected["fingerprint"]
    assert research_content_hash(fingerprint, rendered) == expected["content_hash"]


def test_verify_parent_accepts_authenticated_policy_v2_warn_approved(
    tmp_path: Path, monkeypatch
) -> None:
    from quantara.derive_descriptor import load_derived_descriptor
    from quantara.research_pipeline import _verify_parent
    from test_derive_pipeline import _run_warn_approved_derived_fixture

    root, data_root, descriptor_path, derived_dir, _, _ = (
        _run_warn_approved_derived_fixture(tmp_path, monkeypatch)
    )
    parent = _verify_parent(
        derived_dir,
        data_root,
        load_derived_descriptor(descriptor_path),
        repo_root=root,
    )
    assert parent["quality_state"] == "WARN_APPROVED"
    assert parent["quality_raw_state"] == "WARN_BLOCKED"


def _assert_research_parent_rejected(
    root: Path,
    data_root: Path,
    descriptor_path: Path,
    derived_dir: Path,
) -> None:
    from quantara.derive_descriptor import load_derived_descriptor
    from quantara.errors import QuantaraError
    from quantara.research_pipeline import _verify_parent

    with pytest.raises(QuantaraError):
        _verify_parent(
            derived_dir,
            data_root,
            load_derived_descriptor(descriptor_path),
            repo_root=root,
        )


@pytest.mark.parametrize(
    "tamper",
    ["manifest_only", "committed_approval", "repository_approval"],
)
def test_verify_parent_rejects_warn_approved_forgery_or_drift(
    tmp_path: Path, monkeypatch, tamper: str
) -> None:
    from quantara.hashing import sha256_hex
    from quantara.jcs import canonicalize
    from test_derive_pipeline import _run_warn_approved_derived_fixture

    root, data_root, descriptor_path, derived_dir, commit_dir, approval_path = (
        _run_warn_approved_derived_fixture(tmp_path, monkeypatch)
    )
    if tamper == "manifest_only":
        (commit_dir / "quality-approval.json").unlink()
    elif tamper == "committed_approval":
        committed = json.loads(
            (commit_dir / "quality-approval.json").read_text(encoding="utf-8")
        )
        committed["rationale"] = "tampered after publication"
        (commit_dir / "quality-approval.json").write_text(
            json.dumps(committed, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    else:
        repository = yaml.safe_load(approval_path.read_text(encoding="utf-8"))
        repository["rationale"] = "repository drift after publication"
        semantics = {
            key: value
            for key, value in repository.items()
            if key != "record_sha256"
        }
        repository["record_sha256"] = sha256_hex(
            canonicalize(semantics).encode("utf-8")
        )
        approval_path.write_text(yaml.safe_dump(repository), encoding="utf-8")
    _assert_research_parent_rejected(
        root, data_root, descriptor_path, derived_dir
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("canonical_content_hash", "0" * 64),
        ("schema_fingerprint", "1" * 64),
        ("source_sha256", ["2" * 64]),
        ("quality_identity_sha256", "3" * 64),
    ],
)
def test_verify_parent_rejects_stale_warn_approved_bindings(
    tmp_path: Path, monkeypatch, field: str, value
) -> None:
    from test_derive_pipeline import (
        _rewrite_derived_approval_binding,
        _run_warn_approved_derived_fixture,
    )

    root, data_root, descriptor_path, derived_dir, commit_dir, approval_path = (
        _run_warn_approved_derived_fixture(tmp_path, monkeypatch)
    )
    _rewrite_derived_approval_binding(
        derived_dir,
        commit_dir,
        approval_path,
        lambda document: document.__setitem__(field, value),
    )
    _assert_research_parent_rejected(
        root, data_root, descriptor_path, derived_dir
    )


def test_verify_parent_rejects_fresh_warn_approved_rederivation_mismatch(
    tmp_path: Path, monkeypatch
) -> None:
    from quantara.derive_quality import DerivedQualityReport, Finding
    from test_derive_pipeline import _run_warn_approved_derived_fixture

    root, data_root, descriptor_path, derived_dir, _, _ = (
        _run_warn_approved_derived_fixture(tmp_path, monkeypatch)
    )
    monkeypatch.setattr(
        "quantara.research_pipeline.evaluate_derived_quality",
        lambda *args, **kwargs: DerivedQualityReport(
            [Finding("derived_zero_volume_bucket", "pass", "warning", 0, {})]
        ),
    )
    _assert_research_parent_rejected(
        root, data_root, descriptor_path, derived_dir
    )


def test_verify_parent_rejects_policy_v1_warn_blocked(
    tmp_path: Path, monkeypatch
) -> None:
    from quantara.hashing import sha256_hex
    from test_derive_pipeline import _run_warn_approved_derived_fixture

    root, data_root, descriptor_path, derived_dir, commit_dir, _ = (
        _run_warn_approved_derived_fixture(tmp_path, monkeypatch)
    )
    descriptor = yaml.safe_load(descriptor_path.read_text(encoding="utf-8"))
    descriptor["quality_policy_version"] = "1"
    descriptor.pop("quality_approval")
    descriptor_path.write_text(yaml.safe_dump(descriptor), encoding="utf-8")
    for filename in ("manifest.json", "quality.json", "content.json"):
        path = commit_dir / filename
        document = json.loads(path.read_text(encoding="utf-8"))
        if filename == "manifest.json":
            document["quality_policy_version"] = "1"
            document["quality_state"] = "WARN_BLOCKED"
        elif filename == "quality.json":
            document["policy_version"] = "1"
            document["state"] = "WARN_BLOCKED"
            for key in (
                "raw_state",
                "identity_sha256",
                "approval_record_id",
                "approval_record_sha256",
            ):
                document.pop(key, None)
        else:
            for key in (
                "quality_state",
                "quality_raw_state",
                "quality_identity_sha256",
                "quality_approval_record_id",
                "quality_approval_record_sha256",
            ):
                document.pop(key, None)
        path.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    (commit_dir / "quality-approval.json").unlink()
    pointer = json.loads((derived_dir / "current.json").read_text())
    pointer["manifest_sha256"] = sha256_hex(
        (commit_dir / "manifest.json").read_bytes()
    )
    (derived_dir / "current.json").write_text(
        json.dumps(pointer, indent=2, sort_keys=True), encoding="utf-8"
    )
    _assert_research_parent_rejected(
        root, data_root, descriptor_path, derived_dir
    )


def test_verify_parent_accepts_legacy_pass_parent(chain) -> None:
    from quantara.research_descriptor import load_research_descriptor
    from quantara.research_pipeline import _parent_klines_dir, _verify_parent

    root, data_root = chain
    research_descriptor = load_research_descriptor(
        write_research_descriptor(root, "1h")
    )
    base = research_descriptor.base_descriptor
    parent_dir = _parent_klines_dir(
        data_root, base.provider_symbol, base.interval, base.start_utc
    )
    parent = _verify_parent(parent_dir, data_root, base, repo_root=root)
    assert parent["quality_state"] == "PASS"
    assert "quality_raw_state" not in parent
