"""Quality evaluator (component 5).

Runs explicit field, row, sequence, boundary, and reconciliation checks; emits
one finding per check with evidence counts; aggregates to PASS / WARN_BLOCKED /
WARN_APPROVED / FAIL under the quality policy where any warning blocks the
golden slice and aggregate scores never gate alone.
"""
