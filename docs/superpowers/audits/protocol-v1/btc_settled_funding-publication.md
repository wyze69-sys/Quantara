# btc_settled_funding — audited publication (S01-C)

**Status:** COMPLETE
**Series:** `btc_settled_funding` (Binance USD-M futures, BTCUSDT settled funding rate)
**Descriptor:** `configs/series/binance-usdm-btcusdt-funding-settled-2020-2024.yaml`
**Published:** all 60 frozen monthly objects, `2020-01` through `2024-12`
**Date:** 2026-09-05
**Baseline:** `main` at `fb71da02d97bc456d8b4e1c33e929aff7c939224`
**Data root:** `D:/PROJECT/Quantara/data` (the real production root; not tracked in Git)

Stop C of the uniform source-packet protocol. S01-B returned provisional quality `PASS`
on all 60 periods with zero `warn` and zero `fail` findings, so **no designed-gap or
duplicate approval record is required and none was created**. This document records the
publication and its independent verification.

## 1. Publication

| Measure | Value |
| --- | --- |
| Periods in frozen inventory | 60 |
| Periods published | 60 |
| Terminal states | `PUBLISHED` x 60 |
| HTTP requests | 120 (one archive + one adjacent `.CHECKSUM` per period) |
| Requests outside the allowlist | 0 |
| Driver exit code | 0 |
| `stopped_at` | `null` |
| Workers | 1 (F-S01B-1 residual risk: parallel is unreliable against this provider) |

Driver result, verbatim:

```json
{"counts": {"PUBLISHED": 60}, "distinct_urls_contacted": 120, "exit_code": 0,
 "http_rejected_count": 0, "http_request_count": 120, "not_attempted": [],
 "outcome_count": 60, "period_count": 60, "phase": "publish", "preflight": null,
 "series_id": "btc_settled_funding", "stopped_at": null}
```

Preflight refused to proceed unless both held, checked before any write:

- S01-B inventory covers 60 periods and every `quality_state` is `PASS`.
- No `datasets/series/btc_settled_funding` lane existed in the production root, so this
  is a first publication that cannot overwrite an existing series pointer. Observed
  `existing_series_lanes=[]`.

## 2. Independent verification of the published lane

The publish invocation completed all 60 periods and then its own evidence collector
aborted on a stale parse-attempt file left by an earlier smoke test — `parse_scalar_rows`
refuses to overwrite an existing attempt path. Nothing published was affected, but the
run's self-report was lost. Rather than trust it, verification was redone by a separate
script (`verify_publication.py`) reading **only** the published production objects.

| Check | Result |
| --- | --- |
| Authenticated commit graph verified | 60 / 60 |
| `current.json` commit matches the verified graph | 60 / 60 |
| Provider `.CHECKSUM` digest == retained ZIP sha256 == graph `source_sha256` | 60 / 60 |
| Member sha256 == graph `parser_input_sha256` | 60 / 60 |
| Quality recomputed from published bytes | `PASS` 60 / 60 |
| Recomputed `quality_identity` == published `quality_identity` | 60 / 60 |
| Duplicates | 0 |
| Same-key conflicts | 0 |
| Source byte order strictly increasing | 60 / 60 |
| Object ref kinds present per period | `checksum`, `normalized`, `raw` |
| Publication protocol version | `v1` on all 60 pointers |

Aggregate:

```json
{"distinct_commits": 60, "distinct_content_hashes": 60,
 "first_event_utc": "2020-01-01T00:00:00Z", "last_event_utc": "2024-12-31T16:00:00Z",
 "total_conflicts": 0, "total_duplicates": 0, "total_jitter_rows": 2403,
 "total_source_rows": 5481}
```

Per-period row counts are 84, 87, 90 or 93 — three settlements per day for a 28, 29, 30
or 31 day month. Total 5481 equals 1827 days x 3, as established in S01-B.

## 3. Cross-check against S01-B

Every identity recorded in the S01-B temporary-root inventory was compared to the
identity published here: `zip_sha256`, `member_sha256`, `source_rows`,
`canonical_content_hash`, `quality_identity`.

**Mismatches: 0 of 60.** Publishing to the production root reproduced the S01-B result
exactly; the content address is a pure function of the source bytes, not of the lane.

`commit == canonical_content_hash` for all 60 periods, which is the content-addressed
commit scheme behaving as designed.

## 4. Verified no-op rerun

The entire frozen inventory was rerun against the now-published production lane:

