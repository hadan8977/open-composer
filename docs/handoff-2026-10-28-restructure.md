# Handoff 2026-10-28: Open Composer restructure (Claude to Codex)

Owner decisions on 2026-10-28: "额度经理也取消。模拟盘要续期。磁盘123都可以。" Goal: "正向思考，pstack+奥卡姆剃刀，精简md/prompt/opencomposer的内容，提升研究速度和token到产出的效率". Do not start the A/B research until the owner says so ("先不用开始"). `AGENTS.md` has uncommitted owner edits; preserve them.

## Done and verified (2026-10-28 UTC)
Backups for everything below are in `/root/oc-retired-20261028/`.
- **Quota manager:** Paseo heartbeat 7afe0e4d deleted, agent a7f63106 archived, `config/research-quota-manager.json` set `enabled=false`.
- **Six-policy paper service:** earlyoom sent SIGTERM at 03:35 UTC. systemd counted that as a clean exit, so `Restart=on-failure` did nothing. Added drop-in `/etc/systemd/system/oc-six-paper-validation.service.d/restart-after-earlyoom.conf` (`RestartForceExitStatus=SIGTERM`, `OOMScoreAdjust=-300`). `expires_at` in `service-config.json` moved from 2026-11-14 to 2026-12-12. Restarted 04:38 UTC; all 6 policies `ready_waiting_rth`, 0 open orders. The one-shot STATE capture/transition modules return early (output dirs exist), so the config edit does not affect them.
- **Legacy ETF S1-S3 and C2:** renewed with `oc paper authorize-rehearsal`, 45 days, to 2026-12-12 05:37 UTC. Account hash, limits, spec hash and gate notes are unchanged. New authorization ids restart the per-authorization total-notional counter, as at earlier renewals.
- **Cron:** the four `rehearsal-reconcile` lines moved from 14:xx to 15:xx UTC. After DST ends on 11-01, the open is 14:30 UTC.
- **Disk:** 91% to 84% (35 GB free).
  - Caches pruned (uv, pip, journal, `~/.codex/.tmp`). Playwright, camoufox and HF caches were kept because quantcheck, oc-search and Hermes use them.
  - 7 clean worktrees removed (branches kept) and 10 stale entries pruned.
  - Uploaded to Drive, checked with `rclone check` (0 differences), then deleted locally: Claude transcripts tgz, `headline-contextual-return-20261017`, `data/live/backup-refresh/2026-10-07..16`, `day-goal-20261011`, and 792 Codex session files older than 14 days.
  - Deleted research and backup dirs are now symlinks into the read-only `/mnt/gdrive`.
  - Logs: `disk-step3-result.jsonl` and `reports/ops/disk-ledger.jsonl`.

## Waiting on the owner
1. **v1.2 book (quant1):** paused since 10-21, data stale since 10-16. It still holds 1,503 positions (gross about $1.79M on $1.02M equity) with 0 open orders. Not renewed. The owner must choose resume or flatten. Resuming needs the SIP refresh hold lifted and the plan cron moved 18:30 to 19:30.
2. **Memory pressure:** 23 idle Paseo agents in `/tmp/fpcheck` (parent "Claude｜finance") hold about 1 GB RAM and 3.1 GB swap. That pressure caused today's kill. They belong to another project, so the owner decides.
3. **Disk step 4:** `day-goal-20261013/hf-factor-return` (18 GB, protected by policy), `/root/work/work`, `.hermes`.
4. **disk_guard cron (line 19):** before re-enabling it, check that the glob `data/**/backup-*` cannot rmtree `data/live/backup-refresh`, which now holds only symlinks.

## Work for Codex, in order
### 1. Instruction layer: write drafts, get owner review, then apply
Write drafts in `drafts/instruction-layer-20261028/`. Everything an agent must read at startup stays at or under 8 KB.
- **`AGENTS.md`** (3 KB or less): mission in 3 lines linking `docs/research-mission.zh.md`, hard rules, the loop in step 2, a path map.
- **`docs/rules.md`** (3 KB or less): only the valid rows of `docs/owner-rules-register.zh.md`. Archive the register unchanged.
- **`control.json`** (2 KB or less): research on/off, per-strategy paper authorization paths and expiries, quota pacing. Agents read this instead of `owner-compute-hold.json`.
- **Keep `owner-compute-hold.json` as is for now.** Live paper code reads these keys: `existing_paper_operations_allowed`, `status`, `old_etf_paper_resume_20261023.allowed`, `paper_launch_20min_20261021.necessary_current_paper_input_inference_and_repair_allowed`, `reporting`, `hadan`, `training`, `research_paused`. Migrate those readers later, in a worktree.
- **Remove from the agent path:**
  - the quota manager and the 10-point/70% protocol;
  - `scripts/research_task_prompt.py` (source of the SHA handoffs);
  - `config/research-agent-roles.json` (replace with 5 lines in `AGENTS.md`);
  - `docs/task-owned-research.zh.md`;
  - `prompts/continuous-alpha-*.zh.md` (replace with `prompts/lead.md` and `prompts/worker.md`, 1 KB or less each);
  - day/week goal JSON as authority (replace with `board.md`, one line per round).
