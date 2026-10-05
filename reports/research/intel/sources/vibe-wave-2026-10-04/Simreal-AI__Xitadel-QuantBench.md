<!-- source: https://raw.githubusercontent.com/Simreal-AI/Xitadel-QuantBench/HEAD/README.md ; fetched 2026-10-04T18:45Z ; original bytes truncated: False -->
# Xitadel-QuantBench

[![Status: public preview](https://img.shields.io/badge/status-public%20preview-34d399)](https://github.com/Simreal-AI)

**The first public trading benchmark scored against what human competitors
actually made on the same day.**

> **Public preview.** This repository is the open, minimal slice of Xitadel, SimReal's trading environment: the published tasks with their training data, the strategy SDK, the scoring specification and the public report. The matching engine, the counterparty model, the held-out scored days, the session controller and the reserve tasks run on the SimReal engine and are not in this repository. It is early and will change.
>
> Full access for labs and partners: [business@simreal.co](mailto:business@simreal.co) · All SimReal previews: [github.com/Simreal-AI](https://github.com/Simreal-AI)

Seven research tasks across two market suites. An agent receives historical
order books, product rules and position limits; it researches, writes a Python
strategy, and ships it. We replay that strategy on a market day it has never
seen and score the result against the best human competition strategy on that
same day.

Human reference scores 80. Twice that combined performance scores 100.

| Rank | Model | Score / 100 | Tasks at or above human |
| --- | --- | ---: | ---: |
| 1 | GPT 6 | 77.28 | 5 / 7 |
| 2 | GLM 5.3 | 30.12 | 1 / 7 |
| 3 | Kimi K3 | 27.68 | 0 / 7 |
| 4 | DeepSeek V4 Pro | 24.58 | 0 / 7 |

**No model has cleared the human bar overall.**

Published results use a 2h/4h pilot allocation; the standard protocol is 6h/12h.
The allocation is identical for every model in a comparison and is reported with
the result.

## Why the score means something

**The verifier is a simulator, not an opinion.** No judge model, no rubric, no
LLM grading another LLM. A submitted strategy executes against a historical
order book and is scored on realized P&L, maximum drawdown and Sharpe. The same
code yields the same number every time.

**The reference is a real result, not an estimate.** Human strategies are
replayed from published competition submissions under the same isolation, the
same test episode and the same metric convention as every model run.

**The scored day is never seen.** Training episodes are published; the scored
episode is not, and neither are the raw metrics measured on it — those would
characterise the episode well enough to tune against. `COMMITMENT.json`
publishes their hash, so the full evaluation can be audited without being
disclosed and released once those episodes retire.

## Designed as a trading problem, not a prediction task

**Execution is modelled, not assumed.** Orders join a queue, cross the touch or
rest behind it. Every fill is attributed against the book as it stood when the
order was submitted, so passive and aggressive fills are separable and expired
orders are counted.

**Risk is priced into the score, not reported beside it.** Combined performance
is `max(0, P - 0.1 x D)` scaled by a Sharpe quality factor. This is not
cosmetic: in our own reference set, repairing three logic defects in one human
strategy raised its P&L by 63% while its Sharpe fell from 7.27 to 3.03. Ranking
on P&L alone would have inverted the conclusion.

**The instruments behave.** Baskets and components trade independently with no
creation or redemption. Options and their underlying carry separate inventory
caps. Conversion quotes include transport and tariffs, and long inventory
accrues storage cost. Two tasks disclose counterparty identity; the rest do not.

**The accounting convention is fixed and published**, down to what happens when
one side of the book is empty. Cross-task P&L is never summed: products and
scale differ, so normalized per-task scores drive the comparison.

## Scope

Seven tasks cover single-product market making, basket and component
relationships, options against an underlying, external conversion with tariffs
and storage, and a multi-asset market with disclosed counterparty identities.
Tasks were selected for capability coverage before any result was consulted.

More exist. They are held in reserve and are what this benchmark refreshes onto
when the published episodes stop being meaningfully hidden. What is withheld is
instances, not rigor: every published task runs the same engine, isolation,
accounting convention and held-out protocol as the reserve.

## Quick start

Python 3.12 is the tested version.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python scripts/prepare_data.py
python -m unittest discover -s tests
```

Each task then contains `prices.csv`, `trades.csv`, position limits and applicable
product rules. Read [DATASETS.md](DATASETS.md), then implement
`Trader.run(state)` using [examples/strategy_template.py](examples/strategy_template.py)
and the [Agent Guide](AGENT_GUIDE.md).

## Research and evaluation

- The last complete market day is held out by the operator.
- Agents use restricted file, Python, backtest, visualization and submission tools.
- Standard tasks have 6 active hours; options/PIZZA tasks have 12.
- The reported pilot used 2h/4h research allocations.
- Submission shows remaining time and requires explicit irreversible confirmation.
- The main score combines P&L, maximum drawdown and Sharpe.

Scores are in the results table above. Read the [complete report](reports/REPORT.md)
and [scoring specification](SCORING.md). The overall mean covers the 7 published tasks.

## Operator side

Scoring requires the matching engine, the counterparty behaviour model, the
held-out episodes and the session controller. Those stay on the evaluator's
machine, which is what makes the held-out day held out. An agent connects to an
assigned research session and nothing else; installing this SDK does not install
the evaluator.

The controller accounts for research time in active seconds: confirmed provider
outages and reconnection waits are excluded from an agent's budget, so a flaky
endpoint does not silently become a capability measurement.

## Reward signal

Each task exposes a deterministic, programmatically computed reward over a
complete research episode. Observation is the assigned data and tool output,
action is a research decision or a code edit, and the terminal signal is
verified market performance. Reward comes from a simulator, not from a model's
opinion of another model. Reserve tasks are held back so that any claim of
improvement can be measured on instances that were never available for
development.

## Part of SimReal

This repository is one public preview in the [SimReal](https://simreal.co) product line: environments where AI agents act and real outcomes decide the score. See every preview at [github.com/Simreal-AI](https://github.com/Simreal-AI).

## License and independence

Code is MIT; see [LICENSE](LICENSE). Dataset terms are in
[DATA_LICENSE.md](DATA_LICENSE.md) and attribution in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Xitadel-QuantBench is an independent research project. The name is a pun and
implies no affiliation with, endorsement by, or relationship to any financial
institution.
