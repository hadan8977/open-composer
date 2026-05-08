from __future__ import annotations

from pathlib import Path

from open_composer.config import ensure_dir
from open_composer.models.strategy_spec import StrategySpec


def write_python_stub(spec: StrategySpec, path: Path) -> Path:
    ensure_dir(path.parent)
    path.write_text(
        "\n".join(
            [
                f'"""Generated strategy stub for {spec.name}."""',
                "",
                "# The deterministic MVP engine evaluates StrategySpec expressions directly.",
                "# Custom strategy code can be added here in later slices.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path
