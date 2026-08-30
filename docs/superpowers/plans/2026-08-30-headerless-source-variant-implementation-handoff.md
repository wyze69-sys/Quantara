# Headerless Source Variant — Implementation Handoff

**Date:** 2026-08-30
**Project:** Quantara (`D:\PROJECT\Quantara`)
**Governing design:** `docs/superpowers/specs/2026-08-30-headerless-source-variant-amendment-design.md`
**Amends:** `docs/superpowers/specs/2026-08-24-binance-btcusdt-perpetual-january-2024-data-slice-design.md` §3.3
**Blocker of record:** `docs/research/per-year-feature-distribution-2020-2022.md` §9 (option 1 adopted)

This document is the durable implementation snapshot for the amendment that
admits the headerless monthly Binance Vision CSV variant (2020-01 … 2021-12).
It exists so the work can be resumed or audited without re-deriving anything
from the working tree, and so the observed digests survive the deletion of the
temporary tooling that produced them.

## 1. Why the amendment exists

The 24 official monthly archives covering 2020-01 … 2021-12 contain a single CSV
member whose first line is already a data row. Slice 001 §3.3 states the header
contract as exact, so `parsing.parse_rows` rejects all 24 members with
`source_header_mismatch` and both years report `BLOCKED` — even though their
bytes are retained, checksum-verified, and structurally sound. The boundary is
exact at 2021-12 → 2022-01; there is no mixed month.

The amendment follows the slice 010A precedent: an explicit, versioned, narrowly
allow-listed declaration, never a relaxation of the default contract.

## 2. Already implemented in the working tree

Inspected, not re-authored. Do not revert or rewrite these.

- `src/quantara/descriptor.py`
  - `HEADERLESS_CSV_HEADER_VALUE = "absent"` and
    `HEADERLESS_SOURCE_DATASET_IDS = {binance_usdm_btcusdt_klines_1m_2020,
    binance_usdm_btcusdt_klines_1m_2021}`.
  - `DatasetDescriptor.csv_header_absent: bool = False` (new field, defaulted, so
    `dataclasses.replace` in `pipeline._segment_descriptor` propagates it).
  - `_validate_allowed_hosts(source, dataset_id)` now returns
    `(hosts, csv_header_absent)`. `csv_header` is the only key admitted beside
    `allowed_hosts`; any other value than the literal `absent` is rejected; any
    dataset identity outside the allow-list is rejected.
  - v1 descriptors reject `source.csv_header` outright.
  - `canonical_semantics()` emits `source.csv_header` **only when declared**, so
    every descriptor that omits the key keeps its published JCS bytes
    byte-for-byte.
- `src/quantara/parsing.py`
  - `parse_rows` branches on `descriptor.csv_header_absent`. On the headerless
    path the first line is a data row and line numbering starts at 1; a first
    line that *is* the frozen 12-name header raises `SourceHeaderMismatch`
    ("first line is the exact 12-name header row"); an empty member raises
    "member has no data rows". The default path is byte-for-byte unchanged.
  - All numeric, timestamp, `close_time == open_time + 59,999`, half-open
    membership, `count`, and decimal128(38,18) rules are shared verbatim.
- `src/quantara/manifests.py`
  - `HEADERLESS_PARSER_VERSION = "binance_kline_csv_v1_headerless"` and
    `parser_version_for(descriptor)`. `PARSER_VERSION` is **not** bumped, so
    every published dataset resolves to the unchanged string.
- `src/quantara/pipeline.py`
  - `parser_version_for(descriptor)` in both the identity-evidence block and the
    dataset manifest.
  - `source_header` is `None` under the headerless variant instead of splitting a
    data row into fabricated header evidence.
- `tests/test_parsing.py` — 11 new headerless cases:
  first line parsed as data; all twelve fields bound positionally; declared
  absence with a header present rejected; headered descriptor still requires the
  header; empty member rejected; wrong field count reports line 1; second-line
  wrong field count reports line 2; CRLF and trailing blank lines accepted;
  period and timestamp invariants still enforced; BOM still rejected; the 2021
  identity is also allow-listed.
- `tests/test_descriptor.py` — the unknown-source-key test now matches
  `"may only add 'csv_header'"`.
- `docs/superpowers/specs/2026-08-24-...-data-slice-design.md` — amendment note
  inserted directly after the exact-header paragraph in §3.3.
- `docs/superpowers/specs/2026-08-30-headerless-source-variant-amendment-design.md`
  — the new formal amendment (untracked at handoff time).

