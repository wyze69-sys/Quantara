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
import re
from collections.abc import Iterable, Sequence
from decimal import MAX_EMAX, MIN_EMIN, ROUND_HALF_EVEN, Context, Decimal

from quantara.errors import QuantaraError
from quantara.jcs import canonicalize

__all__ = [
    "CANONICAL_COLUMNS",
    "CONTENT_HASH_DOMAIN",
    "EVALUATION_CONTENT_HASH_DOMAIN",
    "EVALUATION_SCHEMA_VERSION",
    "HASH_CONTRACT_VERSION",
    "RESEARCH_COLUMNS",
    "RESEARCH_CONTENT_HASH_DOMAIN",
    "RESEARCH_SCHEMA_VERSION",
    "RANGE_SCHEMA_FINGERPRINT_DOMAIN",
    "VALIDATION_CONTENT_HASH_DOMAIN",
    "VALIDATION_SCHEMA_VERSION",
    "canonical_content_hash",
    "canonical_row_array",
    "descriptor_hash",
    "evaluation_content_hash",
    "evaluation_schema_fingerprint",
    "quality_identity",
    "render_decimal_18",
    "research_content_hash",
    "research_row_array",
    "research_schema_fingerprint",
    "schema_fingerprint",
    "sha256_hex",
    "validation_content_hash",
    "validation_schema_fingerprint",
]

HASH_CONTRACT_VERSION = "hash_contract_v1"
CONTENT_HASH_DOMAIN = "quantara-canonical-content-v1"
SCHEMA_VERSION = "binance_usdm_kline_1m_v1"
RANGE_SCHEMA_FINGERPRINT_DOMAIN = "quantara-range-schema-fingerprint-v1"

# Data slice 003b: research-table identity domain and schema version.
RESEARCH_CONTENT_HASH_DOMAIN = "quantara-research-content-v1"
RESEARCH_SCHEMA_VERSION = "quantara_research_featureset_v1"

# Data slice 004: validation-folds identity domain and schema version.
VALIDATION_CONTENT_HASH_DOMAIN = "quantara-validation-content-v1"
VALIDATION_SCHEMA_VERSION = "quantara_validation_folds_v1"

# Data slice 006: dual-IC feature-evaluation identity domain and schema version.
EVALUATION_CONTENT_HASH_DOMAIN = "quantara-evaluation-content-v1"
EVALUATION_SCHEMA_VERSION = "quantara_feature_evaluation_v1"

DECIMAL_TYPE = "decimal128_38_18"

# Minimum working precision for exact rendering inside the local context.
_RENDER_MIN_PRECISION = 60

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


