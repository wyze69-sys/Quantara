"""Derivation corruption and recovery scenarios (plan Task 9, correction 2).

Every fixture assembles a fully genuine parent graph — real descriptor hash,
real schema fingerprint, real canonical-content hash, real manifest digest —
through the publication primitives. Fabricated hashes are never accepted, by
the tests or by the production verifier. Each scenario asserts hard stops with
stable diagnostics and no discoverable partial graph, or documented recovery.
"""

from __future__ import annotations

import json
from pathlib import Path

from conftest import (
    BASE_DESCRIPTOR_NAME,
    HOUR_MS,
    build_month_minute_rows,
    derived_cfg_tree,
    make_minute_row,
    write_derived_descriptor,
)
from quantara.canonical import (
    read_canonical_rows,
    reconcile_rows,
    write_canonical_parquet,
)
from quantara.derive_pipeline import run_derivation_pipeline
from quantara.descriptor import load_descriptor
from quantara.hashing import (
    canonical_content_hash,
    descriptor_hash,
    schema_fingerprint,
    sha256_hex,
)
from quantara.manifests import PARSER_VERSION
from quantara.publication import (
    publish_commit,
    put_object,
    stage_commit,
    write_current,
)
from quantara.quality import evaluate_quality


def _parent_dir(data_root: Path) -> Path:
    return (
        data_root / "datasets" / "binance" / "usdm" / "klines" / "BTCUSDT"
        / "1m" / "year=2024" / "month=01"
    )


def _derived_dir(data_root: Path, interval: str = "1h") -> Path:
    return (
        data_root / "datasets" / "binance" / "usdm" / "klines" / "BTCUSDT"
        / interval / "year=2024" / "month=01"
    )


