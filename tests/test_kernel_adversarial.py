"""Adversarial error and serialization parity for the Rust hash kernel."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from decimal import Decimal
from pathlib import Path

import pytest

from quantara import hashing


def _canonical_row() -> list[object]:
    return [0] * len(hashing.CANONICAL_COLUMNS)


def _research_row() -> list[object]:
    return [
        1_704_067_200_000,
        None,
        "1.000000000000000000",
        None,
        "2.000000000000000000",
        None,
        1,
    ]


def _payload_error(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    function: Callable[[str, Iterable[Sequence[object]]], str],
    fingerprint: str,
    rows: Iterable[Sequence[object]],
) -> tuple[type[BaseException], str, str]:
    monkeypatch.setenv("QUANTARA_HASH_KERNEL", mode)
    with pytest.raises(hashing.HashPayloadError) as caught:
        function(fingerprint, rows)
    return type(caught.value), str(caught.value), caught.value.error_id


def _type_error(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    rows: Iterable[object],
) -> type[BaseException]:
    monkeypatch.setenv("QUANTARA_HASH_KERNEL", mode)
    with pytest.raises(TypeError) as caught:
        hashing.canonical_content_hash(hashing.schema_fingerprint(), rows)
    return type(caught.value)


def test_float_row_raises_identically(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [_canonical_row() for _ in range(5)]
    rows[2][11] = 1.5

    for lazy in (False, True):
        python_error = _payload_error(
            monkeypatch,
            "python",
            hashing.canonical_content_hash,
            hashing.schema_fingerprint(),
            (row for row in rows) if lazy else rows,
        )
        rust_error = _payload_error(
            monkeypatch,
            "rust",
            hashing.canonical_content_hash,
            hashing.schema_fingerprint(),
            (row for row in rows) if lazy else rows,
        )
        assert rust_error == python_error


def test_wrong_arity_raises_identically(monkeypatch: pytest.MonkeyPatch) -> None:
    for field_count in (22, 24):
        row = [0] * field_count
        python_error = _payload_error(
            monkeypatch,
            "python",
            hashing.canonical_content_hash,
            hashing.schema_fingerprint(),
            [row],
        )
        rust_error = _payload_error(
            monkeypatch,
            "rust",
            hashing.canonical_content_hash,
            hashing.schema_fingerprint(),
            [row],
        )
        assert rust_error == python_error


def test_unsupported_type_raises_identically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for unsupported in (None, Decimal("1.0"), object()):
        row = _canonical_row()
        row[7] = unsupported
        python_error = _payload_error(
            monkeypatch,
            "python",
            hashing.canonical_content_hash,
            hashing.schema_fingerprint(),
            [row],
        )
        rust_error = _payload_error(
            monkeypatch,
            "rust",
            hashing.canonical_content_hash,
            hashing.schema_fingerprint(),
            [row],
        )
        assert rust_error == python_error


def test_non_sequence_row_raises_typeerror_both_modes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _type_error(monkeypatch, "python", iter([5])) is TypeError
    assert _type_error(monkeypatch, "rust", iter([5])) is TypeError


def test_bool_renders_as_json_bool_identically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _canonical_row()
    row[10] = True
    row[11] = False
    monkeypatch.setenv("QUANTARA_HASH_KERNEL", "python")
    python_digest = hashing.canonical_content_hash(hashing.schema_fingerprint(), [row])
    monkeypatch.setenv("QUANTARA_HASH_KERNEL", "rust")
    rust_digest = hashing.canonical_content_hash(hashing.schema_fingerprint(), [row])

    assert rust_digest == python_digest


def test_research_validation_errors_identical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_rows = []
    non_q18 = _research_row()
    non_q18[1] = "1.25"
    invalid_rows.append(non_q18)
    never_null = _research_row()
    never_null[0] = None
    invalid_rows.append(never_null)
    bool_label = _research_row()
    bool_label[6] = True
    invalid_rows.append(bool_label)

    for row in invalid_rows:
        python_error = _payload_error(
            monkeypatch,
            "python",
            hashing.research_content_hash,
            hashing.research_schema_fingerprint(),
            [row],
        )
        rust_error = _payload_error(
            monkeypatch,
            "rust",
            hashing.research_content_hash,
            hashing.research_schema_fingerprint(),
            [row],
        )
        assert rust_error == python_error


def test_kernel_source_contains_no_binary_floats() -> None:
    source_root = Path(__file__).parents[1] / "kernel" / "src"
    sources = [path.read_text(encoding="utf-8") for path in source_root.rglob("*.rs")]

    assert sources
    assert all("f64" not in source and "f32" not in source for source in sources)