```json
{"counts": {"VERIFIED_NO_OP": 60}, "exit_code": 0, "http_rejected_count": 0,
 "http_request_count": 0, "not_attempted": [], "outcome_count": 60,
 "period_count": 60, "phase": "rerun", "series_id": "btc_settled_funding",
 "stopped_at": null}
```

- All 60 terminal states are `VERIFIED_NO_OP`.
- **Zero HTTP requests.** No re-download occurred; the frozen driver recognised every
  period as already published and verified.
- Commit, `canonical_content_hash` and `manifest_sha256` are byte-identical to the
  publish phase for all 60 periods. `IDENTITIES_STABLE True`.

## 5. Pre-existing production identities did not move

S01-A and S01-B carried a caveat: no production pointer snapshot was taken, so the claim
was only "no production root was passed to the pipeline" rather than a before/after
comparison. **That caveat is now closed by measurement.** The full production root was
hashed file-by-file immediately before publishing and again afterwards.

| Measure | Before | After |
| --- | --- | --- |
| Files under the data root | 1408 | 2428 |
| `current.json` pointers | 25 | 85 |

| Check | Result |
| --- | --- |
| Pre-existing files with changed size or digest | **0** |
| Pre-existing files missing | **0** |
| Pre-existing pointers moved | **0** |
| New pointers | 60 (exactly one per published period) |
| Added files outside `datasets/series/` and `attempts/` | **0** |
| Verdict | `PASS: no pre-existing file or pointer moved` |

The 25 pre-existing pointers include the old BTC kline lanes (`1m`, `1h`, `1d` for
2020-2024) and the research, training, validation and evaluation lanes. All are
confirmed unmoved by digest comparison, satisfying phase-gate item 7 with evidence
rather than assertion.

Of the 1020 added files, 900 are the new series lane and 120 are diagnostic attempt
manifests.

## 6. Per-period published identities