## 3. Remaining work

1. Commit the two specification/documentation changes on their own, then push.
2. Recreate `tmp_compute_digests.py` from the `extended_year_1m_descriptor_text`
   fixture, run it, and capture the four real JCS digests.
3. Record those four digests in §6 of this file **before** deleting the tooling.
4. `tests/test_descriptor.py`: add `EXTENDED_YEAR_HEADERLESS_CANONICAL_DIGESTS`
   plus the non-perturbation proof that the plain 2020/2021 descriptors still
   reproduce the already-frozen `EXTENDED_YEAR_CANONICAL_DIGESTS` values.
5. Add `source.csv_header: absent` to the 2020 and 2021 repository dataset
   configs, keeping `quality_policy_version: "1"`.
6. Add the two zero-volume approval records mirroring the 2022 record structure:
   - `configs/quality/approvals/binance-usdm-btcusdt-1m-2020-zero-volume.v1.yaml`
     (2 approved `zero_volume_candle` occurrences)
   - `configs/quality/approvals/binance-usdm-btcusdt-1m-2021-zero-volume.v1.yaml`
     (59 approved `zero_volume_candle` occurrences)
7. Full `python -m pytest`, `ruff check`, `ruff format --check`; fix and rerun
   until clean.
8. Verify 2022–2024 descriptor/canonical non-perturbation explicitly.
9. Delete the temporary digest tooling and output.
10. Commit the implementation on its own with the real digests, real test count,
    and real verification results; push.

## 4. CRLF editing warning

`src/quantara/descriptor.py` and `src/quantara/pipeline.py` are stored with
**CRLF** line terminators. The `patch` tool silently dropped adjacent lines on
these files in the previous session and produced syntax/indentation damage.

For those two files use a literal read → replace → write operation that asserts
the replacement target occurs **exactly once**:

```python
with path.open("r", encoding="utf-8", newline="") as handle:  # preserves CRLF
    text = handle.read()
assert text.count(target) == 1, text.count(target)
with path.open("w", encoding="utf-8", newline="") as handle:
    handle.write(text.replace(target, replacement))
```

`Path.read_text` accepts no `newline` argument before Python 3.13, so the
explicit `open()` form above is the portable one. Build the target/replacement
strings with `\n` and convert them with `.replace("\n", "\r\n")` when the file
under edit contains CRLF, so the same script works on both families.

This is the technique used by `tmp_apply_headerless_edits.py`. Never let an
editor normalize the endings. `tests/test_descriptor.py` is also CRLF;
`parsing.py`, `manifests.py`, `tests/test_parsing.py`, and the spec markdown are
LF. `configs/quality/approvals/*.yaml` are CRLF-terminated — the 2020/2021
records must be written the same way or `verify_self_hash()` still passes (the
digest is over JCS semantics, not the file bytes) but the files would differ in
style from their siblings.

## 5. Digest-generation procedure

`tmp_compute_digests.py` at the repository root, run as `python
tmp_compute_digests.py`:

1. Prepend `src/` and `tests/` to `sys.path`.
2. Import `extended_year_1m_descriptor_text` from `conftest`,
   `load_descriptor` from `quantara.descriptor`, `descriptor_hash` from
   `quantara.hashing`, and `parser_version_for` from `quantara.manifests`.
3. For each of 2020 and 2021, render the plain descriptor text, then build the
   variant by the single substitution

   ```
   "    - data.binance.vision"
   →
   "    - data.binance.vision\n  csv_header: absent"
   ```

4. Write both to `tmp_digest_out/`, load them, and print
   `csv_header_absent`, `parser_version_for(...)`, and
   `descriptor_hash(descriptor.canonical_semantics())` for each.

The plain digests must reproduce the existing frozen
`EXTENDED_YEAR_CANONICAL_DIGESTS` entries exactly; only the variant digests are
new. The same substitution is used by `make_headerless_descriptor` in
`tests/test_parsing.py`, so the fixture and the frozen values cannot diverge.

## 6. Digests observed at implementation time

Real values from `python tmp_compute_digests.py` on 2026-08-30, over the
`extended_year_1m_descriptor_text` fixture. This is the durable snapshot: it
must survive the deletion of the temporary digest tooling.

```
2020 plain:   eb589f21f01499444b832fcbfa611addc5bb2889a2d2b8cedbc926d7551dd7f9
2020 variant: f6f7f579b4b3563581ec53ead3eb37faedf3f03b733715ad91489420fef00cf8
2021 plain:   4e3e359ccaded605e9f82003e99fba81b72f09bfbb359f8a011852293903f19f
2021 variant: c3ed017c8eed270fc02ccbaec568841f0f007bd371ed234f3348ca5d106bac77
```

