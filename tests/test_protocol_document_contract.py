"""P00 contract test: freeze the documentary and machine-readable Protocol v1.

This test is deliberately independent of any production protocol loader
(``src/quantara/protocol.py`` does not exist yet and must never be imported
here). It uses PyYAML and the hand-authored literal expectations in
``tests/fixtures/protocol_v1_expected.json`` only.

Hermes P00 audit corrections encoded here:
- exact ordered 17-field canonical-record contract;
- fixed literal EXPECTED_SEMANTIC_SHA256 outside the mutable JSON fixture
  (the fixture's recorded hash must equal the same literal);
- normalized UTF-8/LF SHA-256 pin of the reviewed human-readable spec;
- exact literal sealed-2025 and fold expectations (no vocabulary scanning);
- exact inventory IDs, feature-formula keys, model ladder, and exclusions,
  with normalized forbidden-scope aliases;
- all eight A7-A10 references bound to normalized UTF-8/LF content via a fixed
  path -> SHA-256 literal mapping, in both YAML and MD.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "docs" / "superpowers" / "specs" / "2026-08-31-quantara-protocol-v1.md"
YAML_PATH = REPO_ROOT / "configs" / "protocols" / "quantara-protocol-v1.yaml"
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "protocol_v1_expected.json"

# Frozen semantic SHA-256 of the canonicalized Protocol-v1 semantics. This
# literal lives OUTSIDE the mutable JSON fixture and is never derived at test
# runtime from the YAML or the fixture.
EXPECTED_SEMANTIC_SHA256 = "91457d3f1497abfd4e20cf4624768a5d9e9ba4b4478008fb4c7f65c17d90c65a"

# Frozen SHA-256 of the reviewed human-readable specification after
# normalization: UTF-8 decode, CRLF/CR folded to LF, UTF-8 re-encode. Any
# material MD edit changes this digest even if required substrings survive.
EXPECTED_SPEC_SHA256 = "9aaa9d76557d76ced7a5c0cff20a02dbb7f735f555a8e696c3289dfe3963ec68"

AUDIT_REFERENCE_HASH_BASIS = "utf8_text_normalized_to_lf_before_sha256"

# Exact ordered canonical-record field contract (plan section 4.4).
CANONICAL_RECORD_FIELDS = [
    "provider",
    "venue",
    "market_type",
    "instrument_id",
    "provider_symbol",
    "series_id",
    "native_interval",
    "source_file",
    "source_sha256",
    "event_ts",
    "interval_open_ts",
    "interval_close_ts",
    "settlement_or_snapshot_ts",
    "archive_publication_ts",
    "ingestion_ts",
    "eligibility_ts",
    "quality_flags",
]

EXPECTED_INVENTORY_IDS = [
    "btcusdt_perp_ohlcv",
    "btc_settled_funding",
    "btc_open_interest_5m",
    "btc_mark_price_1m",
    "btc_index_price_1m",
    "btc_native_premium_1m",
    "binance_btc_spot_ohlcv_1m",
    "kraken_xbtusd_spot_ohlcv_1h",
    "ethusdt_perp_ohlcv_1m",
    "eth_settled_funding",
    "eth_open_interest_5m",
    "eth_mark_price_1m",
    "eth_index_price_1m",
    "eth_native_premium_1m",
]

EXPECTED_FEATURE_FORMULA_KEYS = [
    "funding_24h_sum",
    "dlog_oi_24h",
    "native_premium_1h_mean",
    "spot_perp_dislocation",
    "eth_ret_1h",
    "eth_rv_24h",
    "eth_funding_24h_sum",
    "eth_native_premium_1h_mean",
    "eth_btc_relative_ret_24h",
    "eth_dlog_oi_24h",
    "kraken_ret_1h",
    "kraken_rv_24h",
    "binance_kraken_ret_divergence_1h",
    "binance_kraken_cross_quote_log_ratio",
]

EXPECTED_MODEL_LADDER = {
    "B0": {"base": None, "adds": [], "definition": "training-only climatology"},
    "B1": {
        "base": None,
        "adds": ["log(RV_1d)"],
        "definition": "logistic model using causal log(RV_1d)",
    },
    "B2": {
        "base": None,
        "adds": ["log(RV_1d)", "log(RV_7d)", "log(RV_30d)"],
        "definition": "HAR-style logistic model",
    },
    "M1": {
        "base": "B2",
        "adds": ["funding_24h_sum", "dlog_oi_24h", "native_premium_1h_mean"],
        "definition": "B2 plus frozen BTC derivatives block",
    },
    "M2": {
        "base": "M1",
        "adds": ["spot_perp_dislocation"],
        "definition": "M1 plus BTC perpetual versus Binance spot dislocation",
    },
    "M3": {
        "base": "M2",
        "adds": [
            "eth_ret_1h",
            "eth_rv_24h",
            "eth_funding_24h_sum",
            "eth_native_premium_1h_mean",
            "eth_btc_relative_ret_24h",
        ],
        "definition": "M2 plus frozen ETH family, excluding ETH OI",
    },
    "M3b": {
        "base": "M3",
        "adds": ["eth_dlog_oi_24h"],
        "definition": "M3 plus ETH dlog_oi_24h on the identical post-2021-12-01 common sample",
    },
    "M4": {
        "base": "M3",
        "adds": [
            "kraken_ret_1h",
            "kraken_rv_24h",
            "binance_kraken_ret_divergence_1h",
            "binance_kraken_cross_quote_log_ratio",
        ],
        "definition": "M3 plus frozen Kraken cross-venue family",
    },
}

EXPECTED_EXCLUSION_FAMILIES = [
    "liquidations",
    "options",
    "long_short_ratios",
    "taker_ratios",
    "altcoins",
    "order_books",
    "macro",
    "on_chain",
    "sentiment",
    "news",
    "technical_indicator_searches",
]

EXPECTED_SEALED_2025 = {
    "state": "SEALED",
    "scoring_permission": "FORBIDDEN_UNTIL_GATE_PASS",
    "allowed_pre_gate_checks": [
        "file_inventory",
        "cryptographic_hashes",
        "parser_compatibility",
        "expected_boundaries",
        "mechanical_corruption",
    ],
    "forbidden_operations": [
        "labels",
        "feature_distributions",
        "model_scores",
        "conditional_outcome_inspection",
        "protocol_adaptation",
    ],
    "on_gate_pass": "run exactly one frozen 2025 evaluation",
    "failure_outcome": "DID_NOT_REPLICATE",
    "failure_rule": "never redesign and retest on 2025",
}

EXPECTED_OUTER_FOLDS = [
    {"fold": 1, "train_start": "2020-09-01", "train_end": "2021-12-31", "test_year": 2022},
    {"fold": 2, "train_start": "2020-09-01", "train_end": "2022-12-31", "test_year": 2023},
    {"fold": 3, "train_start": "2020-09-01", "train_end": "2023-12-31", "test_year": 2024},
]

# Fixed path -> SHA-256 literal mapping for the eight A7-A10 audit references.
A7_A10_SHA256_REFS = {
    "a7_report": {
        "path": "docs/superpowers/plans/2026-08-31-a7-ethusdt-perpetual.md",
        "sha256": "379a70250630f1e914618eda33131f6d396535126cbedbde7955a4216e7b2f72",
        "md_row_label": "A7 report",
    },
    "a7_sidecar": {
        "path": "temp/audit_a7_a8/a7_ethusdt_probe_v1.json",
        "sha256": "3b3b6ea81b3e1d91a9c10140333b2e01ab39929ff9022d0573878defd043ff58",
        "md_row_label": "A7 sidecar",
    },
    "a8_report": {
        "path": "docs/superpowers/plans/2026-08-31-a8-btcusdt-spot.md",
        "sha256": "548ad0c2c6d766f49d5bb41de0fa1fecd0e928ec8939d253db5a1d31e55a9919",
        "md_row_label": "A8 report",
    },
    "a8_sidecar": {
        "path": "temp/audit_a7_a8/a8_btcusdt_spot_probe_v1.json",
        "sha256": "08f972fcbc9776d5a6cdc028a2d7523d24355887b204dddc2277a540c22a2c52",
        "md_row_label": "A8 sidecar",
    },
    "a9_report": {
        "path": "docs/superpowers/plans/2026-08-31-a9-second-btc-venue-kraken.md",
        "sha256": "225793a4723c1f55345084fe0a5be5c68273181798ce96ba61ac3283adaf5fb5",
        "md_row_label": "A9 report",
    },
    "a9_sidecar": {
        "path": "temp/audit_a9_kraken/a9_kraken_range_probe_v1.json",
        "sha256": "808c1a17c0b710187c36254c31992d2b645cc2533b7fec4b4c0d05b7d42f7c14",
        "md_row_label": "A9 sidecar",
    },
    "a10_report": {
        "path": "docs/superpowers/plans/2026-08-31-a10-live-acquisition-consolidation.md",
        "sha256": "61881d940dca4810293b487cb172427fc5c18d1936724ba28939eabc4a88e9ee",
        "md_row_label": "A10 report",
    },
    "a10_sidecar": {
        "path": "temp/audit_a10_corrections/a3a4_reprobe_v2.json",
        "sha256": "621c5781df4d94810dbfc2fa61f9a78767f6b735ed9d42c421d2cfc5e10cfe86",
        "md_row_label": "A10 sidecar",
    },
}

# Forbidden Protocol-v1 families per plan section 3.3, with normalized aliases
# (top_trader, top-trader, orderbook, order_book, long-short, long_short).
# These tokens must never appear outside the exclusions section itself.
FORBIDDEN_FAMILY_TOKENS = (
    "liquidation",
    "options",
    "long_short",
    "long-short",
    "top_trader",
    "top-trader",
    "taker",
    "altcoin",
    "order_book",
    "orderbook",
    "macro",
    "on_chain",
    "onchain",
    "sentiment",
    "news",
    "technical_indicator",
)

REQUIRED_SPEC_SUBSTRINGS = (
    # Status freeze marker.
    "FROZEN_BEFORE_2022_2024_SCORING",
    # Research question.
    "probability forecasts of unusually large BTCUSDT 24-hour moves",
    # Target definition.
    "r24_t  = log(P[t+24h] / P[t])",
    "empirical Q80(Z_t) on eligible 2020-2021 design origins",
    "No 2022 value may enter threshold design",
    # Ladder.
    "B0",
    "B1",
    "B2",
    "M1",
    "M2",
    "M3",
    "M3b",
    "M4",
    "RV_H = sqrt(sum of squared eligible hourly log returns over H hours)",
    # Logistic constants.
    "lambda = 1",
    "max_iterations = 50",
    "0.000000000001",
    "eta clamp 24",
    "Gaussian elimination with partial pivoting",
    # No-search / no-calibration rules.
    "no regularization search",
    "no post-hoc probability calibration",
    # Point-in-time.
    "prediction_ts = T + 1 ms",
    "eligibility_ts < prediction_ts",
    "backward as-of joins on eligibility_ts",
    "nominal historical point-in-time safety, not reconstruction of historical",
    # Missing / duplicate policy.
    "Missing is null, never zero",
    "Same-key conflicting rows block publication",
    "ETH OI before 2021-12-01 is null",
    # Validation.
    "train 2020-09-01..2021-12-31; test 2022",
    "train 2020-09-01..2022-12-31; test 2023",
    "train 2020-09-01..2023-12-31; test 2024",
    "24-hour purge",
    "168-hour blocks",
    "2,000 resamples",
    "20260831",
    # Gate and optional-family rule.
    "BSS_B2 >= 0.02",
    "Holm",
    "DID_NOT_REPLICATE",
    # Sealed 2025.
    "file inventory, cryptographic hashes, parser",
    # Dislocation roles.
    "pre-registered primary futures-dislocation feature",
    "diagnostics only and never enter M1-M4",
)


def _canonical_json(value: object) -> str:
    """Independent canonicalization used for the frozen semantic hash."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256_of_canonical(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _normalized_utf8_lf_sha256(path: Path) -> str:
    """SHA-256 after strict UTF-8 decode and CRLF/CR-to-LF normalization."""
    text = path.read_bytes().decode("utf-8")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _normalized_md_sha256(path: Path) -> str:
    return _normalized_utf8_lf_sha256(path)


