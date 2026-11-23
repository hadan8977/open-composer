# Six-policy production layout

The existing six-policy service executes versioned code from
`open_composer/paper_runtime/` and `open_composer/intraday_runner/`. Its deployment
configuration is `config/paper/six-service.json`; mutable books, pending orders,
consumed IDs, risk latches, target instructions, authorization copy and event log
live under `runtime/paper/six/`. Runtime files are excluded from git. The service
refuses to start when `runtime/paper/six/runtime-state.json` is missing, so it never
creates fresh capital.

The existing authorization, expiry, capital, stops, execution windows and order
handling remain unchanged. This layout grants no authority to quant1 or any
new sleeve. Historical checkpoints, models, source pages, contracts and reviews
remain at their original evidence paths. No market datasets are copied into git.

## Frozen scientific source

The accepted research code that computes targets is kept as package copies under
`open_composer/paper_runtime/frozen_sources/`, mirroring
`reports/research/program/`. `source_loader.py` executes a copy with its historical
`__file__`, so the frozen helpers still find their evidence next to the original
path. Imports, `importlib.util.spec_from_file_location` calls and `.py` reads below
`reports/research/program/` go to the copy; a research module without a copy is
refused. The loader also maps the hard-coded `/root/codex-test/open-composer` root.
Data reads and arithmetic are unchanged. Frozen sources are excluded from automatic
formatting; some of them still compare their own inputs (and, in
`next_session_data.py`, `open_composer/market_sessions.py`) against recorded hashes.

## Runtime environments

The service runs on the uv-managed `.venv` (Python 3.11); LSTM inference runs on
`/usr/bin/python3.12` with Torch. `runtime/requirements-service.txt` and
`runtime/requirements-inference.txt` list the installed versions for rebuilding an
environment. Keep the two environments separate and do not sync a healthy running
environment.

## Deploying a change

```bash
cd /root/codex-test/open-composer
install -m 644 deploy/paper/systemd/oc-six-paper-validation.service /etc/systemd/system/oc-six-paper-validation.service
install -d /etc/systemd/system/oc-six-paper-validation.service.d
install -m 644 deploy/paper/systemd/oc-six-paper-validation.service.d/restart-after-earlyoom.conf /etc/systemd/system/oc-six-paper-validation.service.d/restart-after-earlyoom.conf
systemctl daemon-reload
systemctl restart oc-six-paper-validation.service
systemctl show oc-six-paper-validation.service --property=ActiveState,SubState,ExecMainPID,RestartForceExitStatus,OOMScoreAdjust
```

The unit keeps the existing slice, memory, swap, nice, thread and stop settings.
Its drop-in preserves the SIGTERM restart and OOM score repair. The Cockpit reads
the service state and the target identities.

## Cockpit updates

Keep the existing daily publisher on the two root crontab slots. It rebuilds
closed-session history from broker equity, owned fills and raw SIP closes.
Use a separate read-only cron entry for current balances on `/paper/accounts`.
On the VPS, `/etc/cron.d/open-composer-paper-snapshots` runs:

```cron
* * * * * root cd /root/codex-test/open-composer && flock -n runtime/paper/account-snapshots.lock sh -c 'for account in legacy six quant1; do timeout -k 3 15 .venv/bin/python -m scripts.capture_paper_account_snapshots "$account" || logger -t oc-paper-snapshots "$account refresh failed"; done' >> logs/paper_account_snapshots.log 2>&1
```

## Tests

Run one pytest process at a time. `make verify` runs the release checks; the
six-policy tests are `tests/test_six_paper_*.py`, `tests/test_paper_*.py`,
`tests/test_STATE_quantity_lock_transition.py` and `tests/test_source_*.py`. Several
of them need the Linux host (`fcntl`, Python 3.11, evidence under
`/root/codex-test/open-composer`).
