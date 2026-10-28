# Six-policy production layout

The existing six-policy service executes versioned code from
`open_composer/paper_runtime/` and `open_composer/intraday_runner/`. Its deployment
configuration is `config/paper/six-service.json`; mutable books, pending orders,
consumed IDs, risk latches, target instructions, authorization copy and event log
live under `runtime/paper/six/`. Runtime files are excluded from git.

The existing authorization, expiry, capital, stops, execution windows and order
handling remain unchanged. This migration grants no authority to quant1 or any
new sleeve. Historical checkpoints, models, source pages, contracts and reviews
remain at their original evidence paths. No market datasets are copied into git.

## Scientific source identity

`open_composer/paper_runtime/source-manifest.json` records exact accepted source
bytes and original evidence identities. The scientific child executes package
copies through an allowlisted loader. `__file__` still identifies the historical
receipt, so existing source/model/clock checks retain their meaning.

The loader adapts only source-text reads, dynamic Python loading, imports from
manifest directories, and the two fixed installation-root literals. Numerical
expressions, frozen model state, date boundaries and authorization checks are
unchanged. Source hashes are verified before compilation; an unlisted research
source or a source from another repository root is refused. Frozen sources are
excluded from automatic formatting and are checked by their byte hashes.

## Runtime pins and read-only verification

`runtime/environment.json` records the actual service Python 3.11.15 and inference
`/usr/bin/python3.12` 3.12.3, executable digests, complete relevant dependency
closures, DuckDB 1.5.5 and PyArrow 24.0.0 for the active numeric readers, and Torch
build `2.13.0+cu130` with its CUDA and git build identities.
`runtime/requirements-service.txt` and `runtime/requirements-inference.txt` pin
those installed distributions. The Torch distribution version is `2.13.0`;
its separate build tag is verified explicitly. Installing a different build with
the same distribution version does not pass verification.

Restore the exact interpreter and pinned distributions from matching package
artifacts before restarting a damaged environment. Python 3.12's OS package
versions and the uv-managed service interpreter location are in the manifest.
Keep the two environments separate. Do not recreate or sync a healthy running
environment during integration.

From the live checkout, these commands read metadata and source files. The service
check also imports the pinned DuckDB, NumPy, pandas and PyArrow Parquet readers
to catch missing native reader implementations. It reads no dataset or model;
neither check imports Torch, loads credentials, fetches data or constructs a broker client:

```bash
.venv/bin/python deploy/paper/runtime/verify_runtime.py --environment service
/usr/bin/python3.12 deploy/paper/runtime/verify_runtime.py --environment inference
.venv/bin/python -m open_composer.paper_runtime.migrate --root /root/codex-test/open-composer
```

Both interpreter checks also run as systemd `ExecStartPre` checks. A mismatched
binary or dependency prevents restart, and an absent relocated ledger prevents
the service from initializing fresh capital.

The reader audit follows the current service and its finite input producer.
Saved arrays use NumPy; Parquet reads use PyArrow; H5 uses retained scalar tree
evaluation and gzip/JSON state. The inactive LightGBM fitting/prediction lifecycle,
HDF5 readers, optional research engines and cloud storage readers are outside
this deployment lock. Saved LSTM checkpoints remain in the separately pinned
Torch/NumPy inference environment.

## Coordinated integration

The interactive owner of integration reviews the migration and tests, copies
only `integration-files.json` paths, and performs the following outside
13:30–21:00 UTC. The migration command enforces that window and refuses an active
service. This worker has not stopped, restarted or written to any broker.

```bash
cd /root/codex-test/open-composer
systemctl stop oc-six-paper-validation.service
.venv/bin/python -m open_composer.paper_runtime.migrate --root "$PWD" --apply
install -m 644 deploy/paper/systemd/oc-six-paper-validation.service /etc/systemd/system/oc-six-paper-validation.service
install -d /etc/systemd/system/oc-six-paper-validation.service.d
install -m 644 deploy/paper/systemd/oc-six-paper-validation.service.d/restart-after-earlyoom.conf /etc/systemd/system/oc-six-paper-validation.service.d/restart-after-earlyoom.conf
systemctl daemon-reload
systemctl start oc-six-paper-validation.service
systemctl show oc-six-paper-validation.service --property=ActiveState,SubState,ExecMainPID,RestartForceExitStatus,OOMScoreAdjust
```

The migration takes the same file lock as the service, preserves every input
byte, verifies the copied hashes and source stability, fsyncs the files and
directories, then renames the complete runtime directory atomically. It never
removes original files. Interrupted staging directories are retained for repair.
A marked destination is never overwritten on a repeated invocation, including
after the new service has processed subsequent fills. An unmarked destination
requires inspection. The original directory is evidence and a pre-cutover
rollback snapshot; once the new service has advanced, do not restore that older
ledger or restart the old unit against it.

The new unit retains the existing slice, memory, swap, nice, thread and stop
settings. Its drop-in preserves the installed SIGTERM restart and OOM score
repair. The Cockpit can read the relocated state and both original and relocated
target identities, so old evidence remains inspectable.

## Verification commands

Run one pytest process at a time with the existing memory guard. The accepted
scientific fixtures are read-only and require the existing evidence tree;
`OPEN_COMPOSER_ROOT` selects that evidence while `PYTHONPATH` selects candidate
code during worktree review:

```bash
scripts/run_capped.sh --class paper --mem 900M --swap 0 -- env OPEN_COMPOSER_ROOT=/root/codex-test/open-composer PYTHONPATH=/root/codex-test/oc-restructure-paper-20261028 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 /root/codex-test/open-composer/.venv/bin/python -m pytest tests/test_paper_production_migration.py tests/test_six_paper_service.py tests/test_six_paper_service_fill_regression.py tests/test_six_paper_input_hook.py tests/test_six_paper_order_lookup_evidence.py tests/test_source_state_checkpoint.py tests/test_cockpit_paper_trials.py tests/test_cockpit_input_recovery_reading.py tests/test_dated_refresh_exec_recovery.py tests/test_paper_formation_continuity.py
```

No test activation, new timer, authorization renewal or numerical job is needed
to validate this relocation. A historical recovery manifest remains evidence of
its original code/runtime; it cannot authorize recovery with changed code.
