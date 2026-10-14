import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "research_task_prompt", Path(__file__).parents[1] / "scripts/research_task_prompt.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def setup_workspace(root):
    (root / "config").mkdir()
    (root / "prompts").mkdir()
    (root / "prompts/owner.md").write_text(
        "Challenge the experiment premise before implementation."
    )
    (root / "brief.md").write_text(
        "Evaluate a historical method; do not claim current profitability."
    )
    config = {
        "roles": {
            "execution": {
                "provider": "codex/model-a",
                "settings": {"thinkingOptionId": "xhigh", "modeId": "full-access"},
                "prompt": "prompts/owner.md",
            },
            "reporting": {"prompts": ["existing-route.md"]},
        }
    }
    (root / "config/research-agent-roles.json").write_text(json.dumps(config))
    return config


def test_current_prompt_and_model_are_consumed_without_cached_copy(tmp_path):
    config = setup_workspace(tmp_path)
    first = MODULE.build_handoff(tmp_path, "execution", Path("brief.md"))
    (tmp_path / "prompts/owner.md").write_text(
        "NEW: distinguish source replication from current value."
    )
    config["roles"]["execution"]["provider"] = "codex/model-b"
    (tmp_path / "config/research-agent-roles.json").write_text(json.dumps(config))
    second = MODULE.build_handoff(tmp_path, "execution", Path("brief.md"))
    assert first["create_agent"]["provider"] == "codex/model-a"
    assert second["create_agent"]["provider"] == "codex/model-b"
    assert "NEW:" in second["create_agent"]["initialPrompt"]
    assert "Challenge the experiment premise" not in second["create_agent"]["initialPrompt"]
    assert first["bindings"] != second["bindings"]


def test_changed_brief_reaches_actual_handoff_without_losing_role(tmp_path):
    setup_workspace(tmp_path)
    (tmp_path / "brief.md").write_text("Current scope changed: retain the old failed experiment.")
    result = MODULE.build_handoff(tmp_path, "execution", Path("brief.md"))
    assert "Current scope changed" in result["create_agent"]["initialPrompt"]
    assert "Challenge the experiment premise" in result["continuation_prompt"]
    assert result["runtime_started"] is False


@pytest.mark.parametrize("missing", ["prompts/owner.md", "brief.md"])
def test_missing_canonical_input_does_not_silently_use_an_old_copy(tmp_path, missing):
    setup_workspace(tmp_path)
    (tmp_path / missing).unlink()
    with pytest.raises(FileNotFoundError):
        MODULE.build_handoff(tmp_path, "execution", Path("brief.md"))


def test_report_route_is_not_replaced_by_task_creation(tmp_path):
    setup_workspace(tmp_path)
    with pytest.raises(ValueError, match="existing reporting route"):
        MODULE.build_handoff(tmp_path, "reporting", Path("brief.md"))
