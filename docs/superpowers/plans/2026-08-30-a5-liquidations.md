# A5 — Liquidations (BTCUSDT, USD-M)

**Slice status:** COMPLETE
**Audit window:** 2020-01-01 → 2024-12-31
**Authorisation:** owner, 2026-08-30 ("after task 1 done go to another one")
**Probed:** 2026-08-30 (UTC retrieval)
**Probe script:** `temp/probe_liquidations_v1.py`
**Raw evidence:** `temp/audit_a5_liquidations/liquidation_probe_v1.json`
**Verdict:** **DROP** — Binance does **not** publish a liquidation archive. The live API endpoint `/fapi/v1/allForceOrders` only retains the **most recent 7 days**, and since **2021-04-27 09:00 UTC** the WebSocket `@forceOrder` stream has been throttled to **1 liquidation per second per symbol**. Pre-2021-04-27 history is not publicly archived. The audit recommends a **vendor fallback** (Coinalyze / CoinGlass / CoinAPI) for any liquidation feature, with the explicit understanding that the 2020-01 → 2024-12 vendor data is **not auditable to first-party source** and must carry a `LIQUIDATION_VENDOR` flag in the loader.

## 1. Primary source — none

There is **no public Binance liquidation archive** on
`data.binance.vision`. The audit probed six plausible paths and got
HTTP 404 on every one:

| URL probed | Status |
| --- | --- |
| `…/futures/um/monthly/liquidations/BTCUSDT/` | 404 |
| `…/futures/um/daily/liquidations/BTCUSDT/` | 404 |
| `…/futures/um/monthly/forceOrders/BTCUSDT/` | 404 |
| `…/futures/um/daily/forceOrders/BTCUSDT/` | 404 |
| `…/futures/um/monthly/liqOrders/BTCUSDT/` | 404 |
| `…/futures/um/daily/liqOrders/BTCUSDT/` | 404 |

A directory listing of `data/futures/um/monthly/` (from A1, A3) shows
exactly eight archives: `aggTrades`, `bookTicker`, `fundingRate`,
`indexPriceKlines`, `klines`, `markPriceKlines`,
`premiumIndexKlines`, `trades`. **No liquidation archive** is
exposed.

## 2. Live API — bounded retention + 1/sec throttling

### 2.1 REST endpoint retention

Binance's official `/fapi/v1/allForceOrders` endpoint
documentation (https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/All-Force-Orders)
and the changelog (2021-01-26) state:

> "The query time period for endpoint GET /fapi/v1/allForceOrders
> must be within the recent 7 days."

**Retention window: 7 days rolling.** This is **half** the
`openInterestHist` retention (1 month) and an order of magnitude
shorter than what the audit needs (5 years). With API key, the
most one can scrape is the past week.

### 2.2 WebSocket stream throttling

Effective **2021-04-27 09:00 UTC**, Binance's `@forceOrder`
WebSocket stream switched from real-time push to a snapshot pattern
documented as:

> "For each symbol, only the latest one liquidation order within
> 1000ms will be pushed as the snapshot. If no liquidation happens
> in the interval of 1000ms, no stream will be pushed."

(Quoted from the Binance developer community post linked below; the
upgrade was announced on 2021-04-22 and rolled out 5 days later.)

**Implication:** at most 1 liquidation per second per symbol is
publicly broadcast, and that one is the **most recent** snapshot.
During a cascade with hundreds of liquidations in a second, the
public stream sees 1 of them; the rest are private. Vendor archives
that claim full liquidation history either ingest a private data
feed (paid) or have the same 1/sec cap baked in.

## 3. Earliest real timestamp

**Not auditable to first-party source for any date before the past
7 days at probe time.** The audit cannot place a verifiable
earliest timestamp on BTCUSDT USD-M liquidation history.

## 4. Coverage across 2020-2024

- **2020-01 → 2021-04-27 (pre-throttle):** full liquidation history
  was broadcast on the `@forceOrder` WebSocket in real time. No
  public archive retains this — it is gone unless someone was
  listening at the time.
- **2021-04-27 09:00 UTC → probe time (post-throttle):** at most
  one liquidation per second per symbol is publicly available,
  retained on Binance's servers for at most 7 days. The actual
  count of publicly observable liquidations is therefore an
  unknown but small fraction of the true count.

**Coverage is therefore effectively zero** for the 2020-01 →
2024-12 audit window. The audit can neither confirm nor deny the
existence of any specific historical liquidation from the public
data surface.

## 5. Timestamp and settlement semantics (where the public source
   would have applied)

For documentation completeness — the format the live endpoint /
stream **would have used** if the audit had been able to retrieve
historical data:

