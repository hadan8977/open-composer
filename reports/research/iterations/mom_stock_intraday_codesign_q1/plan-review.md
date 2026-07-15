# UltraCode Plan Review: mom_stock_intraday_codesign_q1

## Scope

- Review target: Q.0 knowledge memory, source evidence bindings, frozen candidate manifest, and iteration gates.
- Safety boundary: no active spec, broker, paper-order, credential, training, or backtest changes.
- Acceptance: no unresolved P0/P1, focused tests pass, knowledge assessment passes, and iteration validation passes.

## Adversarial Findings And Resolutions

1. Restricted challenge or forward outcomes could be downgraded by declared provenance.
   Resolution: inferred restricted partitions take precedence; provenance may only upgrade a record into a restricted partition.
2. Current source-card exclusion did not bind the brief's exact claim.
   Resolution: source-card claim and brief claim now have separate fingerprints and both are validated.
3. A pre-iteration baseline could inherit verification metadata from current source cards.
   Resolution: the baseline is rebuilt from raw prior occurrences after excluding all current iteration locations.
4. Candidate rows and referenced specs were mutable after preregistration.
   Resolution: the manifest binds its own SHA256 plus every referenced spec content hash; dossier validation rejects drift.
5. Local and private URL aliases could enter external knowledge memory.
   Resolution: non-Web schemes, credentials, local suffixes, non-global IPs, DNS aliases, and legacy decimal/octal/hex IPv4 forms are rejected with adversarial tests.

## Verification

- `uv run ruff check open_composer/research/knowledge_memory.py tests/test_knowledge_memory.py`
- `uv run pytest -q tests/test_knowledge_memory.py`
- `uv run oc research knowledge scout mom_stock_intraday_codesign_q1`
- `uv run oc research knowledge assess mom_stock_intraday_codesign_q1 --json`
- `uv run oc research iteration validate mom_stock_intraday_codesign_q1 --json`

## Verdict

Final independent verdict: `GO`; no unresolved P0/P1 remains. Passing Q.0 authorizes Q.1 feasibility work; it is not evidence of strategy alpha, LLM contribution, paper readiness, or order authority.
