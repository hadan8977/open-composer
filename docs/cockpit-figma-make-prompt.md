# Figma Make prompt — research cockpit (v1, 2026-09-20)

Paste everything below the line into Figma Make as-is. It describes function, not style; the point is to get an independent visual take on the same six screens so the two can be compared and the better ideas ported.

---

Design a read-only monitoring dashboard called **Cockpit** for one person who runs AI research agents around the clock on a server and trades a paper (simulated) stock account. They open it on a phone during the day and on a laptop at night to answer four questions without interrupting the agents: what happened while I was away, what are the agents doing right now, how far has the research got, what state are the paper account and my API quota in.

It is strictly read-only: there is no button, form, or control that changes anything. Every number that can go stale shows its timestamp. All text is English. Dense, quiet, no marketing copy, no empty-state cheerleading, no emoji. Numbers are monospace and right-aligned. Dark by default. Both a phone layout and a desktop layout are needed — on the phone, wide tables become stacked cards.

## Persistent top bar (every screen)

- Claude quota: two thin bars, 5-hour window and 7-day window, each with percent used and a reset countdown. When the live figure is unavailable the bar is replaced by a short reason (`token expired -- re-login`) and an estimate line: tokens used in the current 5-hour window from local logs, labelled `estimate`.
- Codex: a single state chip (`api key billing -- no subscription quota`, or a bar when a subscription exists).
- One dot per running agent (ok / idle / error).
- A data-freshness dot.
- A countdown to the soonest paper-trading authorization expiry.

## Screen 1 — Hypotheses (landing screen)

A board of research hypothesis cards in swimlanes: proposed, approved, preregistered, running, shipped, refuted, on hold, data card, unclassified. Each card: id (`H-20260919-01`), title, lane chip, data layer, and when results exist a few headline numbers (cell count, best Sharpe vs the incumbent to beat). Cards in `unclassified` show their raw status text and the reason.

Card detail view: the card's markdown body; a block titled `criteria vs result` that puts the pre-registered pass/fail criteria beside the actual numbers (labelled `unstructured` when the criteria only exist as prose); a small histogram of placebo outcomes with the real result marked as a vertical line; a "trial budget" bar for the card's hypothesis family (looks like a quota bar: trials used of the family's budget); the card's lineage neighbours.

## Screen 2 — Lineage

A directed graph of the cards: node colour = outcome; solid edges = a card declares its predecessor; dashed edges = a card merely mentions another. On the phone, an indented list grouped by root instead of a graph. Click a node to open the card.

## Screen 3 — Agents

One row or card per agent: provider (claude / codex), model, state (running / idle / error), running time, the file it is currently reading, and the last line of its reasoning. Expanding one shows a live, auto-scrolling timeline of its reasoning and tool calls (each entry: time, tool, target, duration, outcome). A second section lists heavy background jobs: name, memory cap, elapsed time, last log lines.

## Screen 4 — Paper

Summary table, one row per strategy (five today): name, authorization state chip (authorized / observation only / expired), days to expiry, last cycle time, target-vs-actual agreement, fill rate, last order time. `observation only` means the strategy computes signals but never places orders and must not look like it trades.

Strategy detail: authorization block (limits, scope, expiry countdown); target weights next to actual positions; orders table; fills table with slippage; an equity bar chart when there is real history, otherwise a single stat card that says `no history yet`.

## Screen 5 — Quota

All Claude windows (5h, 7d, 7d-opus, 7d-sonnet) with percent, reset time; extra-usage state; a table of credential sources tried and each outcome (absent / ok / expired / insufficient scope); the local estimate broken down by model and by role (main session vs subagents) with input, output, cache-write and cache-read tokens shown as separate columns — cache-read is never folded into a total; last throttle event with its reset time; cache age and circuit-breaker state.

## Screen 6 — Health

Cron jobs: schedule, last run, exit status, log freshness. Data sources: latest date per dataset with an ok / stale dot. Disk and memory. Recent error log lines.

## Data

Each screen is fed by one JSON document from a small read-only API; a state field on every value uses the same four words everywhere: `ok`, `warn`, `stale`, `unknown`. Design the components around those four states so colour carries meaning and nothing else.
