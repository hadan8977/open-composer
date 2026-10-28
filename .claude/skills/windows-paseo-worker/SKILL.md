---
name: windows-paseo-worker
description: >
  Use the owner's Windows research worker through Paseo, with its fixed
  C:\paseo root, 50 GiB cap, local pause controls, preflight, manifest,
  transfer verification and recovery/cleanup requirements.
---

# Windows research worker

Read [the machine contract](../../../config/windows-paseo-worker.json) and [the Windows runbook](../../../docs/runbook-windows-compute.zh.md) for deployment, dispatch, native checkpoint recovery and cleanup. This worker is a temporary research executor, never a broker or paper host. Models/effort come from [the runtime role bindings](../../../research/workflow.json), not a duplicated skill default.

```text
uv run --no-sync oc remote windows-worker contract --json
uv run --no-sync oc remote windows-worker preflight --remote --json
uv run --no-sync oc remote windows-worker status --json
uv run --no-sync oc remote windows-worker workspace-list --json
uv run --no-sync oc remote windows-worker manifest-validate MANIFEST.json
```

For admitted remote work, require a fresh preflight with `ok=true`, worker `root=C:\paseo`, `status=ready`, `usage_ok=true`, `paused=false`, `hard_off=false`, and nonnegative integer `usage_bytes` strictly below 50 GiB. Rounded `usage_gib` and daemon connectivity cannot replace this evidence. Missing, mistyped or conflicting fields block dispatch; inspect the old job before any uncertain retry.

Keep every project workspace, scratch, temporary file, checkpoint and result cache inside `C:\paseo`. Use Paseo pairing/relay only; never use another tunnel, wake/resume/hard-on the device, or bypass local pause/hard-off. The pairing offer stays outside Git and must not enter prompts, logs, manifests or tool output.

Bind relative paths, byte sizes, SHA-256 and peak added space to a manifest before transfer into `C:\paseo\scratch\<job_id>`. Do not transfer credentials or paper/live account files. Verify returned hashes, preserve the latest complete native checkpoint/completed shards during recoverable interruptions, and clean scratch only after verified return/completion or explicit abandonment. Report usage before and after the task and retain cumulative time, cost and trial exposure. A disconnect proves neither checkpoint success nor process termination.

Local script support and historical fixture acceptance do not establish current remote readiness; use the actual fresh worker response.
