UV_CACHE_DIR ?= /tmp/open-composer-uv-cache
NPM_CONFIG_CACHE ?= /tmp/open-composer-npm-cache
MONITOR_INTERVAL_SECONDS ?= 60
MONITOR_MAX_CYCLES ?= 1
PAPER_STRATEGY ?= qqq_pullback_15m

VPS_DEPLOY_ARGS ?=
VPS_STOP_ARGS ?=

.PHONY: start bootstrap doctor readiness deploy-prepare repo-check capability-test agent-parity test test-fast test-full lint format check dashboard-catalog dashboard-html dashboard-build dashboard-dev dashboard-serve dashboard-check feature-validate paper-readiness paper-sync paper-sync-account paper-status paper-reconcile paper-alerts paper-monitor paper-monitor-sync paper-monitor-loop paper-monitor-loop-sync vps-plan vps-deploy vps-stop verify

start:
	./scripts/setup-local.sh

bootstrap:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv sync
	NPM_CONFIG_CACHE=$(NPM_CONFIG_CACHE) npm --prefix dashboard install

doctor:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run oc doctor

readiness:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run oc readiness --strict

deploy-prepare:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run oc deploy prepare --strict

repo-check:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run oc repo check --strict

capability-test:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run oc capability test

agent-parity:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run python scripts/check-agent-parity.py

test:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run pytest

test-fast:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run --with pytest-xdist pytest -n 2

test-full:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run --with pytest-xdist pytest --runslow -n 2

lint:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run ruff check .

format:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run ruff format .

check: format lint test

dashboard-catalog:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run oc dashboard catalog

dashboard-html:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run oc dashboard html

dashboard-build: dashboard-catalog
	NPM_CONFIG_CACHE=$(NPM_CONFIG_CACHE) npm --prefix dashboard run build

dashboard-dev: dashboard-catalog
	NPM_CONFIG_CACHE=$(NPM_CONFIG_CACHE) npm --prefix dashboard run dev

dashboard-serve: dashboard-build
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run oc dashboard serve

dashboard-check: dashboard-html dashboard-build

feature-validate:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run oc feature validate --strict

paper-readiness:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run oc paper readiness $(PAPER_STRATEGY)

paper-sync:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run oc paper sync

paper-sync-account:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run oc paper sync-account

paper-status:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run oc paper status

paper-reconcile:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run oc paper reconcile

paper-alerts:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run oc paper alerts

paper-monitor:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run oc paper monitor

paper-monitor-sync:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run oc paper monitor --sync-broker

paper-monitor-loop:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run oc paper monitor-loop --interval-seconds $(MONITOR_INTERVAL_SECONDS) --max-cycles $(MONITOR_MAX_CYCLES)

paper-monitor-loop-sync:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run oc paper monitor-loop --sync-broker --interval-seconds $(MONITOR_INTERVAL_SECONDS) --max-cycles $(MONITOR_MAX_CYCLES)

vps-plan:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run oc dashboard deploy-vps $(VPS_DEPLOY_ARGS)

vps-deploy:
	UV_CACHE_DIR=$(UV_CACHE_DIR) NPM_CONFIG_CACHE=$(NPM_CONFIG_CACHE) ./scripts/deploy-vps.sh $(VPS_DEPLOY_ARGS)

vps-stop:
	./scripts/stop-remote-dashboard.sh $(VPS_STOP_ARGS)

verify: format lint test-full repo-check capability-test agent-parity deploy-prepare dashboard-check feature-validate readiness
