---
name: windows-paseo-worker
description: >
  Use when a research task needs the owner's Windows compute worker through
  Paseo. Provides the fixed C:\\paseo/50 GiB contract, local pause controls,
  remote preflight, manifest-bound transfer requirements, and cleanup rules.
---

# Windows Paseo Worker

Use this skill when a research task needs more memory, CPU, GPU, or temporary
disk than the Linux host can provide. The worker is a temporary research
executor, not a broker or paper-trading host.

## Single source of truth

Read `config/windows-paseo-worker.json` first. Use the CLI adapter instead of
reconstructing a pairing URL or calling `paseo` with an inline secret:

```text
uv run oc remote windows-worker contract --json
uv run oc remote windows-worker preflight --remote --json
uv run oc remote windows-worker status --json
uv run oc remote windows-worker workspace-list --json
uv run oc remote windows-worker manifest-validate MANIFEST.json
```

The pairing offer is stored outside Git at the path in the contract and must
never appear in prompts, reports, logs, manifests, or tool output. The wrapper
`scripts/paseo-windows` checks that the offer file is mode `600` and redacts
offer-shaped errors.

`status` is the worker's PowerShell state (`ready`, `paused`, `hard_off`, or
`over_limit`). `daemon-status` is only Paseo connectivity and must not be used
as a substitute for worker readiness.

## Minimal requirements

- Transport is Paseo daemon pairing/relay only. Do not install or use Tailscale,
  Windows OpenSSH, WSL2, or another tunnel for this worker.
- Every worker path is under exactly `C:\paseo`; use the `paseo` workspace, not
  the similarly named `C:\AI` workspace.
- Total `C:\paseo` usage is capped at 50 GiB. Refuse new work at or above the
  cap; report usage before and after every task.
- The owner controls availability locally with the localhost web panel at
  `http://127.0.0.1:8765/`, or with `pause`, `resume`, `hard-off`, and `hard-on`.
  Respect `paused` and `hard_off`; never try to bypass them.
- Paseo and the panel are configured to start for the current Windows user at
  login. The panel is local-only; tell the owner to open
  `http://127.0.0.1:8765/` for the switch.
- Never transfer credentials or paper/live account files. Keep market data
  temporary and delete it after the task.

## Before any research task

1. Run the iteration gates when the work belongs to a research iteration.
2. Within current action-specific permission, run a fresh
   `oc remote windows-worker preflight --remote --json` and require `ok=true`,
   actual worker `root=C:\paseo`, `status=ready`, `usage_ok=true`, `paused=false`
   and `hard_off=false`. Require a nonnegative integer `usage_bytes` strictly
   below 50 GiB. Missing, mistyped or contradictory fields do not admit work;
   rounded `usage_gib` is display information, not a readiness substitute.
3. Validate a small manifest with `oc remote windows-worker manifest-validate`:
   relative input paths, byte sizes, SHA-256, and cleanup scratch.
4. Transfer only the declared files under `C:\paseo\scratch\<job_id>`.

## After the task

Verify returned SHA-256 values. Remove scratch only after verified return,
completion, or explicit abandonment of continuation. For a recoverable pause,
power-off or lost connection, preserve the latest complete native framework
checkpoint and completed shards within C:\paseo/50 GiB. Keep the original
configuration, seed and model/data versions; retain cumulative time, cost and
trial exposure. After online + fresh ready, inspect the old job before native
resume or a same-definition rerun. A rerun is acceptable when native resume is
unsupported. Never claim a save or stop succeeded merely from disconnection;
do not build a recovery platform or wake/resume the device. Details are in
`docs/runbook-windows-compute.zh.md`.

Remote completion is workflow evidence only; it is not `research_pass`, Alpha,
paper readiness, or permission to submit orders.

## Current acceptance state

Protocol compatibility, 2026-10-13: the repository's
`deploy/windows/open-composer-worker.ps1` now publishes exact `usage_bytes`
and refuses readiness at equality with 50 GiB. This local update has not been
deployed or validated on Hadan; an older installed worker may lack the new
field and must not pass the new preflight. Within existing valid device
maintenance/deployment authorization, use the established runbook deployment
path to update `C:\paseo\open-composer-worker.ps1`, then verify the complete
response through an authorized fresh preflight before admitting a new task.
This guidance does not trigger an automatic probe, deployment, wake, resume
or hard-on. The historical acceptance below does not validate the new protocol.

The endpoint label is `hadan`. The worker scripts have passed fixture write,
hash, deletion, pause/resume, and localhost API checks. The owner has now
authorized routine research use: after iteration gates pass, high-memory
feature construction, model training, and wide backtests should prefer this
worker. The first real job should remain a small manifest-bound DLSA data
slice; expand only after its result hash and cleanup audit pass. Respect a
locally controlled `paused` or `hard_off` state and never retry around it.
