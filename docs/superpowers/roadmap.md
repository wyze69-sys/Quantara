# Quantara Roadmap — Protocol v1 Evidence Program

**Status date:** 2026-08-31
**Current branch:** `protocol-v1-p00-freeze`
**Current gate:** P00 accepted; P01 is next
**Authoritative routing index:** [`plans/2026-08-31-protocol-v1-freeze-and-canonicalization-master-plan.md`](plans/2026-08-31-protocol-v1-freeze-and-canonicalization-master-plan.md)

## 1. Honest current state

Quantara already has a verified archive-to-canonical pipeline and canonical BTCUSDT perpetual OHLCV covering 2020–2024. The former four-feature OHLCV 24-hour-direction line was terminated after preregistered multi-year evidence: it did not beat the required baselines. That negative result is final for that modeling line; it is not a reason to weaken the evidence standard.

The active program is now **Protocol v1**: freeze the scientific question first, canonicalize exactly the frozen raw inventory, build a point-in-time hourly research table, and run one locked multi-year experiment. A profitable or positive result is not promised. A defensible null result is a valid completion state.

## 2. Frozen scope

The canonical Protocol v1 inventory is fixed to:

- Existing BTCUSDT perpetual traded-price OHLCV, 2020–2024.
- BTC settled funding, open interest, mark price, index price, native premium, Binance spot, and Kraken XBT/USD spot.
- ETH perpetual traded price, settled funding, open interest, mark price, index price, and native premium.

No additional datasets enter before the locked experiment completes. In particular, liquidations, options, long/short ratios, taker ratios, altcoins, order books, macro, on-chain, sentiment, news, and new technical-indicator searches are excluded.

Native premium is the preregistered futures-dislocation feature. Constructed mark/index basis remains diagnostic. ETH open interest starts on 2021-12-01, is never zero-filled, and belongs only in the identical-common-sample M3b ablation.

## 3. Execution and acceptance model

Work advances through one bounded packet at a time:

> Zcode implementation → local commit and evidence → Hermes independent audit → correction if required → `ACCEPTED` → next packet

Zcode does not execute an entire stage, self-accept, push, merge, or auto-advance. Hermes verifies the actual diff, tests, runtime behavior, hashes, quality decisions, publication graph, and protocol compliance. The durable repository rules are in [`AGENTS.md`](../../AGENTS.md).

## 4. Four-stage program

### Stage 1 — Scientific freeze: P00–P02

**Purpose:** Make the scientific semantics and the 2025 blind seal mechanically enforceable before data work expands.

- **P00 — Protocol v1 specification and contract:** `ACCEPTED`
  - Frozen semantic SHA-256: `91457d3f1497abfd4e20cf4624768a5d9e9ba4b4478008fb4c7f65c17d90c65a`
  - Frozen Markdown SHA-256: `9aaa9d76557d76ced7a5c0cff20a02dbb7f735f555a8e696c3289dfe3963ec68`
  - Text-reference hash basis: UTF-8 with CRLF/CR normalized to LF before SHA-256.
- **P01 — Machine-readable protocol verification tools:** `NEXT`
- **P02 — 2025 tamper-protection and access guard:** `BLOCKED ON P01 ACCEPTANCE`

No source implementation, feature generation, model training, or 2025 access may bypass this stage.

### Stage 2 — Shared data platform plus BTC funding vertical slice: D00–D07, S01

**Purpose:** Establish the common descriptor, schema, provenance, quality, gap-mask, manifest, publication, and audit infrastructure, then prove it against one complete real series before scaling.

**Status:** `BLOCKED ON STAGE 1 ACCEPTANCE`

### Stage 3 — Remaining 12 source series: S02–S13

**Purpose:** Canonicalize each remaining frozen source separately, using source-specific acquire/normalize/publish packets and an independent acceptance gate for every series.

**Status:** `BLOCKED ON STAGE 2 ACCEPTANCE`

No source may be zero-filled, silently interpolated, or promoted with unresolved quality warnings.

### Stage 4 — Point-in-time research and locked evaluation: H00–H07, E00–E04

**Purpose:** Build the authenticated hourly feature/label table, rehearse only on the 2020–2021 design period, then run the locked 2022–2024 experiment.

**Status:** `BLOCKED ON STAGE 3 ACCEPTANCE`

The 2025 window remains blind-sealed. It may be evaluated exactly once only if the frozen 2022–2024 gate passes and all protocol preconditions authorize release.

## 5. Acceptance end states

Protocol v1 is complete when one of these evidence-backed outcomes is reached:

1. The locked candidate clears every preregistered gate, followed by the authorized single 2025 evaluation.
2. The candidate fails a gate and the program reports the null result without accessing 2025.
3. A data-quality, provenance, legal-use, or seal-integrity failure blocks the experiment and is reported honestly.

Failure to find predictive edge is not an engineering failure. Bypassing the protocol, surrendering multiple years of evidence to a single point, or opening 2025 early would be.

## 6. Deferred product work

Live collection, signal serving, backtesting with execution costs, portfolio construction, order execution, customer-facing APIs, and commercial deployment are outside Protocol v1. They require separate scientific, legal-use, security, and production-readiness decisions after this evidence program concludes.

## 7. Superseded roadmap material

The former slice-013/014 expansion and broad P2 roadmap are superseded for the duration of Protocol v1. Specifically, their long/short-ratio, taker-ratio, ordinary-2025-holdout, and open-ended dataset/model expansion directions are not authorized by the current frozen protocol.
