"""Canonical rows, row/sequence invariants, and Parquet persistence.

Assembles the fixed 23-column canonical rows from validated source rows plus
descriptor identity fields, enforces every row invariant (OHLC bounds,
positivity, non-negativity, taker-buy subsets, non-nullity) and monthly
sequence invariant (derived expected count, unique strictly ascending open
times, exact 60,000 ms adjacency, exact boundaries), writes the staged
canonical Parquet object under a pinned writer configuration, reads it back
through the approved explicit schema, and reconciles every source row against
every Parquet row via exact decimal-string comparisons — binary floats are
never constructed in any reconciliation path.
"""