@pytest.fixture(scope="module")
def expected() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def protocol_yaml() -> dict:
    return yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def semantic(expected: dict, protocol_yaml: dict) -> dict:
    return {key: protocol_yaml[key] for key in expected["expected_top_level_keys"]}


def test_expected_files_exist() -> None:
    assert SPEC_PATH.is_file(), f"missing frozen spec document: {SPEC_PATH}"
    assert YAML_PATH.is_file(), f"missing frozen protocol YAML: {YAML_PATH}"
    assert FIXTURE_PATH.is_file(), f"missing expected fixture: {FIXTURE_PATH}"


def test_spec_document_normalized_sha256() -> None:
    assert _normalized_md_sha256(SPEC_PATH) == EXPECTED_SPEC_SHA256, (
        "the reviewed human-readable specification was materially edited; "
        "a new reviewed and pinned revision is required"
    )


def test_spec_document_contains_frozen_contract() -> None:
    spec_text = SPEC_PATH.read_text(encoding="utf-8")
    missing = [s for s in REQUIRED_SPEC_SUBSTRINGS if s not in spec_text]
    assert not missing, f"spec document missing required frozen content: {missing}"
    for label, ref in A7_A10_SHA256_REFS.items():
        assert ref["sha256"] in spec_text, f"spec document missing {label} SHA-256 {ref['sha256']}"


