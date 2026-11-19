"""Print the project rules for an agent's session start and after compaction.

Codex (.codex/hooks.json SessionStart) adds this output to the model context,
so the rules survive compaction and need not be re-read. Claude loads the
same files through CLAUDE.md imports.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ("docs/rules.md", "docs/owner-taste.md")

print(
    "Full current text of " + " and ".join(FILES) + ", loaded automatically at session "
    "start and after compaction. Follow them; there is no need to open these files again.\n"
)
for name in FILES:
    print(f"===== {name} =====\n" + (ROOT / name).read_text(encoding="utf-8"))
