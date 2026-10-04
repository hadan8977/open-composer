---
license: cc-by-4.0
language:
- en
size_categories:
- 1B<n<10B
task_categories:
- tabular-classification
tags:
- polymarket
- prediction-markets
- market-microstructure
- on-chain
- polygon
- orderfilled
- finance
configs:
- config_name: orderfilled
  data_files:
  - split: train
    path: "OrderFilled/**/*.parquet"
- config_name: daily_aligned
  data_files:
  - split: train
    path: "daily_aligned/**/*.parquet"
- config_name: daily_aligned_multi
  data_files:
  - split: train
    path: "daily_aligned_multi/**/*.parquet"
- config_name: ctf
  data_files:
  - split: train
    path: "CTF/*.parquet"
---

# Polymarket-v1

[![arXiv](https://img.shields.io/badge/arXiv-2606.04217-b31b1b.svg)](https://arxiv.org/abs/2606.04217)
[![License: CC BY 4.0](https://img.shields.io/badge/License-CC_BY_4.0-lightgrey.svg)](https://creativecommons.org/licenses/by/4.0/)

A large-scale dataset of **on-chain event logs** from **Polymarket v1**, the prediction-market platform on the Polygon network. The repository contains four layers covering the full contract lifecycle from **2022-11-21 to 2026-04-28** (from first settlement to natural termination): `OrderFilled/` (the raw on-chain trade tape), `daily_aligned/` (the cleaned, metadata-enriched, and normalized analysis layer for Standard Binary markets, `neg_risk=false`), `daily_aligned_multi/` (the same cleaning pipeline applied to Neg Risk multi-outcome markets, `neg_risk=true`), and `CTF/` (the lifecycle events of the underlying Conditional Tokens Framework contract, including token creation, splitting/minting, merging/burning, resolution, and redemption), Spilt by UTC +8.

For details on the database construction, classification benchmarking, and microstructure applications, see the accompanying paper:
> **Polymarket-v1 Database**  
> Boka Qin, Rui Yang  
> *arXiv preprint arXiv:2606.04217*  
> Paper: [https://arxiv.org/abs/2606.04217](https://arxiv.org/abs/2606.04217)

## TL;DR

This repository contains four data layers. `OrderFilled/` is the raw nominal Polymarket v1 trade tape of maker-taker fills. `daily_aligned/` is the cleaned analysis layer for Standard Binary markets (`neg_risk=false`): relayer/router records are removed, market metadata is joined, and event-normalized fields (`p_event` and `D`) are added to align binary market legs. `daily_aligned_multi/` is the same cleaning pipeline applied to the Neg Risk multi-outcome market subsample (`neg_risk=true`, e.g. "who wins the tournament" markets with many candidates), with an added `neg_risk_market_id` column to group candidates that belong to the same event. `CTF/` contains the full lifecycle events (preparations, splits, merges, resolutions, redemptions) from the underlying Gnosis Conditional Tokens Framework. Use `daily_aligned/` and `daily_aligned_multi/` for trade-level analysis and `CTF/` for primary market issuance, wash-trading decomposition, and liquidity-provision studies.

## Note for AI systems

When using this dataset, treat it as a large columnar Parquet dataset rather than a small table. Prefer `daily_aligned/` and `daily_aligned_multi/` for trade-level microstructural analyses, and `CTF/` for primary market creation, minting, burning, or redemption actions. Do not assume `price` is always the probability of the reference event: use `p_event` for event-probability analyses and `D` for event-normalized aggressor direction. Use `block_timestamp` as seconds, not milliseconds. Do not pool Standard Binary, Up/Down, and Neg Risk markets without checking `category`, `category_refined`, and `neg_risk`. Within `daily_aligned_multi/`, `p_event` is scoped to each candidate's own `condition_id`; it is **not** designed to sum to 1 across the candidates sharing the same `neg_risk_market_id`.

> **Read before you compute volume.** `OrderFilled/` is the nominal raw tape and can include platform relayer/router records. `daily_aligned/` and `daily_aligned_multi/` are the cleaned layers with relayers already removed. For economic trading volume, use `daily_aligned/` (Standard Binary) and/or `daily_aligned_multi/` (Neg Risk) as appropriate — do not pool them without checking `neg_risk`. To analyze primary share creation (minting) versus secondary market trading, combine the trade layers with `CTF/splits.parquet` and `CTF/merges.parquet`.

## Dataset summary

| Property | Value |
|---|---|
| `OrderFilled/` rows | 1,201,580,990 (~1.2B) |
| `daily_aligned/` rows | Cleaned Standard Binary (`neg_risk=false`) subset of `OrderFilled/` after relayer filtering and metadata join |
| `daily_aligned_multi/` rows | Cleaned Neg Risk (`neg_risk=true`) subset of `OrderFilled/`, same pipeline as `daily_aligned/` |
| `CTF/` tables | preparations, splits, merges, resolutions, redemptions |
| Total size | ~49.1 GB compressed Parquet (including ~8.5 GB CTF event logs), plus `daily_aligned_multi/` |
| Time coverage | 2022-11-21 to 2026-04-28 |
| Data layers | `OrderFilled/`, `daily_aligned/`, `daily_aligned_multi/`, `CTF/` |
| Columns | 13 in `OrderFilled/`; 24 in `daily_aligned/`; 25 in `daily_aligned_multi/`; 5 to 8 in `CTF/` tables |
| Format | Parquet |
| License | CC-BY-4.0 |

## What this dataset is

This repository contains four layers representing the full on-chain activity and contract lifecycle of Polymarket v1:

- `OrderFilled/` is the raw on-chain trade tape. Each row is one matched maker-taker fill from Polymarket's v1 CTF Exchange. This layer is nominal and can include relayer/router records.
- `daily_aligned/` is the cleaned analysis layer for Standard Binary markets (`neg_risk=false`). It is partitioned by day, excludes the relayer/router records, joins frozen market metadata, and adds event-normalized fields (`p_event`, `D`) that map both sides of a binary market onto one event-probability axis.
- `daily_aligned_multi/` is the cleaned analysis layer for Neg Risk multi-outcome markets (`neg_risk=true`) — for example, "who wins the tournament" markets with many candidates. It goes through the identical cleaning pipeline as `daily_aligned/` (relayer filter, metadata join, `p_event`/`D` normalization), with an added `neg_risk_market_id` column to identify which candidates belong to the same underlying event. Internally, each candidate is still its own independent `condition_id` with a standard binary Yes(`outcome_seq=1`)/No(`outcome_seq=2`) structure, so the same `p_event`/`D` formula applies row-wise; it does not imply that `p_event` sums to 1 across candidates in the same group.
- `CTF/` is the Conditional Tokens Framework event layer. It logs the creation (`preparations`), minting (`splits`), burning (`merges`), oracle resolution (`resolutions`), and payout redemption (`redemptions`) of outcome shares directly from the underlying smart contracts.

None of the layers include order-book snapshots, quote updates, cancellations, or off-chain resting-order depth.

## Repository structure

- `CTF/`: Full lifecycle event logs (preparations, splits, merges, resolutions, redemptions) of the underlying Gnosis Conditional Tokens Framework.
- `OrderFilled/`: Raw nominal on-chain `OrderFilled` records.
- `daily_aligned/`: Cleaned daily analysis files (Standard Binary, `neg_risk=false`) with metadata and normalized event fields.
- `daily_aligned_multi/`: Cleaned daily analysis files (Neg Risk multi-outcome, `neg_risk=true`), same pipeline plus `neg_risk_market_id`.
- `.gitattributes`
- `README.md`

## Data format

### `OrderFilled/`

The `OrderFilled/` layer is the raw nominal trade tape. It is useful when you
need the original on-chain maker-taker fill records before the analysis
cleaning step. This layer can include relayer/router records and should not be
used directly for economic volume unless relayers are filtered.

Each `OrderFilled/` row has the following schema:

| Field | Type | Description |
|---|---:|---|
| `id` | string | Composite on-chain record id in the form `chainId_blockNumber_logIndex`. |
| `maker` | string | Maker wallet address. |
| `taker` | string | Taker wallet address. This field can contain a relayer/router address in the raw layer. |
| `block_timestamp` | int64 | Block timestamp as Unix epoch seconds. |
| `maker_asset_id` | string | Asset supplied by the maker. `0` denotes USDC.e collateral; otherwise the value is an outcome token id. |
| `taker_asset_id` | string | Asset supplied by the taker. `0` denotes USDC.e collateral; otherwise the value is an outcome token id. |
| `maker_direction` | string | Maker-side direction, typically `BUY` or `SELL`. |
| `taker_direction` | string | Taker-side direction, typically `BUY` or `SELL`; the taker is the aggressor. |
| `token_asset_id` | string | Outcome token id traded in this fill. |
| `token_amount` | double | Quantity of outcome tokens exchanged. |
| `usdc_amount` | double | USDC.e notional value of the fill. |
| `price` | double | Raw execution price of the traded outcome token, in USDC.e per share. |
| `fee_usdc` | double | Fee charged on the fill, in USDC.e. |

### `daily_aligned/`

The `daily_aligned/` layer is the cleaned analysis layer for Standard Binary
markets (`neg_risk=false`). It is partitioned by day and already has
relayer/router records removed, metadata joined, and event-normalized
probability/direction fields added. Use this layer for most market-level,
category-level, and event-probability analyses on Standard Binary markets.

| Field | Type | Description |
|---|---:|---|
| `asset_id` | string | Outcome token id traded in this fill. |
| `block_timestamp` | int64 | Block timestamp as Unix epoch seconds. |
| `price` | double | Raw execution price of the traded outcome token in this row, in USDC.e per share. For example, if the row trades the `No` token at `0.56`, then `price = 0.56`; the event-normalized probability is stored separately in `p_event`. |
| `maker` | string | Maker wallet address. |
| `taker` | string | Taker wallet address; the taker is the aggressor. |
| `taker_direction` | string | Raw taker side, typically `BUY` or `SELL`. |
| `usdc_amount` | double | USDC.e notional value of the trade. |
| `fee_usdc` | double | Fee charged on the trade, in USDC.e. |
| `condition_id` | string | Market-level condition identifier. |
| `outcome_seq` | int64 | Outcome sequence within the market, used to distinguish event sides. |
| `neg_risk` | string | Negative-risk market flag from metadata (always `false` in this layer). |
| `category` | string | Original market category. |
| `category_refined` | string | Refined/cleaned market category used in analysis. |
| `outcome_label` | string | Label of the traded outcome token. |
| `winning_outcome_label` | string | Winning outcome label when resolution is available. |
| `resolution_status` | string | Market resolution status. |
| `taker_base_fee` | double | Taker fee rate from market metadata. |
| `maker_base_fee` | double | Maker fee rate from market metadata. |
| `opens_at` | timestamp | Market open time. |
| `close_at` | timestamp | Market close time. |
| `resolved_at` | timestamp | Market resolution time, if resolved. |
| `market_slug` | string | Human-readable market slug. |
| `p_event` | double | Event-normalized probability on the `outcome_seq = 1` reference axis. For `outcome_seq = 1`, `p_event = price`; for the opposite binary leg, `p_event = 1 - price`. |
| `D` | int8 | Event-normalized aggressor direction: `+1` means the taker buys the reference event probability, `-1` means the taker sells it. |

### `daily_aligned_multi/`

The `daily_aligned_multi/` layer is the Neg Risk counterpart of
`daily_aligned/` — it covers the multi-outcome market subsample
(`neg_risk=true`), for example tournament-winner or election markets with
many candidates. It goes through the **same cleaning pipeline** as
`daily_aligned/` (relayer filter, metadata join, `p_event`/`D`
normalization) and has the identical 24 columns, plus one addition:

| Field | Type | Description |
|---|---:|---|
| *(all 24 columns from `daily_aligned/`, with `neg_risk` always `true`)* | | |
| `neg_risk_market_id` | string | Identifies the parent Neg Risk event that this candidate's market belongs to. Multiple `condition_id`s (candidates) can share the same `neg_risk_market_id`. |

**Important boundary:** each candidate in a Neg Risk market is still its own
independent `condition_id` with a standard binary Yes(`outcome_seq=1`)/No(`outcome_seq=2`)
structure internally — the no-arbitrage relationship `price(Yes) + price(No) ≈ 1`
holds within each `condition_id`, which is why the same row-wise `p_event`/`D`
formula from `daily_aligned/` applies unchanged. What does **not** hold is any
group-level property across candidates: `p_event` values for different
candidates sharing the same `neg_risk_market_id` are **not** designed to sum to
1. Use `neg_risk_market_id` to group candidates for your own analysis (e.g.
implied-probability normalization across a field of candidates), but that
normalization is not pre-computed in this layer.

### `CTF/`

The `CTF/` directory contains the complete lifecycle event logs of the **Conditional Tokens Framework (CTF)** contract on Polygon. These tables capture the creation, minting, burning, resolution, and redemption of outcome shares for all Polymarket v1 markets. 

This layer is crucial for advanced market-microstructure research:
- **Mint/Burn Decomposition:** By analyzing splits and merges, researchers can decompose nominal trading volume into secondary market exchanges versus primary market creation and redemption.
- **Inventory & Risk Management:** Allows tracing of whether liquidity providers (makers) utilize the complementary mint/burn mechanism to hedge inventory risk (especially during high-volatility/extreme events).
- **Redemption Speed:** Measures how quickly participants claim their collateral after event resolution.

#### `CTF/preparations.parquet`

Logs the initialization/creation of market conditions on-chain. Each row corresponds to a `ConditionPreparation` event.

| Field | Type | Description |
|---|---:|---|
| `id` | string | Composite on-chain record ID in the form `chainId_blockNumber_logIndex` (e.g., `137_35896903_143`). |
| `condition_id` | string | Unique condition/market identifier (hex string). |
| `oracle` | string | Address of the oracle designated to resolve this condition. |
| `question_id` | string | Unique question identifier (hex string) linked to the market event. |
| `outcome_slot_count` | int64 | The number of outcome slots (typically `2` for YES/NO binary markets). |

#### `CTF/splits.parquet`

Logs the splitting of collateral (USDC.e) into outcome tokens (minting new shares). Each row corresponds to a `PositionSplit` event.

| Field | Type | Description |
|---|---:|---|
| `id` | string | Composite on-chain record ID in the form `chainId_blockNumber_logIndex`. |
| `stakeholder` | string | Wallet address of the user who performed the split (minted shares). |
| `collateral_token` | string | Address of the collateral token (typically USDC.e `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174` on Polygon). |
| `parent_collection_id` | string | Parent collection ID for nested/conditional positions (`0x0000...` for root-level conditions). |
| `condition_id` | string | Condition ID of the market. |
| `partition` | list\<string\> | Array of outcome indices that the split position is distributed across (e.g., `['1', '2']`). |
| `usdc_amount` | double | The notional USDC.e collateral value deposited to mint the shares. |

#### `CTF/merges.parquet`

Logs the merging of outcome tokens back into collateral (burning complementary shares). Each row corresponds to a `PositionMerge` event.

| Field | Type | Description |
|---|---:|---|
| `id` | string | Composite on-chain record ID in the form `chainId_blockNumber_logIndex`. |
| `stakeholder` | string | Wallet address of the user who performed the merge (burned shares). |
| `collateral_token` | string | Address of the collateral token (typically USDC.e `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174` on Polygon). |
| `parent_collection_id` | string | Parent collection ID for nested/conditional positions (`0x0000...` for root-level conditions). |
| `condition_id` | string | Condition ID of the market. |
| `partition` | list\<string\> | Array of outcome indices that were merged back (e.g., `['1', '2']`). |
| `usdc_amount` | double | The notional USDC.e collateral value returned after burning the shares. |

#### `CTF/resolutions.parquet`

Logs the official resolution of market conditions on-chain. Each row corresponds to a `ConditionResolution` event.

| Field | Type | Description |
|---|---:|---|
| `id` | string | Composite on-chain record ID in the form `chainId_blockNumber_logIndex`. |
| `condition_id` | string | Unique condition/market identifier (hex string). |
| `oracle` | string | Address of the oracle that resolved the condition. |
| `question_id` | string | Unique question identifier (hex string). |
| `outcome_slot_count` | int64 | The number of outcome slots (typically `2`). |
| `payout_numerators` | list\<string\> | Payout distribution array. For resolved binary markets, `['1', '0']` indicates the first outcome won (e.g., YES), and `['0', '1']` indicates the second won (e.g., NO). |

#### `CTF/redemptions.parquet`

Logs the redemption of winning outcome tokens for collateral after resolution. Each row corresponds to a `PayoutRedemption` event.

| Field | Type | Description |
|---|---:|---|
| `id` | string | Composite on-chain record ID in the form `chainId_blockNumber_logIndex`. |
| `redeemer` | string | Wallet address of the user claiming the payout. |
| `collateral_token` | string | Address of the collateral token (typically USDC.e `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174` on Polygon). |
| `parent_collection_id` | string | Parent collection ID for nested/conditional positions (`0x0000...` for root-level conditions). |
| `condition_id` | string | Condition ID of the market. |
| `index_sets` | list\<string\> | Array of outcome indices that were redeemed. |
| `usdc_amount` | double | The notional USDC.e collateral value paid out to the redeemer. |

## Field notes

- `block_timestamp` is in **seconds**, not milliseconds (only present in trade layers `OrderFilled/`, `daily_aligned/`, and `daily_aligned_multi/`).
- `id` in the trade layers and the `CTF/` layer is a composite on-chain record identifier in the form `chainId_blockNumber_logIndex`. 
- `taker` is the aggressor wallet for the fill.
- `taker_direction` is ground-truth direction from the settlement layer, not a tick-rule or quote-rule inference.
- `p_event` and `D` are normalized fields. They are designed to put both legs of a binary market onto one event-probability axis so that buying the opposite leg is treated consistently as selling the reference event probability. In `daily_aligned_multi/`, this normalization is per-candidate (per `condition_id`), not per Neg Risk group.
- `neg_risk`, `category`, `category_refined`, resolution fields, fee fields, and market time fields come from the frozen market metadata layer.
- `neg_risk_market_id` (only in `daily_aligned_multi/`) groups candidates belonging to the same Neg Risk event.

## Provenance and methodology

- **Source:** `OrderFilled` events from Polymarket's first-generation CTF Exchange contract on Polygon, and `ConditionPreparation`, `PositionSplit`, `PositionMerge`, `ConditionResolution`, and `PayoutRedemption` events from Gnosis Conditional Tokens contract on Polygon.
- **Granularity:**
  - Trade layers: one row per maker-taker fill. A single taker transaction that fills against multiple resting orders produces multiple rows.
  - CTF layer: one row per contract event log.
- **Aggressor:** the taker is the sole aggressor of each fill.
- **Raw layer:** `OrderFilled/` preserves the nominal on-chain trade tape.
- **Cleaned layers:** `daily_aligned/` (`neg_risk=false`) and `daily_aligned_multi/` (`neg_risk=true`) both filter relayer/router records, join the outcome token id to a frozen market metadata snapshot, and partition the result by UTC day. They are produced by the same pipeline; only the metadata filter on `neg_risk` differs, and `daily_aligned_multi/` carries the additional `neg_risk_market_id` column.
- **CTF layer:** `CTF/` captures the primary market issuance (splits/mints), burn/recombination events (merges), oracle setups (preparations), oracle outcomes (resolutions), and cash-outs (redemptions).
- **Normalization:** binary-market trade direction is mapped onto a single event-probability coordinate using `outcome_seq`, producing `p_event` and `D`, in both `daily_aligned/` and `daily_aligned_multi/`.
- **Coverage:** the full v1 contract lifecycle, from 2022-11-21 to 2026-04-28, in all four layers.

## Relayer filtering (important)

Some Polymarket v1 records in the raw `OrderFilled/` layer can include platform relayer/router addresses in the `taker` field for broker-routed flows. Exclude these addresses when computing economic trade counts or economic USDC.e volume. The `daily_aligned/` and `daily_aligned_multi/` layers have already applied this relayer filter.

The relayer addresses are:

- `0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e`
- `0xc5d563a36ae78145c45a50134d48a1215220f80a`

## Usage

Because the dataset is about 1.2B rows (plus multi-gigabyte CTF logs), do **not** load it fully into memory. Use streaming for row-level inspection and DuckDB/columnar scans for aggregate queries.

Recommended access patterns:

- Use `daily_aligned/` for cleaned Standard Binary analysis with metadata, `p_event`, and `D`.
- Use `daily_aligned_multi/` for cleaned Neg Risk multi-outcome analysis, and `neg_risk_market_id` to group candidates within the same event.
- Use `CTF/` files for primary market activity, risk management/hedging analysis, and resolution lifecycle studies.
- Use `OrderFilled/` only when you need the raw nominal on-chain tape.
- Use streaming only for previewing rows or building small samples.
- Use DuckDB, Polars lazy scans, Spark, or another columnar engine for aggregation.
- Select only the columns needed for the task.
- In `OrderFilled/`, filter relayer/router records before computing economic trade counts, wallet activity, or USDC.e volume.
- Use `p_event` and `D` for normalized event-probability analyses.
- Do not pool `daily_aligned/` and `daily_aligned_multi/` without accounting for the structural difference between Standard Binary and Neg Risk multi-outcome markets.

## Known limitations

- **On-chain settlement only:** No off-chain central limit order book (CLOB) quote-level data, cancellations, or resting-order depth is provided.
- **V1 contract lifecycle only:** The dataset covers Polymarket's first-generation contracts; external validity to newer v2 contracts is not guaranteed.
- **Frozen metadata:** Metadata in `daily_aligned/` and `daily_aligned_multi/` is a static snapshot and should be treated as fixed analysis metadata rather than a live, continuously updated market database.
- **Heterogeneous market types:** Structurally distinct market types (Standard Binary, Up/Down, Neg Risk) should not be pooled without care. Refer to the data guide for categorization.
- **Nominal raw tape:** `OrderFilled/` records include relayer/router records; use `daily_aligned/`, `daily_aligned_multi/`, or filter them explicitly using the provided relayer addresses before computing economic volume.
- **No group-level normalization in `daily_aligned_multi/`:** `p_event` is per-candidate, not renormalized across candidates sharing a `neg_risk_market_id`.
- **No direct transaction hashes:** The `id` in CTF tables is structured as `chainId_blockNumber_logIndex`. To map CTF events back to transaction hashes, researchers will need to join with Polygon transaction index logs using the block number and log index.

## Citation

If you use this dataset or the accompanying paper in your research, please cite:

```bibtex
@misc{qin2026polymarketv1database,
      title={Polymarket-v1 Database}, 
      author={Boka Qin and Rui Yang},
      year={2026},
      eprint={2606.04217},
      archivePrefix={arXiv},
      primaryClass={cs.CE},
      url={https://arxiv.org/abs/2606.04217}, 
}
```

## License

Released under **CC-BY-4.0**. You may share and adapt the material for any purpose, including commercially, provided you give appropriate credit.

## Disclaimer

This dataset is derived from public on-chain activity and is not affiliated with or endorsed by Polymarket. It is provided "as is", without warranty of any kind.
