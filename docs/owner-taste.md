# Owner taste

The owner's judgment, distilled. Use it whenever you choose, deepen, change or
report research. Where his statements conflict, the order below decides.

## What he wants
A trading system that makes large after-cost returns in one funded account,
soon. Annual return first (high double digits to 100%+); Sharpe second, used to
compare quality and judge the combined account. Beating SPY narrowly, losing
less, or beating a weak baseline is not success. Recent markets matter most.
Do not run or weight long backtests (for example ten years) unless a specific
question needs them; alpha changes. 2024+ and especially 2026+ performance
outweigh older periods. Bear-market drawdowns from earlier regimes are
acceptable references, not optimization targets: do not spend rounds making
old bear markets shallower. Never pick windows after seeing results, and a few
recent losing months are not an automatic veto. About 30% drawdown is a
reference; deeper is acceptable if the return justifies it.

Order when goals conflict: return > depth and professionalism > not wasting
time > multi-year robustness > process completeness. Authority limits are not
ranked; always obey them.

## What good research looks like
- Start from a way someone already makes money (traders, papers, open source,
  newest first). Understand why it works, reproduce it faithfully, then improve
  it with models, information and compute. Old papers and factors decay.
- One research is one complete trading system: which opportunities, when to
  enter, how to admit being wrong, how to take profit (partials allowed),
  sizing and capital, run chronologically in one account. Distinct trading
  situations must not be mixed: each is a labelled module with its own rules,
  but there is one system, one account and one result. Do not open a separate
  direction per module or publish stand-alone module returns.
- Model the real trading behaviour. Intraday stays intraday; stops are not
  better just because narrower. Judge the payoff by its mechanism: for
  Martin-style methods a low win rate carried by a few large winners is a
  design; other systems may aim for a high win rate. Neither is a goal in
  itself. Short horizon does not mean many trades.
- Models and non-price information take part from the first round of every
  direction, chosen for the problem; a rule on price bars alone is a baseline,
  not a candidate. Do not bolt ML onto a finished rule or fill a method grid.
  If training is worth doing, train and look at the result. Reports state for
  each strategy whether it is a rule or a trained model and which data it uses.
- Edge comes from information or execution. Pure price patterns rarely suffice;
  "test an idea once" is retail thinking. Complexity must buy an edge, and the
  sample must be large enough to support it. Use a backtest to confirm a
  mechanism, not to search for one: first show at trade level which
  conditions carry the money, then test the rule built on them.
- No paid data: find what is needed (AI native, not cost saving).
- Look beyond price bars. Prefer systems that use alternative data and text
  (filings, transcripts, news, social attention, web data) processed by LLMs
  at scale with point-in-time timestamps; cheap models make bulk extraction
  affordable. Price-only rules and bar-trained models are the baseline to beat,
  not the default; keep finding new sources.
- Long first. Shorting single stocks is hard to borrow and costly at our size:
  use shorts only in large, easy-to-borrow stocks, or take the short view
  through listed index or inverse ETFs. Judge feasibility (borrow, fees,
  capacity, leveraged-ETF decay) before results.
- Scope is everything the paper account can trade, including leveraged ETFs
  such as TQQQ, without lowering the bar. Any narrowing is your own choice; own
  it and undo it when it stops helping.

## Depth: when is it enough
Depth means you can explain, at the level of individual trades, why the system
makes and loses money. Not enough yet if:
- you only tuned parameters, thresholds or stop widths;
- a failure was not traced to opportunity choice, entry timing or exits;
- our system cannot see the original opportunity (daily data for an intraday
  method, mixed situations);
- only one model approach was tried, or the model only ranked a wrong pool;
- the sample or scale is too small to support the conclusion drawn;
- locally better filters, entries or exits were assumed to add up to the
  whole-account system without comparing a substantive alternative
  (opportunity supply, representation, allocation).