Accompanying observations from the same run:

- `csv_header_absent` is `False` on both plain descriptors and `True` on both
  variants.
- `parser_version_for` returns `binance_kline_csv_v1` on both plain descriptors
  and `binance_kline_csv_v1_headerless` on both variants.
- The variant JCS `source` object is
  `{"allowed_hosts":["data.binance.vision"],"csv_header":"absent"}`; the plain
  object omits the key entirely.

### 6a. 2022–2024 non-perturbation, measured

Two independent proofs were run, because the first expectation was wrong and the
correction matters for anyone reading this later.

**Wrong expectation, recorded so it is not repeated.**
`EXTENDED_YEAR_CANONICAL_DIGESTS` is frozen over the *conftest fixture* form of a
year descriptor — `quality_policy_version: "1"`, no `quality_approval`. The
committed `configs/datasets/binance-usdm-btcusdt-1m-{2022,2023,2024}.yaml` are
policy `"2"` **with** an approval path, so their digests were never supposed to
equal the fixture digests and never did. Comparing the two is a category error,
not a drift.

**Proof 1 — same config files, baseline code vs amended code.** Digesting the
identical committed descriptors under `git worktree` HEAD (`49cd48b`) and under
the amended tree gives byte-identical JCS digests:

```
2022                                  146a3f96e18ee0654e298aa64e5b468ea9b4d44f911a14ba4e44b8a38d275ec6
2023                                  80ac6d89a3a09f0e76060b4fd8b29bfaa1fdd05e189640127952caef65357391
2024                                  7ffe2a0e0fe17c940c823e516cbeb8d71b9a2f53daad3580aa0f9445cdf63de3
binance-usdm-btcusdt-1m-2024-01.yaml  6a4427b6625768932cdd73c4f6672b89903d2ad57414e8ed8747a7f2beda44dc
binance-usdm-btcusdt-1m-2024-q1.yaml  8079498831e6033e1e04e5006c625b3651c3d6c7d492c7a9511949f0d97dee9a
```

`parser_version_for` resolves `binance_kline_csv_v1` for every one of them. A
third configuration — amended code reading the baseline configs — reproduces the
same five digests, so neither the grammar change nor the config edits moved
anything.

**Proof 2 — independent re-hash from retained bytes.** Reparsing all 36 headered
monthly archives out of `data/objects/raw/sha256/` under the amended parser and
re-deriving the identities from scratch reproduces every value already frozen in
the approval records:

```
2022  rows 525600  fingerprint 6739560e…c4544  content 84e4147f…9882b  identity 6828b5d7…75602
2023  rows 525600  fingerprint 6a65a5ca…31ac3  content 3ab4e5c7…83217  identity c52e095a…23c379
2024  rows 527040  fingerprint f0d6a8dd…724a    content 28137ac3…48db5  identity 10e100b4…343b8
```

All three years still report raw `WARN_BLOCKED` and still resolve the unchanged
parser identity. This is the stronger of the two proofs: it does not trust the
descriptor layer at all, it re-derives the canonical content hash from the source
bytes.

**Correction to design decision 10.** The design anticipated that the frozen
`EXTENDED_YEAR_CANONICAL_DIGESTS[2020]` and `[2021]` entries would have to move.
They do not. The observed plain digests are byte-identical to the already-frozen
values, because `csv_header` enters canonical semantics only when declared and
the fixture that anchors that table does not declare it. The two tables coexist:
`EXTENDED_YEAR_CANONICAL_DIGESTS` continues to anchor the undeclared form for all
four years, and `EXTENDED_YEAR_HEADERLESS_CANONICAL_DIGESTS` anchors the declared
form for 2020/2021 only. Decision 10's permission was therefore not exercised,
which is a stronger result than the design asked for: no frozen digest moves at
all.

## 7. Acceptance criteria

- `python -m pytest` fully green; the pre-amendment suite count grows only by
  the additive headerless cases.
- `ruff check` clean and `ruff format --check` clean.
- The four digests frozen in `tests/test_descriptor.py` equal the four values
  recorded in §6 of this file.
- Plain 2020/2021 digests still equal `EXTENDED_YEAR_CANONICAL_DIGESTS` —
  proving the amendment perturbs nothing that omits the key.
