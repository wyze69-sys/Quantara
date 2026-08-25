"""Derivation pipeline tests (plan Tasks 4–6).

Sections:
- Task 4: schema-fingerprint parameterization regression proofs.
- Task 5: publication idempotency-evidence key extension.
- Task 6: offline lineage-bound derivation orchestration.
"""

from __future__ import annotations

from quantara.hashing import SCHEMA_VERSION, schema_fingerprint

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


def test_distinct_timeframe_versions_produce_distinct_fingerprints() -> None:
    one_m = schema_fingerprint("binance_usdm_kline_1m_v1")
    one_h = schema_fingerprint("binance_usdm_kline_1h_v1")
    one_d = schema_fingerprint("binance_usdm_kline_1d_v1")
    assert len({one_m, one_h, one_d}) == 3


def test_logical_change_produces_identity_change() -> None:
    base = schema_fingerprint("binance_usdm_kline_1h_v1")
    assert schema_fingerprint("binance_usdm_kline_1h_v2") != base
