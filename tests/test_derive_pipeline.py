"""Derivation pipeline tests (plan Tasks 4–6).

Sections:
- Task 4: schema-fingerprint parameterization regression proofs.
- Task 5: publication idempotency-evidence key extension.
- Task 6: offline lineage-bound derivation orchestration.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import httpx
import pytest

from conftest import (
    HOUR_MS,
    MONTH_OPEN_START,
    build_month_minute_rows,
    derived_cfg_tree,
    write_derived_descriptor,
)
from quantara.hashing import SCHEMA_VERSION, schema_fingerprint, sha256_hex
from quantara.pipeline import run_pipeline
from quantara.publication import (
    existing_commit_matches,
    publish_commit,
    put_object,
    stage_commit,
    write_current,
)

# --- Task 4: schema fingerprint parameterization ------------------------------

FROZEN_SLICE_001_FINGERPRINT = (
    "feab7d2bb40de94e3621d6ff9847363eddd52b7fd8cd3c07f66def664da614c8"
)


def test_no_argument_fingerprint_is_byte_identical_to_slice_001() -> None:
    # Regression anchor frozen pre-edit at HEAD 7e17ca8 (plan Task 4) and
    # independently captured in %TEMP%\quantara-slice-002 before any edit.
    assert schema_fingerprint() == FROZEN_SLICE_001_FINGERPRINT


def test_explicit_1m_version_equals_default_behavior() -> None:
    assert schema_fingerprint(SCHEMA_VERSION) == FROZEN_SLICE_001_FINGERPRINT


def test_parent_fingerprint_preserves_v1_and_binds_v2_months() -> None:
    from quantara.derive_pipeline import _parent_schema_fingerprint
    from quantara.descriptor import load_descriptor

    repo_root = Path(__file__).resolve().parents[1]
    jan = load_descriptor(
        repo_root / "configs/datasets/binance-usdm-btcusdt-1m-2024-01.yaml"
    )
    q1 = load_descriptor(
        repo_root / "configs/datasets/binance-usdm-btcusdt-1m-2024-q1.yaml"
    )

    assert _parent_schema_fingerprint(jan) == FROZEN_SLICE_001_FINGERPRINT
    assert _parent_schema_fingerprint(q1) == schema_fingerprint(
        q1.schema_version, months=("2024-01", "2024-02", "2024-03")
    )
    assert _parent_schema_fingerprint(q1) != FROZEN_SLICE_001_FINGERPRINT


def test_distinct_timeframe_versions_produce_distinct_fingerprints() -> None:
    one_m = schema_fingerprint("binance_usdm_kline_1m_v1")
    one_h = schema_fingerprint("binance_usdm_kline_1h_v1")
    one_d = schema_fingerprint("binance_usdm_kline_1d_v1")
    assert len({one_m, one_h, one_d}) == 3


def test_logical_change_produces_identity_change() -> None:
    base = schema_fingerprint("binance_usdm_kline_1h_v1")
    assert schema_fingerprint("binance_usdm_kline_1h_v2") != base


# --- Task 5: publication idempotency-evidence key extension -------------------




def _build_commit(tmp_path: Path) -> tuple:
    data_root = tmp_path / "data"
    dataset_dir = data_root / "datasets" / "x" / "1h" / "year=2024" / "month=01"
    payload = b"parquet-bytes"
    digest = hashlib.sha256(payload).hexdigest()
    put_object(data_root, "normalized", payload)
    evidence = {
        "descriptor_sha256": "d" * 64,
        "schema_fingerprint": "f" * 64,
        "canonical_content_hash": "c" * 64,
        "quality_identity": "q",
        "object_refs": [{"kind": "normalized", "sha256": digest}],
        "derived_from": {"parent": "p" * 64},
    }
    content = {
        **evidence,
        "object_refs": evidence["object_refs"],
    }
    files = {
        "content.json": (json.dumps(content) + "\n").encode(),
    }
    staging = stage_commit(dataset_dir, "attempt-5", files)
    commit_dir = publish_commit(staging, dataset_dir / "commits", "c" * 64)
    write_current(dataset_dir, "c" * 64, "m" * 64)
    return data_root, dataset_dir, commit_dir, evidence


def test_default_keys_preserve_current_behavior(tmp_path: Path) -> None:
    import inspect

    from quantara import publication

    source = inspect.getsource(publication.existing_commit_matches)
    # Default key set must be unchanged; derived_from only enters via keys=.
    assert '"derived_from"' not in source.split("keys is None")[0].split("keys = (")[0]
    data_root, dataset_dir, commit_dir, evidence = _build_commit(tmp_path)
    # Default call ignores the extra lineage key entirely.
    assert existing_commit_matches(data_root, commit_dir, evidence) is True
    tampered_lineage = {**evidence, "derived_from": {"parent": "0" * 64}}
    assert existing_commit_matches(data_root, commit_dir, tampered_lineage) is True


def test_extended_keys_match_on_lineage_block(tmp_path: Path) -> None:
    data_root, dataset_dir, commit_dir, evidence = _build_commit(tmp_path)
    keys = (
        "descriptor_sha256",
        "schema_fingerprint",
        "canonical_content_hash",
        "quality_identity",
        "object_refs",
        "derived_from",
    )
    assert existing_commit_matches(
        data_root, commit_dir, evidence, keys=keys
    ) is True
    tampered = {**evidence, "derived_from": {"parent": "0" * 64}}
    assert existing_commit_matches(
        data_root, commit_dir, tampered, keys=keys
    ) is False




def _publish_parent_via_slice_001(tmp_path: Path):
    """Publish the synthetic 44,640-row month through the real pipeline."""
    root = derived_cfg_tree(tmp_path)
    csv_lines = [
        "open_time,open,high,low,close,volume,close_time,"
        "quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore\n"
    ]
    for i in range(44_640):
        t = MONTH_OPEN_START + i * 60_000
        csv_lines.append(
            f"{t},42571.90,42600.00,42500.10,42590.50,12.5,"
            f"{t + 59_999},500000.25,3210,6.25,250000.125,0\n"
        )
    archive = tmp_path / "BTCUSDT-1m-2024-01.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("BTCUSDT-1m-2024-01.csv", "".join(csv_lines))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".CHECKSUM"):
            return httpx.Response(200, text=f"{digest}  BTCUSDT-1m-2024-01.zip\n")
        return httpx.Response(200, content=archive.read_bytes())

    base_descriptor = (
        tmp_path / "configs" / "datasets" / "binance-usdm-btcusdt-1m-2024-01.yaml"
    )
    code = run_pipeline(
        descriptor_path=base_descriptor,
        data_root=tmp_path / "data",
        repo_root=root,
        transport=httpx.MockTransport(handler),
    )
    assert code == 0
    return root, tmp_path / "data"


def _parent_commit_hash(data_root: Path) -> str:
    pointer = _derived_dataset_dir(data_root, "1m") / "current.json"
    return json.loads(pointer.read_text())["commit"]


def _derived_dataset_dir(data_root: Path, interval: str) -> Path:
    return (
        data_root / "datasets" / "binance" / "usdm" / "klines" / "BTCUSDT"
        / interval / "year=2024" / "month=01"
    )


def test_offline_end_to_end_derive_both_timeframes_then_no_op(tmp_path: Path) -> None:
    from quantara.derive_pipeline import run_derivation_pipeline

    root, data_root = _publish_parent_via_slice_001(tmp_path)
    parent_hash = _parent_commit_hash(data_root)

    pointers = {}
    for interval, expected_rows in (("1h", 744), ("1d", 31)):
        descriptor = write_derived_descriptor(root, interval)
        assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
        dataset_dir = _derived_dataset_dir(data_root, interval)
        pointer_before = (dataset_dir / "current.json").read_bytes()
        pointers[interval] = pointer_before
        commit = json.loads(pointer_before)["commit"]
        manifest = json.loads(
            (dataset_dir / "commits" / commit / "manifest.json").read_text()
        )
        quality = json.loads(
            (dataset_dir / "commits" / commit / "quality.json").read_text()
        )
        assert manifest["canonical_row_count"] == expected_rows
        assert quality["state"] == "PASS"
        lineage = manifest["derived_from"]
        assert lineage["parent_dataset_id"] == (
            "binance_usdm_btcusdt_klines_1m_2024_01"
        )
        assert lineage["parent_canonical_content_hash"] == parent_hash
        assert lineage["transformation"]["timeframe_ms"] == (
            HOUR_MS if interval == "1h" else 86_400_000
        )

    # Rerun both: VERIFIED_NO_OP; commits and pointers byte-identical.
    for interval in ("1h", "1d"):
        descriptor = write_derived_descriptor(root, interval)
        assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
        dataset_dir = _derived_dataset_dir(data_root, interval)
        assert (dataset_dir / "current.json").read_bytes() == pointers[interval]
        commits = [
            p for p in (dataset_dir / "commits").iterdir()
            if not p.name.startswith(".")
        ]
        assert len(commits) == 1


def test_dry_run_verifies_descriptor_and_parent_without_mutation(tmp_path: Path) -> None:
    from quantara.derive_pipeline import run_derivation_pipeline

    root, data_root = _publish_parent_via_slice_001(tmp_path)
    descriptor = write_derived_descriptor(root, "1h")
    derived_dir = _derived_dataset_dir(data_root, "1h")
    assert (
        run_derivation_pipeline(descriptor, data_root, dry_run=True, repo_root=root)
        == 0
    )
    assert not derived_dir.exists()


def test_missing_parent_blocks_with_stable_diagnostic(tmp_path: Path) -> None:
    from quantara.derive_pipeline import run_derivation_pipeline

    root = derived_cfg_tree(tmp_path)
    data_root = tmp_path / "data"
    descriptor = write_derived_descriptor(root, "1h")
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 2
    attempts = list((data_root / "attempts").glob("*.json"))
    assert len(attempts) == 1
    attempt = json.loads(attempts[0].read_text())
    assert attempt["terminal_result"] == "BLOCKED"
    assert attempt["diagnostics"] == ["parent_dataset_unavailable"]


def test_minimal_parent_graph_via_publication_primitives(tmp_path: Path) -> None:
    """Fast path: assemble a fully GENUINE parent graph directly through the
    publication primitives (real descriptor hash, fingerprint, canonical
    content hash and manifest digest), derive 1d, and prove idempotent rerun."""
    from quantara.canonical import (
        read_canonical_rows,
        reconcile_rows,
        write_canonical_parquet,
    )
    from quantara.derive_pipeline import run_derivation_pipeline
    from quantara.descriptor import load_descriptor
    from quantara.hashing import canonical_content_hash, descriptor_hash
    from quantara.manifests import PARSER_VERSION
    from quantara.publication import put_object

    root = derived_cfg_tree(tmp_path)
    data_root = tmp_path / "data"
    rows = build_month_minute_rows()
    staging = data_root / "staging" / "manual-parent"
    staging.mkdir(parents=True)
    parquet_path = staging / "canonical.parquet"
    write_canonical_parquet(rows, parquet_path)
    persisted = read_canonical_rows(parquet_path)
    reconcile_rows(rows, persisted)
    parquet_bytes = parquet_path.read_bytes()
    parquet_sha = sha256_hex(parquet_bytes)
    normalized_ref = put_object(data_root, "normalized", parquet_bytes)
    assert normalized_ref == parquet_sha

    from quantara.quality import evaluate_quality

    base = load_descriptor(
        root / "configs" / "datasets" / "binance-usdm-btcusdt-1m-2024-01.yaml"
    )
    fingerprint = schema_fingerprint(base.schema_version)
    parent_cch = canonical_content_hash(
        fingerprint, [row.to_content_array() for row in rows]
    )
    report = evaluate_quality(
        rows, base, source_order_valid=True,
        expected_count=base.expected_row_count,
    )
    assert report.state == "PASS"
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

    parent_dir = _derived_dataset_dir(data_root, "1m")
    manifest_dict = {
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
        "canonical_content_hash": parent_cch,
        "parquet_sha256": parquet_sha,
        "parquet_size": len(parquet_bytes),
        "object_refs": [{"kind": "normalized", "sha256": parquet_sha}],
    }
    manifest_bytes = (
        json.dumps(manifest_dict, indent=2, sort_keys=True) + "\n"
    ).encode()
    content = {
        "descriptor_sha256": descriptor_hash(base.canonical_semantics()),
        "schema_fingerprint": fingerprint,
        "parser_version": PARSER_VERSION,
        "canonical_content_hash": parent_cch,
        "quality_identity": identity,
        "object_refs": [{"kind": "normalized", "sha256": parquet_sha}],
    }
    files = {
        "content.json": (json.dumps(content) + "\n").encode(),
        "manifest.json": manifest_bytes,
        "quality.json": (
            json.dumps(quality_doc, indent=2, sort_keys=True) + "\n"
        ).encode(),
    }
    staged = stage_commit(parent_dir, "manual", files)
    publish_commit(staged, parent_dir / "commits", parent_cch)
    write_current(parent_dir, parent_cch, sha256_hex(manifest_bytes))

    descriptor = write_derived_descriptor(root, "1d")
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    dataset_dir = _derived_dataset_dir(data_root, "1d")
    pointer = (dataset_dir / "current.json").read_bytes()
    commit = json.loads(pointer)["commit"]

    # Lineage binds to the exact parent commit and parquet bytes.
    derived_content = json.loads(
        (dataset_dir / "commits" / commit / "content.json").read_text()
    )
    assert derived_content["derived_from"]["parent_parquet_sha256"] == parquet_sha
    assert (
        derived_content["derived_from"]["parent_canonical_content_hash"]
        == parent_cch
    )

    # Idempotent rerun leaves bytes untouched.
    assert run_derivation_pipeline(descriptor, data_root, repo_root=root) == 0
    assert (dataset_dir / "current.json").read_bytes() == pointer


_PARENT_CACHE: dict = {}


def _get_parent_cache_data(base):
    key = (base.dataset_id, base.expected_row_count)
    if key not in _PARENT_CACHE:
        from decimal import Decimal

        from quantara.canonical import (
            CanonicalRow,
            read_canonical_rows,
            reconcile_rows,
            write_canonical_parquet,
        )
        from quantara.hashing import canonical_content_hash
        from quantara.quality import evaluate_quality

        identity = (
            base.provider,
            base.market_type,
            base.instrument_id,
            base.provider_symbol,
            base.base_asset,
            base.quote_asset,
            base.settlement_asset,
            base.contract_type,
            base.interval,
            base.schema_version,
        )
        t_start = 1704067200000
        canonical_rows = []
        d_zero = Decimal("0")
        d_ten = Decimal("10")
        d_open = Decimal("42000")
        d_high = Decimal("42100")
        d_low = Decimal("41900")
        d_close = Decimal("42050")
        d_qvol = Decimal("420000")

        n_rows = base.expected_row_count
        for i in range(n_rows):
            t = t_start + i * 60_000
            is_zero = (i < 89)
            canonical_rows.append(
                CanonicalRow(
                    identity=identity,
                    open_time_ms=t,
                    close_time_ms=t + 59_999,
                    nominal_available_ms=t + 60_000,
                    open=d_open,
                    high=d_high,
                    low=d_low,
                    close=d_close,
                    base_asset_volume=d_zero if is_zero else d_ten,
                    quote_asset_volume=d_zero if is_zero else d_qvol,
                    trade_count=0 if is_zero else 100,
                    taker_buy_base_volume=d_zero if is_zero else d_ten,
                    taker_buy_quote_volume=d_zero if is_zero else d_qvol,
                    source_ignore="0",
                )
            )

        import tempfile
        tmp_pq = Path(tempfile.mkdtemp()) / "canonical.parquet"
        write_canonical_parquet(canonical_rows, tmp_pq)
        persisted = read_canonical_rows(tmp_pq)
        reconcile_rows(canonical_rows, persisted)
        parquet_bytes = tmp_pq.read_bytes()
        parquet_sha = sha256_hex(parquet_bytes)
        tmp_pq.unlink()

        from quantara.derive_pipeline import _parent_schema_fingerprint

        fingerprint = _parent_schema_fingerprint(base)
        parent_cch = canonical_content_hash(
            fingerprint, [row.to_content_array() for row in canonical_rows]
        )
        report = evaluate_quality(
            canonical_rows,
            base,
            source_order_valid=True,
            expected_count=base.expected_row_count,
        )
        identity_str = report.identity()
        identity_sha = sha256_hex(identity_str.encode("utf-8"))
        _PARENT_CACHE[key] = (
            parquet_bytes,
            parquet_sha,
            fingerprint,
            parent_cch,
            report,
            identity_str,
            identity_sha,
        )
    return _PARENT_CACHE[key]


def _setup_test_parent_commit(
    tmp_path: Path,
    *,
    policy: str = "2",
    quality_state: str = "WARN_APPROVED",
    with_approval: bool = True,
    corrupt_approval: bool = False,
    stale_approval: bool = False,
) -> tuple[Path, Path, object]:
    from quantara.descriptor import load_descriptor
    from quantara.hashing import descriptor_hash
    from quantara.jcs import canonicalize
    from quantara.manifests import PARSER_VERSION
    from quantara.publication import put_object
    from quantara.quality_approval import APPROVAL_SCHEMA, canonical_finding_sha256

    root = derived_cfg_tree(tmp_path)
    data_root = tmp_path / "data"

    if policy == "2":
        base_src = Path("configs/datasets/binance-usdm-btcusdt-1m-2024.yaml")
        base_desc_path = root / "configs" / "datasets" / "binance-usdm-btcusdt-1m-2024.yaml"
    else:
        base_src = Path("configs/datasets/binance-usdm-btcusdt-1m-2024-01.yaml")
        base_desc_path = root / "configs" / "datasets" / "binance-usdm-btcusdt-1m-2024-01.yaml"
    base_desc_path.write_text(base_src.read_text(encoding="utf-8"), encoding="utf-8")
    base = load_descriptor(base_desc_path)

    legal_dir = root / "configs" / "legal"
    legal_dir.mkdir(parents=True, exist_ok=True)
    rights_text = Path("configs/legal/binance-usdm-provider-rights.v2.yaml").read_text(
        encoding="utf-8"
    )
    (legal_dir / "binance-usdm-provider-rights.v2.yaml").write_text(
        rights_text, encoding="utf-8"
    )
    rights_v1_text = Path("configs/legal/binance-usdm-provider-rights.v1.yaml").read_text(
        encoding="utf-8"
    )
    (legal_dir / "binance-usdm-provider-rights.v1.yaml").write_text(
        rights_v1_text, encoding="utf-8"
    )

    (
        parquet_bytes,
        parquet_sha,
        fingerprint,
        parent_cch,
        report,
        identity,
        identity_sha,
    ) = _get_parent_cache_data(base)

    put_object(data_root, "normalized", parquet_bytes)

    warn_finding = [f for f in report.findings if f.outcome == "warn"][0]
    finding_sha = canonical_finding_sha256(warn_finding)
    source_digests = ["a" * 64 for _ in getattr(base, "months", ["2024-01"])]

    approval_payload = {
        "schema": APPROVAL_SCHEMA,
        "record_id": "binance-usdm-btcusdt-1m-2024-zero-volume-v1",
        "dataset_id": base.dataset_id,
        "canonical_content_hash": "f" * 64 if stale_approval else parent_cch,
        "schema_fingerprint": fingerprint,
        "source_sha256": source_digests,
        "quality_policy_version": "2",
        "quality_identity_sha256": identity_sha,
        "approved_findings": [
            {
                "check_id": warn_finding.check_id,
                "count": warn_finding.count,
                "canonical_finding_sha256": finding_sha,
            }
        ],
        "approver": "258711354+wyze69-sys@users.noreply.github.com",
        "decision_time_utc": "2026-08-28T07:07:38Z",
        "rationale": "test fixture",
        "scope": "test",
    }
    app_sha = (
        "bad" * 21 + "b"
        if corrupt_approval
        else sha256_hex(canonicalize(approval_payload).encode("utf-8"))
    )

    quality_doc = {
        "state": quality_state,
        "raw_state": "WARN_BLOCKED",
        "policy_version": policy,
        "identity": identity,
        "identity_sha256": identity_sha,
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
    if policy == "2" and quality_state == "WARN_APPROVED":
        quality_doc["approval_record_id"] = "binance-usdm-btcusdt-1m-2024-zero-volume-v1"
        quality_doc["approval_record_sha256"] = app_sha

    from quantara.derive_pipeline import _dataset_dir

    parent_dir = _dataset_dir(data_root, base.provider_symbol, "1m", base.start_utc)
    manifest_dict = {
        "dataset_id": base.dataset_id,
        "instrument_id": base.instrument_id,
        "schema_version": base.schema_version,
        "schema_fingerprint": fingerprint,
        "timestamp_semantics": base.timestamp_semantics,
        "quality_policy_version": policy,
        "quality_state": quality_state,
        "quality_identity": identity,
        "source_row_count": base.expected_row_count,
        "canonical_row_count": base.expected_row_count,
        "canonical_content_hash": parent_cch,
        "local_zip_sha256": source_digests,
        "parquet_sha256": parquet_sha,
        "parquet_size": len(parquet_bytes),
        "object_refs": [{"kind": "normalized", "sha256": parquet_sha}],
    }
    if policy == "2":
        manifest_dict["quality_raw_state"] = "WARN_BLOCKED"
        manifest_dict["quality_identity_sha256"] = identity_sha
        if quality_state == "WARN_APPROVED":
            manifest_dict["quality_approval_record_id"] = (
                "binance-usdm-btcusdt-1m-2024-zero-volume-v1"
            )
            manifest_dict["quality_approval_record_sha256"] = app_sha

    manifest_bytes = (json.dumps(manifest_dict, indent=2, sort_keys=True) + "\n").encode()
    content = {
        "descriptor_sha256": descriptor_hash(base.canonical_semantics()),
        "schema_fingerprint": fingerprint,
        "parser_version": PARSER_VERSION,
        "canonical_content_hash": parent_cch,
        "quality_identity": identity,
        "quality_state": quality_state,
        "object_refs": [{"kind": "normalized", "sha256": parquet_sha}],
    }
    files = {
        "content.json": (json.dumps(content) + "\n").encode(),
        "manifest.json": manifest_bytes,
        "quality.json": (json.dumps(quality_doc, indent=2, sort_keys=True) + "\n").encode(),
    }
    if with_approval and policy == "2":
        files["quality-approval.json"] = (
            json.dumps(approval_payload, indent=2, sort_keys=True) + "\n"
        ).encode()

    staged = stage_commit(parent_dir, f"manual-{policy}-{quality_state}", files)
    publish_commit(staged, parent_dir / "commits", parent_cch)
    write_current(parent_dir, parent_cch, sha256_hex(manifest_bytes))

    return parent_dir, data_root, base


def test_verify_parent_authenticates_policy_v2_warn_approved(tmp_path: Path) -> None:
    from quantara.derive_pipeline import _verify_parent

    parent_dir, data_root, base = _setup_test_parent_commit(
        tmp_path,
        policy="2",
        quality_state="WARN_APPROVED",
        with_approval=True,
    )
    parent_info = _verify_parent(parent_dir, data_root, base)
    assert parent_info["quality_state"] == "WARN_APPROVED"
    assert parent_info["quality_raw_state"] == "WARN_BLOCKED"
    assert (
        parent_info["quality_approval_record_id"]
        == "binance-usdm-btcusdt-1m-2024-zero-volume-v1"
    )


def test_verify_parent_rejects_unapproved_warn_blocked(tmp_path: Path) -> None:
    from quantara.derive_pipeline import _verify_parent
    from quantara.errors import QuantaraError

    parent_dir, data_root, base = _setup_test_parent_commit(
        tmp_path,
        policy="2",
        quality_state="WARN_BLOCKED",
        with_approval=False,
    )
    with pytest.raises(QuantaraError):
        _verify_parent(parent_dir, data_root, base)


def test_verify_parent_rejects_tampered_approval_self_hash(tmp_path: Path) -> None:
    from quantara.derive_pipeline import _verify_parent
    from quantara.errors import QuantaraError

    parent_dir, data_root, base = _setup_test_parent_commit(
        tmp_path,
        policy="2",
        quality_state="WARN_APPROVED",
        with_approval=True,
        corrupt_approval=True,
    )
    with pytest.raises(QuantaraError, match="self-hash mismatch"):
        _verify_parent(parent_dir, data_root, base)


def test_verify_parent_rejects_stale_approval_canonical_hash(tmp_path: Path) -> None:
    from quantara.derive_pipeline import _verify_parent
    from quantara.errors import QuantaraError

    parent_dir, data_root, base = _setup_test_parent_commit(
        tmp_path,
        policy="2",
        quality_state="WARN_APPROVED",
        with_approval=True,
        stale_approval=True,
    )
    with pytest.raises(QuantaraError, match="canonical_content_hash mismatch"):
        _verify_parent(parent_dir, data_root, base)


def test_verify_parent_rejects_policy_v1_warn_state(tmp_path: Path) -> None:
    from quantara.derive_pipeline import _verify_parent
    from quantara.errors import QuantaraError

    parent_dir, data_root, base = _setup_test_parent_commit(
        tmp_path,
        policy="1",
        quality_state="WARN_BLOCKED",
        with_approval=False,
    )
    with pytest.raises(QuantaraError, match="less-than-verified parent"):
        _verify_parent(parent_dir, data_root, base)


