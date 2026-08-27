"""Rust Q18 decimal rendering parity: kernel vs retained Python oracle.

Every assertion runs the kernel through the public dispatch with
``QUANTARA_HASH_KERNEL=rust`` and compares against the retained Python
oracle (forced ``python`` mode and ``_render_decimal_18_python``), so the
kernel must be byte-for-byte identical including exception messages.
"""

from __future__ import annotations

import random
import re
from decimal import ROUND_DOWN, Decimal, InvalidOperation, getcontext, setcontext

import pytest
import quantara_kernel

from quantara import hashing
from quantara.canonical import CanonicalRow
from quantara.hashing import (
    HashPayloadError,
    canonical_content_hash,
    render_decimal_18,
    schema_fingerprint,
)

Q18_PATTERN = re.compile(r"^-?\d+\.\d{18}$")

IDENTITY = (
    "binance",
    "usd_m_futures",
    "binance:usd_m_futures:BTCUSDT:perpetual",
    "BTCUSDT",
    "BTC",
    "USDT",
    "USDT",
    "perpetual",
    "1m",
    "binance_usdm_kline_1m_v1",
)

GOLDEN_CORPUS = (
    ("42571.90", "42571.900000000000000000"),
    ("42600", "42600.000000000000000000"),
    ("12.345678901234567890", "12.345678901234567890"),
    ("987654.321098765432109876", "987654.321098765432109876"),
    ("7", "7.000000000000000000"),
    ("400000", "400000.000000000000000000"),
    ("0", "0.000000000000000000"),
    ("12.34567890123456789", "12.345678901234567890"),
)

WIDE_CORPUS = (
    (
        "1234567890123456789012345678901234567890",
        "1234567890123456789012345678901234567890.000000000000000000",
    ),
    ("1E+30", "1000000000000000000000000000000.000000000000000000"),
    (
        "12345678901234567890123456789012345678E+5",
        "1234567890123456789012345678901234567800000.000000000000000000",
    ),
    ("9999999999.123456789012345678", "9999999999.123456789012345678"),
)


def _outputs(monkeypatch: pytest.MonkeyPatch, value: object) -> tuple[str, str]:
    """Render once under forced rust mode, then forced python mode."""
    monkeypatch.setenv("QUANTARA_HASH_KERNEL", "rust")
    rust_output = render_decimal_18(value)
    monkeypatch.setenv("QUANTARA_HASH_KERNEL", "python")
    python_output = render_decimal_18(value)
    return rust_output, python_output


def test_render_parity_golden_corpus(monkeypatch: pytest.MonkeyPatch) -> None:
    assert hasattr(quantara_kernel, "render_decimal_18")
    for text, expected in GOLDEN_CORPUS:
        for given in (text, Decimal(text)):
            rust_output, python_output = _outputs(monkeypatch, given)
            assert rust_output == python_output == expected


def test_render_parity_randomized_battery(monkeypatch: pytest.MonkeyPatch) -> None:
    generator = random.Random(20260828)
    values: list[tuple[Decimal, str]] = []
    for _ in range(2_000):
        digit_count = generator.randrange(1, 41)
        digits = [
            (
                generator.choice("123456789")
                if position == 0
                else generator.choice("0123456789")
            )
            for position in range(digit_count)
        ]
        digits.extend("0" * generator.randrange(0, 26))
        exponent = generator.randrange(-28, 29)
        sign = generator.randrange(0, 2)
        value = Decimal((sign, tuple(int(digit) for digit in digits), exponent))
        values.append((value, str(value)))

    for value, text in values:
        for given in (value, text):
            outputs: dict[str, str] = {}
            failures: dict[str, str] = {}
            for mode in ("python", "rust"):
                monkeypatch.setenv("QUANTARA_HASH_KERNEL", mode)
                try:
                    outputs[mode] = render_decimal_18(given)
                except HashPayloadError as exc:
                    failures[mode] = str(exc)
                else:
                    assert Q18_PATTERN.fullmatch(outputs[mode]), (text, mode)
            if failures:
                assert set(failures) == {"python", "rust"}, (text, given)
                assert failures["python"] == failures["rust"], (text, given)
            else:
                assert outputs["python"] == outputs["rust"], (text, given)



