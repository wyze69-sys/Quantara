"""Rights-record gate semantics and period-validation tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from conftest import (
    VALID_DESCRIPTOR_YAML,
)
from conftest import (
    op as _op,
)
from conftest import (
    rights_yaml as _rights_yaml,
)
from conftest import (
    write_text as _write,
)
from quantara.descriptor import (
    APPROVED_INTERNAL_OPERATIONS,
    RIGHTS_OPERATIONS,
    DescriptorError,
    load_descriptor,
    load_rights_record,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
V2_RECORD_PATH = (
    REPO_ROOT / "configs" / "legal" / "binance-usdm-provider-rights.v2.yaml"
)


def test_v2_rights_record_loads_and_authorizes_analytical_use() -> None:
    record = load_rights_record(V2_RECORD_PATH)
    assert record.record_id == "binance-usdm-provider-rights.v2"
    assert set(record.operations) == set(RIGHTS_OPERATIONS)
    assert record.review_date == "2026-08-26"
    assert record.permits("analyze_internal") is True


def test_bad_periods_are_rejected(valid_path: Path) -> None:
    bad_periods = [
        ("2024-02-01T00:00:00Z", "2024-01-01T00:00:00Z"),  # inverted
        ("2024-01-01T00:00:00+01:00", "2024-02-01T00:00:00Z"),  # offset, not Z
        ("2024-01-01 00:00:00", "2024-02-01T00:00:00Z"),  # naive format
        ("2024-01-01T00:00:00.500Z", "2024-02-01T00:00:00Z"),  # sub-second
    ]
    for start_value, end_value in bad_periods:
        lines = []
        skipping = False
        for line in VALID_DESCRIPTOR_YAML.splitlines():
            if line.startswith("period:"):
                skipping = True
                lines.append("period:")
                lines.append(f'  start: "{start_value}"')
                lines.append(f'  end: "{end_value}"')
                continue
            if skipping and line.startswith("  "):
                continue
            skipping = False
            lines.append(line)
        rebuilt = "\n".join(lines) + "\n"
        with pytest.raises(DescriptorError):
            load_descriptor(_write(valid_path.parent, rebuilt))


def test_non_allowlisted_host_is_rejected(valid_path: Path) -> None:
    text = VALID_DESCRIPTOR_YAML.replace(
        "https://data.binance.vision/", "https://evil.example.com/"
    )
    with pytest.raises(DescriptorError):
        load_descriptor(_write(valid_path.parent, text))


@pytest.mark.parametrize(
    "symbol",
    ["../etc", "BTC/USDT", "btcusdt", "BTC%2F"],
)
def test_path_manipulation_through_symbol_is_rejected(
    valid_path: Path, symbol: str
) -> None:
    text = VALID_DESCRIPTOR_YAML.replace("BTCUSDT", symbol)
    with pytest.raises(DescriptorError):
        load_descriptor(_write(valid_path.parent, text))


def test_rights_record_permits_only_approved_operations(tmp_path: Path) -> None:
    operations = {
        "acquire_internal": _op("OWNER_APPROVED_PENDING_COUNSEL"),
        "retain_raw_internal": _op("OWNER_APPROVED_PENDING_COUNSEL"),
        "normalize_internal": _op("OWNER_APPROVED_PENDING_COUNSEL"),
        "analyze_internal": _op("UNKNOWN"),
        "model_train_internal": _op("UNKNOWN"),
        "commercial_production_eligible": _op("UNKNOWN"),
        "customer_display": _op("UNKNOWN"),
        "raw_redistribution": _op("UNKNOWN"),
    }
    path = tmp_path / "rights.yaml"
    path.write_text(yaml.safe_dump(_rights_yaml(operations)), encoding="utf-8")
    record = load_rights_record(path)
    assert set(record.operations) == set(RIGHTS_OPERATIONS)
    assert record.permits("acquire_internal") is True
    assert record.permits("retain_raw_internal") is True
    assert record.permits("normalize_internal") is True
    assert record.permits("analyze_internal") is False
    assert record.permits("model_train_internal") is False
    assert record.permits("commercial_production_eligible") is False
    assert record.permits("customer_display") is False
    assert record.permits("raw_redistribution") is False


def test_pending_counsel_never_permits_commercial_or_customer_ops(
    tmp_path: Path,
) -> None:
    operations = {op: _op("UNKNOWN") for op in RIGHTS_OPERATIONS}
    for op in ("customer_display", "commercial_production_eligible"):
        operations[op] = _op("OWNER_APPROVED_PENDING_COUNSEL")
    path = tmp_path / "rights.yaml"
    path.write_text(
        yaml.safe_dump(_rights_yaml(operations)), encoding="utf-8"
    )
    record = load_rights_record(path)
    assert record.permits("customer_display") is False
    assert record.permits("commercial_production_eligible") is False


def test_missing_operation_is_rejected(tmp_path: Path) -> None:
    operations = {op: _op("ALLOWED") for op in RIGHTS_OPERATIONS}
    del operations["raw_redistribution"]
    payload = _rights_yaml(operations)
    del payload["reviewer"]  # also exercises required top-level fields
    path = tmp_path / "rights.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(DescriptorError):
        load_rights_record(path)


def test_approved_internal_operation_names() -> None:
    assert APPROVED_INTERNAL_OPERATIONS == (
        "acquire_internal",
        "retain_raw_internal",
        "normalize_internal",
    )
