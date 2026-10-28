# Owner reporting

This document defines reporting content and delivery. Research method and scientific thresholds live in their own references; a report does not authorize research, spending or orders. Write owner-facing reports in the owner's requested language, currently Chinese. English guidance does not require translating historical reports or quotations.

## 0. Editorial rules

Lead with money, useful research evidence and consequential problems. Separate existing paper/live operations from new research. Explain conclusions in business language; keep task IDs, hashes, internal approval jargon and file paths in the evidence appendix. A report must be understandable without opening attachments.

Use actual dated results, not plans or stale summaries. Address unresolved owner questions from `reports/owner/live-track.json`. Report confirmed quota exhaustion, unavailable inputs or permissions and financial decisions when consequential; do not turn ordinary technical recovery into owner approval. Already-decided matters such as parked DS are not new pending decisions.

### 0.1 Standard report structure

Use the five semantic sections expected by `scripts/owner_report.py lint`, in the owner's language:

1. Conclusions:3–6 concise points covering account outcomes, decisive progress, the main gap and any owner decision.
2. Paper and live operations:ETF sleeves, equity long/short, intraday/HFT and live status; actual orders, fills, rejections, partial/missing receipts, reconciliation, PnL and data dates.
3. Research:question, method, real numbers, economic meaning, limitations, next action and date.
4. Progress on the owner's questions and requirements.
5. Owner decisions:issue, impact, recommendation/options, deadline and what happens without a reply. State none when applicable.

Append evidence paths and detailed inventories. Round reports prioritize the period's increment in roughly600–1200 Chinese characters; daily/weekly reports may expand. Do not repeat unchanged inventories every two hours.

### 0.2 Writers and state

`config/owner-reporting.json` and `config/autonomous-report-target.json` are the current routes. `config/research-agent-roles.json` retains reporting settings only; new research roles live in `research/workflow.json`. Reuse the single persistent report hub and existing event state; never recreate research rounds for reporting.

Before reporting, check the action-specific hold. Read relevant task states and original evidence, not entire histories. A process/session ending is not proof of an economic result. If events change materially while drafting, add a timestamped publication update without mixing it into the earlier counting window.

## 2. Existing cadence

| Output | Existing time/route |
|---|---|
| Round | Every even UTC hour at:05, covering the previous approximately2hours; persistent hub |
| Daily | Writer00:05UTC; publication01:00UTC,09:00Beijing |
| Weekly | Sunday, replacing that day's daily report |
| Material blocker | One event when confirmed; coalesce unchanged repeats |

Read actual schedule context when execution is delayed. Existing mail delivery remains separate from chat publication. This document does not authorize creating schedules, extra emails or replaying missed reports in a burst.

Daily drafts: `reports/owner/daily/<UTC-date>.zh.md`; weekly drafts: `reports/owner/weekly/<ISO-week>.zh.md`. Published chat reports: `reports/owner/updates/<UTC-time>-<kind>.zh.md`. Missing human-readable drafts must be disclosed; do not claim a scheduled trigger produced a report.

## 3. Weekly additions

Include account/sleeve returns, matched benchmarks, drawdown, authorization expiry and forward-versus-backtest evidence; a strategy pipeline with next milestones; significant findings and shared failure modes across mechanisms; operational incidents and actual budgets; useful engineering changes; next week's proposal and genuine owner decisions. Update the existing research map for actual changes. A historical example is `reports/owner/weekly/2026-W40.zh.md`, not a source of current numbers.

## 4. Measurement

