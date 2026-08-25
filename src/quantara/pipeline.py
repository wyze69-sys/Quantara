"""22-step pipeline orchestration.

Executes the approved processing flow in order: descriptor/rights validation,
verified acquisition, safe archive inspection, exact parsing, quality
evaluation, Parquet write/read-back/reconciliation, hashing, immutable
publication, discovery verification, and idempotent rerun detection, exiting
0 PUBLISHED/VERIFIED_NO_OP, 2 BLOCKED, 3 FAILED, 4 QUARANTINED.
"""