def _write_parent_commit(
    root: Path,
    data_root: Path,
    rows,
    tag: str,
    parquet_bytes_override: bytes | None = None,
) -> tuple:
    """Publish one genuine parent commit; returns (parquet_sha, content_hash).

    ``parquet_bytes_override`` allows publishing logically identical rows
    under different physical Parquet bytes (e.g., multi-row-group encoding),
    which changes the authenticated byte-level lineage while leaving every
    aggregate — and therefore the canonical content hash — untouched.
    """
    staging = data_root / "staging" / f"parent-build-{tag}"
    staging.mkdir(parents=True, exist_ok=True)
    parquet_path = staging / "canonical.parquet"
    if parquet_bytes_override is None:
        write_canonical_parquet(rows, parquet_path)
    else:
        parquet_path.write_bytes(parquet_bytes_override)
    persisted = read_canonical_rows(parquet_path)
    reconcile_rows(rows, persisted)
    parquet_bytes = parquet_path.read_bytes()
    parquet_sha = sha256_hex(parquet_bytes)

    base = load_descriptor(root / "configs" / "datasets" / BASE_DESCRIPTOR_NAME)
    fingerprint = schema_fingerprint(base.schema_version)
    content_hash_value = canonical_content_hash(
        fingerprint, [row.to_content_array() for row in rows]
    )
    put_object(data_root, "normalized", parquet_bytes)

    # Genuine Slice 001 quality evidence for these exact rows.
    report = evaluate_quality(
        rows, base, source_order_valid=True,
        expected_count=base.expected_row_count,
    )
    assert report.state == "PASS", report.state
    identity = report.identity()
    quality_doc = {
        "state": report.state,
        "policy_version": "1",
        "identity": identity,
        "findings": [
            {
                "check_id": f.check_id,
                "outcome": f.outcome,
                "severity": f.severity,
                "count": f.count,
                "evidence": f.evidence,
            }
            for f in report.findings
        ],
    }

    manifest = {
        "dataset_id": base.dataset_id,
        "instrument_id": base.instrument_id,
        "schema_version": base.schema_version,
        "schema_fingerprint": fingerprint,
        "timestamp_semantics": base.timestamp_semantics,
        "quality_policy_version": "1",
        "quality_state": "PASS",
        "quality_identity": identity,
        "source_row_count": len(rows),
        "canonical_row_count": len(rows),
        "canonical_content_hash": content_hash_value,
        "parquet_sha256": parquet_sha,
        "parquet_size": len(parquet_bytes),
        "object_refs": [{"kind": "normalized", "sha256": parquet_sha}],
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    content = {
        "descriptor_sha256": descriptor_hash(base.canonical_semantics()),
        "schema_fingerprint": fingerprint,
        "parser_version": PARSER_VERSION,
        "canonical_content_hash": content_hash_value,
        "quality_identity": identity,
        "object_refs": [{"kind": "normalized", "sha256": parquet_sha}],
    }
    staged = stage_commit(_parent_dir(data_root), tag, {
        "content.json": (json.dumps(content) + "\n").encode(),
        "manifest.json": manifest_bytes,
        "quality.json": (
            json.dumps(quality_doc, indent=2, sort_keys=True) + "\n"
        ).encode(),
    })
    publish_commit(staged, _parent_dir(data_root) / "commits", content_hash_value)
    write_current(
        _parent_dir(data_root), content_hash_value, sha256_hex(manifest_bytes)
    )
    return parquet_sha, content_hash_value


def _setup(tmp_path: Path):
    root = derived_cfg_tree(tmp_path)
    return root, tmp_path / "data"


def _publish_parent(rows, tmp_path: Path):
    root, data_root = _setup(tmp_path)
    parquet_sha, content_hash_value = _write_parent_commit(
        root, data_root, rows, "initial"
    )
    return root, data_root, parquet_sha, content_hash_value


def _valid_parent(tmp_path: Path):
    return _publish_parent(build_month_minute_rows(), tmp_path)


def _assert_blocked_with(root, data_root, diagnostic):
    descriptor = write_derived_descriptor(root, "1h")
    code = run_derivation_pipeline(descriptor, data_root, repo_root=root)
    assert code == 2
    attempts = list((data_root / "attempts").glob("*.json"))
    diagnostics = [json.loads(p.read_text())["diagnostics"] for p in attempts]
    assert diagnostics == [[diagnostic]]


# --- baseline rejection scenarios (retained from plan Task 9) -----------------


def test_missing_parent_current_json_blocks(tmp_path: Path) -> None:
    root, data_root, *_ = _valid_parent(tmp_path)
    (_parent_dir(data_root) / "current.json").unlink()
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")
    assert not _derived_dir(data_root).exists()


def test_invalid_parent_current_json_blocks(tmp_path: Path) -> None:
    root, data_root, *_ = _valid_parent(tmp_path)
    (_parent_dir(data_root) / "current.json").write_text(
        "{not json", encoding="utf-8"
    )
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")


def test_parent_object_drift_blocks_before_compute(tmp_path: Path) -> None:
    root, data_root, parquet_sha, *_ = _valid_parent(tmp_path)
    obj = data_root / "objects" / "normalized" / "sha256" / parquet_sha
    obj.write_bytes(b"tampered")  # drift the committed bytes
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")
    assert not _derived_dir(data_root).exists()


def test_incomplete_parent_commit_graph_blocks(tmp_path: Path) -> None:
    root, data_root, *_ = _valid_parent(tmp_path)
    commit = json.loads((_parent_dir(data_root) / "current.json").read_text())[
        "commit"
    ]
    (_parent_dir(data_root) / "commits" / commit / "COMMITTED").unlink()
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")


# --- correction 2 helpers ------------------------------------------------------


def _rewrite_manifest_consistently(data_root: Path, mutate) -> None:
    """Tamper the manifest and keep pointer digest consistent so ONLY the
    semantic check under test can reject the graph."""
    commit = json.loads((_parent_dir(data_root) / "current.json").read_text())[
        "commit"
    ]
    manifest_path = _parent_dir(data_root) / "commits" / commit / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    mutate(manifest)
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    manifest_path.write_bytes(manifest_bytes)
    pointer_path = _parent_dir(data_root) / "current.json"
    pointer = json.loads(pointer_path.read_text())
    pointer["manifest_sha256"] = sha256_hex(manifest_bytes)
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")


def _pointer_commit(data_root: Path) -> str:
    return json.loads((_parent_dir(data_root) / "current.json").read_text())[
        "commit"
    ]



# --- correction 2: fabricated or inconsistent evidence must block -------------


def test_malformed_pointer_structure_blocks(tmp_path: Path) -> None:
    root, data_root, *_ = _valid_parent(tmp_path)
    pointer_path = _parent_dir(data_root) / "current.json"
    pointer = json.loads(pointer_path.read_text())
    del pointer["manifest_sha256"]  # structurally incomplete pointer
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")


def test_wrong_pointer_protocol_version_blocks(tmp_path: Path) -> None:
    root, data_root, *_ = _valid_parent(tmp_path)
    pointer_path = _parent_dir(data_root) / "current.json"
    pointer = json.loads(pointer_path.read_text())
    pointer["publication_protocol_version"] = "v0"
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")


def test_manifest_digest_mismatch_blocks(tmp_path: Path) -> None:
    """manifest.json tampered after publication: current.json pins the digest."""
    root, data_root, *_ = _valid_parent(tmp_path)
    manifest_path = (
        _parent_dir(data_root) / "commits" / _pointer_commit(data_root)
        / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text())
    manifest["source_row_count"] = 1  # tamper
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")


def test_missing_required_manifest_field_blocks(tmp_path: Path) -> None:
    def drop_parquet_sha(manifest):
        del manifest["parquet_sha256"]

    root, data_root, *_ = _valid_parent(tmp_path)
    _rewrite_manifest_consistently(data_root, drop_parquet_sha)
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")


def test_parquet_size_mismatch_blocks(tmp_path: Path) -> None:
    def shrink_size(manifest):
        manifest["parquet_size"] -= 1

    root, data_root, *_ = _valid_parent(tmp_path)
    _rewrite_manifest_consistently(data_root, shrink_size)
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")



def test_canonical_content_identity_mismatch_blocks(tmp_path: Path) -> None:
    """content.json identity disagrees with the commit directory name: a
    fabricated graph object hashing alone cannot detect."""
    root, data_root, *_ = _valid_parent(tmp_path)
    content_path = (
        _parent_dir(data_root) / "commits" / _pointer_commit(data_root)
        / "content.json"
    )
    content = json.loads(content_path.read_text())
    content["canonical_content_hash"] = "a" * 64
    content_path.write_text(json.dumps(content) + "\n", encoding="utf-8")
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")


def test_committed_schema_evidence_mismatch_blocks(tmp_path: Path) -> None:
    """Manifest evidence internally consistent but contradicting the approved
    loaded base descriptor must be rejected."""
    def swap_schema(manifest):
        manifest["schema_version"] = "binance_usdm_kline_5m_v1"

    root, data_root, *_ = _valid_parent(tmp_path)
    _rewrite_manifest_consistently(data_root, swap_schema)
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")


def test_parent_quality_not_pass_blocks(tmp_path: Path) -> None:
    def degrade_quality(manifest):
        manifest["quality_state"] = "WARN_BLOCKED"

    root, data_root, *_ = _valid_parent(tmp_path)
    _rewrite_manifest_consistently(data_root, degrade_quality)
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")



# --- recovery behavior (retained from plan Task 9) -----------------------------


def test_derived_pointer_to_missing_commit_recovers(tmp_path: Path) -> None:
    root, data_root, *_ = _valid_parent(tmp_path)
    descriptor = write_derived_descriptor(root, "1h")
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    derived = _derived_dir(data_root)

    write_current(derived, "f" * 64, "m" * 64)  # dangling pointer
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    restored = json.loads((derived / "current.json").read_text())["commit"]
    assert (derived / "commits" / restored).is_dir()
    commits = [
        p for p in (derived / "commits").iterdir() if not p.name.startswith(".")
    ]
    assert len(commits) == 1
    assert restored == commits[0].name


def test_pointer_loss_never_creates_partial_graph(tmp_path: Path) -> None:
    root, data_root, *_ = _valid_parent(tmp_path)
    descriptor = write_derived_descriptor(root, "1h")
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    derived = _derived_dir(data_root)
    commit = json.loads((derived / "current.json").read_text())["commit"]

    # Failure after object write + commit rename but BEFORE pointer
    # replacement: safe orphan, never canonical.
    (derived / "current.json").unlink()
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    assert json.loads((derived / "current.json").read_text())["commit"] == commit
    commits = sorted(
        p.name for p in (derived / "commits").iterdir()
        if not p.name.startswith(".")
    )
    assert commits == [commit]


def test_stale_staging_is_discarded(tmp_path: Path) -> None:
    root, data_root, *_ = _valid_parent(tmp_path)
    derived = _derived_dir(data_root)
    stale = derived / "commits" / ".staging-stale-attempt"
    stale.mkdir(parents=True)
    (stale / "junk.bin").write_bytes(b"0")
    descriptor = write_derived_descriptor(root, "1h")
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    assert not list((derived / "commits").glob(".staging-*"))



def test_parent_republished_derived_rerun_publishes_new_lineage_commit(
    tmp_path: Path,
) -> None:
    rows = build_month_minute_rows()
    root, data_root = _setup(tmp_path)
    _, old_parent_cch = _write_parent_commit(root, data_root, rows, "gen1")
    descriptor = write_derived_descriptor(root, "1h")
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    derived = _derived_dir(data_root)
    old_pointer = (derived / "current.json").read_bytes()
    old_commit = json.loads(old_pointer)["commit"]
    old_files = {
        p.relative_to(derived).as_posix(): sha256_hex(p.read_bytes())
        for p in derived.rglob("*") if p.is_file()
    }

    # Parent legitimately republished with different content: fully genuine
    # second commit (changed close changes the affected hourly aggregates).
    changed = list(rows)
    victim = changed[10]
    changed[10] = make_minute_row(
        victim.open_time_ms,
        o="42571.90", h="50000.00", lo="42500.10", c="42590.50",
        bv=victim.base_asset_volume, qv=victim.quote_asset_volume,
        n=3210, tbv=victim.taker_buy_base_volume,
        tqv=victim.taker_buy_quote_volume,
    )
    new_sha, new_cch = _write_parent_commit(root, data_root, changed, "repub")
    assert new_cch != old_parent_cch

    # Derived rerun publishes a NEW lineage-bound commit.
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    new_pointer = (derived / "current.json").read_bytes()
    new_commit = json.loads(new_pointer)["commit"]
    assert new_commit != old_commit
    new_content = json.loads(
        (derived / "commits" / new_commit / "content.json").read_text()
    )
    assert new_content["derived_from"]["parent_parquet_sha256"] == new_sha

    # The old derived commit stays byte-identical (immutable history).
    for rel, digest in old_files.items():
        path = derived / rel
        if old_commit in path.as_posix():
            assert sha256_hex(path.read_bytes()) == digest
    commits = [
        p.name for p in (derived / "commits").iterdir()
        if not p.name.startswith(".")
    ]
    assert sorted(commits) == sorted({old_commit, new_commit})







def test_changed_parent_lineage_identical_aggregates_create_distinct_commit(
    tmp_path: Path,
) -> None:
    """A parent row change that provably leaves every hourly aggregate
    untouched (an interior minute's close moves within [low, high], away from
    the hour's first/last constituents and extremes) changes the authenticated
    parent lineage while canonical_content_hash stays identical. The derived
    commit identity must still yield a distinct immutable commit, current.json
    must advance atomically, and the old commit must remain byte-identical."""
    rows = build_month_minute_rows()
    root, data_root = _setup(tmp_path)
    _, parent_cch_1 = _write_parent_commit(root, data_root, rows, "gen1")
    descriptor = write_derived_descriptor(root, "1h")
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    derived = _derived_dir(data_root)
    old_pointer = (derived / "current.json").read_bytes()
    old_commit = json.loads(old_pointer)["commit"]
    old_content = json.loads(
        (derived / "commits" / old_commit / "content.json").read_text()
    )
    old_cch = old_content["canonical_content_hash"]
    commit_dir_old = derived / "commits" / old_commit
    old_tree = {
        p.relative_to(commit_dir_old).as_posix(): sha256_hex(p.read_bytes())
        for p in commit_dir_old.rglob("*") if p.is_file()
    }

    # Interior-minute close change: not an hour boundary constituent (index 10
    # of 0..59), strictly inside [low, high] of its hour.
    changed = list(rows)
    victim = changed[10]
    assert victim.open_time_ms % HOUR_MS not in (0, HOUR_MS - 60_000)
    new_close = (victim.low + victim.high) / 2
    assert victim.low < new_close < victim.high
    changed[10] = make_minute_row(
        victim.open_time_ms,
        o=victim.open, h=victim.high, lo=victim.low, c=new_close,
        bv=victim.base_asset_volume, qv=victim.quote_asset_volume,
        n=victim.trade_count, tbv=victim.taker_buy_base_volume,
        tqv=victim.taker_buy_quote_volume,
    )
    new_sha, parent_cch_2 = _write_parent_commit(
        root, data_root, changed, "same-aggregates"
    )
    assert parent_cch_2 != parent_cch_1  # parent content authentically moved

    # Rerun publishes a NEW lineage-bound derived commit even though every
    # 1h bar — and therefore canonical_content_hash — is identical.
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    advanced_pointer = (derived / "current.json").read_bytes()
    assert advanced_pointer != old_pointer
    new_commit = json.loads(advanced_pointer)["commit"]
    assert new_commit != old_commit
    new_content = json.loads(
        (derived / "commits" / new_commit / "content.json").read_text()
    )
    assert new_content["canonical_content_hash"] == old_cch
    assert new_content["derived_from"]["parent_parquet_sha256"] == new_sha
    assert (
        new_content["derived_from"]["parent_canonical_content_hash"]
        == parent_cch_2
    )

    # Old derived commit byte-identical and still discoverable; pointer moved.
    new_tree = {
        p.relative_to(commit_dir_old).as_posix(): sha256_hex(p.read_bytes())
        for p in commit_dir_old.rglob("*") if p.is_file()
    }
    assert new_tree == old_tree
    commits = {
        p.name for p in (derived / "commits").iterdir()
        if not p.name.startswith(".")
    }
    assert commits == {old_commit, new_commit}

    # Idempotency under identical lineage: VERIFIED_NO_OP, byte-identical
    # pointer and complete commit tree, exactly two new attempt manifests.
    attempts_before = {p.name for p in (data_root / "attempts").glob("*.json")}
    noop_pointer_before = (derived / "current.json").read_bytes()
    noop_tree_before = {
        p.relative_to(derived).as_posix(): sha256_hex(p.read_bytes())
        for p in derived.rglob("*") if p.is_file()
    }
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    assert (derived / "current.json").read_bytes() == noop_pointer_before
    noop_tree_after = {
        p.relative_to(derived).as_posix(): sha256_hex(p.read_bytes())
        for p in derived.rglob("*") if p.is_file()
    }
    assert noop_tree_after == noop_tree_before
    added = {
        p.name for p in (data_root / "attempts").glob("*.json")
    } - attempts_before
    assert len(added) == 1  # one per derived interval
    results = [
        json.loads((data_root / "attempts" / name).read_text())["terminal_result"]
        for name in added
    ]
    assert results == ["VERIFIED_NO_OP"]


# --- correction 4: attempt evidence accuracy, staging hygiene, fault injection ---


def _noop_attempt_ids(data_root: Path):

    results = {}
    for p in (data_root / "attempts").glob("*.json"):
        payload = json.loads(p.read_text())
        if payload["terminal_result"] == "VERIFIED_NO_OP":
            results[p.name] = payload
    return results


def _force_quality_failure(monkeypatch):
    """Force the derived quality gate to FAIL after the staged Parquet was
    already written, exposing disposition inaccuracies."""
    import quantara.derive_pipeline as dp

    real = dp.evaluate_derived_quality

    def failing(*args, **kwargs):
        report = real(*args, **kwargs)
        from quantara.derive_quality import DerivedQualityReport, Finding

        findings = list(report.findings) + [
            Finding(
                check_id="derived_forced_failure",
                outcome="fail",
                severity="hard",
                count=1,
                evidence={"injected": True},
            )
        ]
        return DerivedQualityReport(findings=findings)

    monkeypatch.setattr(dp, "evaluate_derived_quality", failing)


def test_quality_blocked_after_staging_reports_staged_not_published(
    tmp_path, monkeypatch
) -> None:
    root, data_root, *_ = _valid_parent(tmp_path)
    descriptor = write_derived_descriptor(root, "1h")
    _force_quality_failure(monkeypatch)
    code = run_derivation_pipeline(descriptor, data_root, repo_root=root)
    assert code == 2
    attempts = list((data_root / "attempts").glob("*.json"))
    assert len(attempts) == 1
    attempt = json.loads(attempts[0].read_text())
    assert attempt["terminal_result"] == "BLOCKED"
    # The staged Parquet existed at blocking time; reporting it as
    # not_written is exactly the defect this correction removes.
    assert (
        attempt["artifact_dispositions"]["normalized_parquet"]
        != "not_written"
    )
    # Staging evidence is cleaned up either way.
    residue = [
        p for p in (data_root / "staging").glob("*")
        if not p.name.startswith("parent-build")  # fixture-owned inputs
    ]
    assert residue == []


def test_fault_injection_object_write_failure(tmp_path, monkeypatch) -> None:
    import quantara.derive_pipeline as dp
    from quantara.errors import QuantaraError

    root, data_root, *_ = _valid_parent(tmp_path)
    descriptor = write_derived_descriptor(root, "1h")

    def boom(*a, **k):
        raise QuantaraError("injected object write failure")

    monkeypatch.setattr(dp, "put_object", boom)
    code = run_derivation_pipeline(descriptor, data_root, repo_root=root)
    assert code == 3
    attempts = list((data_root / "attempts").glob("*.json"))
    attempt = json.loads(attempts[-1].read_text())
    assert attempt["terminal_result"] == "FAILED"
    assert attempt["diagnostics"] == ["quantara_error"] or any(
        "injected" in d for d in attempt["diagnostics"]
    )
    assert not (_derived_dir(data_root) / "current.json").exists()
    residue = [
        p for p in (data_root / "staging").glob("*")
        if not p.name.startswith("parent-build")  # fixture-owned inputs
    ]
    assert residue == []


def test_fault_injection_commit_rename_failure(tmp_path, monkeypatch) -> None:
    import quantara.derive_pipeline as dp
    from quantara.publication import PublicationError

    root, data_root, *_ = _valid_parent(tmp_path)
    descriptor = write_derived_descriptor(root, "1h")

    def boom(*a, **k):
        raise PublicationError("injected rename failure")

    monkeypatch.setattr(dp, "publish_commit", boom)
    code = run_derivation_pipeline(descriptor, data_root, repo_root=root)
    assert code == 3
    derived = _derived_dir(data_root)
    assert not (derived / "current.json").exists()
    visible = [
        p for p in (derived / "commits").iterdir() if not p.name.startswith(".")
    ] if (derived / "commits").exists() else []
    assert visible == []  # rename failed: nothing discoverable
    attempts = list((data_root / "attempts").glob("*.json"))
    assert json.loads(attempts[-1].read_text())["terminal_result"] == "FAILED"
    residue = [
        p for p in (data_root / "staging").glob("*")
        if not p.name.startswith("parent-build")  # fixture-owned inputs
    ]
    assert residue == []


def test_fault_injection_pointer_replacement_failure(tmp_path, monkeypatch) -> None:
    import quantara.derive_pipeline as dp
    from quantara.errors import QuantaraError

    root, data_root, *_ = _valid_parent(tmp_path)
    descriptor = write_derived_descriptor(root, "1h")

    def boom(*a, **k):
        raise QuantaraError("injected pointer failure")

    monkeypatch.setattr(dp, "write_current", boom)
    code = run_derivation_pipeline(descriptor, data_root, repo_root=root)
    assert code == 3
    derived = _derived_dir(data_root)
    # The renamed commit is a safe orphan; nothing is discoverable.
    assert not (derived / "current.json").exists()
    attempts = list((data_root / "attempts").glob("*.json"))
    assert json.loads(attempts[-1].read_text())["terminal_result"] == "FAILED"


def test_fault_injection_discovery_readback_failure(tmp_path, monkeypatch) -> None:
    """Closure 2.7: pointer replacement succeeded but discovery verification
    failed — evidence must record the actual published-but-unverified state,
    and the next invocation must recover it as VERIFIED_NO_OP without
    duplicating or mutating the retained commit."""
    import quantara.derive_pipeline as dp

    root, data_root, *_ = _valid_parent(tmp_path)
    descriptor = write_derived_descriptor(root, "1h")

    real = dp.verify_derived_current_graph
    calls = {"n": 0}

    def flaky(dataset_dir, data_root_arg):
        calls["n"] += 1
        if calls["n"] == 1:
            # The only call so far is the final post-pointer discovery.
            raise OSError("injected discovery io failure")
        return real(dataset_dir, data_root_arg)

    monkeypatch.setattr(dp, "verify_derived_current_graph", flaky)
    code = run_derivation_pipeline(descriptor, data_root, repo_root=root)
    assert code == 3  # policy-approved non-success: verification incomplete

    derived = _derived_dir(data_root)
    pointer_commit = json.loads((derived / "current.json").read_text())["commit"]
    payload = _attempt_payloads(data_root)[-1]
    assert payload["terminal_result"] == "FAILED"
    assert payload["referenced_commit"] == pointer_commit
    assert payload["artifact_dispositions"]["pointer_replaced"] is True
    assert payload["artifact_dispositions"]["discovery_verified"] is False
    assert payload["artifact_dispositions"]["post_pointer"] == (
        "published_unverified"
    )
    # The atomic pointer/commit graph remains internally valid.
    real(derived, data_root)

    # Recovery: the next invocation verifies the published state fully and
    # reports VERIFIED_NO_OP without duplicating or mutating the commit.
    commits_before = {
        p.name for p in (derived / "commits").iterdir()
        if not p.name.startswith(".")
    }
    attempts_before = {p.name for p in (data_root / "attempts").glob("*.json")}
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    assert json.loads((derived / "current.json").read_text())["commit"] == (
        pointer_commit
    )
    commits_after = {
        p.name for p in (derived / "commits").iterdir()
        if not p.name.startswith(".")
    }
    assert commits_after == commits_before
    recovery = {
        p.name: json.loads(p.read_text())
        for p in (data_root / "attempts").glob("*.json")
        if p.name not in attempts_before
    }
    assert [a["terminal_result"] for a in recovery.values()] == ["VERIFIED_NO_OP"]

def test_attempt_manifest_write_failure_does_not_mask_result(
    tmp_path, monkeypatch, capsys
) -> None:
    import quantara.derive_pipeline as dp

    root, data_root, *_ = _valid_parent(tmp_path)
    descriptor = write_derived_descriptor(root, "1h")

    real_write_json = dp.write_json
    attempted = {"n": 0}

    def flaky(path, payload):
        attempted["n"] += 1
        if attempted["n"] == 1:
            raise OSError("injected attempt-manifest failure")
        return real_write_json(path, payload)

    monkeypatch.setattr(dp, "write_json", flaky)
    code = run_derivation_pipeline(descriptor, data_root, repo_root=root)
    assert code == 0  # publication succeeded despite evidence-recording fault
    assert (_derived_dir(data_root) / "current.json").exists()
    captured = capsys.readouterr()
    assert "attempt manifest" in (captured.err + captured.out)


# --- correction 7: bounded transient-status retries for verified downloads ----




def test_verified_download_retries_eligible_statuses_then_succeeds() -> None:
    from types import SimpleNamespace

    from test_integration_derivation import _verified_download

    calls = {"n": 0}

    def fake_get(url, timeout):
        calls["n"] += 1
        if calls["n"] < 3:
            return SimpleNamespace(status_code=503, content=b"")
        return SimpleNamespace(status_code=200, content=b"payload-bytes")

    sleeps = []
    out = _verified_download(
        "https://data.binance.vision/data/futures/x.zip",
        retries=4,
        transport=fake_get,
        sleeper=sleeps.append,
    )
    assert out == b"payload-bytes"
    assert calls["n"] == 3
    assert len(sleeps) == 2  # bounded backoff between the two 503s


def test_verified_download_fails_fast_on_ineligible_status() -> None:
    from types import SimpleNamespace

    import pytest as _pytest

    from test_integration_derivation import _verified_download

    calls = {"n": 0}

    def fake_get(url, timeout):
        calls["n"] += 1
        return SimpleNamespace(status_code=404, content=b"")

    with _pytest.raises(AssertionError, match="non-retryable HTTP 404"):
        _verified_download(
            "https://data.binance.vision/data/futures/x.zip",
            retries=4,
            transport=fake_get,
            sleeper=lambda _s: None,
        )
    assert calls["n"] == 1  # no retries for ineligible statuses


def test_verified_download_rejects_non_allowlisted_host() -> None:
    import pytest as _pytest

    from test_integration_derivation import _verified_download

    with _pytest.raises(AssertionError, match="non-allowlisted host"):
        _verified_download("https://evil.example.com/file.zip")


# --- phase closure 2.1: authenticate parent canonical rows --------------------


def test_fabricated_canonical_content_identity_blocks_before_derivation(
    tmp_path: Path,
) -> None:
    """Adversarial: a parent graph that is internally consistent at the
    byte/digest level but whose committed canonical_content_hash does NOT
    match its actual retained rows must be rejected before any derivation."""
    from quantara.canonical import write_canonical_parquet as _write_pq
    from quantara.descriptor import load_descriptor
    from quantara.hashing import canonical_content_hash, schema_fingerprint
    from quantara.publication import put_object

    rows = build_month_minute_rows()
    root, data_root = _setup(tmp_path)
    _, original_cch = _write_parent_commit(root, data_root, rows, "gen1")

    # Build different valid canonical content and swap the object in,
    # updating every byte-level pointer consistently.
    changed = list(rows)
    victim = changed[100]
    changed[100] = make_minute_row(
        victim.open_time_ms,
        o=victim.open, h=victim.high, lo=victim.low, c="77777.77",
        bv=victim.base_asset_volume, qv=victim.quote_asset_volume,
        n=victim.trade_count, tbv=victim.taker_buy_base_volume,
        tqv=victim.taker_buy_quote_volume,
    )
    staging = data_root / "staging" / "adversarial-swap"
    staging.mkdir(parents=True)
    swap_path = staging / "canonical.parquet"
    _write_pq(changed, swap_path)
    new_bytes = swap_path.read_bytes()
    new_sha = sha256_hex(new_bytes)
    put_object(data_root, "normalized", new_bytes)

    commit = json.loads((_parent_dir(data_root) / "current.json").read_text())[
        "commit"
    ]
    assert commit == original_cch  # internally consistent but FALSE identity

    manifest_path = _parent_dir(data_root) / "commits" / commit / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["parquet_sha256"] = new_sha
    manifest["parquet_size"] = len(new_bytes)
    manifest["object_refs"] = [{"kind": "normalized", "sha256": new_sha}]
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    manifest_path.write_bytes(manifest_bytes)

    content_path = _parent_dir(data_root) / "commits" / commit / "content.json"
    content = json.loads(content_path.read_text())
    content["object_refs"] = [{"kind": "normalized", "sha256": new_sha}]
    content_path.write_text(json.dumps(content) + "\n", encoding="utf-8")

    pointer_path = _parent_dir(data_root) / "current.json"
    pointer = json.loads(pointer_path.read_text())
    pointer["manifest_sha256"] = sha256_hex(manifest_bytes)
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")

    # The lie is fully consistent except against the actual retained rows:
    base = load_descriptor(root / "configs" / "datasets" / BASE_DESCRIPTOR_NAME)
    recomputed = canonical_content_hash(
        schema_fingerprint(base.schema_version),
        [r.to_content_array() for r in changed],
    )
    assert recomputed != commit  # the swapped rows hash differently

    descriptor = write_derived_descriptor(root, "1h")
    code = run_derivation_pipeline(descriptor, data_root, repo_root=root)
    assert code == 2
    attempts = list((data_root / "attempts").glob("*.json"))
    diagnostics = [json.loads(p.read_text())["diagnostics"] for p in attempts]
    assert diagnostics == [["parent_dataset_unavailable"]]
    assert not _derived_dir(data_root).exists()


# --- phase closure 2.2: authenticate parent quality evidence ------------------


def _rewrite_quality_consistently(data_root: Path, mutate_doc) -> None:
    """Tamper quality.json AND keep every digest consistent so only semantic
    authentication (not byte digests) can reject the graph."""
    commit = _pointer_commit(data_root)
    qpath = _parent_dir(data_root) / "commits" / commit / "quality.json"
    doc = json.loads(qpath.read_text())
    mutate_doc(doc)
    qbytes = (json.dumps(doc, indent=2, sort_keys=True) + "\n").encode()
    qpath.write_bytes(qbytes)
    pointer_path = _parent_dir(data_root) / "current.json"
    pointer = json.loads(pointer_path.read_text())
    pointer["manifest_sha256"] = pointer["manifest_sha256"]  # unchanged
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")


def test_tampered_quality_findings_break_identity_chain(tmp_path: Path) -> None:
    root, data_root, *_ = _valid_parent(tmp_path)

    def tamper(doc):
        doc["findings"][0]["count"] = 999999  # forged evidence

    _rewrite_quality_consistently(data_root, tamper)
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")


def test_manifest_only_pass_lie_blocks(tmp_path: Path) -> None:
    """quality.json honestly records WARN_BLOCKED while the manifest claims
    PASS: the disagreement itself must block."""
    root, data_root, *_ = _valid_parent(tmp_path)

    def degrade(doc):
        doc["state"] = "WARN_BLOCKED"

    commit = _pointer_commit(data_root)
    qpath = _parent_dir(data_root) / "commits" / commit / "quality.json"
    degrade(json.loads(qpath.read_text()))
    doc = json.loads(qpath.read_text())
    doc["state"] = "WARN_BLOCKED"
    qbytes = (json.dumps(doc, indent=2, sort_keys=True) + "\n").encode()
    qpath.write_bytes(qbytes)
    # Manifest still claims PASS; digests elsewhere untouched.
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")


def test_rows_failing_fresh_quality_block_despite_fabricated_metadata(
    tmp_path: Path,
) -> None:
    """Every committed artifact is internally consistent and claims PASS, but
    the actual retained rows contain an impossible negative volume: the fresh
    independent evaluation must block."""
    from quantara.canonical import write_canonical_parquet as _write_pq
    from quantara.descriptor import load_descriptor
    from quantara.hashing import canonical_content_hash, descriptor_hash
    from quantara.publication import put_object
    from quantara.quality import evaluate_quality

    good_rows = build_month_minute_rows()
    root, data_root = _setup(tmp_path)
    _, genuine_cch = _write_parent_commit(root, data_root, good_rows, "gen1")

    # Genuine quality evidence of the GOOD rows, reused as the lie.
    base = load_descriptor(root / "configs" / "datasets" / BASE_DESCRIPTOR_NAME)
    good_report = evaluate_quality(
        good_rows, base, source_order_valid=True,
        expected_count=base.expected_row_count,
    )
    identity = good_report.identity()
    quality_doc = {
        "state": good_report.state,
        "policy_version": "1",
        "identity": identity,
        "findings": [
            {
                "check_id": f.check_id,
                "outcome": f.outcome,
                "severity": f.severity,
                "count": f.count,
                "evidence": f.evidence,
            }
            for f in good_report.findings
        ],
    }

    # Bad rows: impossible negative quote volume on one minute.
    bad_rows = list(good_rows)
    v = bad_rows[500]
    bad_rows[500] = make_minute_row(
        v.open_time_ms, o=v.open, h=v.high, lo=v.low, c=v.close,
        bv=v.base_asset_volume, qv="-5", n=v.trade_count,
        tbv=v.taker_buy_base_volume, tqv=v.taker_buy_quote_volume,
    )
    staging = data_root / "staging" / "bad-rows"
    staging.mkdir(parents=True)
    pq = staging / "canonical.parquet"
    _write_pq(bad_rows, pq)
    bad_bytes = pq.read_bytes()
    bad_sha = sha256_hex(bad_bytes)
    fingerprint = schema_fingerprint(base.schema_version)
    bad_cch = canonical_content_hash(
        fingerprint, [r.to_content_array() for r in bad_rows]
    )
    put_object(data_root, "normalized", bad_bytes)

    manifest = {
        "dataset_id": base.dataset_id,
        "instrument_id": base.instrument_id,
        "schema_version": base.schema_version,
        "schema_fingerprint": fingerprint,
        "timestamp_semantics": base.timestamp_semantics,
        "quality_policy_version": "1",
        "quality_state": "PASS",
        "quality_identity": identity,
        "source_row_count": len(bad_rows),
        "canonical_row_count": len(bad_rows),
        "canonical_content_hash": bad_cch,
        "parquet_sha256": bad_sha,
        "parquet_size": len(bad_bytes),
        "object_refs": [{"kind": "normalized", "sha256": bad_sha}],
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    content = {
        "descriptor_sha256": descriptor_hash(base.canonical_semantics()),
        "schema_fingerprint": fingerprint,
        "parser_version": PARSER_VERSION,
        "canonical_content_hash": bad_cch,
        "quality_identity": identity,
        "object_refs": [{"kind": "normalized", "sha256": bad_sha}],
    }
    staged = stage_commit(_parent_dir(data_root), "bad", {
        "content.json": (json.dumps(content) + "\n").encode(),
        "manifest.json": manifest_bytes,
        "quality.json": (
            json.dumps(quality_doc, indent=2, sort_keys=True) + "\n"
        ).encode(),
    })
    publish_commit(staged, _parent_dir(data_root) / "commits", bad_cch)
    write_current(_parent_dir(data_root), bad_cch, sha256_hex(manifest_bytes))
    assert bad_cch != genuine_cch

    descriptor = write_derived_descriptor(root, "1h")
    code = run_derivation_pipeline(descriptor, data_root, repo_root=root)
    assert code == 2
    attempts = list((data_root / "attempts").glob("*.json"))
    diagnostics = [json.loads(p.read_text())["diagnostics"] for p in attempts]
    assert diagnostics == [["parent_dataset_unavailable"]]


def test_trade_count_overflow_pipeline_exit_failed_with_cleanup(
    tmp_path: Path,
) -> None:
    """An int64-unrepresentable hourly count must produce a controlled
    EXIT_FAILED with accurate FAILED attempt evidence and no residue."""

    from quantara.aggregation import aggregate_timeframe

    rows = build_month_minute_rows()
    for i in range(60):
        rows[i] = make_minute_row(rows[i].open_time_ms, n=2**62)
    # Sanity: the constituents are individually representable.
    aggregate_timeframe(rows[60:120], (
        "binance", "usd_m_futures",
        "binance:usd_m_futures:BTCUSDT:perpetual", "BTCUSDT", "BTC", "USDT",
        "USDT", "perpetual", "1h", "binance_usdm_kline_1h_v1"), HOUR_MS)

    root, data_root = _setup(tmp_path)
    _write_parent_commit(root, data_root, rows, "big-counts")
    descriptor = write_derived_descriptor(root, "1h")
    code = run_derivation_pipeline(descriptor, data_root, repo_root=root)
    assert code == 3
    attempts = list((data_root / "attempts").glob("*.json"))
    assert len(attempts) == 1
    attempt = json.loads(attempts[0].read_text())
    assert attempt["terminal_result"] == "FAILED"
    assert attempt["diagnostics"] == ["integer_precision_overflow"]
    assert attempt["artifact_dispositions"]["normalized_parquet"] == (
        "not_written"  # overflow fires during aggregation, before staging
    )
    assert not (_derived_dir(data_root) / "current.json").exists()
    residue = [
        p for p in (data_root / "staging").glob("*")
        if not p.name.startswith("parent-build")
    ]
    assert residue == []


# --- phase closure 2.5/2.6/2.7: termination, addressing, outcomes ------------


def _attempt_payloads(data_root: Path):
    return [
        json.loads(p.read_text())
        for p in sorted((data_root / "attempts").glob("*.json"))
    ]


def test_invalid_descriptor_returns_exit_3(tmp_path: Path) -> None:
    root, data_root = _setup(tmp_path)
    bad = root / "configs" / "datasets" / "broken.yaml"
    bad.write_text("::: [not: yaml:\n  - x", encoding="utf-8")
    code = run_derivation_pipeline(bad, data_root, repo_root=root)
    assert code == 3


def test_rights_record_load_failure_returns_exit_3(tmp_path: Path) -> None:
    root, data_root, *_ = _valid_parent(tmp_path)
    legal = root / "configs" / "legal" / "binance-usdm-provider-rights.v1.yaml"
    legal.write_bytes(b"::: [broken: yaml\n")
    descriptor = write_derived_descriptor(root, "1h")
    code = run_derivation_pipeline(descriptor, data_root, repo_root=root)
    assert code == 3


def test_staging_mkdir_failure_returns_exit_3_with_evidence(
    tmp_path: Path,
) -> None:
    root, data_root, *_ = _valid_parent(tmp_path)
    import shutil as _shutil

    _shutil.rmtree(data_root / "staging", ignore_errors=True)
    (data_root / "staging").write_bytes(b"not a directory")
    descriptor = write_derived_descriptor(root, "1h")
    code = run_derivation_pipeline(descriptor, data_root, repo_root=root)
    assert code == 3
    payloads = _attempt_payloads(data_root)
    assert payloads[-1]["terminal_result"] == "FAILED"


def test_unreadable_derived_pointer_returns_exit_3(tmp_path: Path) -> None:
    root, data_root, *_ = _valid_parent(tmp_path)
    descriptor = write_derived_descriptor(root, "1h")
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    derived = _derived_dir(data_root)
    (derived / "current.json").write_bytes(b"\xff\xfe\x00binary")
    code = run_derivation_pipeline(descriptor, data_root, repo_root=root)
    assert code == 3
    payloads = _attempt_payloads(data_root)
    assert payloads[-1]["terminal_result"] == "FAILED"


def test_oserror_at_stage_commit_boundary_is_controlled(
    tmp_path, monkeypatch
) -> None:
    import quantara.derive_pipeline as dp

    root, data_root, *_ = _valid_parent(tmp_path)
    descriptor = write_derived_descriptor(root, "1h")

    def boom(*a, **k):
        raise OSError("injected fsync failure")

    monkeypatch.setattr(dp, "stage_commit", boom)
    code = run_derivation_pipeline(descriptor, data_root, repo_root=root)
    assert code == 3
    payloads = _attempt_payloads(data_root)
    assert payloads[-1]["terminal_result"] == "FAILED"
    derived = _derived_dir(data_root)
    assert not list((derived / "commits").glob(".staging-*"))
    residue = [
        p for p in (data_root / "staging").glob("*")
        if not p.name.startswith("parent-build")
    ]
    assert residue == []


def test_oserror_at_commit_verification_before_pointer(tmp_path, monkeypatch):
    import quantara.derive_pipeline as dp

    root, data_root, *_ = _valid_parent(tmp_path)
    descriptor = write_derived_descriptor(root, "1h")

    def boom(*a, **k):
        raise OSError("injected verification io failure")

    monkeypatch.setattr(dp, "verify_commit_graph", boom)
    code = run_derivation_pipeline(descriptor, data_root, repo_root=root)
    assert code == 3
    payload = _attempt_payloads(data_root)[-1]
    assert payload["terminal_result"] == "FAILED"
    assert payload["referenced_commit"] is None  # pre-pointer replacement
    assert payload["artifact_dispositions"]["pointer_replaced"] is False
    assert "post_pointer" not in payload["artifact_dispositions"]


def test_renamed_derived_commit_is_rejected_never_no_op(tmp_path: Path) -> None:
    root, data_root, *_ = _valid_parent(tmp_path)
    descriptor = write_derived_descriptor(root, "1h")
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    derived = _derived_dir(data_root)
    old_commit = json.loads((derived / "current.json").read_text())["commit"]
    forged_name = sha256_hex(b"forged-address")
    (derived / "commits" / old_commit).rename(derived / "commits" / forged_name)
    pointer = json.loads((derived / "current.json").read_text())
    pointer["commit"] = forged_name
    (derived / "current.json").write_text(json.dumps(pointer), encoding="utf-8")

    code = run_derivation_pipeline(descriptor, data_root, repo_root=root)
    assert code == 3  # rejected — never VERIFIED_NO_OP, never silent republish
    payload = _attempt_payloads(data_root)[-1]
    assert payload["terminal_result"] == "FAILED"
    assert "derived_current_verification_failed" in payload["diagnostics"]


def test_verified_download_exhaustion_sleeps_exactly_n_minus_1() -> None:
    from types import SimpleNamespace

    import pytest

    from test_integration_derivation import _verified_download

    calls = {"n": 0}

    def fake_get(url, timeout):
        calls["n"] += 1
        return SimpleNamespace(status_code=503, content=b"")

    sleeps = []
    with pytest.raises(AssertionError, match="after 4 attempts"):
        _verified_download(
            "https://data.binance.vision/data/futures/x.zip",
            retries=4,
            transport=fake_get,
            sleeper=sleeps.append,
        )
    assert calls["n"] == 4
    assert len(sleeps) == 3  # never sleeps after the final exhausted attempt


# --- final correction phase regressions (slices 1–4) ---------------------------
#
# Slice 1: PASS-only derived verification.
# Slice 2: JSON shape validation before use (parent and derived paths).
# Slice 3: early FAILED attempt evidence that never masks the primary result.
# Slice 4: milestone evidence truthful for the current invocation.


def _degrade_committed_derived_quality(data_root: Path) -> None:
    """Rewrite the committed derived quality evidence to a mutually consistent
    WARN_BLOCKED while keeping every digest pinned and every identity intact:
    only a PASS-only verification policy can reject this graph."""
    derived = _derived_dir(data_root)
    commit_dir = derived / "commits" / json.loads(
        (derived / "current.json").read_text()
    )["commit"]

    qpath = commit_dir / "quality.json"
    qdoc = json.loads(qpath.read_text())
    qdoc["state"] = "WARN_BLOCKED"
    qpath.write_bytes(
        (json.dumps(qdoc, indent=2, sort_keys=True) + "\n").encode()
    )

    mpath = commit_dir / "manifest.json"
    manifest = json.loads(mpath.read_text())
    manifest["quality_state"] = "WARN_BLOCKED"
    manifest_bytes = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode()
    mpath.write_bytes(manifest_bytes)

    pointer_path = derived / "current.json"
    pointer = json.loads(pointer_path.read_text())
    pointer["manifest_sha256"] = sha256_hex(manifest_bytes)
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")


def test_consistent_warn_blocked_graph_never_verifies_as_no_op(
    tmp_path: Path,
) -> None:
    """Slice 1: a fully self-consistent committed graph whose authenticated
    quality state is WARN_BLOCKED must be rejected — never honored as
    VERIFIED_NO_OP."""
    root, data_root, *_ = _valid_parent(tmp_path)
    descriptor = write_derived_descriptor(root, "1h")
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    _degrade_committed_derived_quality(data_root)

    attempts_before = {p.name for p in (data_root / "attempts").glob("*.json")}
    code = run_derivation_pipeline(descriptor, data_root, repo_root=root)
    assert code == 3  # rejected — never VERIFIED_NO_OP, never republished
    added = {
        p.name for p in (data_root / "attempts").glob("*.json")
    } - attempts_before
    payloads = [
        json.loads((data_root / "attempts" / name).read_text()) for name in added
    ]
    assert [p["terminal_result"] for p in payloads] == ["FAILED"]
    assert "derived_current_verification_failed" in payloads[0]["diagnostics"]


def test_non_object_derived_pointer_is_controlled_failure(
    tmp_path: Path,
) -> None:
    """Slice 2: derived current.json containing [] must produce a controlled
    FAILED exit with attempt evidence — never a raw AttributeError."""
    root, data_root, *_ = _valid_parent(tmp_path)
    descriptor = write_derived_descriptor(root, "1h")
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    derived = _derived_dir(data_root)
    (derived / "current.json").write_text("[]", encoding="utf-8")

    attempts_before = {p.name for p in (data_root / "attempts").glob("*.json")}
    code = run_derivation_pipeline(descriptor, data_root, repo_root=root)
    assert code == 3
    added = {
        p.name for p in (data_root / "attempts").glob("*.json")
    } - attempts_before
    payloads = [
        json.loads((data_root / "attempts" / name).read_text()) for name in added
    ]
    assert [p["terminal_result"] for p in payloads] == ["FAILED"]


def test_non_object_derived_manifest_is_controlled_failure(
    tmp_path: Path,
) -> None:
    """Slice 2: derived manifest.json containing [] must be rejected through
    the controlled failure path — never a raw AttributeError."""
    root, data_root, *_ = _valid_parent(tmp_path)
    descriptor = write_derived_descriptor(root, "1h")
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    derived = _derived_dir(data_root)
    commit_dir = derived / "commits" / json.loads(
        (derived / "current.json").read_text()
    )["commit"]
    (commit_dir / "manifest.json").write_bytes(b"[]\n")
    pointer_path = derived / "current.json"
    pointer = json.loads(pointer_path.read_text())
    pointer["manifest_sha256"] = sha256_hex(b"[]\n")
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")

    code = run_derivation_pipeline(descriptor, data_root, repo_root=root)
    assert code == 3
    payloads = _attempt_payloads(data_root)
    assert payloads[-1]["terminal_result"] == "FAILED"


def test_non_object_parent_content_json_blocks(tmp_path: Path) -> None:
    """Slice 2: parent content.json containing [] blocks as
    parent_dataset_unavailable — never a raw AttributeError/TypeError."""
    root, data_root, *_ = _valid_parent(tmp_path)
    content_path = (
        _parent_dir(data_root) / "commits" / _pointer_commit(data_root)
        / "content.json"
    )
    content_path.write_bytes(b"[]\n")
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")
    assert not _derived_dir(data_root).exists()


def test_non_object_parent_manifest_blocks(tmp_path: Path) -> None:
    """Slice 2: syntactically valid non-object parent manifest.json blocks as
    parent_dataset_unavailable — never a raw AttributeError."""
    root, data_root, *_ = _valid_parent(tmp_path)
    manifest_path = (
        _parent_dir(data_root) / "commits" / _pointer_commit(data_root)
        / "manifest.json"
    )
    manifest_path.write_bytes(b"[]\n")
    pointer_path = _parent_dir(data_root) / "current.json"
    pointer = json.loads(pointer_path.read_text())
    pointer["manifest_sha256"] = sha256_hex(b"[]\n")
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")


def test_non_mapping_parent_object_ref_blocks(tmp_path: Path) -> None:
    """Slice 2 (inspection finding): a content.json object_refs entry that is
    not a {kind, sha256} mapping blocks as parent_dataset_unavailable —
    never a raw TypeError."""
    root, data_root, *_ = _valid_parent(tmp_path)
    content_path = (
        _parent_dir(data_root) / "commits" / _pointer_commit(data_root)
        / "content.json"
    )
    content = json.loads(content_path.read_text())
    content["object_refs"] = ["not-a-mapping"]
    content_path.write_text(json.dumps(content) + "\n", encoding="utf-8")
    _assert_blocked_with(root, data_root, "parent_dataset_unavailable")
    assert not _derived_dir(data_root).exists()


def test_invalid_descriptor_writes_failed_attempt_evidence(
    tmp_path: Path,
) -> None:
    """Slice 3: an invalid descriptor records accurate FAILED attempt
    evidence when the attempt store is writable."""
    root, data_root = _setup(tmp_path)
    bad = root / "configs" / "datasets" / "broken.yaml"
    bad.write_text("::: [not: yaml:\n  - x", encoding="utf-8")
    code = run_derivation_pipeline(bad, data_root, repo_root=root)
    assert code == 3
    payloads = _attempt_payloads(data_root)
    assert len(payloads) == 1
    assert payloads[0]["terminal_result"] == "FAILED"
    assert payloads[0]["diagnostics"] == ["invalid_descriptor"]
    assert payloads[0]["artifact_dispositions"]["normalized_parquet"] == (
        "not_written"
    )


def test_rights_record_failure_writes_failed_attempt_evidence(
    tmp_path: Path,
) -> None:
    """Slice 3: a rights-record loading failure records accurate FAILED
    attempt evidence when the attempt store is writable."""
    root, data_root, *_ = _valid_parent(tmp_path)
    legal = root / "configs" / "legal" / "binance-usdm-provider-rights.v1.yaml"
    legal.write_bytes(b"::: [broken: yaml\n")
    descriptor = write_derived_descriptor(root, "1h")
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 3
    payloads = _attempt_payloads(data_root)
    assert len(payloads) == 1
    assert payloads[0]["terminal_result"] == "FAILED"
    assert payloads[0]["diagnostics"] == ["rights_record_unavailable"]
    assert payloads[0]["artifact_dispositions"]["normalized_parquet"] == (
        "not_written"
    )


def test_early_evidence_write_failure_does_not_mask_primary_result(
    tmp_path, monkeypatch, capsys
) -> None:
    """Slice 3: when recording the early FAILED evidence itself faults, the
    primary terminal result still stands."""
    root, data_root = _setup(tmp_path)
    bad = root / "configs" / "datasets" / "broken.yaml"
    bad.write_text("::: [not: yaml:\n  - x", encoding="utf-8")

    import quantara.derive_pipeline as dp

    def refuse(path, payload):
        raise OSError("injected early-evidence failure")

    monkeypatch.setattr(dp, "write_json", refuse)
    code = run_derivation_pipeline(bad, data_root, repo_root=root)
    assert code == 3
    captured = capsys.readouterr()
    assert "attempt manifest" in (captured.err + captured.out)


def test_verified_no_op_milestones_are_truthful(tmp_path: Path) -> None:
    """Slice 4: VERIFIED_NO_OP must describe this invocation — it staged,
    wrote the deduplicated object, verified the retained graph, and cleaned
    up; it did NOT rename any commit or replace any pointer."""
    root, data_root, *_ = _valid_parent(tmp_path)
    descriptor = write_derived_descriptor(root, "1h")
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    pointer_before = (_derived_dir(data_root) / "current.json").read_bytes()

    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    assert (_derived_dir(data_root) / "current.json").read_bytes() == (
        pointer_before
    )

    noop = [
        p for p in _attempt_payloads(data_root)
        if p["terminal_result"] == "VERIFIED_NO_OP"
    ]
    assert len(noop) == 1
    dispositions = noop[0]["artifact_dispositions"]
    assert dispositions["normalized_parquet"] == "already_published"
    assert dispositions["attempt_staged"] is True
    assert dispositions["object_written"] is True
    assert dispositions["commit_renamed"] is False
    assert dispositions["pointer_replaced"] is False
    assert dispositions["discovery_verified"] is True
    assert dispositions["attempt_staging"] == "discarded"


def test_published_attempt_records_true_milestones(tmp_path: Path) -> None:
    """Slice 4: PUBLISHED evidence records every action that actually
    occurred during this invocation."""
    root, data_root, *_ = _valid_parent(tmp_path)
    descriptor = write_derived_descriptor(root, "1h")
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    payload = _attempt_payloads(data_root)[-1]
    assert payload["terminal_result"] == "PUBLISHED"
    dispositions = payload["artifact_dispositions"]
    assert dispositions["normalized_parquet"] == "published"
    for key in (
        "attempt_staged",
        "object_written",
        "commit_renamed",
        "pointer_replaced",
        "discovery_verified",
    ):
        assert dispositions[key] is True, key
    assert dispositions["attempt_staging"] == "discarded"
    assert "post_pointer" not in dispositions


def test_cleanup_failure_is_reported_accurately(tmp_path, monkeypatch) -> None:
    """Slice 4: staging may only be reported as discarded when cleanup
    succeeded; the primary BLOCKED result is unaffected by the cleanup
    fault."""
    import shutil as _shutil

    import quantara.derive_pipeline as dp

    root, data_root, *_ = _valid_parent(tmp_path)
    descriptor = write_derived_descriptor(root, "1h")
    _force_quality_failure(monkeypatch)

    real_rmtree = _shutil.rmtree
    data_prefix = str(data_root)

    def refusing_rmtree(path, *args, **kwargs):
        if str(path).startswith(data_prefix):
            raise OSError("injected cleanup failure")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(dp.shutil, "rmtree", refusing_rmtree)
    code = run_derivation_pipeline(descriptor, data_root, repo_root=root)
    assert code == 2  # primary result unaffected
    payload = _attempt_payloads(data_root)[-1]
    assert payload["terminal_result"] == "BLOCKED"
    assert payload["artifact_dispositions"]["attempt_staging"] == (
        "cleanup_failed"
    )
