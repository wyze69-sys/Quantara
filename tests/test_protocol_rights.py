"""D00 audit of rights coverage for the frozen Protocol v1.1 inventory."""

from collections import Counter
from pathlib import Path

import pytest
import yaml

from quantara.descriptor import (
    RIGHTS_OPERATIONS,
    DescriptorError,
    RightsRecord,
    load_rights_record,
)
from quantara.protocol_v11 import load_protocol_v11

REPO_ROOT = Path(__file__).resolve().parents[1]
LEGAL_ROOT = REPO_ROOT / "configs/legal"
PROTOCOL_PATH = "configs/protocols/quantara-protocol-v1_1.yaml"
AUDIT_REFERENCES = (
    "docs/superpowers/plans/2026-08-31-a8-btcusdt-spot.md",
    "docs/superpowers/plans/2026-08-31-a9-second-btc-venue-kraken.md",
    PROTOCOL_PATH,
)
INTERNAL_OPERATIONS = {
    "acquire_internal",
    "retain_raw_internal",
    "normalize_internal",
    "analyze_internal",
    "model_train_internal",
}
FORBIDDEN_OPERATIONS = (
    "commercial_production_eligible",
    "customer_display",
    "raw_redistribution",
)
PENDING_COUNSEL = "OWNER_APPROVED_PENDING_COUNSEL"
USDM_RECORD_ID = "binance-usdm-provider-rights.v3"
SPOT_RECORDS = {
    "binance-spot-provider-rights.v1": (
        "binance_spot",
        "Binance Terms of Use; data.binance.vision public archives",
    ),
    "kraken-spot-provider-rights.v1": (
        "kraken",
        "Kraken Terms of Service; Kraken public REST API",
    ),
}
# Explicit audit bindings; these do not add the D01 runtime descriptor registry.
# The frozen inventory names eight USD-M series with the binance_futures alias.
GOVERNING_SCOPES = {
    USDM_RECORD_ID: {
        ("binance_usd_m_futures", "binance", "perpetual"),
        ("binance_futures", "binance", "perpetual"),
    },
    "binance-spot-provider-rights.v1": {("binance_spot", "binance", "spot")},
    "kraken-spot-provider-rights.v1": {("kraken", "kraken", "spot")},
}


def _resolve_governing_record(series: dict, records: list[RightsRecord]) -> RightsRecord:
    """Assert the packet's identity/scope binding over records loaded by production code."""
    scope = (series["provider"], series["venue"], series["market_type"])
    matches = [
        record for record in records if scope in GOVERNING_SCOPES.get(record.record_id, set())
    ]
    if len(matches) != 1:
        raise ValueError(f"{series['series_id']}: expected one rights record, got {len(matches)}")
    return matches[0]


@pytest.fixture(scope="module")
def inventory() -> list[dict]:
    return load_protocol_v11(REPO_ROOT / PROTOCOL_PATH).to_dict()["inventory"]


@pytest.fixture(scope="module")
def governing_records() -> list[RightsRecord]:
    return [load_rights_record(LEGAL_ROOT / f"{record_id}.yaml") for record_id in GOVERNING_SCOPES]


@pytest.fixture(params=tuple(SPOT_RECORDS))
def spot_path(request: pytest.FixtureRequest) -> Path:
    return LEGAL_ROOT / f"{request.param}.yaml"


def _tampered_record(tmp_path: Path, source: Path, old: str, new: str) -> Path:
    text = source.read_text(encoding="utf-8")
    assert old in text
    path = tmp_path / source.name
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return path


def test_all_frozen_series_have_exactly_one_governing_record(
    inventory: list[dict], governing_records: list[RightsRecord]
) -> None:
    assert len(inventory) == 14
    assert len({series["series_id"] for series in inventory}) == 14
    resolved = {
        series["series_id"]: _resolve_governing_record(series, governing_records).record_id
        for series in inventory
    }
    assert Counter(resolved.values()) == {
        USDM_RECORD_ID: 12,
        "binance-spot-provider-rights.v1": 1,
        "kraken-spot-provider-rights.v1": 1,
    }
    assert resolved["binance_btc_spot_ohlcv_1m"] == "binance-spot-provider-rights.v1"
    assert resolved["kraken_xbtusd_spot_ohlcv_1h"] == "kraken-spot-provider-rights.v1"
    for record in governing_records:
        expected_provider = "binance" if record.record_id == USDM_RECORD_ID else (
            SPOT_RECORDS[record.record_id][0]
        )
        assert record.provider == expected_provider


