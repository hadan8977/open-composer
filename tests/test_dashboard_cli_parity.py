from __future__ import annotations

from open_composer.dashboard.server import DASHBOARD_CLI_PARITY

DASHBOARD_ACTIONS = {
    "POST /api/build/draft": "oc strategy draft",
    "POST /api/projects/{id}/queue": "oc project continue",
    "POST /api/projects/{id}/stop": "oc agent stop",
    "POST /api/strategies/{name}/actions/evidence": "oc strategy evidence",
    "POST /api/strategies/{name}/actions/materialize": "oc feature materialize",
    "POST /api/strategies/{name}/actions/promote": "oc strategy approve",
    "POST /api/strategies/{name}/actions/activate": "oc strategy activate",
    "POST /api/strategies/{name}/actions/disable": "oc strategy disable",
    "POST /api/strategies/{name}/spec/accept": "oc strategy approve",
    "POST /api/paper/kill-switch": "oc paper kill-switch",
    "POST /api/paper/sync": "oc paper sync / oc paper sync-account",
    "POST /api/paper/monitor/refresh": "oc paper monitor",
    "POST /api/settings/capabilities/test": "oc capability test",
    "POST /api/settings/agent-backend": "oc agent use",
}

RELEVANT_CLI_COMMANDS = {
    "oc strategy draft",
    "oc project continue",
    "oc agent stop",
    "oc strategy evidence",
    "oc feature materialize",
    "oc strategy approve",
    "oc strategy activate",
    "oc strategy disable",
    "oc paper kill-switch",
    "oc paper sync",
    "oc paper monitor",
    "oc capability test",
    "oc agent use",
}


def test_every_dashboard_action_has_cli_equivalent() -> None:
    assert DASHBOARD_CLI_PARITY == DASHBOARD_ACTIONS


def test_every_relevant_cli_command_has_dashboard_action() -> None:
    parity_text = "\n".join(DASHBOARD_CLI_PARITY.values())
    missing = [command for command in sorted(RELEVANT_CLI_COMMANDS) if command not in parity_text]
    assert missing == []