def test_spec_declares_final_semantic_hash() -> None:
    spec_text = SPEC_PATH.read_text(encoding="utf-8")
    match = re.search(
        r"## 10\. Frozen semantic hash.*?```text\s*([0-9a-f]{64})\s*```",
        spec_text,
        flags=re.DOTALL,
    )
    assert match is not None, "specification does not declare one frozen semantic SHA-256"
    assert match.group(1) == EXPECTED_SEMANTIC_SHA256, (
        "MD-declared semantic hash does not equal the fixed semantic literal"
    )


def test_yaml_top_level_keys_equal_fixture(expected: dict, protocol_yaml: dict) -> None:
    expected_keys = expected["expected_top_level_keys"]
    actual_keys = list(protocol_yaml.keys())
    assert set(actual_keys) == set(expected_keys), (
        f"top-level key mismatch: extra={set(actual_keys) - set(expected_keys)}, "
        f"missing={set(expected_keys) - set(actual_keys)}"
    )
    assert actual_keys == expected_keys, "top-level key order differs from frozen fixture"


def test_yaml_semantic_matches_independent_fixture(expected: dict, semantic: dict) -> None:
    assert semantic == expected["expected_semantic"], (
        "machine-readable protocol diverges from the independently rendered "
        "expected semantic fixture"
    )


