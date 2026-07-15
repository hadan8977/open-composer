# Step 9.P Plan Review

## Verdict

Proceed after amendments. The plan is implementable without active-spec or broker changes, but historical multimodal Alpha cannot be guaranteed because licensed transcript/news history and a pristine LLM holdout are not presently available.

## Findings

- P0 resolved: A passive index would only reorganize old material. The plan now requires a versioned scout manifest, canonical dedupe, freshness checks and explicit new/refreshed/conflicting candidate output.
- P0 resolved: Research memory can leak challenge outcomes into future candidate generation. Knowledge is partitioned into public literature, train-only empirical evidence, challenge results and forward observations.
- P0 resolved: Reusing a serialized estimator is not equivalent to retaining valid knowledge. Model memory now includes data, feature, prompt, validation and failure provenance, and requires an explicit reuse/retrain reason.
- P0 resolved: Retrospective LLM processing can contain model-training-time future knowledge. Historical outputs require input-grounded evidence spans and remain exploratory; formal evidence starts at the frozen forward epoch.
- P1 open external gate: SEC access requires a configured product User-Agent/contact identity. Missing configuration must block live filing collection rather than invent an identity.
- P1 open external gate: Earnings-call transcripts require a licensed source. No scraper or fixture may be represented as real historical coverage.
- P1 open external gate: Alpha Vantage credentials are absent; GDELT coverage and entity resolution need measured evidence before use.
- P1 accepted negative path: If real history is insufficient, P.2 may only produce infrastructure, retrospective diagnostics and forward challengers. Research and LLM-contribution status remain false.
- P2 resolved: The complete benchmark family, 24-candidate cap, matched ablations, missing-modality fallback and shuffled/stale placebos are preregistered.
- P3 resolved: New dossier enforcement must be opt-in through `knowledge_contract` so older completed iterations remain valid.

## Acceptance

Implementation may start when `oc research iteration validate mom_multiasset_multimodal_r3 --stage pre-backtest` passes. P.2 training additionally requires a passing knowledge assessment and multimodal capability/PIT report.