| Period | Rows | Commit / content hash | Manifest | ZIP sha256 | Member sha256 | Jitter | Quality |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2020-01 | 93 | `ae73d2e3de3c` | `e111378d7711` | `7f81b2f3694d` | `b566eea750ed` | 14 | PASS |
| 2020-02 | 87 | `40eb8206e215` | `81229168919a` | `6599466d108d` | `e1ff46ee6c1d` | 15 | PASS |
| 2020-03 | 93 | `c5522b9597e4` | `8a8ff13ddc03` | `eee845fde633` | `1ca0430f06cd` | 23 | PASS |
| 2020-04 | 90 | `f2dc622158f4` | `5c77bfbbdc4c` | `d009ce034d08` | `f9f9f1d211c4` | 14 | PASS |
| 2020-05 | 93 | `9bf38027d295` | `fbdba66bfac7` | `3f2b56dd6b9a` | `51e9d27a9c57` | 17 | PASS |
| 2020-06 | 90 | `62de95871f63` | `87b4fa9e27a3` | `30b3470ff985` | `6ad618ae28a1` | 39 | PASS |
| 2020-07 | 93 | `7a1a61bcce7d` | `fa2ebc09c86a` | `18dae7b11075` | `da2268dcb243` | 28 | PASS |
| 2020-08 | 93 | `09acc9108e74` | `6a8f4c278cb1` | `e6f6d1749f67` | `78de37294fb2` | 30 | PASS |
| 2020-09 | 90 | `febb1dc4464f` | `20d9461973bb` | `7ae9a3b6afb2` | `b92ada45ee14` | 48 | PASS |
| 2020-10 | 93 | `c64b6107339c` | `d4afb721f2d5` | `4c55b191c101` | `77b1a0826243` | 43 | PASS |
| 2020-11 | 90 | `8859529c5d61` | `415413148c0a` | `676356a2d075` | `474c0b124cc9` | 53 | PASS |
| 2020-12 | 93 | `660c1a9ce53d` | `ddc8d0978e16` | `d7390f90edf5` | `6450a5b509fb` | 48 | PASS |
| 2021-01 | 93 | `68fff0789eeb` | `7f9bcb2c4d66` | `cff916dc4b63` | `5be276b08532` | 47 | PASS |
| 2021-02 | 84 | `144608b533ad` | `88b3c0cbca2e` | `819a7b107443` | `d163ae55143b` | 53 | PASS |
| 2021-03 | 93 | `f14c916689d4` | `cab8ebf93c51` | `2125fd300848` | `1e1bf39fe6f6` | 47 | PASS |
| 2021-04 | 90 | `c2983a386d29` | `f54ff3eef522` | `9cd888e3b0a1` | `fa2d4f4af93e` | 60 | PASS |
| 2021-05 | 93 | `c9bc184c5773` | `812571c2cf0d` | `ed934afb9cf8` | `7bef9fb0da55` | 66 | PASS |
| 2021-06 | 90 | `d71a77059206` | `692b32ba15a3` | `7b8d9bfb8816` | `838c3a004e80` | 65 | PASS |
| 2021-07 | 93 | `f2bf339e24ae` | `2ea498ba20dd` | `8ab3df641d3b` | `58dbb17f8eca` | 65 | PASS |
| 2021-08 | 93 | `2b8af86c6968` | `c99a6f044be2` | `7eb681cc45b9` | `d90f25a13bb7` | 58 | PASS |
| 2021-09 | 90 | `ba0c55a29f47` | `b4e26e0e11d6` | `03f25a7c25ee` | `5245309395b0` | 62 | PASS |
| 2021-10 | 93 | `5b9c64339e18` | `c96168cd250b` | `f25820d6add6` | `3665c1f20956` | 72 | PASS |
| 2021-11 | 90 | `34f398d00806` | `11af89f781fe` | `e2e6b2d72186` | `007948d31914` | 60 | PASS |
| 2021-12 | 93 | `27aeed4167f4` | `7a1eecd73cd3` | `bf3ce484faf4` | `dc76057b5a7e` | 64 | PASS |
| 2022-01 | 93 | `7185ca6e99eb` | `cbac21266805` | `22ee19079b62` | `58ef13e02a06` | 59 | PASS |
| 2022-02 | 84 | `d9aedc626dc9` | `19522c0e4074` | `fa95088258a9` | `673deb571d8d` | 61 | PASS |
| 2022-03 | 93 | `da0e1317c54e` | `7635667cb1e9` | `4cf0883bc07f` | `91ad72b00344` | 63 | PASS |
| 2022-04 | 90 | `a9f4f5227dcf` | `ef17711cccdf` | `57e2776cc68b` | `17fb657620aa` | 59 | PASS |
| 2022-05 | 93 | `d38373776e98` | `947a8533365c` | `bced8a5013d0` | `6e45c571be54` | 65 | PASS |
| 2022-06 | 90 | `b4226e046104` | `d04c50f8040c` | `0cd0708f8903` | `e4bf4d198700` | 61 | PASS |
| 2022-07 | 93 | `adfb79156eb8` | `126fb285b9ca` | `29d58cce0cd4` | `3a078bd60b69` | 62 | PASS |
| 2022-08 | 93 | `497736006276` | `1a29e3ed38b8` | `6f4f0c6c84c0` | `7a5fd83b9046` | 63 | PASS |
| 2022-09 | 90 | `a68e3affa176` | `2f6be6dc2241` | `d62cd4e13009` | `8bba85a3aaae` | 58 | PASS |
| 2022-10 | 93 | `f713963a7ee4` | `63bef5ffda3b` | `ad9efed10d4c` | `4f513a5a6416` | 64 | PASS |
| 2022-11 | 90 | `ef089354e550` | `1930ca568c09` | `8febe5bec1a0` | `98b0632629a7` | 57 | PASS |
| 2022-12 | 93 | `f409ab51d559` | `1091effedbd2` | `4218c78331bc` | `a7527621060c` | 65 | PASS |
| 2023-01 | 93 | `7d69085d8caa` | `1304889d20b0` | `05e3df32f28d` | `b83a5af33157` | 60 | PASS |
| 2023-02 | 84 | `23f974c5e9df` | `b1129ef55c62` | `5227accd9aaa` | `c346990315d8` | 69 | PASS |
| 2023-03 | 93 | `7041cc4cdb00` | `000c0024ee51` | `ab022adff9b8` | `d776e94a48c8` | 71 | PASS |
| 2023-04 | 90 | `ba9b1a0915f5` | `4107b23fb3f2` | `2931039d2681` | `1c2b6f3e55fb` | 73 | PASS |
| 2023-05 | 93 | `919d0eca4835` | `8f291ee91c07` | `5d026fece46d` | `a979797e9509` | 62 | PASS |
| 2023-06 | 90 | `f10526edd285` | `5cb8050f9ae9` | `3ffdde6f1dc9` | `1d076e090a53` | 16 | PASS |
| 2023-07 | 93 | `34544415a44e` | `25d9c1da7675` | `0304baed9fd4` | `65c6e99359aa` | 9 | PASS |
| 2023-08 | 93 | `b91d101555d8` | `2209fd2f9627` | `516a8f50631c` | `e92d6c334b66` | 10 | PASS |
| 2023-09 | 90 | `c9bf1f0723c2` | `d15370845d38` | `3fd9df6fd1ee` | `f7ad0d9e9039` | 7 | PASS |
| 2023-10 | 93 | `277dc5f1e4ea` | `4e67e9dbcba5` | `03105cc14015` | `01d36bd8eccb` | 10 | PASS |
| 2023-11 | 90 | `c39ffc06a759` | `fb1455b76084` | `8015d2997f8d` | `bde8bb8a6a7f` | 11 | PASS |
| 2023-12 | 93 | `3729a2a375cc` | `64e080081ec3` | `8f02fdd2a2da` | `00a808892d8c` | 7 | PASS |
| 2024-01 | 93 | `2c7ef76f69cb` | `ae28e3862d42` | `3e0d30870672` | `232a13d92487` | 15 | PASS |
| 2024-02 | 87 | `91e7ed89025b` | `66497327fefb` | `daf1e4901e3d` | `e08c820f5019` | 11 | PASS |
| 2024-03 | 93 | `d200441bec87` | `8fe0b5dc3921` | `711dcaf2a341` | `1ac0fa4862ab` | 11 | PASS |
| 2024-04 | 90 | `d8f95602eb3d` | `215fba45bd68` | `6d220b8e2815` | `a7dfc9321f21` | 16 | PASS |
| 2024-05 | 93 | `c423f4e5855a` | `455a9cfbfcc7` | `aef8c5fdce14` | `a34fabae463d` | 7 | PASS |
| 2024-06 | 90 | `3329df06c4cb` | `29bc381544f3` | `43fc4473820d` | `7c470eeee314` | 13 | PASS |
| 2024-07 | 93 | `8077e01132ff` | `68c2f592a8f3` | `acab0593c145` | `60d8e545d103` | 13 | PASS |
| 2024-08 | 93 | `b8246039f1ea` | `26f8c809b055` | `7003d29a43dd` | `5031f1d1dde9` | 15 | PASS |
| 2024-09 | 90 | `3e7705a80017` | `9ac3b5eac121` | `6ef23b02392b` | `5ba49e01519e` | 22 | PASS |
| 2024-10 | 93 | `2143897070b0` | `04b3905215b7` | `26db65ac8020` | `c20b8d0f1239` | 14 | PASS |
| 2024-11 | 90 | `6be025024fa6` | `7c2b783f41b5` | `e1b19cccfe2c` | `56722e25782b` | 15 | PASS |
| 2024-12 | 93 | `65dc6bd0854f` | `7a9662fd381a` | `069409f525eb` | `46bd01d8e090` | 18 | PASS |