def _canonical_row(
    index: int,
    generator: random.Random | None = None,
    *,
    override: dict[str, object] | None = None,
) -> CanonicalRow:
    open_time = 1_704_067_200_000 + index * 60_000
    row: dict[str, object] = {
        "identity": IDENTITY,
        "open_time_ms": open_time,
        "close_time_ms": open_time + 59_999,
        "nominal_available_ms": open_time + 60_000,
        "open": Decimal("42571.123456789012345678"),
        "high": Decimal("50000"),
        "low": Decimal("40000"),
        "close": Decimal("42600.987654321098765432"),
        "base_asset_volume": Decimal("12.345678901234567800"),
        "quote_asset_volume": Decimal("523456.78"),
        "trade_count": 1 + index % 97,
        "taker_buy_base_volume": Decimal("0.500000000000000000000000"),
        "taker_buy_quote_volume": Decimal("21234.567890123456789012"),
        "source_ignore": "0",
    }
    if generator is not None:
        price = 42_000 + generator.randrange(0, 800)
        row["open"] = Decimal(f"{price}.{generator.randrange(0, 10**18):018d}")
        row["close"] = Decimal(f"{price + 1}.{generator.randrange(0, 10**18):018d}")
        row["quote_asset_volume"] = Decimal(
            f"{100_000 + generator.randrange(0, 900_000)}.{index % 100:02d}"
        )
    if override:
        row |= override
    return CanonicalRow(**row)


def test_render_parity_canonical_rows_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = random.Random(20260828)
    seeded_rows = [_canonical_row(index, generator) for index in range(50)]
    pinned_rows = [
        _canonical_row(
            50,
            override={
                "open": Decimal("987654.321098765432109876"),
                "close": Decimal("12.345678901234567800"),
            },
        ),
        _canonical_row(
            51,
            override={
                "open": Decimal("0.000000000000000001"),
                "close": Decimal("-7.987654321098765432"),
            },
        ),
    ]
    rows = [*pinned_rows, *seeded_rows]
    fingerprint = schema_fingerprint()

    def digest(mode: str, source: list[CanonicalRow]) -> str:
        monkeypatch.setenv("QUANTARA_HASH_KERNEL", mode)
        return canonical_content_hash(
            fingerprint, (row.to_content_array() for row in source)
        )

    assert digest("rust", rows) == digest("python", rows)
    assert digest("rust", seeded_rows) == digest("python", seeded_rows)


def test_render_dispatch_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    corpus = tuple(Decimal(text) for text, _ in GOLDEN_CORPUS)
    monkeypatch.delenv("QUANTARA_HASH_KERNEL", raising=False)
    assert hashing.active_hash_kernel() == "rust"
    default_outputs = [render_decimal_18(value) for value in corpus]

    monkeypatch.setenv("QUANTARA_HASH_KERNEL", "python")
    assert hashing.active_hash_kernel() == "python"
    assert [render_decimal_18(value) for value in corpus] == default_outputs

    monkeypatch.setattr(hashing, "_KERNEL_AVAILABLE", False)
    monkeypatch.setenv("QUANTARA_HASH_KERNEL", "rust")
    with pytest.raises(RuntimeError):
        render_decimal_18("7")

    monkeypatch.setattr(hashing, "_KERNEL_AVAILABLE", True)
    monkeypatch.setenv("QUANTARA_HASH_KERNEL", "banana")
    assert hashing.active_hash_kernel() == "rust"
    assert [render_decimal_18(value) for value in corpus] == default_outputs