@pytest.mark.parametrize("record_count", [0, 2])
def test_missing_or_ambiguous_governance_fails_closed(
    inventory: list[dict], governing_records: list[RightsRecord], record_count: int
) -> None:
    for series in inventory:
        governing = _resolve_governing_record(series, governing_records)
        candidates = [record for record in governing_records if record != governing]
        candidates.extend([governing] * record_count)
        with pytest.raises(ValueError, match=f"expected one rights record, got {record_count}"):
            _resolve_governing_record(series, candidates)


def test_new_records_bind_review_terms_and_audits(spot_path: Path) -> None:
    record = load_rights_record(spot_path)
    provider, source_terms = SPOT_RECORDS[spot_path.stem]
    assert record.record_id == spot_path.stem
    assert record.provider == provider
    assert record.reviewer == "wyze69-sys"
    assert record.review_date == "2026-09-03"
    rationales = "\n".join(operation.rationale for operation in record.operations.values())
    for reference in AUDIT_REFERENCES:
        assert (REPO_ROOT / reference).is_file()
        assert reference in rationales
    for operation in record.operations.values():
        assert operation.source_terms == source_terms
        assert operation.reviewer == "wyze69-sys"
        assert operation.review_date == "2026-09-03"
        assert operation.rationale.strip()


def test_new_records_permit_exactly_five_internal_operations(spot_path: Path) -> None:
    record = load_rights_record(spot_path)
    assert set(record.operations) == set(RIGHTS_OPERATIONS)
    assert set(RIGHTS_OPERATIONS) == INTERNAL_OPERATIONS | set(FORBIDDEN_OPERATIONS)
    for name, operation in record.operations.items():
        internal = name in INTERNAL_OPERATIONS
        assert operation.state == (PENDING_COUNSEL if internal else "UNKNOWN")
        assert record.permits(name) is internal
    assert record.permits("unknown_operation") is False


@pytest.mark.parametrize("operation", FORBIDDEN_OPERATIONS)
def test_pending_counsel_never_permits_external_operations(
    spot_path: Path, tmp_path: Path, operation: str
) -> None:
    path = _tampered_record(
        tmp_path, spot_path,
        f"  {operation}:\n    state: UNKNOWN",
        f"  {operation}:\n    state: {PENDING_COUNSEL}",
    )
    record = load_rights_record(path)
    assert record.operations[operation].state == PENDING_COUNSEL
    assert record.permits(operation) is False


@pytest.mark.parametrize("operation", RIGHTS_OPERATIONS)
def test_unsupported_operation_state_fails_closed(
    spot_path: Path, tmp_path: Path, operation: str
) -> None:
    expected_state = PENDING_COUNSEL if operation in INTERNAL_OPERATIONS else "UNKNOWN"
    path = _tampered_record(
        tmp_path, spot_path,
        f"  {operation}:\n    state: {expected_state}",
        f"  {operation}:\n    state: UNSUPPORTED",
    )
    with pytest.raises(DescriptorError, match=f"operation {operation} has invalid state"):
        load_rights_record(path)


@pytest.mark.parametrize("operation", RIGHTS_OPERATIONS)
def test_missing_operation_key_fails_closed(
    spot_path: Path, tmp_path: Path, operation: str
) -> None:
    # PyYAML only constructs a mutation; the production loader validates it.
    document = yaml.safe_load(spot_path.read_text(encoding="utf-8"))
    del document["operations"][operation]
    path = tmp_path / spot_path.name
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    with pytest.raises(DescriptorError, match="operations must cover exactly"):
        load_rights_record(path)


def test_unknown_record_id_cannot_govern_frozen_inventory(
    spot_path: Path, tmp_path: Path, inventory: list[dict],
    governing_records: list[RightsRecord],
) -> None:
    path = _tampered_record(
        tmp_path, spot_path,
        f"record_id: {spot_path.stem}",
        "record_id: unknown-provider-rights.v1",
    )
    # The generic loader parses the schema; D00's audit binding rejects unknown
    # identities. Runtime descriptor enforcement belongs to D01, not this packet.
    tampered = load_rights_record(path)
    assert tampered.record_id == "unknown-provider-rights.v1"
    candidates = [
        tampered if record.record_id == spot_path.stem else record
        for record in governing_records
    ]
    for series in inventory:
        governing = _resolve_governing_record(series, governing_records)
        if governing.record_id == spot_path.stem:
            with pytest.raises(ValueError, match="expected one rights record, got 0"):
                _resolve_governing_record(series, candidates)
        else:
            assert _resolve_governing_record(series, candidates) == governing
