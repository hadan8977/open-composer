# Figma Make prompt v2 — designed cockpit, Apple design language (2026-09-20)

Paste everything below the line into Figma Make. v1 (`figma-make-prompt-v1.md`) described function only; this one adds the design direction. The screens and data are the same so either result ports onto the same read-only JSON API.

---

Design **Cockpit**: a personal, read-only monitoring app for one quantitative researcher who runs AI research agents around the clock on a server and trades a paper (simulated) stock account. He opens it on iPhone during the day and on a Mac at night to answer, without interrupting the agents: what changed while I was away, what are the agents doing now, how far has the research got, what state are the paper account and my API quota in.

## Design language

Apple's current design language — Liquid Glass as revised for iOS 27 and macOS 27 — applied the way Apple applies it, not as a visual effect.

- Two layers. **Content is opaque**: tables, cards, charts sit on the system grouped background. **Glass belongs to the control layer only**: sidebar, floating tab bar, toolbar, inspector header, segmented controls. Never glass on glass. Default transparency restrained; everything legible with Reduce Transparency on.
- Concentric corners: inner radius = outer radius − padding. Containers ~16–20, inner elements ~10–12.
- Typography: SF Pro text styles (Large Title, Title 2, Headline, Body, Footnote, Caption). **Numbers carry the weight**: SF Mono or tabular figures, large; labels secondary and small. No all-caps labels except tiny section headers.
- Colour: system semantic colours, one app tint used only for selection and links. Status uses exactly four states everywhere — `ok` green, `warn` orange, `stale` red, `unknown` gray — shown as a dot, never as a filled coloured card.
- Motion only where it explains: tab bar minimises on scroll, inspector slides in, a new live row fades in. No counters, no gradients breathing, no decorative animation.
- Words: labels are nouns; no sentence tells the reader what is already visible; empty state is `None` or `No data yet`; every value that can go stale shows a relative time (`2m ago`) with the absolute time on hover.

## Shell

- **Mac / iPad**: sidebar (glass) → content → right inspector. Selecting a row opens it in the inspector; nothing navigates away. A search field filters the current list as you type. Keyboard: ⌘1–6 switch screens, ⌘F filter, ↑↓ select, Space preview, Esc close inspector.
- **iPhone**: floating tab bar — Hypotheses · Agents · Paper · Quota · More (Lineage, Health). Row tap opens a sheet. Pull to refresh. Wide tables become stacked rows, never horizontal scroll.
- **Status strip** under the toolbar on every screen, one line: Claude 5h and 7d quota as two thin bars (or one reason chip when unavailable, e.g. `token expired`), fresh-token estimate for the current 5h window, one dot per live agent, a data-freshness dot, and a countdown to the soonest paper authorization expiry.

## Screens

Each screen = a metric strip (3–4 large numbers) + one list or table + an inspector/sheet for the selected row.

**Hypotheses (default).** Metrics: running · shipped · refuted · unclassified. List grouped by lane — proposed, approved, preregistered, running, shipped, refuted, on hold, data card, unclassified; row: id (`H-20260919-01`), title, status dot, headline numbers when results exist (cells, best Sharpe vs incumbent). Inspector: the card's markdown; a **criteria vs result** block placing the pre-registered pass/fail criteria beside the actual numbers (badge `unstructured` when the criteria only exist as prose); a small histogram of placebo outcomes with the real result as a vertical line; a **trial budget** bar for the card's hypothesis family (looks like a quota bar); lineage neighbours.

**Lineage.** Metrics: declared edges · mentioned edges · roots. Mac: a graph of only the connected cards — solid edge = declares a predecessor, dashed = merely mentions — with isolated cards in a compact list beside it. iPhone: an indented list grouped by root. Selecting a node opens the card inspector.

**Agents.** Metrics: running · idle · error · fresh tokens today. Row per agent: provider (claude / codex), model, state dot, running time, file currently being read, last line of reasoning. Inspector: a live auto-scrolling timeline — time, tool, target, duration, outcome — plus a section of heavy background jobs (name, memory cap, elapsed, last log lines).

**Paper.** Metrics: account equity · day P&L · open orders · soonest expiry. Row per strategy (five today): name, authorization chip — `authorized` / `observation only` / `expired` — days to expiry, last cycle, fill rate, last order. `observation only` computes signals but never places orders and must not look like it trades; `expired` means orders have silently stopped and must be unmissable. Inspector: authorization (limits, scope, countdown); target weights beside actual positions; orders; fills with slippage; an equity bar chart only when real history exists, otherwise one tile: `No history yet`.

**Quota.** Metrics: 5h fresh tokens · 7d fresh tokens · fresh tokens at last throttle (`empirical window capacity`) · cache reads. Table by role (main session / subagents) then model, columns input · output · cache write · **fresh** · cache read — cache read is never folded into a total. A second table of subagent tasks sorted by fresh tokens: label, model, fresh, cache read, turns, first/last activity. Inspector: credential sources tried and each outcome (absent / ok / expired / insufficient scope), throttle events with reset times, cache age, circuit-breaker state.

**Health.** Metrics: stale data sources · failed cron jobs · disk free · memory free. Tables: cron jobs (schedule, last run, exit status, log freshness); data sources (latest date, dot); recent error lines.

## Deliver

Light and dark. iPhone and Mac frames for every screen, one Mac frame with the inspector open, one iPhone frame with the tab bar minimised mid-scroll. A component sheet: status dot, chip, metric tile, table row (desktop and stacked), sparkline, quota bar, inspector header. Every screen is fed by one JSON document from a small read-only API and every value carries one of the four state words — design the components around those four states so colour means one thing only.