def schema_fingerprint(
    schema_version: str = SCHEMA_VERSION,
    months: Sequence[str] | None = None,
) -> str:
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
    encoded = canonicalize(payload).encode("utf-8")
    if months is None:
        return sha256_hex(encoded)
    range_payload = canonicalize(
        {"months": list(months), "schema_fingerprint_payload": payload}
    ).encode("utf-8")
    return sha256_hex(
        RANGE_SCHEMA_FINGERPRINT_DOMAIN.encode("ascii")
        + b"\x00"
        + range_payload
    )


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
    All Decimal operations run in a local high-precision context so the
    ambient process-global context can never round a wide coefficient.
    """
    number = value if isinstance(value, Decimal) else Decimal(str(value))
    # A private, fully specified context: ambient precision/rounding/exponent
    # limits/traps/flags are never read or mutated.
    ctx = Context(
        prec=max(len(number.as_tuple().digits), _RENDER_MIN_PRECISION) + 4,
        rounding=ROUND_HALF_EVEN,
        Emax=MAX_EMAX,
        Emin=MIN_EMIN,
        traps=[],
    )
    trimmed = ctx.normalize(number)
    scaled = ctx.scaleb(trimmed, Decimal(18))
    integral = ctx.to_integral_value(scaled)
    if scaled != integral:
        raise HashPayloadError(
            f"decimal {number} exceeds 18 fractional digits; rounding is "
            "forbidden"
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


# --- Data slice 003b: research-table identity ---------------------------------

# The fixed seven-column research schema in order (design §5). Each column
# carries its authoritative role so consumers cannot confuse features with
# labels without producing a different schema fingerprint.
RESEARCH_COLUMNS: tuple[tuple[str, str, str, bool], ...] = (
    # (name, type, role, nullable)
    ("open_time_ms", "int64", "index", False),
    ("f_ret_1", DECIMAL_TYPE, "feature", True),
    ("f_roc_60", DECIMAL_TYPE, "feature", True),
    ("f_rvol_20", DECIMAL_TYPE, "feature", True),
    ("f_volratio_20", DECIMAL_TYPE, "feature", True),
    ("l_fwdret_24", DECIMAL_TYPE, "label", True),
    ("l_fwddir_24", "int8", "label", True),
)

_RESEARCH_Q18_PATTERN = re.compile(r"^-?\d+\.\d{18}$")


def _research_fingerprint_payload(
    schema_version: str = RESEARCH_SCHEMA_VERSION,
) -> dict:
    return {
        "schema_version": schema_version,
        "columns": [
            {
                "index": index,
                "name": name,
                "type": ctype,
                "role": role,
                "nullable": nullable,
            }
            for index, (name, ctype, role, nullable) in enumerate(RESEARCH_COLUMNS)
        ],
    }


def research_schema_fingerprint(
    schema_version: str = RESEARCH_SCHEMA_VERSION,
) -> str:
    """SHA-256 over JCS of the ordered seven-column research payload.

    The role registry and nullability participate in the identity; the
    no-argument call is the approved ``quantara_research_featureset_v1``
    fingerprint.
    """
    payload = _research_fingerprint_payload(schema_version)
    return sha256_hex(canonicalize(payload).encode("utf-8"))


def research_row_array(values: Sequence[object]) -> list[object]:
    """Validate one research row into its JSON-ready JCS array form.

    Decimal columns must already be Q18-framed strings (exactly 18 fractional
    digits) or null; binary floats are structurally excluded everywhere.
    """
    if len(values) != len(RESEARCH_COLUMNS):
        raise HashPayloadError(
            f"research row must have exactly {len(RESEARCH_COLUMNS)} fields"
        )
    for index, value in enumerate(values):
        name, ctype, _role, nullable = RESEARCH_COLUMNS[index]
        if isinstance(value, float):
            raise HashPayloadError("binary floats are forbidden in research rows")
        if value is None:
            if not nullable:
                raise HashPayloadError(f"research column {name} is never null")
            continue
        if ctype == DECIMAL_TYPE:
            if not isinstance(value, str) or not _RESEARCH_Q18_PATTERN.fullmatch(
                value
            ):
                raise HashPayloadError(
                    f"research column {name} must be a Q18-framed string "
                    f"(exactly 18 fractional digits), got {value!r}"
                )
        else:
            if isinstance(value, bool) or not isinstance(value, int):
                raise HashPayloadError(
                    f"research column {name} must be an int, got {type(value)!r}"
                )
    return list(values)


def research_content_hash(
    fingerprint: str,
    rows: Iterable[Sequence[object]],
) -> str:
    """SHA-256 over the domain-separated research row framing.

    Same framing grammar as the canonical contract but under the dedicated
    ``quantara-research-content-v1`` domain — kline framing can never collide
    with research-table identity.
    """
    parts: list[bytes] = [
        RESEARCH_CONTENT_HASH_DOMAIN.encode("ascii"),
        b"\x00",
        fingerprint.lower().encode("ascii"),
        b"\n",
    ]
    for row in rows:
        parts.append(canonicalize(research_row_array(row)).encode("utf-8"))
        parts.append(b"\n")
    return sha256_hex(b"".join(parts))


# --- Data slice 004: validation-folds identity -------------------------------


def validation_schema_fingerprint(
    parent_fingerprint: str | None = None,
    schema_id: str = VALIDATION_SCHEMA_VERSION,
    scheme: str = "anchored_walkforward_v1",
    parameters: dict[str, int] | None = None,
    fold_set_name: str = "btcusdt_core_v1_wf72_v1",
    fold_set_version: str = "1",
) -> str:
    """SHA-256 over JCS of the validation schema domain payload.

    Domain-separated over schema id, scheme, parameters (test_size,
    min_train_size, embargo), fold set name/version, and parent research
    fingerprint.
    """
    if parent_fingerprint is None:
        parent_fingerprint = research_schema_fingerprint()
    if parameters is None:
        parameters = {"test_size": 72, "min_train_size": 336, "embargo": 24}
    payload = {
        "domain": "quantara-validation-schema-v1",
        "schema_id": schema_id,
        "scheme": scheme,
        "parameters": {
            "test_size": parameters["test_size"],
            "min_train_size": parameters["min_train_size"],
            "embargo": parameters.get("embargo", 24),
        },
        "fold_set": {
            "name": fold_set_name,
            "version": str(fold_set_version),
        },
        "parent_research_fingerprint": parent_fingerprint.lower(),
    }
    return sha256_hex(canonicalize(payload).encode("utf-8"))


def validation_content_hash(
    fingerprint: str,
    artifact: bytes | str | dict,
) -> str:
    """SHA-256 over domain-separated validation artifact bytes.

    Binds the validation schema fingerprint and canonical artifact bytes
    under the dedicated ``quantara-validation-content-v1`` domain.
    """
    if isinstance(artifact, dict):
        payload_bytes = canonicalize(artifact).encode("utf-8")
    elif isinstance(artifact, str):
        payload_bytes = artifact.encode("utf-8")
    elif isinstance(artifact, (bytes, bytearray)):
        payload_bytes = bytes(artifact)
    else:
        raise HashPayloadError(
            f"validation artifact must be dict, str, or bytes, got {type(artifact)!r}"
        )

    parts: list[bytes] = [
        VALIDATION_CONTENT_HASH_DOMAIN.encode("ascii"),
        b"\x00",
        fingerprint.lower().encode("ascii"),
        b"\n",
        payload_bytes,
        b"\n",
    ]
    return sha256_hex(b"".join(parts))


# --- Data slice 006: dual-IC feature-evaluation identity ---------------------


def evaluation_schema_fingerprint(
    parent_validation_fingerprint: str | None = None,
    schema_id: str = EVALUATION_SCHEMA_VERSION,
    evaluation_set: dict[str, str] | None = None,
    features: Sequence[str] | None = None,
    target: str = "l_fwdret_24",
    metrics: Sequence[str] | None = None,
    decimal_contract: dict | None = None,
) -> str:
    """SHA-256 over JCS of the evaluation schema domain payload (design §9.3)."""
    if parent_validation_fingerprint is None:
        parent_validation_fingerprint = validation_schema_fingerprint()
    if (
        not isinstance(parent_validation_fingerprint, str)
        or len(parent_validation_fingerprint) != 64
        or any(c not in "0123456789abcdef" for c in parent_validation_fingerprint)
    ):
        raise HashPayloadError(
            "parent_validation_fingerprint must be a 64-character lowercase hex digest"
        )
    if evaluation_set is None:
        evaluation_set = {"name": "btcusdt_core_v1_dual_ic_v1", "version": "1"}
    if features is None:
        features = ("f_ret_1", "f_roc_60", "f_rvol_20", "f_volratio_20")
    if metrics is None:
        metrics = ("pearson_ic", "spearman_ic")
    if decimal_contract is None:
        decimal_contract = {
            "precision": 50,
            "rounding": "ROUND_HALF_EVEN",
            "emin": -999999,
            "emax": 999999,
            "capitals": 1,
            "clamp": 0,
            "enabled_traps": ["InvalidOperation", "DivisionByZero", "Overflow"],
            "storage_quantum": "0.000000000000000001",
        }
    payload = {
        "domain": "quantara-evaluation-schema-v1",
        "schema_id": schema_id,
        "evaluation_set": {
            "name": evaluation_set["name"],
            "version": str(evaluation_set["version"]),
        },
        "features": list(features),
        "target": target,
        "metrics": list(metrics),
        "decimal_contract": decimal_contract,
        "parent_validation_fingerprint": parent_validation_fingerprint,
    }
    return sha256_hex(canonicalize(payload).encode("utf-8"))


def evaluation_content_hash(
    fingerprint: str,
    artifact: bytes | str | dict,
) -> str:
    """SHA-256 over domain-separated evaluation artifact bytes (design §9.3).

    Binds the evaluation schema fingerprint and canonical artifact bytes
    under the dedicated ``quantara-evaluation-content-v1`` domain.
    """
    if (
        not isinstance(fingerprint, str)
        or len(fingerprint) != 64
        or any(c not in "0123456789abcdef" for c in fingerprint)
    ):
        raise HashPayloadError(
            "fingerprint must be a 64-character lowercase hex digest"
        )

    if isinstance(artifact, dict):
        payload_bytes = canonicalize(artifact).encode("utf-8") + b"\n"
    elif isinstance(artifact, str):
        payload_bytes = artifact.encode("utf-8")
        if not payload_bytes.endswith(b"\n"):
            payload_bytes += b"\n"
    elif isinstance(artifact, (bytes, bytearray)):
        payload_bytes = bytes(artifact)
        if not payload_bytes.endswith(b"\n"):
            payload_bytes += b"\n"
    else:
        raise HashPayloadError(
            f"evaluation artifact must be dict, str, or bytes, got {type(artifact)!r}"
        )

    parts: list[bytes] = [
        EVALUATION_CONTENT_HASH_DOMAIN.encode("ascii"),
        b"\x00",
        fingerprint.encode("ascii"),
        b"\n",
        payload_bytes,
        b"\n",
    ]
    return sha256_hex(b"".join(parts))