def test_yaml_semantic_sha256_equals_fixed_literal(semantic: dict) -> None:
    assert _sha256_of_canonical(semantic) == EXPECTED_SEMANTIC_SHA256, (
        "canonicalized YAML semantics do not equal the fixed frozen literal"
    )


def test_fixture_semantic_sha256_equals_fixed_literal(expected: dict) -> None:
    assert _sha256_of_canonical(expected["expected_semantic"]) == EXPECTED_SEMANTIC_SHA256, (
        "canonicalized fixture semantics do not equal the fixed frozen literal"
    )
    assert expected["semantic_sha256"] == EXPECTED_SEMANTIC_SHA256, (
        "fixture's recorded semantic hash does not equal the fixed frozen literal"
    )


def test_canonical_record_fields_exact_ordered(semantic: dict) -> None:
    fields = semantic["canonical_record_fields"]
    assert isinstance(fields, list)
    assert len(fields) == 17, f"expected exactly 17 canonical-record fields, got {len(fields)}"
    assert fields == CANONICAL_RECORD_FIELDS, (
        "canonical-record field contract diverges from the frozen ordered 17-field list"
    )


def test_immutability_cross_quote_and_funding_time_encoded(semantic: dict) -> None:
    immutability = semantic["canonical_lane_immutability"]
    assert set(immutability) == {"subject", "rule"}
    for token in (
        "published identities",
        "pointers",
        "descriptors",
        "parser identity",
        "manifests",
        "quality evidence",
        "canonical bytes",
    ):
        assert token in immutability["rule"], f"canonical lane immutability missing '{token}'"

    cross_quote = semantic["cross_quote_dislocation_policy"]
    assert set(cross_quote) == {"feature", "rule"}
    assert cross_quote["feature"] == "binance_kraken_cross_quote_log_ratio"
    for token in (
        "no invented USD/USDT FX conversion",
        "cross-venue, cross-quote dislocation",
        "quote-currency",
    ):
        assert token in cross_quote["rule"], f"cross-quote policy missing '{token}'"

    funding_rule = semantic["point_in_time"]["funding_eligibility"]
    assert "source calculation/settlement time F" in funding_rule, (
        "funding timestamp F must be defined as the source calculation/settlement time"
    )


