"""Hash contract v1 (hash_contract_v1).

SHA-256 identities over exact artifact bytes (ZIP, checksum document, ZIP
member), the JCS-canonicalized descriptor semantics, the ordered logical
schema fingerprint, deterministic quality identity, and the row-framed
canonical-content hash (spec §12.1). Decimal values are rendered with exactly
18 fractional digits and no exponent; binary floats are structurally excluded
from every payload.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from decimal import Decimal

from quantara.errors import QuantaraError
from quantara.jcs import canonicalize

__all__ = [
    "CANONICAL_COLUMNS",
    "CONTENT_HASH_DOMAIN",
    "HASH_CONTRACT_VERSION",
    "SCHEMA_VERSION",
    "canonical_content_hash",
    "canonical_row_array",
    "descriptor_hash",
    "quality_identity",
    "render_decimal_18",
    "schema_fingerprint",
    "sha256_hex",
]

HASH_CONTRACT_VERSION = "hash_contract_v1"
CONTENT_HASH_DOMAIN = "quantara-canonical-content-v1"
SCHEMA_VERSION = "binance_usdm_kline_1m_v1"

DECIMAL_TYPE = "decimal128_38_18"

# The fixed 23-column canonical schema, in order (spec §6.6).
CANONICAL_COLUMNS: tuple[tuple[str, str], ...] = (
    ("provider", "utf8"),
    ("market_type", "utf8"),
    ("instrument_id", "utf8"),
    ("provider_symbol", "utf8"),
    ("base_asset", "utf8"),
    ("quote_asset", "utf8"),
    ("settlement_asset", "utf8"),
    ("contract_type", "utf8"),
    ("interval", "utf8"),
    ("schema_version", "utf8"),
    ("open_time_utc", "timestamp_ms_utc"),
    ("close_time_utc", "timestamp_ms_utc"),
    ("nominal_available_time_utc", "timestamp_ms_utc"),
    ("open", DECIMAL_TYPE),
    ("high", DECIMAL_TYPE),
    ("low", DECIMAL_TYPE),
    ("close", DECIMAL_TYPE),
    ("base_asset_volume", DECIMAL_TYPE),
    ("quote_asset_volume", DECIMAL_TYPE),
    ("trade_count", "int64_nonnegative"),
    ("taker_buy_base_volume", DECIMAL_TYPE),
    ("taker_buy_quote_volume", DECIMAL_TYPE),
    ("source_ignore", "utf8"),
)


class HashPayloadError(QuantaraError):
    error_id = "manifest_inconsistency"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def descriptor_hash(canonical_semantics: str) -> str:
    """SHA-256 over UTF-8 JCS of validated descriptor semantics."""
    return sha256_hex(canonical_semantics.encode("utf-8"))


def schema_fingerprint(schema_version: str = SCHEMA_VERSION) -> str:
    """SHA-256 over JCS of the complete ordered logical schema + nullability.

    The payload's schema_version field is the parameter; the column list is
    unchanged. The no-argument call remains byte-identical to the frozen
    slice 001 fingerprint (design §9).
    """
    payload = {
        "schema_version": schema_version,
        "columns": [
            {"index": index, "name": name, "type": ctype, "nullable": False}
            for index, (name, ctype) in enumerate(CANONICAL_COLUMNS)
        ],
    }
    return sha256_hex(canonicalize(payload).encode("utf-8"))


def quality_identity(checks: Sequence[dict]) -> str:
    """JCS over ordered check ids, outcomes, counts, evidence; operational
    timestamps are excluded by the caller's contract and stripped defensively."""
    normalized = [
        {k: v for k, v in check.items() if k != "operational_timestamp"}
        for check in checks
    ]
    return canonicalize({"checks": list(normalized)})


def render_decimal_18(value: Decimal | str) -> str:
    """Render an exact decimal with exactly 18 fractional digits, no exponent.

    Trailing fractional zeros are insignificant for representability; any
    value needing more than 18 fractional digits is rejected — never rounded.
    """
    number = value if isinstance(value, Decimal) else Decimal(str(value))
    trimmed = number.normalize()
    scaled = trimmed.scaleb(18)
    integral = scaled.to_integral_value()
    if scaled != integral:
        raise HashPayloadError(
            f"decimal {number} exceeds 18 fractional digits; rounding is forbidden"
        )
    magnitude = int(integral)
    sign = "-" if magnitude < 0 else ""
    digits = str(abs(magnitude)).rjust(19, "0")
    return f"{sign}{digits[:-18]}.{digits[-18:]}"


def canonical_row_array(values: Sequence[object]) -> list[object]:
    """Validate one canonical row into its JSON-ready JCS array form."""
    if len(values) != len(CANONICAL_COLUMNS):
        raise HashPayloadError(
            f"canonical row must have exactly {len(CANONICAL_COLUMNS)} fields"
        )
    for value in values:
        if isinstance(value, float):
            raise HashPayloadError("binary floats are forbidden in canonical rows")
        if not isinstance(value, (str, int)):
            raise HashPayloadError(
                f"canonical rows admit strings/ints/bools/nulls only, got {type(value)!r}"
            )
    return list(values)


def canonical_content_hash(fingerprint: str, rows: Iterable[Sequence[object]]) -> str:
    """SHA-256(domain NUL fingerprint NL row-JCS NL ...) per spec §12.1."""
    parts: list[bytes] = [
        CONTENT_HASH_DOMAIN.encode("ascii"),
        b"\x00",
        fingerprint.lower().encode("ascii"),
        b"\n",
    ]
    for row in rows:
        parts.append(canonicalize(canonical_row_array(row)).encode("utf-8"))
        parts.append(b"\n")
    return sha256_hex(b"".join(parts))