- **Archive (move, do not delete):**
  - the 76 docs no agent read (recompute: not referenced by code and not opened in sessions);
  - the never-used skills `evidence-curator`, `pine-exporter`, `signal-parity-reviewer`, `strategy-researcher` and `weekly-reviewer`;
  - `prompts/*_factor_v1.txt`, except `momentum_multimodal_grounded_v1.txt`, which code uses;
  - `reports/research/control/auto_*`.
- **Claude hooks:** the paper write-guard and Stop hooks crash on every call. The python heredoc consumes stdin, which raises JSONDecodeError and exits 1, a non-blocking code, so they never blocked anything. The UserPromptSubmit hook injects stale mission text. Remove all three from `.claude/settings.json`.

### 2. Research loop (pstack hillclimb plus Occam)
- **One dir per direction:** `research/<direction>/` holds:
  - `brief.md` (1 KB or less): question, data, baseline, metric, variant budget, done-when;
  - `results.json` in a fixed schema, written by the engine;
  - `decisions.tsv`, one row per variant: id, hypothesis, change, metric, keep/revert, note.
- **Lead round:** a fresh session (Astra) reads `board.md` and new results. It decides continue, branch or stop for each direction, writes the next briefs, and appends one board line: briefs, results, tokens, paper candidates. No standing agents, no agent-to-agent messages, no SHA receipts. Provenance comes from git and result files.
- **Worker:** one `codex exec` per brief (Sol), run with `--output-schema research/results.schema.json` under an external timeout.
- **Stopping:** a direction stops only after its variant budget (20-50 materially different variants) or a written mechanism reason. A plateau means change the method.
- **Paper and live:** a development-period pass plus a positive DSR-adjusted edge goes to paper under the owner's standing paper authority (rule of 10-06 evening). The live bar is unchanged.
- **Quota:** the lead reads usage once per round and paces to 15-20% of the weekly window per day.

### 3. Shared engine `open_composer/lab/`
- **Components:** one daily/minute simulator with costs, a ledger, metrics, DSR (reuse `open_composer/research/scorecard_v2.dsr`), a trial ledger, a batch variant runner (reuse `scripts/screen_batch.py` and `scripts/screen_lane.py`), and `sanitize_price_matrices`.
- **Check 1, ablation:** every config flag must change some output. This would have caught the hard-coded `True` values in Martin `native_f1.py` lines 261, 276 and 277.
- **Check 2:** `results.json` carries `n_trials` and DSR.
- **Why:** today the code has 11 `simulate()` copies, 10 fee functions and 4 DSR implementations.

### 4. Paper production into git
Work in a worktree, get review, and restart outside 13:30-21:00 UTC.
- Commit `six_paper_service.py` and the 50 untracked `intraday_runner` files.
- Move config and state out of `reports/research/program/paper-launch-20min-20261021/` and the dirs it imports: `owner-profit-delivery-plan-20261017/{current-paper-science-20261020,second-learned-paper-20261019}` and `return-line-replenishment-20261016`.
- Put the systemd unit and drop-in in `deploy/`.
- Pin the inference interpreter (`/usr/bin/python3.12`, torch 2.13.0+cu130). The 10-26 outage happened when that environment vanished.

### 5. A/B (only after the owner says start; earliest after the 11-02 06:07 UTC Codex reset)
- **Groups:** pure Codex (Astra lead, Sol workers) against pure Claude (Opus 5.5 lead, Sonnet 5.5 workers).
- **Same for both:** briefs, engine and schema, and two directions (faithful Martin replication plus variants, and one factor or model direction), over 3-5 days.
- **Metrics, fixed before the start:**
  - costed results per day;
  - quota share per result;
  - time from brief to first result;
  - variants per direction;
  - error rate on 3 randomly re-checked results;
  - owner interventions.

## Constraints (unchanged)
- Paper only.
- Never print credentials.
- Change paper code only in a git worktree.
- Stage explicit paths; never run `git add -A`.
- Keep about 500 MB RAM free and run one pytest at a time.
- Use Hadan only via Paseo, under `C:\paseo`, below 50 GiB.
- Use the Modal free tier only, via `scripts/modal_budget.py check`.
- Never touch `gdrive:vps-backup` or `rclone.conf`.
- Frozen OOS data and criteria stay unchanged.
- Diagnosis evidence is in `/root/oc-retired-20261028/diag/`.
