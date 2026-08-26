# Quantara

![Quantara — foundation-stage, correctness-first market-data infrastructure specified but not implemented](docs/assets/quantara-header.svg)

> **FOUNDATION-STAGE — SPECIFIED, NOT IMPLEMENTED**
> Quantara currently publishes engineering contracts and repository standards. It does not yet ship executable ingestion, market-data, machine-learning, backtesting, or trading software.

**No trading signals. No production execution. No performance claims.**

Quantara is correctness-first infrastructure for reproducible market-data and machine-learning research. Its first bounded target is an auditable archive-to-canonical data slice for Binance USD-M `BTCUSDT` perpetual one-minute data from January 2024.

[Read the first data-slice specification](docs/superpowers/specs/2026-08-24-binance-btcusdt-perpetual-january-2024-data-slice-design.md) · [Review the roadmap](#roadmap) · [Contribute](CONTRIBUTING.md)

## Why Quantara exists

Quantitative research can look reproducible while depending on data that was unavailable at decision time, silently incomplete, numerically ambiguous, or transformed without verifiable provenance. Quantara treats those failures as contract violations—not modeling details.

The project is being built one bounded vertical slice at a time. Each slice must make its source, legal-use decision, temporal assumptions, canonical representation, quality state, and content identity reviewable before broader capabilities are added.

## Specified design invariants

These are **specified requirements, not claims about running software**:

- **Point-in-time-aware consumption:** later knowledge must not enter an earlier research decision.
- **Exact canonical values:** currency and volume fields use decimal-safe representations rather than binary floating point.
- **Temporal validation:** validation respects event order; random train/test splitting is out of scope.
- **Deterministic content identity:** logical content receives deterministic SHA-256 identity, while each operational attempt retains separate timestamped and UUID-addressed evidence.
- **Quality-gated publication:** **No canonical promotion without `PASS`**.
- **Immutable canonical content:** publication produces content-addressable, verifiable artifacts rather than silently replaced datasets.

For the first historical slice, nominal closed-candle availability is recorded and same-close execution assumptions are forbidden. The archive does **not** reconstruct historical exchange publication time, receipt time, network latency, processing latency, or order latency. Point-in-time safety is therefore bounded by the timestamp evidence actually available.

## Current bounded scope

The approved first slice specifies:

- Binance USD-M Futures;
- `BTCUSDT` perpetual;
- one-minute klines;
- January 2024 UTC;
- archive-first acquisition and canonical normalization.

Live collectors, higher-timeframe derivation, features, labels, models, backtesting, execution, APIs, and user interfaces are not current capabilities.

## Specified first-slice flow — not implemented

```mermaid
flowchart TB
    X[Validated descriptor] --> L{Acquisition legal-use<br/>gate permits action?}
    L -->|Eligible| A[Provider archive]
    L -->|Blocked| J[Attempt evidence]
    A --> B[Unique staging]
    B --> C{Integrity, schema, row,<br/>and sequence validation}
    C -->|Verified| D[Content-addressed<br/>raw object]
    C -->|Failed| Q[Optional diagnostics<br/>or quarantine]
    D --> E[Normalize, write,<br/>read back, reconcile]
    E --> F{Quality state<br/>exactly PASS?}
    F -->|No| Q
    F -->|Yes| P{Publication legal-use<br/>gate permits commit?}
    P -->|No| J
    P -->|Yes| G[Immutable dataset commit]
    G --> H[Atomic current.json promotion]
    H --> I[Discovery read-back verification]
    G --> K[Content manifest<br/>and quality evidence]
```

This summary preserves the first slice’s key boundaries: separate legal-use gates for governed operations, unique staging, verified raw retention, normalization reconciliation, an exact `PASS` gate, immutable commit publication, atomic `current.json` promotion, and discovery read-back. Every acquisition attempt—including legal rejection, validation failure, quality ineligibility, operational failure, and success—must produce the attempt evidence required by the specification. Deterministic content identity remains distinct from per-attempt operational provenance.

## Current specification

The [Binance BTCUSDT perpetual January 2024 data-slice design](docs/superpowers/specs/2026-08-24-binance-btcusdt-perpetual-january-2024-data-slice-design.md) is the authoritative contract for the first vertical slice. Its detailed schema, hashing rules, timestamp semantics, legal-use states, and publication invariants are not duplicated here.

## Repository map

```text
.
├── .github/                 Issue forms and pull-request controls
├── configs/
│   ├── datasets/            Version-controlled dataset descriptors
│   └── legal/               Versioned provider-rights records
├── docs/
│   ├── assets/              Deterministic repository visual sources
│   └── superpowers/
│       ├── plans/           Approved bounded implementation plans
│       └── specs/           Reviewed technical contracts
├── src/quantara/            Implementation package (layout below)
├── tests/                   Test suite mirroring the module layout
├── data/                    Runtime artifacts; Git-ignored, never committed
├── CITATION.cff             Preferred citation metadata
├── CODE_OF_CONDUCT.md       Community standards and private reporting
├── CONTRIBUTING.md          Correctness-first contribution workflow
├── LICENSE                  Apache License 2.0
├── SECURITY.md              Private vulnerability reporting policy
└── README.md                Repository front door
```

### Package layout

`src/quantara` is intentionally a flat module package at its current size;
the architecture is expressed through module docstrings, module naming, and
the mirrored test layout rather than nested folders:

- **Contracts and validation:** `descriptor.py`, `derive_descriptor.py`, `errors.py`, `jcs.py`
- **Ingest:** `acquisition.py`, `archive.py`, `parsing.py`
- **Canonical transform:** `canonical.py`, `hashing.py`, `aggregation.py`, `quality.py`, `derive_quality.py`
- **Publication:** `publication.py`, `manifests.py`
- **Orchestration:** `pipeline.py`, `derive_pipeline.py`, `cli.py`

Nested subpackages will be introduced deliberately, through a reviewed plan,
when a second domain lane (features and labels) lands — not before.

No empty API, tutorial, package, source, or speculative architecture directories are maintained before real artifacts exist.

## Roadmap

### Implemented and verified

- No executable market-data or ML capabilities yet.

### Specified but not implemented

- The Binance USD-M `BTCUSDT` perpetual one-minute archive-to-canonical slice for January 2024.
- Descriptor validation, operation-specific legal-use gates, unique staging, integrity validation, deterministic content identity, immutable publication, and attempt/content evidence.

### Planned

- Higher-timeframe derivation from the canonical one-minute base.
- Feature and label contracts with leakage-resistant temporal validation.
- Research evaluation and calibration workflows.

Live collection, forecasting models, backtesting, portfolio construction, and order execution require separate design and verification gates.

## Engineering and contribution standards

The required sequence is:

> Define → Risk-review → Design → Test → Bounded implementation → Verification → Stabilization

A contribution is not accepted because it is plausible or because unit tests happen to be green. Review must address temporal ordering, leakage risk, provenance, legal-use state, deterministic serialization, failure paths, and live behavior where applicable.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the contribution contract, [SECURITY.md](SECURITY.md) for private vulnerability reporting, and [`CITATION.cff`](CITATION.cff) for citation metadata.

## Licensing, data rights, and responsible use

Original Quantara repository material is licensed under the [Apache License 2.0](LICENSE). That license does **not** relicense third-party market data, exchange/provider content, trained artifacts, model weights, names, or trademarks.

Raw and normalized Binance artifacts for the first slice remain restricted to private/internal evaluation while commercial-use rights are unresolved. Users are responsible for provider terms, data rights, and applicable law.

Quantara is research and engineering software. It is not investment advice, a recommendation, a representation of expected performance, or a warranty of data fitness. Financial markets involve substantial risk; users remain responsible for independent validation and decisions.

## Data foundation status

Slice 001 (Binance USD-M BTCUSDT perpetual, one-minute klines, January
2024) is implemented and verified end to end: checksum-verified acquisition,
exact-decimal normalization, full row reconciliation, immutable
content-addressed publication, and idempotent reruns.

All artifacts for this slice are restricted to internal use while
commercial-use rights remain under review; nothing here is customer-facing
or commercially production-eligible.

Configuration lives in
[configs/datasets/binance-usdm-btcusdt-1m-2024-01.yaml](configs/datasets/binance-usdm-btcusdt-1m-2024-01.yaml);
the governing provider-rights record is
[configs/legal/binance-usdm-provider-rights.v1.yaml](configs/legal/binance-usdm-provider-rights.v1.yaml).

A versioned amendment,
[configs/legal/binance-usdm-provider-rights.v2.yaml](configs/legal/binance-usdm-provider-rights.v2.yaml),
now authorizes internal analytical computation over already-retained
artifacts while counsel review remains pending; v1 stays the binding record
for published datasets, and training, commercial production, customer
display, and redistribution remain ineligible.

## Derived datasets status

The 1-hour (744 bars) and 1-day (31 bars) klines for January 2024 are
derived internally from the verified January 2024 one-minute base dataset
and published through the same immutable, content-addressed protocol with
full lineage back to the parent commit.

All derived artifacts inherit the parent's restrictions completely: they are
internal-use only and remain ineligible for commercial use or customer
display while commercial rights are pending counsel review.

## Research tables status

The first research table (`btcusdt_core_v1`: four causal decimal features,
two strictly-forward 24-bar labels, single-rounding `Q18` storage
quantization) is computed from the verified 1h parent commit and published
through the same immutable protocol with lineage-bound addresses, PASS-only
quality gating, and exact designed-null budgets. Like everything else here it
is strictly internal-use: gated on `analyze_internal` under rights v2, never
customer-facing, redistributable, or commercially eligible.
