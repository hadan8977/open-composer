# Windows research compute through Paseo

Hadan is a temporary research executor through its existing Windows Paseo daemon. It is not a broker, paper-trading host or permanent market-data store. Transport is Paseo pairing/relay only: no Tailscale, Windows OpenSSH, WSL2 or alternative tunnel.

[config/windows-paseo-worker.json](../config/windows-paseo-worker.json) defines the endpoint (`hadan`), workspace (`paseo`), wrapper and protected offer-file location. All project files, worker scripts, workspace, scratch, temporary files, checkpoints and result caches must be inside exactly `C:\paseo`; total usage must remain strictly below 50 GiB. The installed Paseo executable may reside at its standard installation path; that is not another project workspace.

Current action permission comes from `reports/research/control/owner-compute-hold.json` and the admitted task, not an old pause/resume statement or this runbook. Training and optimizer updates can use suitable already-authorized resources with valid inputs, manifests and remaining budgets. Do not revive withdrawn experiments, add spending, wake the device, resume it, or issue `hard-on`. High-memory research prefers Hadan when suitable and ready; otherwise use an already-approved fallback within its own admission.

## Readiness and discovery

Use the CLI adapter rather than constructing host commands or exposing the pairing offer:

```text
uv run oc remote windows-worker contract --json
uv run oc remote windows-worker preflight --remote --json
uv run oc remote windows-worker status --json
uv run oc remote windows-worker daemon-status --json
uv run oc remote windows-worker workspace-list --json
uv run oc remote windows-worker manifest-validate MANIFEST.json
```

A fresh remote preflight for each dispatch must show:

| Field | Required value |
|---|---|
| Top-level `ok` | `true` |
| `remote.worker_status.root` | `C:\paseo` |
| `remote.worker_status.status` | `ready` |
| `usage_ok`, `paused`, `hard_off` in worker status | `true`, `false`, `false` |
| `usage_bytes` in worker status | Nonnegative integer, strictly below `50 * 1024^3` |

Missing, mistyped or conflicting fields do not admit work. Rounded `usage_gib` is display information. `daemon-status` shows relay connectivity, not worker readiness. Include anticipated peak added space, including downloads/model loads, in the headroom decision; preflight alone does not reserve future space.

`scripts/paseo-windows` uses the offer stored outside Git with mode `600`, redacts offer-shaped errors, and reuses the control terminal ID in `~/.config/open-composer/paseo-windows-worker-state.json`. A stale control terminal can be recreated by the adapter. Never put offers into prompts, logs, manifests, reports or tool output, and never read broker credentials to set up research.

Protocol validation uses the actual fresh response. The local `deploy/windows/open-composer-worker.ps1` publishes exact `usage_bytes` and rejects equality with50GiB, but local source or a dated fixture is not proof of the remote version. Missing required fields block that dispatch until the established maintenance path resolves the mismatch; a stale deployment note is not evidence of a current fault.

## Manifest-bound dispatch

Apply the native gates for the actual research work before dependent computation. Source/plan/review preparation stays within its separate scope; it does not authorize training or backtests.

Prepare a complete brief and manifest before transfer. The existing validator in `open_composer/remote/windows_worker.py` checks:

- `job_id`: nonempty, using letters, digits, `.`, `_` or `-`.
- `remote_root`: `C:\paseo`; `remote_scratch`: `C:\paseo\scratch\<job_id>`.
- Nonempty `inputs`: each has project-relative `local_path`, exact `bytes` and `sha256`; no absolute path, traversal or resolved path outside the repository.
- `cleanup.required=true`.
- If supplied, `expected_added_bytes` is an integer covering at least the inputs and below 50 GiB. Include it for peak-footprint accounting; the validator reports `dynamic_headroom_checked=false`, so compare it with actual worker usage separately.

Transfer only declared dates, symbols, features and code into that job's scratch directory. Do not copy the whole minute archive, `.env`, keys, cookies, private keys or paper/live account files. Report total usage before and after the task and verify every returned SHA-256 before cleanup.

