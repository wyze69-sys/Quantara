# Quantara Provider-Rights Record v2 — Internal Analytical Use (Data Slice 003a)

**Status:** Proposed design; awaiting owner review and approval
**Date:** 2026-08-26
**Project:** Quantara
**Project root:** `D:\PROJECT\Quantara`
**Design scope:** Versioned governance amendment authorizing internal analytical computation, preparing the features/labels lane (slice 003b)
**Governing predecessors:** slice 001 design §17 (legal-use governance); slice 002 design §3.6/§13 (operation-mapping discipline)

## 1. Purpose

The approved roadmap places features and labels next. Both are *analytical* artifacts: they are computed from retained canonical data for research use, which the rights vocabulary governs through `analyze_internal`. That state is `UNKNOWN` in the only existing record (`binance-usdm-provider-rights.v1`), so any feature/label pipeline would be legally blocked before its first test.

Rather than laundering analysis through `normalize_internal`, this slice makes the honest governance move first: a **versioned rights-record amendment**, exactly mirroring how slice 001 originally recorded owner risk acceptance for acquisition, retention, and normalization. It changes no pipeline behavior by itself; slice 003b will gate feature/label computation on `analyze_internal`.

The governing principle is unchanged:

> Preserve source evidence, make every decision explicit, reject ambiguity, and never promote unverified permissions into governed operations.

## 2. Approved decisions inherited

All predecessor decisions remain in force: private repository, internal-only posture while counsel review is pending, owner risk acceptance as a recorded decision (never legal verification), commercial/customer/redistribution states requiring verified `ALLOWED`, descriptors binding to a specific legal record by path, and manifests embedding the loaded `record_id`.

## 3. New decisions

1. **Versioned amendment, never in-place edit.** A new file `configs/legal/binance-usdm-provider-rights.v2.yaml` is added with `record_id: binance-usdm-provider-rights.v2`. The v1 file is preserved byte-for-byte forever as historical evidence; published datasets that reference v1 remain valid with zero identity impact.
2. **Exactly one operation changes.** `analyze_internal`: `UNKNOWN → OWNER_APPROVED_PENDING_COUNSEL`. Rationale must state the boundary explicitly: owner-approved internal analytical computation over already-retained artifacts pending counsel review; outputs remain private, non-customer-facing, non-redistributable, and commercially ineligible.
3. **All other operations carry over verbatim.** Same states, source_terms, per-operation review dates, reviewers, and rationales as v1 (they were reviewed 2026-08-24 and are unchanged). Only top-level `review_date` moves to 2026-08-26, reflecting the amendment review.
4. **Schema stays `quantara.provider-rights/v1`.** The validation grammar is unchanged; document versioning lives in the record id/filename, not the schema string.
5. **Code reclassification is part of this amendment.** `descriptor.APPROVED_INTERNAL_OPERATIONS` gains `"analyze_internal"` so that `permits("analyze_internal")` accepts `OWNER_APPROVED_PENDING_COUNSEL`. This is the only code change. Deliberate friction is intentional: each future reclassification (e.g., `model_train_internal`) requires its own reviewed amendment plus code change.
6. **Anti-laundering freeze.** `model_train_internal`, `commercial_production_eligible`, `customer_display`, and `raw_redistribution` continue to require exact `ALLOWED`. A regression test must pin `permits("model_train_internal") is False` even under an `OWNER_APPROVED_PENDING_COUNSEL` state, so no future YAML edit alone can unlock training.
7. **No descriptor churn.** The three existing dataset descriptors keep referencing v1. Changing their `legal_record` path would alter descriptor hashes and break publication idempotency for settled datasets; it is forbidden. Slice 003b's new feature/label descriptors will reference v2.

## 4. Explicit non-goals

This slice does not include: features or labels code, pipelines, or descriptors (003b); any change to `model_train_internal`; any movement toward commercial production, customer display, or redistribution; edits to the v1 record or any dataset descriptor; schema-version bumps; new providers, periods, timeframes, models, APIs, UI, databases, or services.

## 5. Rights record v2 (authoritative content)

