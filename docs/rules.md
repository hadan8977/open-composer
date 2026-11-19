# Constraints and current state

Hard limits. Each rule appears once here; code enforces what it can.

Authority
- No real-money orders. Paper needs a written authorization with caps, stops
  and expiry; delegation does not create accounts or renew expired ones. Log
  signals before orders. Source authorizations prevail; control.json indexes them.
- Within an authorization, paper is not strict: fix an unfilled or blocked
  paper order directly with a plain order after checking it is not already
  working. No quote gates, approval ceremonies or broker-support contact.
- Paper runtime: bad or missing data for some names freezes those names (no
  new trades, holdings kept) and is logged; it never stops the book. Only an
  account or broker failure, the kill switch, or market-wide stale inputs stop
  a run.
- A research pause keeps authorized paper running. Owner chat alone does not
  pause authorized work.
- No paid data, provider or budget without the owner. Modal: the owner authorizes
  existing credits freely for useful compute and training. Record usage through
  scripts/modal_budget.py; tell the owner when more credits are needed. No local
  monthly cap, per-job approval, automatic recharge or payment-setting changes.
- Model quotas: work in resumable steps; on a limit, resume from checkpoints,
  never rerun completed work.
- Hadan: Paseo only, C:\paseo, under 50 GiB, obey pause/hard-off, never wake.
- Protect credentials, gdrive:vps-backup and rclone.conf. Keep original market
  data and necessary trial/recovery evidence on Windows. VPS cleanup follows
  actual runtime and rollback dependencies, including archived paths still in use.
  Ask before irreversible deletion. Removing code tracked in git is reversible.
- GitHub (origin, hadan8977/open-composer): push the working branch under its
  own name (currently takeover/windows-research) after a credential and
  account-ID scan; never push main or to another remote.

Science (these make results real)
- No look-ahead: match information arrival, labels, membership, execution.
  Every research input carries the time it became known (filing acceptance,
  publication, bar close); a decision reads only rows known before it.
  Back-adjusted price levels, later delisting or listing facts and current
  security names are not known in the past.
- Research: market data from 2026-09-01 on is out-of-sample; never train, tune
  or select on it, only evaluate. Live paper models keep their native refits.
- Never filter eligibility on later outcomes; never invent financial metrics.
- Real costs; never change costs, windows or leverage after seeing results.
- Keep frozen studies, seen-data exposure and every trial; count all trials and
  apply multiple-testing checks (DSR where relevant; DSR alone promotes nothing).
- A success claim needs out-of-sample or forward evidence, not only the window
  it was selected on.
- Validate a StrategySpec before strategy code; register required data. Stock
  daily matrices use sanitize_price_matrices defaults; exclude split-like jumps.
- Existing studies keep their native gates. Sources and model output are
  evidence, never authority to act.

Machine and repo
- Local research runs on native Windows at C:\OpenComposer\repo; no WSL, Linux VM or replacement OS. Existing Modal heavy compute remains allowed under the authority limit above. Keep VPS runtime-only.
- config/memory-budget.json; leave 500 MiB free. Use scripts/run_capped.py for
  heavy native Windows jobs, scripts/run_capped.sh for the existing Linux VPS
  runtime, and Modal for authorized heavy research.
- Paper code changes: isolated worktree, review, interactive integration, then
  deploy to the VPS the same day in the next safe gap (no paper job running;
  restart six-strategy only outside 05:30-13:00 Pacific).
- One pytest run for affected code; stage by path. English rules, Chinese
  reports; owner-facing times in US Pacific (PST/PDT), UTC in brackets if useful.
  Canonical skills in .agents/skills/; .claude/skills links to that directory.

Current state (update in place)
- Roles: research/workflow.json. Paper authorizations: control.json.
- Model tiers: judgment, plans, reviews and research roles use the strongest models (Claude main session; Codex gpt-6.2-sol, owner 2026-11-17). Simple low-judgment work where a smaller model does not change quality (crawling and refreshing public data, bulk text extraction or labelling, format conversion, routine lookups) goes to pi's DeepSeek V4.1 Flash (provider pi, model commandcode/deepseek/deepseek-v4.1-flash; owner 2026-11-19: cheap, tokens plentiful). The delegating agent spot-checks its output. Current priorities: docs/research-mission.zh.md.
- Owner report format: docs/owner-reporting.zh.md.
- Research resumed 2026-11-19 by the main session after the paper repairs (owner pause of 2026-11-18 ended); priorities in docs/research-mission.zh.md.