## 7. Verification gates

| Gate | Result |
| --- | --- |
| `ruff check` on all S01-C scripts | clean |
| Publish driver | 60 `PUBLISHED`, exit 0, 120 requests, 0 rejected |
| Deep verification from published objects | 60 / 60 on every check in section 2 |
| Rerun | 60 `VERIFIED_NO_OP`, 0 HTTP requests, identities stable |
| Production before/after comparison | 0 pre-existing files or pointers moved |
| S01-B cross-check | 0 identity mismatches |
| Full suite on this baseline | 2107 passed, 1 skipped (D09, CI 11m15s) |

## 8. Scope and limits

- No funding-rate value appears in this document or in any evidence JSON. Counts,
  timestamps, hashes, filenames and state names only.
- No approval record exists, because none is required: all 60 periods are `PASS`.
  No approver, no decision time, nothing `authorized: true`.
- Timestamp jitter is preserved exactly: 2403 of 5481 rows carry sub-second offsets from
  their own interval grid, per-period counts 7 to 73. Nothing was rounded, snapped or
  filled.
- No 2025 data was acquired. The frozen inventory ends at `2024-12`.
- Publication artifacts live under the configured data root and are deliberately not
  staged into Git; `/data/` is gitignored. This document is the tracked evidence.
- Residual risk carried from D09: parallel acquisition remains unreliable against this
  provider. Full backfills, including this publication, run `workers=1`.
- Not verified: whether other sources would hit the same provider behaviour, since only
  this series has been acquired.

## 9. Next

S01 is complete: A (source contract), B (inventory and provisional quality) and C
(publication) are all accepted. The Stage 2 completion gate additionally requires
D00-D07 accepted, which they are. Remaining Stage 2 work is the other 12 frozen source
series, S02 through S13.