- Variant 2020/2021 digests equal `EXTENDED_YEAR_HEADERLESS_CANONICAL_DIGESTS`.
- 2022 and 2023 entries of `EXTENDED_YEAR_CANONICAL_DIGESTS` unchanged, and
  `parser_version_for` resolves to `binance_kline_csv_v1` for every descriptor
  that omits the key.
- No temporary `tmp_*` script or `tmp_digest_out/` directory remains.
- The 2020/2021 dataset configs stay at `quality_policy_version: "1"`; the
  amendment authorizes parseability, not publication.

## 8. Spec commit message (planned)

```
docs(spec): amend slice 001 §3.3 for the headerless source variant

The 24 official monthly BTCUSDT USD-M 1m archives covering 2020-01 …
2021-12 carry no header line: their first line is already a data row.
The slice 001 §3.3 exact 12-name header contract therefore rejects all
24 members with source_header_mismatch and both years report BLOCKED,
even though the retained bytes are checksum-verified and structurally
sound — 527,040 and 525,600 rows, zero non-60,000 ms adjacencies, zero
duplicate open times, exact UTC boundaries.

This commit records the amendment boundary only; it changes no code.

- The new amendment design admits the variant as an explicit, versioned,
  allow-listed descriptor declaration: source.csv_header: absent,
  permitted only for binance_usdm_btcusdt_klines_1m_2020 and _2021,
  symmetric strictness in both directions, frozen positional binding to
  the same 12-name tuple, per-descriptor parser identity resolution
  (binance_kline_csv_v1_headerless on that path only), truthful null
  source_header manifest evidence, and no schema, hash-contract,
  canonical-column, or quality-policy change.
- The slice 001 design gains an amendment note immediately after the
  exact-header paragraph, so the governing spec is never read without it.

Follows the slice 010A precedent: the default contract is not relaxed, a
narrow declaration is admitted. No published identity moves.
```

## 9. Implementation commit message skeleton

Fill every `<...>` from real output. No placeholder digests, and do not assume
any previously guessed test count.

```
feat(descriptor): admit the headerless 2020/2021 source variant

Implements the 2026-08-30 amendment to slice 001 §3.3. A v2 descriptor
may declare source.csv_header: absent; the parser then treats the
member's first line as a data row and binds fields positionally to the
same frozen 12-name tuple. Nothing else about the source contract moves.

- descriptor: HEADERLESS_CSV_HEADER_VALUE, HEADERLESS_SOURCE_DATASET_IDS,
  DatasetDescriptor.csv_header_absent; source.csv_header is the only new
  key, accepted only as "absent" and only for the two allow-listed 1m
  identities; rejected in v1; emitted into canonical semantics only when
  declared, so descriptors that omit it keep their published JCS bytes.
- parsing: headerless branch with line numbering from 1, symmetric
  rejection when a declared-absent member's first line is the exact
  header, and "member has no data rows" for an empty member. Numeric,
  timestamp, membership, count, and decimal budget policy are shared
  verbatim with the default path.
- manifests: HEADERLESS_PARSER_VERSION and parser_version_for();
  PARSER_VERSION is not bumped, so no published identity moves.
- pipeline: resolves parser identity per descriptor and records
  source_header: null under the variant rather than publishing a data
  row as header evidence.
- configs: 2020 and 2021 1m descriptors declare csv_header: absent and
  stay at quality_policy_version "1". The amendment makes the years
  parseable; it approves no warning and authorizes no publication.
- configs: 2020 and 2021 zero-volume approval records added, mirroring
  the 2022 record, bound to <2020 count> and <59> observed occurrences.

Frozen descriptor digests (JCS canonical semantics):

  2020 plain   <digest>
  2020 variant <digest>
  2021 plain   <digest>
  2021 variant <digest>

The plain values are unchanged from the already-frozen
EXTENDED_YEAR_CANONICAL_DIGESTS, which is asserted in the same test that
freezes the new EXTENDED_YEAR_HEADERLESS_CANONICAL_DIGESTS — the
amendment perturbs nothing that omits the key. 2022 and 2023 digests are
asserted unchanged.

Verification: <N> passed, <extra> in <time> (python -m pytest);
ruff check <result>; ruff format --check <result>.
```

## 10. Scope boundary

The amendment authorizes exactly the descriptor key, parser path, parser-identity
resolution, manifest evidence rule, configs, approval records, and tests above.
It authorizes no publication of 2020 or 2021, no research use of the unblocked
years, and no further relaxation of the source contract. Both years remain at raw
`WARN_BLOCKED` under policy "1".