def test_exact_inventory_feature_and_ladder_scope(semantic: dict) -> None:
    inventory_ids = [entry["series_id"] for entry in semantic["inventory"]]
    assert inventory_ids == EXPECTED_INVENTORY_IDS, (
        "inventory series IDs diverge from the frozen list"
    )
    assert list(semantic["feature_formulas"].keys()) == EXPECTED_FEATURE_FORMULA_KEYS, (
        "feature-formula keys diverge from the frozen list"
    )
    assert semantic["model_ladder"] == EXPECTED_MODEL_LADDER, (
        "model ladder definitions and additions diverge from the frozen ladder"
    )
    assert semantic["exclusions"]["forbidden_families"] == EXPECTED_EXCLUSION_FAMILIES, (
        "exclusions diverge from the frozen forbidden-family list"
    )


def test_no_forbidden_families_in_semantic(semantic: dict) -> None:
    # The exclusions section names forbidden families on purpose; audit everywhere else.
    audited: dict = {k: v for k, v in semantic.items() if k != "exclusions"}

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                lowered = str(key).lower()
                for token in FORBIDDEN_FAMILY_TOKENS:
                    assert token not in lowered, f"forbidden family token '{token}' in key '{key}'"
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, str):
            lowered = node.lower()
            for token in FORBIDDEN_FAMILY_TOKENS:
                assert token not in lowered, f"forbidden family token '{token}' in value '{node}'"

    walk(audited)


def test_sealed_2025_exact_literal(semantic: dict) -> None:
    assert semantic["sealed_2025"] == EXPECTED_SEALED_2025, (
        "sealed-2025 block diverges from the exact frozen literal expectations"
    )


def test_validation_folds_exact(semantic: dict) -> None:
    folds = semantic["validation"]["outer_folds"]
    assert folds == EXPECTED_OUTER_FOLDS, "outer folds diverge from the exact frozen expectations"
    assert {fold["test_year"] for fold in folds} == {2022, 2023, 2024}
    assert 2025 not in {fold["test_year"] for fold in folds}


def test_a7_a10_references_bind_paths_to_digests(
    expected: dict, semantic: dict, protocol_yaml
) -> None:
    assert semantic["audit_reference_hash_basis"] == AUDIT_REFERENCE_HASH_BASIS
    assert expected["expected_semantic"]["audit_reference_hash_basis"] == AUDIT_REFERENCE_HASH_BASIS
    assert semantic["audit_references"] == protocol_yaml["audit_references"]
    spec_text = SPEC_PATH.read_text(encoding="utf-8")
    assert f"`{AUDIT_REFERENCE_HASH_BASIS}`" in spec_text
    for label, ref in A7_A10_SHA256_REFS.items():
        real_path = REPO_ROOT / ref["path"]
        assert real_path.is_file(), f"{label}: referenced file missing: {ref['path']}"
        actual_digest = _normalized_utf8_lf_sha256(real_path)
        assert actual_digest == ref["sha256"], (
            f"{label}: LF-normalized UTF-8 hash {actual_digest} != frozen {ref['sha256']} "
            f"for {ref['path']}"
        )
        assert semantic["audit_references"][label] == {
            "path": ref["path"],
            "sha256": ref["sha256"],
        }, f"{label}: YAML does not bind {ref['path']} to its frozen digest"
        md_row = f"| {ref['md_row_label']} | `{ref['path']}` | `{ref['sha256']}` |"
        assert md_row in spec_text, (
            f"{label}: MD does not bind {ref['path']} to {ref['sha256']} (expected row: {md_row})"
        )
