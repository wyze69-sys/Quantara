"""Stable machine-readable error identifiers.

Every hard failure and warning condition defined by the governing design maps
to a stable string identifier (e.g. checksum_mismatch,
decimal_precision_or_scale_overflow, unsafe_zip_member, source_order_invalid)
carried by QuantaraError subclasses so diagnostics are deterministic across
runs and safe to record in manifests.
"""

from __future__ import annotations


class QuantaraError(Exception):
    """Base class for all quantara hard failures carrying a stable error id."""

    error_id: str = "quantara_error"

    def __init__(self, message: str = "") -> None:
        self.message = message
        super().__init__(message)
