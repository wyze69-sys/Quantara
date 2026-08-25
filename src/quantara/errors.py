"""Stable machine-readable error identifiers.

Every hard failure (spec §14.1) and warning condition (spec §14.2) maps to a
stable string identifier carried by QuantaraError subclasses so diagnostics
are deterministic across runs and safe to record in manifests.
"""

from __future__ import annotations

# Hard-failure identifiers (spec §14.1).
INVALID_DESCRIPTOR = "invalid_descriptor"
NON_ALLOWLISTED_SOURCE = "non_allowlisted_source"
DOWNLOAD_FAILED_AFTER_RETRIES = "download_failed_after_retries"
INVALID_CHECKSUM_DOCUMENT = "invalid_checksum_document"
CHECKSUM_MISMATCH = "checksum_mismatch"
UNSAFE_ZIP_MEMBER = "unsafe_zip_member"
CORRUPT_ARCHIVE = "corrupt_archive"
SOURCE_HEADER_MISMATCH = "source_header_mismatch"
MALFORMED_TIMESTAMP_FIELD = "malformed_timestamp_field"
MALFORMED_NUMERIC_FIELD = "malformed_numeric_field"
DECIMAL_PRECISION_OR_SCALE_OVERFLOW = "decimal_precision_or_scale_overflow"
WRONG_ROW_COUNT = "wrong_row_count"
BOUNDARY_MISMATCH = "boundary_mismatch"
DUPLICATE_OPEN_TIME = "duplicate_open_time"
MISSING_OPEN_TIME = "missing_open_time"
BROKEN_OHLC_INVARIANT = "broken_ohlc_invariant"
IMPOSSIBLE_NEGATIVE_VALUE = "impossible_negative_value"
FAILED_PARQUET_WRITE_OR_READ_BACK = "failed_parquet_write_or_read_back"
RECONCILIATION_MISMATCH = "reconciliation_mismatch"
MANIFEST_INCONSISTENCY = "manifest_inconsistency"
ATOMIC_PROMOTION_FAILURE = "atomic_promotion_failure"

# Warning identifiers (spec §14.2).
SOURCE_ORDER_INVALID = "source_order_invalid"
ZERO_VOLUME_CANDLE = "zero_volume_candle"
NONZERO_SOURCE_IGNORE = "nonzero_source_ignore"
TRANSPORT_METADATA_DIFFERENCE = "transport_metadata_difference"


class QuantaraError(Exception):
    """Base class for all quantara hard failures carrying a stable error id."""

    error_id: str = "quantara_error"

    def __init__(self, message: str = "") -> None:
        self.message = message
        super().__init__(message)