def test_render_accepts_trailing_zeros_beyond_18(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cases = (
        ("0.1000000000000000000", "0.100000000000000000"),
        ("1.230000000000000000000", "1.230000000000000000"),
        (Decimal("0.500000000000000000000000"), "0.500000000000000000"),
    )
    for given, expected in cases:
        rust_output, python_output = _outputs(monkeypatch, given)
        assert rust_output == python_output == expected


def test_render_zero_and_negative_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    zeros = (Decimal("-0"), "-0.000", Decimal("0E-25"), "0E-30")
    for given in zeros:
        rust_output, python_output = _outputs(monkeypatch, given)
        assert rust_output == python_output == "0.000000000000000000"


def test_render_wide_coefficients_and_large_exponents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for text, pinned in WIDE_CORPUS:
        rust_output, python_output = _outputs(monkeypatch, text)
        assert rust_output == python_output == pinned
        assert Q18_PATTERN.fullmatch(pinned)


def test_render_kernel_is_ambient_context_immune(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUANTARA_HASH_KERNEL", "python")
    expected = {text: render_decimal_18(text) for text, _ in WIDE_CORPUS}

    saved = getcontext().copy()
    try:
        context = getcontext()
        context.prec = 1
        context.rounding = ROUND_DOWN
        context.Emax = 1
        context.Emin = -1
        monkeypatch.delenv("QUANTARA_HASH_KERNEL", raising=False)
        assert hashing.active_hash_kernel() == "rust"
        for text, _ in WIDE_CORPUS:
            assert render_decimal_18(text) == expected[text]
            assert render_decimal_18(Decimal(text)) == expected[text]
    finally:
        setcontext(saved)


OVER_EIGHTEEN_CASES = (
    (
        "0.1234567890123456789",
        "decimal 0.1234567890123456789 exceeds 18 fractional digits; rounding is forbidden",
    ),
    (
        "1e-19",
        "decimal 1E-19 exceeds 18 fractional digits; rounding is forbidden",
    ),
    (
        Decimal("1E-19"),
        "decimal 1E-19 exceeds 18 fractional digits; rounding is forbidden",
    ),
    (
        "0.12345678901234567890",
        "decimal 0.12345678901234567890 exceeds 18 fractional digits; rounding is forbidden",
    ),
    (
        "-1.2345678901234567891",
        "decimal -1.2345678901234567891 exceeds 18 fractional digits; rounding is forbidden",
    ),
)

SPECIAL_CASES = (
    (Decimal("Infinity"), OverflowError, "cannot convert Infinity to integer"),
    (Decimal("-Infinity"), OverflowError, "cannot convert Infinity to integer"),
    (
        Decimal("NaN"),
        HashPayloadError,
        "decimal NaN exceeds 18 fractional digits; rounding is forbidden",
    ),
    (
        Decimal("-NaN"),
        HashPayloadError,
        "decimal -NaN exceeds 18 fractional digits; rounding is forbidden",
    ),
    (
        Decimal("sNaN"),
        HashPayloadError,
        "decimal sNaN exceeds 18 fractional digits; rounding is forbidden",
    ),
)

MALFORMED_REJECTS = ("abc", "", "1e", "1.2.3", "--1")
MALFORMED_ACCEPTS = (
    ("1_000", "1000.000000000000000000"),
    (" 1.5 ", "1.500000000000000000"),
    (".5", "0.500000000000000000"),
    ("5.", "5.000000000000000000"),
    ("+5", "5.000000000000000000"),
)


def test_render_rejects_over_18_fractional_digits_identically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for given, message in OVER_EIGHTEEN_CASES:
        for mode in ("python", "rust"):
            monkeypatch.setenv("QUANTARA_HASH_KERNEL", mode)
            with pytest.raises(HashPayloadError) as caught:
                render_decimal_18(given)
            assert type(caught.value) is HashPayloadError
            assert str(caught.value) == message
            assert caught.value.error_id == "manifest_inconsistency"


def test_render_special_values_raise_identically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for given, expected_type, expected_message in SPECIAL_CASES:
        for mode in ("python", "rust"):
            monkeypatch.setenv("QUANTARA_HASH_KERNEL", mode)
            with pytest.raises(expected_type) as caught:
                render_decimal_18(given)
            assert type(caught.value) is expected_type
            assert str(caught.value) == expected_message


def test_render_malformed_strings_raise_identically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for given in MALFORMED_REJECTS:
        for mode in ("python", "rust"):
            monkeypatch.setenv("QUANTARA_HASH_KERNEL", mode)
            with pytest.raises(InvalidOperation) as caught:
                render_decimal_18(given)
            assert type(caught.value) is InvalidOperation
            assert str(caught.value) == "[<class 'decimal.ConversionSyntax'>]"
    for given, expected in MALFORMED_ACCEPTS:
        rust_output, python_output = _outputs(monkeypatch, given)
        assert rust_output == python_output == expected
