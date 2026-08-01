# Momentum Family Roadmap - 2026-07-19

## Current State
- Latest real market session: `2026-07-17`.
- R6 and R7: blocked, audit-only.
- Formal-forward start: `2026-07-20`; observations: `0`.
- Selected strategy: none.
- Broker or paper order authority: none.
- R7 final dossier and harness structure: validated.
- R7 paper readiness: explicitly `blocked`.

## Critical Path
1. Preregister a contract-only R8. Do not change factor formulas or economic thresholds. Encode the full multi-symbol target-weight behavior in StrategySpec/backend parity, reject non-finite states, freeze cap and fold boundaries, split pure timing from first-hour filtering, fix benchmark declarations, and replace four-path PBO/permutation gate semantics.
2. Start a new immutable forward data lane after completed sessions exist. Keep R6/R7 snapshots frozen; add daily plus 1m/5m/30m completeness, SIP or independent consolidated comparisons, official-open references, and corporate-action lineage.
3. Run broker-free forward observation first. Log signal IDs, targets, and rebalance intents; collect matched MOO/LOO/delayed/TWAP references. Alpaca paper fills remain lifecycle evidence only.
4. Add filings, news, earnings, and calls through a separate PIT stock sleeve or an effective-dated ETF constituent aggregation. No issuer event may affect an ETF score without identity, membership, weight, first-seen, input, prompt, model, and evidence provenance.
5. Consider paper automation only after contract-valid historical evidence, at least three forward rebalances, at least thirty matched execution observations, promotion, TCA, and safety gates all pass.

## Stop Rules
- No in-place R7 repair or retuning.
- No generic promotion report for the non-parity R7 YAML.
- No fixtures or retrospective text packets as historical evidence.
- No paper orders before explicit readiness and user confirmation.
