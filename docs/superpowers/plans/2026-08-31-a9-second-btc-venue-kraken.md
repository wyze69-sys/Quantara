# A9 — Second BTC venue selection: Kraken XBT/USD

**Status:** COMPLETE
**Selected venue:** **Kraken spot XBT/USD**
**Verdict:** **KEEP WITH EXPLICIT GAPS AND INTERNAL-USE RIGHTS RESTRICTION**

Kraken wins on first-party bulk provenance, independent venue operation, 2020–2024 coverage, reproducibility, and lower acquisition complexity than API-paginated alternatives. This is a data-quality selection made before predictive comparison.

## Candidate decision

- **Kraken:** selected. First-party-linked bulk OHLCVT archive and separate time-and-sales archive.
- **Coinbase:** not selected. Independent and first-party, but candles require extensive pagination, the API documents missing no-tick intervals, and market-data licensing is restrictive.
- **Bitstamp:** not selected. Independent and long-lived, but 1,000-observation API pages create more acquisition complexity and commercial use requires a data license.
- **Gemini:** not selected. Independent, but no comparably clear full-history bulk OHLCVT archive and greater agreement overhead.

Venue selection is frozen to Kraken for this protocol. A poor predictive result cannot trigger venue shopping.

## Primary evidence

Kraken support page: `https://support.kraken.com/articles/360047124832-downloadable-historical-ohlcvt-open-high-low-close-volume-trades-data`

Operator-linked Google Drive archive ID: `1ptNqWYidLkhb2VAKuLCxmp2OXEfGO-AP`

- Remote archive size: 7,885,068,519 bytes
- ZIP members: 24,056
- Selected member: `master_q4/XBTUSD_60.csv`
- Member SHA-256: `b45e7ce94911d4c1d13bf5c2e270c9219b81631292f7c40bab27e81f7f3f8297`
- Member CRC32 from central directory: `c351083a`
- Probe fetched only 4,769,638 bytes through HTTP ranges while verifying the ZIP central directory and member payload.

Reproducibility:

- Probe: `temp/probe_a9_kraken_range_v1.py`
- Probe SHA-256: `54af490a94023b458b0627acb09d0422c7865b879720071787338cc5e434182c`
- Sidecar: `temp/audit_a9_kraken/a9_kraken_range_probe_v1.json`
- Sidecar SHA-256: `d90cadf07b59c113656518523c6dc257e5971c17ed50546e91d25a6c55a55f33`
- Fresh execution: 2026-08-31, exit 0

Kraken publishes no adjacent operator checksum sidecar for this Google Drive object. The computed member SHA-256 anchors this retrieval but is not a Kraken signature.

## 2020–2024 hourly coverage

- Expected UTC hours: 43,848
- Rows: 43,828
- Distinct timestamps: 43,828
- Duplicate timestamps: 0
- Missing hours: 20

Per year:

- 2020: 8,783/8,784
- 2021: 8,754/8,760
- 2022: 8,760/8,760
- 2023: 8,759/8,760
- 2024: 8,772/8,784

Missing UTC hour starts:

- 2020-10-24 17:00
- 2021-01-29 16:00
- 2021-07-23 03:00, 04:00, 05:00, 06:00, 18:00
- 2023-05-07 20:00
- 2024-01-08 09:00, 10:00
- 2024-01-20 17:00, 18:00, 19:00, 20:00
- 2024-04-01 03:00
- 2024-04-14 08:00, 09:00, 10:00, 11:00, 12:00

Kraken documents candle timestamps as interval starts and can omit intervals with no trades. Therefore an absent hour is not automatically an archive defect. It remains null unless first-party time-and-sales evidence proves there were no trades and the frozen protocol explicitly defines a zero-trade candle policy.

## Point-in-time use

- Use only completed Kraken candles after interval close plus measured/conservative ingestion delay.
- Preserve Kraken’s interval-start timestamp and derive close eligibility separately.
- No forward fill across missing hours.
- Cross-venue features require both Kraken and Binance observations to be valid at the same prediction origin.
- Archive file publication is ex-post provenance, not event-time availability.

## Independence

Kraken is operated by Payward/Kraken legal entities and a separate trading engine. It is organizationally and operationally independent from Binance. Statistical BTC price correlation does not invalidate venue independence.

Regulatory/entity source: `https://support.kraken.com/articles/where-is-kraken-licensed-or-regulated`

## Rights

The support archive and Kraken institutional API materials support internal download, analysis, research, and backtesting. No explicit public license was found granting commercial redistribution of raw or near-raw OHLCVT.

Allowed posture:

- Internal Quantara research and model development.
- Store hashes and derived internal features.

Not cleared:

- Raw CSV redistribution.
- Customer download/API access to reconstructable Kraken data.
- Commercial market-data display.

Obtain written Kraken permission or a data agreement before those uses. This is a project risk classification, not legal advice.

## Remaining implementation gate

Protocol v1 operates hourly, so the verified `XBTUSD_60.csv` is sufficient for the proposed hourly second-venue family. If production implementation chooses to derive hourly values from `XBTUSD_1.csv`, the 1-minute member must receive its own full timestamp, duplicate, OHLC-invariant, hash, and time-and-sales spot-check before publication.

## Final A9 decision

Choose **Kraken XBT/USD** and freeze it before predictive testing. Keep it only as an optional incremental family that must beat the same model without Kraken under the frozen multi-year Brier/calibration gate.
