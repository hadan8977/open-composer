from __future__ import annotations

import shutil
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    source_root = root / ".agents" / "skills"
    target_root = root / ".claude" / "skills"
    if not source_root.exists():
        raise SystemExit(".agents/skills is missing")
    target_root.mkdir(parents=True, exist_ok=True)
    for stale in target_root.iterdir():
        if stale.is_dir() and not (source_root / stale.name).exists():
            shutil.rmtree(stale)
    for skill_dir in sorted(path for path in source_root.iterdir() if path.is_dir()):
        target_dir = target_root / skill_dir.name
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(skill_dir, target_dir)
    print(f"synced {len([path for path in source_root.iterdir() if path.is_dir()])} skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