- Explain net profit consistently. **Broker-reported paper PnL** uses the broker's simulated fills and marks, with external cash flows and missing statements/marks identified; label a raw equity change as such when those adjustments are unavailable. **Model-adjusted paper PnL** subtracts only explicitly stated estimated incremental costs and is not an actual-cost certification. **Historical-simulation net PnL** uses the declared fill, funding, dividend/action and transaction/holding-cost assumptions. Preserve these separate figures and show the reconciliation when comparing them.
- For each cost component, state whether it is already embedded in the fill price or separately deducted, whether it is observed or modeled, its notional/time basis, and missing coverage. Bid/ask fills already embed a spread; additional friction must have a distinct interpretation. Check possible duplicate spread deductions before calling a broker-plus-model figure fully net. Borrow/financing are holding costs, not per-trade fees. Keep primary and stress assumptions distinct; a fixed bps scenario is not the broker's fee schedule. Preserve historical records and publish traceable corrections instead of silently rewriting them.
- Read the current owner's goal interpretation. A valid negative result remains completed scientific research, but does not satisfy a goal explicitly requiring positive model/alternative-data contribution. A queued task, preparation, read-only observation or shadow backtest does not satisfy newly operating paper delivery. Preserve missed original deadlines separately from an explicitly requested recovery date.
- State the report window, as-of time and each account's latest market date. Stale/missing daily ledgers and repeated dates are operating faults, not current profitability. Read the applicable `reports/paper/lifecycle/review-plan-20261014.json` or its accepted successor for review/expiry dates.
- ETF sleeve returns use ledger equity relative to actual allocated capital and local SIP marks. SPY inception comparison uses the sleeve's first-session open through latest close; daily/weekly comparisons use close-to-close. Drawdown starts at allocated capital. Trading week means priorFriday close to currentFriday close; research/operations use the reporting week boundary.
- For equity books, reconcile `plans/`, `orders/` and `daily/` together. A zero unfilled counter does not prove no submission rejection, missing receipt or position drift. Turnover is buy-plus-sell notional divided by the correct equity basis.
- Label backtests with samples, costs, selection and funding assumptions. Original-sample, recent, method and deployment results are separate. Show informative realistic-cost and pressure results together; do not use an old sample's final days as evidence about today's market.
- Fewer than20forward sessions are tracking evidence, not a meaningful forward Sharpe/PSR verdict. Reuse accepted forward statistics and `open_composer/reports/owner_forward.py`; do not derive required record length from a highly noisy short forward Sharpe. A95% duration based on unshrunk backtest moments is only a lower bound.
- Keep workflow, research, ML/LLM contribution and paper readiness separate. Missing performance is N/A, not zero; conditional method results remain visible at their actual scope. Use the progress template for unambiguous inventory and exposure counts.
- When useful results have a relevant correlation comparison, summarize it against existing paper strategies and explain possible account benefit. Keep the common sample and costs clear, and distinguish a proposed different mechanism from measured diversification. Correlation testing is not required for every iteration or report; reuse unchanged evidence and add rolling/downside or portfolio detail only when useful to the decision. Follow the owner's lightweight preference rather than an exhaustive checklist.

## 6. Delivery and material issues

Run `.venv/bin/python scripts/owner_report.py lint <file>`; resolve errors and examine warnings without deleting inconvenient facts. `health <event_id>` verifies the business artifact, not delivery or readership. Maintain `reports/owner/reporting-state.json` event IDs, window, evidence, pending decisions and actual delivery state. Do not claim a queued message was published or read.

The dispatcher routes one event to the valid persistent hub. If it is closed, reuse another valid hub or create one only under current reporting authority, using an actually existing stable project workspace. Do not reuse a dead workspace ID, archive the hub after a report, or prompt it recursively. Hub failures are operational events; do not repeatedly notify a closed decision agent.

The hub writes and publishes the complete report in its own final response. The writer does not send duplicate mail. Existing mail uses the configured SMTP route; never read/print credentials or alter recipients/cadence as a reporting side task. Existing preview commands include `scripts/owner_report.py daily` and `weekly`; `--send` requires the existing applicable delivery authority.

Material owner decisions include new spending, account/authority changes, owner-only information and changes to goals/risk/major priorities. Routine scientific/technical decisions stay with the research team. State evidence, impact, remedies already tried, options, deadline and default. Waiting affects only the dependent operation. Update `owner_decisions` and preserve actual replies; never infer consent from elapsed time.

## 7. Business names

Translate these meanings into the report language instead of exposing internal codes:

| Internal identity | Business meaning |
|---|---|
| S1 / sector rotation | Sector rotation |
| S2 / growth rotation | Growth rotation |
| S3 / leveraged rotation | Leveraged rotation |
| C2 / end-of-month | Month-end effect |
| quant1 / F1 | Market-neutral equity long/short account |
| quant2 / F2 | SPY-enhanced equity account, only when currently applicable |
| P1 / P2 / L1 / L2 | Paper incubation / live candidate / proposed small live pilot / target-scale proposal |
| DSR | Sharpe evidence adjusted for the variants tried |

Use current strategy/account records when roles have changed. A historical label is not proof that an account is still operating that strategy.