```yaml
schema: quantara.provider-rights/v1
record_id: binance-usdm-provider-rights.v2
provider: binance
reviewer: wyze69-sys
review_date: 2026-08-26
# Versioned amendment of binance-usdm-provider-rights.v1: authorizes internal
# analytical computation over retained artifacts (features/labels lane).
# Owner risk acceptance pending counsel review; never makes any artifact
# commercially production-eligible, customer-facing, or redistributable.
operations:
  acquire_internal:
    state: OWNER_APPROVED_PENDING_COUNSEL
    source_terms: "Binance Terms of Use; data.binance.vision public archives"
    rationale: "Owner-approved internal acquisition pending counsel review."
    review_date: 2026-08-24
    reviewer: wyze69-sys
  retain_raw_internal:
    state: OWNER_APPROVED_PENDING_COUNSEL
    source_terms: "Binance Terms of Use; data.binance.vision public archives"
    rationale: "Owner-approved internal raw retention pending counsel review."
    review_date: 2026-08-24
    reviewer: wyze69-sys
  normalize_internal:
    state: OWNER_APPROVED_PENDING_COUNSEL
    source_terms: "Binance Terms of Use; data.binance.vision public archives"
    rationale: "Owner-approved internal normalization pending counsel review."
    review_date: 2026-08-24
    reviewer: wyze69-sys
  analyze_internal:
    state: OWNER_APPROVED_PENDING_COUNSEL
    source_terms: "Binance Terms of Use; data.binance.vision public archives"
    rationale: >-
      Owner-approved internal analytical computation over already-retained,
      internally acquired artifacts pending counsel review. Outputs remain
      private research evidence: no customer display, no redistribution, no
      commercial production use.
    review_date: 2026-08-26
    reviewer: wyze69-sys
  model_train_internal:
    state: UNKNOWN
    source_terms: "Not exercised; training-use permission under counsel review."
    rationale: "Blocked until counsel resolves training-use permission."
    review_date: 2026-08-24
    reviewer: wyze69-sys
  commercial_production_eligible:
    state: UNKNOWN
    source_terms: "Requires verified ALLOWED; never inferable from public URLs."
    rationale: "Ineligible while commercial-use rights remain unresolved."
    review_date: 2026-08-24
    reviewer: wyze69-sys
  customer_display:
    state: UNKNOWN
    source_terms: "Requires verified ALLOWED; pending-counsel status is insufficient."
    rationale: "No artifact is customer-facing while rights remain unresolved."
    review_date: 2026-08-24
    reviewer: wyze69-sys
  raw_redistribution:
    state: UNKNOWN
    source_terms: "Redistribution of Binance market data is not permitted here."
    rationale: "Raw, normalized, derived, and analytical artifacts stay private."
    review_date: 2026-08-24
    reviewer: wyze69-sys
```

## 6. Validation and regression requirements

- The v2 record loads through the unchanged `load_rights_record` grammar (all eight operations present, exact key sets, valid states).
- Permit matrix regressions: under v1, `permits("analyze_internal")` stays `False`; under v2 it becomes `True`; acquire/retain/normalize behave identically under both records; the four restricted operations are `False` under both regardless of any pending-counsel state.
- The `APPROVED_INTERNAL_OPERATIONS` tuple-content assertion is updated deliberately to the four-operation value as part of this amendment; all other existing tests pass untouched.
- Evidence anchor: SHA-256 of the untouched v1 file at starting HEAD `40ae2b0` is `547fc79c060aba09197e7d22efe6cfd8a94a2f2515f8b8150c7a3cf767e03697`; the plan's final verification re-proves it byte-for-byte.

## 7. Commercial-safety boundary

Nothing here claims legal clearance. `OWNER_APPROVED_PENDING_COUNSEL` remains recorded risk acceptance by the owner/reviewer. All artifacts — raw, normalized, derived, and future analytical outputs — stay private and internal-use only. Counsel review of Binance terms remains open; a future counsel verdict may still overturn this acceptance, in which case a v3 record supersedes v2 and dependent pipelines gate accordingly.

## 8. Foundational risks addressed

Silent permission laundering (mapping analysis onto normalization); accidental invalidation of settled publications through descriptor or record edits; unversioned in-place rights edits destroying historical evidence; training access unlocking through a side door; scope creep into features/labels implementation before the governance gate exists.

## 9. Completion statement

This document is the proposed design boundary for Quantara's rights-record v2 amendment. It authorizes implementation planning, not immediate implementation. Implementation may begin only after the detailed plan is written, reviewed, and approved by the owner, preserving this scope without introducing additional operations, states, descriptors, pipelines, or product behavior.
