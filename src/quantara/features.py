"""Causal and forward feature/label engines (data slice 003b).

Pure functions over the positional tuples returned by
``canonical.read_canonical_rows``: every division and square root runs inside
an explicit ``decimal.Context(prec=50)`` with ``ROUND_HALF_EVEN``, binary
floats are structurally excluded, and the only rounding to storage scale is a
single ``Q18`` quantization applied once at the storage boundary
(``build_research_rows``). Feature values are causal — row *t* depends only on
parent rows ``<= t``; label engines (design §3.3) are strictly forward.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_EVEN, Context, Decimal

from quantara.research_descriptor import APPROVED_PARAMETERS

__all__ = [
    "CLOSE_INDEX",
    "COMPUTE_CONTEXT",
    "VOLUME_INDEX",
    "build_research_rows",
    "compute_features",
    "compute_labels",
    "extract_series",
    "one_bar_return",
    "quantize_q18",
]

COMPUTE_CONTEXT = Context(prec=50, rounding=ROUND_HALF_EVEN)
_Q18_UNIT = Decimal((0, (1,), -18))

# Positional tuple layout of canonical rows read back from Parquet.
CLOSE_INDEX = 16
VOLUME_INDEX = 17

_RET_WARMUP = 1


def quantize_q18(value: Decimal) -> Decimal:
    """Single ROUND_HALF_EVEN quantization to exactly 18 fractional digits.

    The only place storage-scale rounding exists; engine outputs above this
    boundary are never rounded to 18 digits.
    """
    return COMPUTE_CONTEXT.quantize(value, _Q18_UNIT)


def _as_decimal(value: object) -> Decimal:
    if isinstance(value, float):
        raise ValueError(f"binary floats are forbidden in parent series, got {value!r}")
    return value if isinstance(value, Decimal) else Decimal(str(value))


def extract_series(rows: Sequence[Sequence]) -> tuple[list[Decimal], list[Decimal]]:
    """Pull exact closes/volumes out of positional parent tuples."""
    closes = [_as_decimal(row[CLOSE_INDEX]) for row in rows]
    volumes = [_as_decimal(row[VOLUME_INDEX]) for row in rows]
    return closes, volumes


def one_bar_return(closes: Sequence[Decimal], index: int) -> Decimal:
    """r_i = c_i / c_{i-1} - 1 inside the explicit prec=50 context."""
    quotient = COMPUTE_CONTEXT.divide(closes[index], closes[index - 1])
    return COMPUTE_CONTEXT.subtract(quotient, 1)


def compute_features(
    closes: Sequence[Decimal], volumes: Sequence[Decimal]
) -> dict[str, list[Decimal | None]]:
    """The four causal features of ``btcusdt_core_v1`` (design §3.2).

    Warm-up positions carry typed ``None``: f_ret_1 first valid at index 1,
    f_roc_60 at 60, f_rvol_20 at 20, f_volratio_20 at 19.
    """
    n = len(closes)
    roc_window = APPROVED_PARAMETERS["roc_window"]
    vol_window = APPROVED_PARAMETERS["vol_window"]
    volume_window = APPROVED_PARAMETERS["volume_window"]

    ret: list[Decimal | None] = [None] * n
    for t in range(_RET_WARMUP, n):
        ret[t] = one_bar_return(closes, t)

    roc: list[Decimal | None] = [None] * n
    for t in range(roc_window, n):
        roc[t] = COMPUTE_CONTEXT.subtract(
            COMPUTE_CONTEXT.divide(closes[t], closes[t - roc_window]), 1
        )

    rvol: list[Decimal | None] = [None] * n
    for t in range(vol_window, n):
        window = ret[t - vol_window + 1 : t + 1]
        total = Decimal(0)
        for value in window:
            total = COMPUTE_CONTEXT.add(total, value)
        mean = COMPUTE_CONTEXT.divide(total, vol_window)
        squared_sum = Decimal(0)
        for value in window:
            deviation = COMPUTE_CONTEXT.subtract(value, mean)
            squared_sum = COMPUTE_CONTEXT.add(
                squared_sum, COMPUTE_CONTEXT.multiply(deviation, deviation)
            )
        variance = COMPUTE_CONTEXT.divide(squared_sum, vol_window - 1)
        rvol[t] = variance.sqrt(COMPUTE_CONTEXT)

    volratio: list[Decimal | None] = [None] * n
    for t in range(volume_window - 1, n):
        window = volumes[t - volume_window + 1 : t + 1]
        total = Decimal(0)
        for value in window:
            total = COMPUTE_CONTEXT.add(total, value)
        mean_volume = COMPUTE_CONTEXT.divide(total, volume_window)
        volratio[t] = COMPUTE_CONTEXT.divide(volumes[t], mean_volume)

    return {
        "f_ret_1": ret,
        "f_roc_60": roc,
        "f_rvol_20": rvol,
        "f_volratio_20": volratio,
    }


def compute_labels(
    closes: Sequence[Decimal],
    horizon: int = APPROVED_PARAMETERS["label_horizon"],
) -> dict[str, list[Decimal | int | None]]:
    """The two strictly-forward labels of label set v1 (design §3.3).

    Row *t* requires bars ``t+1..t+horizon`` to exist completely; trailing
    rows carry typed ``None``. ``l_fwddir_24`` is the exact sign of
    ``l_fwdret_24`` including exact zero (0), computed from exact Decimal
    comparison so it can never become an implicit tolerance.
    """
    n = len(closes)
    fwdret: list[Decimal | None] = [None] * n
    fwddir: list[int | None] = [None] * n
    for t in range(n - horizon):
        future = closes[t + horizon]
        base = closes[t]
        fwdret[t] = COMPUTE_CONTEXT.subtract(COMPUTE_CONTEXT.divide(future, base), 1)
        if future > base:
            fwddir[t] = 1
        elif future < base:
            fwddir[t] = -1
        else:
            fwddir[t] = 0
    return {"l_fwdret_24": fwdret, "l_fwddir_24": fwddir}


def _storage(value: Decimal | None) -> Decimal | None:
    return None if value is None else quantize_q18(value)


def build_research_rows(
    parent_rows: Sequence[Sequence],
    parameters: dict[str, int] | None = None,
) -> list[tuple]:
    """Compute the full research table from verified parent rows.

    This IS the storage boundary: every non-null decimal passes through a
    single ``quantize_q18`` here and nowhere else. Rows are seven-tuples
    ``(open_time_ms, f_ret_1, f_roc_60, f_rvol_20, f_volratio_20,
    l_fwdret_24, l_fwddir_24)`` with typed ``None`` warm-up/trailing nulls.
    """
    params = parameters or APPROVED_PARAMETERS
    closes, volumes = extract_series(parent_rows)
    features = compute_features(closes, volumes)
    labels = compute_labels(closes, params["label_horizon"])
    rows: list[tuple] = []
    for t, parent in enumerate(parent_rows):
        open_time_ms = parent[10]
        if isinstance(open_time_ms, bool) or not isinstance(open_time_ms, int):
            raise ValueError("open_time_ms must be an epoch-ms int")
        rows.append(
            (
                open_time_ms,
                _storage(features["f_ret_1"][t]),
                _storage(features["f_roc_60"][t]),
                _storage(features["f_rvol_20"][t]),
                _storage(features["f_volratio_20"][t]),
                _storage(labels["l_fwdret_24"][t]),
                labels["l_fwddir_24"][t],
            )
        )
    return rows
