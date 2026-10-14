"""Assemble a research handoff from the current role prompt and an existing brief.

This renders instructions only: no agent, provider call, authorization or job is started.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def build_handoff(root: Path, role: str, brief: Path) -> dict[str, Any]:
    root = root.resolve()
    config_path = root / "config/research-agent-roles.json"
    config_bytes = config_path.read_bytes()
    config = json.loads(config_bytes)
    definition = config["roles"][role]
    prompt_name = definition.get("prompt")
    if not prompt_name:
        raise ValueError(
            f"Role {role!r} has no single task prompt; keep its existing reporting route"
        )
    inputs = []
    texts = []
    for label, path in (("role", Path(prompt_name)), ("task", brief)):
        path = (root / path).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"{label} input must belong to this workspace")
        content = path.read_bytes()
        value = content.decode("utf-8").strip()
        if not value:
            raise ValueError(f"Empty {label} input: {path.relative_to(root)}")
        inputs.append(
            {
                "role": label,
                "path": str(path.relative_to(root)),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
        texts.append(value)
    prompt = (
        f"# 当前角色方法\n\n{texts[0]}\n\n# 本任务上下文\n\n{texts[1]}\n\n"
        "# 接续\n\n"
        "本brief中的实验前提也需要证据，不因Root写入而免于质疑。"
        "发现目标与实验错位时主动提出受影响修订；普通执行留给完整owner。"
        "本消息不新增费用、设备或订单授权，不回改旧冻结结果；"
        "动态许可和累计预算读取现行权威文件。"
    )
    return {
        "role": role,
        "create_agent": {
            "provider": definition["provider"],
            "settings": definition["settings"],
            "initialPrompt": prompt,
        },
        "continuation_prompt": prompt,
        "bindings": [
            {
                "role": "role_configuration",
                "path": str(config_path.relative_to(root)),
                "sha256": hashlib.sha256(config_bytes).hexdigest(),
            },
            *inputs,
        ],
        "runtime_started": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", required=True)
    parser.add_argument("--brief", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = build_handoff(args.root, args.role, args.brief)
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