- `/fapi/v1/allForceOrders` returns a JSON object per order with
  fields: `symbol`, `orderId`, `price`, `qty`, `averagePrice`,
  `status` (FILLED), `side` (SELL for longs liquidated, BUY for
  shorts liquidated), `time` (UTC ms), `timeInForce`, `type`
  (LIMIT), `origType`, `positionSide`, `executedQty`.
- WebSocket payload uses the same shape with `e: "forceOrder"` and
  `o: {...}`.
- A "long liquidation" is a SELL market order; a "short
  liquidation" is a BUY market order. The "liquidation amount" is
  `qty * price` (notional) or just `qty` (contracts). Volumes are
  not signed in the public schema; the side field distinguishes.

The audit cannot verify these field names against a real 2020-2024
sample because no public archive exists. The format above is taken
from the official documentation, not from observed evidence.

## 6. Publication delay

For the live API: ~immediate at the time of the liquidation. For
historical backtests: **N/A** because no history is retained.

## 7. Pagination, rate limits, and revision behavior

- REST endpoint: standard 1000-record limit per page; rate-limit
  weight of 20 with symbol / 50 without symbol (Binance changelog
  2021-01-26).
- WebSocket: 1 liquidation per second per symbol post-2021-04-27.
- No revision behavior to assess because no archive exists.

## 8. Licensing and retention/redistribution rights

**First-party (Binance) liquidation history is not licensable for
historical backtests** because Binance does not publish it. The
live endpoint is governed by Binance's standard API Terms of Use,
but a 7-day retention window is not useful for the audit's
2020-01 → 2024-12 scope.

Vendor-sourced liquidation data (Coinalyze, CoinGlass, CoinAPI) is
governed by the vendor's commercial licence and **cannot be
audited to first-party source** — the audit cannot independently
verify that a vendor's "Binance liquidations" series actually
equals the true Binance liquidation count for any date. This is a
**fundamental data-integrity gap** that no contract can paper over.

## 9. Reproducibility and sample hashes

**No reproducible sample exists.** The audit's probe sidecar
contains six 404 entries and zero SHA-256 digests. The sidecar is
the negative result.

## 10. Fallback candidates

In priority order, with explicit caveats:

1. **Coinalyze** (`https://coinalyze.net/.../liquidations/`) — vendor
   historical liquidations across exchanges including Binance.
   Confirmed to claim "Binance" series; **inherits the 1/sec cap
   for post-2021-04-27** because Coinalyze ingest from public
   streams. Pre-2021-04-27 history is more complete but is not
   auditable. Paid plan required for bulk download.
2. **CoinGlass** (`https://www.coinglass.com/pro/futures/Liquidations`)
   — paid Pro plan; same 1/sec cap caveat.
3. **CoinAPI** (https://www.coinapi.io/) — paid Metrics API; same
   caveat.
4. **Internal real-time ingest** — subscribe to `@forceOrder` and
   record 1/sec samples. Useful for **forward** measurement but
   cannot recover 2020-01 → probe-time history.

**None of the four provides a verifiable, first-party-auditable
historical liquidation series for 2020-01 → 2024-12.** The
audit's recommendation is therefore **DROP** for now, and to
re-evaluate in a future slice if Binance publishes a historical
archive or a vendor publishes a first-party-attestable one.

## 11. Implications for the target / protocol design

The audit's A5 result interacts with the rest of the
large-move-target design in three ways:

1. **Liquidation-as-feature must be removed from any candidate
   feature list.** No verifiable history → no strictly
   backward-looking liquidation feature can be built for 2020-01
   → 2024-12 without a vendor dependency that the audit cannot
   validate.
2. **The target is unchanged.** "Large 24h move" does not require
   liquidation data; funding rate (A1), OI (A2), mark/index (A3),
   and basis (A4) are the new information types the audit is
   positioned to ship.
3. **Liquidation cascade events can still be used for regime
   labelling in 2025 sealed evaluation** if a real-time ingest
   is built at that time. The audit's DROP verdict applies to
   the historical feature, not to forward cascade detection.

## 12. Verdict

**DROP for the historical feature.**

- No public Binance liquidation archive exists (6/6 paths 404).
- Live REST endpoint retention is 7 days (documented in Binance
  changelog 2021-01-26).
- Live WebSocket stream is throttled to 1/sec/symbol since
  2021-04-27 09:00 UTC.
- Vendor archives inherit the 1/sec cap for post-throttle data
  and are not auditable to first-party source.
- The target / protocol design does not require liquidation data;
  the rest of the audit (A1-A4, A7-A9) is sufficient.

**Recommendation:** record `LIQUIDATION_VENDOR: null` in the
post-A10 protocol. If a future slice wants liquidation data, the
work is a **separate audit** against a specific vendor's terms,
not a continuation of the current one.
