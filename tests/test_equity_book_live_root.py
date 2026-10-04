"""OC_EQUITY_BOOK_DIR redirects every equity-book directory constant; unset keeps the snapshot."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data/research/equity_book"

_PROBE = """
import json, sys
sys.path.insert(0, "scripts")
from open_composer.research.equity_book import panel, risk, signals
import build_book_v1_alpha as alpha
import build_equity_book_panel as bp
print(json.dumps({
    "default": str(panel.DEFAULT_DIR),
    "risk": str(risk.RISK_DIR),
    "signals": str(signals.SIGNALS_DIR),
    "alpha": str(alpha.OUT_DIR),
    "panel_out": str(bp.OUT),
}))
"""


def _constants(env_dir: str | None, tmp_path: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "OC_EQUITY_BOOK_DIR"}
    if env_dir is not None:
        env["OC_EQUITY_BOOK_DIR"] = env_dir
    out = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_unset_keeps_research_snapshot(tmp_path: Path) -> None:
    c = _constants(None, tmp_path)
    assert c["default"] == str(SNAPSHOT)
    assert c["panel_out"] == str(SNAPSHOT)
    assert c["risk"] == str(SNAPSHOT / "risk")
    assert c["signals"] == str(SNAPSHOT / "signals")
    assert c["alpha"] == str(SNAPSHOT / "alpha" / "book_v1")


def test_empty_value_counts_as_unset(tmp_path: Path) -> None:
    assert _constants("", tmp_path)["default"] == str(SNAPSHOT)


def test_set_moves_every_constant(tmp_path: Path) -> None:
    live = tmp_path / "live_book"
    c = _constants(str(live), tmp_path)
    assert c["default"] == str(live)
    assert c["panel_out"] == str(live)
    assert c["risk"] == str(live / "risk")
    assert c["signals"] == str(live / "signals")
    assert c["alpha"] == str(live / "alpha" / "book_v1")