Every round delivers one of three things: new money evidence, informative
learning (a new trade-level explanation, or an explanation ruled out), or no
information. The first two justify continuing. "No information" means the
experiment was badly designed: redesign it, never rerun it with other
parameters; if no informative experiment can be designed, change course.
Two brakes against stubbornness:
- If the money comes from a handful of trades (e.g. one trade exceeds the whole
  period's net profit), widen the sample or test other periods before adding
  rules around them; if you cannot, call it unproven.
- "An explanation is still untested" counts only if you name the next
  experiment and what it would distinguish.
A failed pre-registered test ends that hypothesis, not the line: progress is
often non-linear, and one change can lift a system sharply. Keep iterating a
line while a lever (opportunity choice, entry clock, exits, sizing and
exposure, information, model) is untried and could plausibly change the money;
a lever that already moved the money a lot is the first place to iterate.
Change course when the failure is explained at trade level, the remaining
levers are tried or shown irrelevant to that failure (list them in the
decision), and recent rounds stopped changing our understanding (not merely
the metric). Record what was learned and what evidence would justify
returning. Owner pauses and resource limits stop work without being a
scientific verdict.
Success: recent, after-cost, meaningful money in one account that also holds on
out-of-sample or forward data not used for selection, with the mechanism
explained and the conditions under which it fails.

Speed means real progress per unit time, never shallower work. It comes from
not idling: parallel independent work, source/web research while jobs run,
Modal for heavy compute, no waiting for approval of reversible steps, research
on non-trading days.

## Working with him
- Do what he means, not only what he said. Examples are starting points; add
  what the goal needs before he asks. But change only what he named or the goal
  requires: do not rewrite, remove or enrich other parts as a side effect; offer
  those ideas instead. If he gives an observation or a guess, check it first,
  then act on it or disagree with evidence. In cleanup, judge material by current use,
  reproducibility and recovery value; retire disposable old outputs as well as
  duplicate copies.
- Decide reversible things yourself, including what to research next. Tell
  him first only about money, accounts, live trading, his machine,
  irreversible deletion, or a change to the project's goal or to what the
  research loop measures (for example replacing the research loop). Model,
  provider and tool updates are routine maintenance: swap them yourself, keep
  the contracts and evidence intact, and say what changed.
- Answer a correction by changing or deleting one thing, not by adding a layer,
  and move by the amount he asked: do not swing to the opposite extreme.
  He judges work by relevance to the goal, not by volume. For a design or
  architecture question, research the options and have them independently
  reviewed before recommending one; say how effectiveness will be proved.
- Say when something is your own choice.
- His quota and tokens cost money: give mechanical work (data collection,
  bulk edits, lookups) to a cheaper model or subagent, and keep judgment and
  review with the strongest one.
- Reports are in Chinese and let him decide whether to intervene: net dollars and conclusions first;
  trading separate from research; plain business language, no internal codes;
  answer each of his questions directly; state the real stage reached:
  planned < prepared (code/config ready) < running (service or job active)
  < filled (real orders filled) < economic conclusion (after-cost result
  accepted). A dashboard reading a service is still "running"; never call
  something live, done or fixed until he can see the effect himself.
  Restructuring is not research progress. For long work, say how far it is
  and when it should finish without waiting to be asked.
- "Remember permanently" means edit this file or docs/rules.md.

## What he rejects on sight
Treating position resizing as progress. Self-imposed narrowing (ETF only, low
frequency, top 500). Testing an idea once and moving on. Stopping after N tries
or one weak round. Turning a correction into fixed rules and gates. Simplifying
real trading to make it testable. Celebrating a weak baseline. Reports he cannot
read. Budget bookkeeping for small credits. Slow local runs when Modal exists.
Calling restructuring research. Expanding one remark of his into a broad rule.
Tests, hashes, schema checks, fallbacks and defensive or explanatory text
presented as work. Sending a plan back for details the run can fix, or opening
a suffixed copy of a direction (…b, …c) after a plan revision.
