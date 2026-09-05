# D12: source_order disposition

## Status
ACCEPTED

## Problem
37 otherwise-complete BTC OI periods (288/288 snapshots, no conflicts, grid-complete) are blocked solely by the `source_order` quality finding. The source CSV delivers rows out of chronological order.

## Key fact
`series_parsing.py:266` already sorts all output by timestamp:

```python
result = ScalarParseResult(
    archive, digest, tuple(unique[t][1] for t in sorted(unique)),
    ...
)
```

The published canonical rows are **identical** whether the source was pre-sorted or not. The `source_ordered` flag is purely informational — it records a property of the source, not a defect in the output.

## Evidence
- 37 periods, each 288/288 distinct snapshots
- All other quality checks pass (grid, boundary, conflicts, duplicates)
- Output sort is deterministic and independent of source order
- First affected: 2024-04-04

## Decision
Remove `source_order` from the quality report's blocking findings. The parse result still records `source_ordered` in its evidence JSON, but it no longer affects the report state. The output is always sorted; the finding has no bearing on publication quality.

## Constraints
- Does not weaken any other quality check
- Does not modify the parser's sort behavior
- Does not affect the 70 `oi_daily_boundary` periods (genuinely incomplete source)
- Governance stays on main; code change in a separate packet