Use `open_composer.remote.windows_worker.run_worker_command` to invoke native Paseo `run` against the contract's workspace, with a complete prompt and task/job identity. Take model/effort defaults from [research/workflow.json](../research/workflow.json); do not copy older worker-specific defaults. The command shape is:

```text
run --cwd C:\paseo --provider <configured-provider> --thinking <configured-effort> --mode full-access --background --json <complete-task-prompt>
inspect <agentId> --json
```

Inspect through the same remote wrapper once to verify actual model, reasoning, mode, working directory and task ownership. Record unsupported readback honestly. Local Linux Paseo MCP plus a changed cwd does not dispatch to Windows. If launch response is uncertain, inspect the existing job/PID/output before retrying; command delivery does not prove process startup.

For native Python, set `PYTHONUTF8=1` and use `-X utf8` in a parent invocation when needed to avoid GBK decoding of UTF-8 files. Transfer long PowerShell scripts as manifest inputs and launch them with a short `-File` command rather than exceeding terminal command limits. Do not restart an unaffected running task merely to update an environment convention.

## Owner controls and installation

The local panel at `http://127.0.0.1:8765/` binds loopback only. It is not a remote command interface. Paseo and the panel are configured to start at the current Windows user's login.

For authorized installation/maintenance, pair the existing Windows daemon and protect the offer on Linux. Confirm that remote workspace discovery identifies Hadan rather than the Linux daemon. Transfer `deploy/windows/open-composer-worker.ps1` and `deploy/windows/open-composer-worker-web.ps1` into `C:\paseo`, then start the panel locally:

```powershell
pwsh -File C:\paseo\open-composer-worker-web.ps1
```

The established login-startup installer is:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\paseo\install-open-composer-worker-autostart.ps1
```

It starts the existing `C:\Program Files\Paseo\Paseo.exe` and the panel; no extra network service is needed. These are deployment commands, not actions to run during ordinary research or documentation work.

The owner can use the panel or local PowerShell:

```powershell
$workerScript = "C:\paseo\open-composer-worker.ps1"
& $workerScript status
& $workerScript pause
& $workerScript resume
& $workerScript hard-off
& $workerScript hard-on
& $workerScript cleanup JOB_ID
```

`pause` refuses new work without forcibly killing an existing task. Cooperative research jobs should stop adding work and checkpoint at a safe point when they detect it. `hard-off` writes the hard-off marker and stops Paseo; only the owner locally restores it with `hard-on`. Research agents must never operate around these controls.

For initial acceptance, check daemon/workspace identity, the complete fresh readiness response, native PowerShell/Python fixtures, one small manifest-bound upload, hash return and cleanup, plus owner-local panel controls. Do not substitute old deployment or fixture records for a current ready response before a real job.

## Interruption, recovery and cleanup

The owner may pause or power off at any time. Calendar daytime predicts availability; it never admits execution. Use native framework checkpoints and completed shards with the original configuration, seed and model/data versions. Retain the latest complete usable checkpoint within the same 50 GiB total cap.

During a recoverable pause or disconnect, preserve the only valid checkpoint and completed shards. A disconnect proves neither a successful save nor a stopped process. When connectivity returns and a fresh preflight is ready, inspect the old process and outputs first; use native resume where supported, otherwise a same-definition rerun or continuation from completed shards. Keep cumulative time, cost, model fits/optimizer updates and trial exposure; renaming a job does not reset them. Stop the affected work if remaining admission is insufficient.

Clean scratch after verified return/completion or explicit abandonment of continuation. Checkpoints are temporary job state, not an indefinite cache. Do not build another recovery daemon or delete the only unreturned recovery point.

## Availability observation

`oc-hadan-availability.timer` runs a local due check every five minutes. [config/hadan-availability-watch.json](../config/hadan-availability-watch.json) controls remote observation cadence: currently every 15 minutes on Beijing-time weekdays 09:00-19:00, otherwise hourly, without holiday inference. Results and change events use `reports/research/control/hadan-availability.json`. Unknown/timeouts remain unknown. Observation is separate from dispatch; every real task still needs its own fresh preflight and current action permission.
