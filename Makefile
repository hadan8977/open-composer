UV_CACHE_DIR ?= /tmp/open-composer-uv-cache
MONITOR_INTERVAL_SECONDS ?= 60
MONITOR_MAX_CYCLES ?= 1
PAPER_STRATEGY ?= qqq_pullback_15m
MAINTAINED_PYTHON := open_composer scripts tests
# A shared editable environment must still import the checkout under review.
export PYTHONPATH := $(CURDIR)$(if $(PYTHONPATH),:$(PYTHONPATH))
TEST_THREADS := OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
# Frozen T21/T15D research sources: retain the bytes behind the historical results.
# T21 build_5m/features are also pinned by the 2026-10-16/26 input/source manifests;
# t15d_tables renders the frozen t20261006_15_intraday_rules results_d.json.
# Exclude only these sources from blanket release lint/format, not their consumers/tests.
FROZEN_RESEARCH_PYTHON := ["scripts/t21_intraday_ml/**", "scripts/t15d_tables.py"]

# Keep the full release path serial, including when make is invoked with -j.
.NOTPARALLEL:

.PHONY: start bootstrap doctor readiness deploy-prepare repo-check capability-test agent-parity test test-fast test-full test-research-snapshots test-native-resource verify-paper lint format format-check check feature-validate paper-readiness paper-sync paper-sync-account paper-status paper-reconcile paper-alerts paper-monitor paper-monitor-sync paper-monitor-loop paper-monitor-loop-sync cockpit-v2 verify

start:
	./scripts/setup-local.sh

bootstrap:
	# --extra workbench: the research loop's tearsheet/tracking path (quantstats,
	# mlflow) is exercised by the test suite; a plain `uv sync` uninstalls it and
	# tests/test_kernel_loop_run_experiment.py then fails on a null tearsheet path.
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv sync --extra workbench

doctor:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run --no-sync oc doctor

readiness:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run --no-sync oc readiness --strict

deploy-prepare:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run --no-sync oc deploy prepare --strict

repo-check:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run --no-sync oc repo check --strict

capability-test:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run --no-sync oc capability test

agent-parity:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run --no-sync python scripts/check-agent-parity.py

test:
	$(TEST_THREADS) UV_CACHE_DIR=$(UV_CACHE_DIR) uv run --no-sync pytest

test-fast:
	$(TEST_THREADS) UV_CACHE_DIR=$(UV_CACHE_DIR) uv run --no-sync pytest

test-full:
	$(TEST_THREADS) UV_CACHE_DIR=$(UV_CACHE_DIR) uv run --no-sync pytest --runslow

test-research-snapshots:
	$(TEST_THREADS) UV_CACHE_DIR=$(UV_CACHE_DIR) uv run --no-sync pytest --runslow --research-snapshots -m research_snapshot

# Physical admission proofs require the real kernel profile, not mocked limits.
test-native-resource:
	$(TEST_THREADS) UV_CACHE_DIR=$(UV_CACHE_DIR) scripts/run_capped.sh --mem 400M --swap 0 --wait-min 0 -- taskset -c 0 uv run --no-sync pytest tests/test_source_runtime_suffix.py --runslow --native-resource -m native_resource

lint:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run --no-sync ruff check --config 'lint.exclude = $(FROZEN_RESEARCH_PYTHON)' $(MAINTAINED_PYTHON)

format:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run --no-sync ruff format --config 'format.exclude = $(FROZEN_RESEARCH_PYTHON)' $(MAINTAINED_PYTHON)

format-check:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run --no-sync ruff format --check $(MAINTAINED_PYTHON) --config 'format.exclude = $(FROZEN_RESEARCH_PYTHON)'

check: format-check lint test

feature-validate:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run --no-sync oc feature validate --strict

paper-readiness:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run --no-sync oc paper readiness $(PAPER_STRATEGY)

paper-sync:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run --no-sync oc paper sync

paper-sync-account:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run --no-sync oc paper sync-account

paper-status:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run --no-sync oc paper status

paper-reconcile:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run --no-sync oc paper reconcile

paper-alerts:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run --no-sync oc paper alerts

paper-monitor:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run --no-sync oc paper monitor

paper-monitor-sync:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run --no-sync oc paper monitor --sync-broker

paper-monitor-loop:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run --no-sync oc paper monitor-loop --interval-seconds $(MONITOR_INTERVAL_SECONDS) --max-cycles $(MONITOR_MAX_CYCLES)

paper-monitor-loop-sync:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run --no-sync oc paper monitor-loop --sync-broker --interval-seconds $(MONITOR_INTERVAL_SECONDS) --max-cycles $(MONITOR_MAX_CYCLES)

verify: format-check lint test-full repo-check capability-test agent-parity deploy-prepare feature-validate readiness

verify-paper: verify test-native-resource

# Cockpit front end B (frontend/cockpit-v2, React/Vite): type-check and build
# the static bundle into open_composer/cockpit/static/v2, which the cockpit
# serves at /v2/ when it exists. Needs node 22 + pnpm; the server never does.
cockpit-v2:
	cd frontend/cockpit-v2 && pnpm install --frozen-lockfile --ignore-scripts && pnpm exec tsc --noEmit && ../../scripts/run_capped.sh --mem 1.2G -- pnpm exec vite build
