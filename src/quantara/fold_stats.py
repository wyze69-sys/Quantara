"""Per-fold test-segment descriptive statistics (data slice 004).

Pure statistics engine computing exact-Decimal descriptive statistics over
a fold's TEST segment rows only (design §6):
- Exact row count and epoch-ms time bounds
- Per-column actual null counts vs structural expectations
- Sign distribution of l_fwddir_24 (-1, 0, +1) summing correctly
- Mean, min, max of l_fwdret_24 rendered via render_decimal_18
- Invariant §5.5: strict causality (mutating any row outside the test segment
  leaves fold statistics bit-identical).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context, Decimal

from quantara.hashing import render_decimal_18

__all__ = [
    "COMPUTE_CONTEXT",
    "NULLABLE_COLUMNS",
    "FoldStats",
    "compute_expected_segment_nulls",
    "compute_fold_stats",
    "quantize_q18",
]

COMPUTE_CONTEXT = Context(prec=50, rounding=ROUND_HALF_EVEN)
_Q18_UNIT = Decimal((0, (1,), -18))


def quantize_q18(value: Decimal) -> Decimal:
    """Single ROUND_HALF_EVEN quantization to exactly 18 fractional digits."""
    return COMPUTE_CONTEXT.quantize(value, _Q18_UNIT)

NULLABLE_COLUMNS: tuple[str, ...] = (
    "f_ret_1",
    "f_roc_60",
    "f_rvol_20",
    "f_volratio_20",
    "l_fwdret_24",
    "l_fwddir_24",
)


@dataclass(frozen=True)
class FoldStats:
    """Per-fold test-segment descriptive statistics."""

    row_count: int
    open_time_ms_first: int
    open_time_ms_last: int
    null_counts: dict[str, int]
    expected_null_counts: dict[str, int]
    sign_distribution: dict[str, int]
    fwdret_mean: str | None
    fwdret_min: str | None
    fwdret_max: str | None

    def to_dict(self) -> dict:
        return {
            "row_count": self.row_count,
            "open_time_ms_first": self.open_time_ms_first,
            "open_time_ms_last": self.open_time_ms_last,
            "null_counts": dict(self.null_counts),
            "expected_null_counts": dict(self.expected_null_counts),
            "sign_distribution": dict(self.sign_distribution),
            "fwdret_mean": self.fwdret_mean,
            "fwdret_min": self.fwdret_min,
            "fwdret_max": self.fwdret_max,
        }


def compute_expected_segment_nulls(
    start_idx: int,
    end_idx: int,
    total_parent_rows: int,
    parameters: dict[str, int] | None = None,
) -> dict[str, int]:
    """Compute expected null counts for each column in segment [start_idx, end_idx).

    Structural-null regions:
    Features are null in table-head warmup [0, window):
      - f_ret_1: [0, 1)
      - f_roc_60: [0, roc_window)
      - f_rvol_20: [0, vol_window)
      - f_volratio_20: [0, volume_window - 1)
    Labels are null in table-tail horizon [N - label_horizon, N):
      - l_fwdret_24: [N - label_horizon, N)
      - l_fwddir_24: [N - label_horizon, N)
    """
    params = parameters or {
        "roc_window": 60,
        "vol_window": 20,
        "volume_window": 20,
        "label_horizon": 24,
    }
    n = total_parent_rows
    h = params["label_horizon"]

    def overlap(a: int, b: int, c: int, d: int) -> int:
        return max(0, min(b, d) - max(a, c))

    return {
        "f_ret_1": overlap(start_idx, end_idx, 0, 1),
        "f_roc_60": overlap(start_idx, end_idx, 0, params["roc_window"]),
        "f_rvol_20": overlap(start_idx, end_idx, 0, params["vol_window"]),
        "f_volratio_20": overlap(start_idx, end_idx, 0, params["volume_window"] - 1),
        "l_fwdret_24": overlap(start_idx, end_idx, max(0, n - h), n),
        "l_fwddir_24": overlap(start_idx, end_idx, max(0, n - h), n),
    }


def compute_fold_stats(
    parent_rows: Sequence[Sequence],
    test_range: tuple[int, int],
    total_parent_rows: int | None = None,
    parameters: dict[str, int] | None = None,
) -> FoldStats:
    """Compute statistics for a fold from its test segment rows ONLY.

    Parameters:
    - parent_rows: positional tuples (open_time_ms, f_ret_1, f_roc_60,
      f_rvol_20, f_volratio_20, l_fwdret_24, l_fwddir_24)
    - test_range: (start_idx, end_idx) integer bounds
    """
    start_idx, end_idx = test_range
    segment_rows = parent_rows[start_idx:end_idx]
    row_count = len(segment_rows)
    if row_count == 0:
        raise ValueError(f"empty test segment range: {test_range}")

    open_time_first = int(segment_rows[0][0])
    open_time_last = int(segment_rows[-1][0])

    null_counts: dict[str, int] = {col: 0 for col in NULLABLE_COLUMNS}
    sign_counts: dict[str, int] = {"-1": 0, "0": 0, "1": 0}
    fwdret_values: list[Decimal] = []

    for row in segment_rows:
        # Check nullable columns
        for idx, col in enumerate(NULLABLE_COLUMNS, start=1):
            if row[idx] is None:
                null_counts[col] += 1

        # Returns
        ret_val = row[5]
        if ret_val is not None:
            d_val = ret_val if isinstance(ret_val, Decimal) else Decimal(str(ret_val))
            fwdret_values.append(d_val)

        # Direction
        dir_val = row[6]
        if dir_val is not None:
            s_val = str(int(dir_val))
            if s_val in sign_counts:
                sign_counts[s_val] += 1

    n_total = total_parent_rows if total_parent_rows is not None else len(parent_rows)
    expected_nulls = compute_expected_segment_nulls(start_idx, end_idx, n_total, parameters)

    if fwdret_values:
        mean_dec = COMPUTE_CONTEXT.divide(sum(fwdret_values), Decimal(len(fwdret_values)))
        fwdret_mean = render_decimal_18(quantize_q18(mean_dec))
        fwdret_min = render_decimal_18(quantize_q18(min(fwdret_values)))
        fwdret_max = render_decimal_18(quantize_q18(max(fwdret_values)))
    else:
        fwdret_mean = None
        fwdret_min = None
        fwdret_max = None

    return FoldStats(
        row_count=row_count,
        open_time_ms_first=open_time_first,
        open_time_ms_last=open_time_last,
        null_counts=null_counts,
        expected_null_counts=expected_nulls,
        sign_distribution=sign_counts,
        fwdret_mean=fwdret_mean,
        fwdret_min=fwdret_min,
        fwdret_max=fwdret_max,
    )
