"""One-off helper (not a batch module): recompute DSR for the T-20260929-01
27-candidate joint family (12 LETF primary + 3 RAND placebo + 12 DIP), and
for the 24-candidate non-placebo family, using the SAME excess-return
construction `screen_lane.evaluate_candidate` uses internally, with
`n_trials` overridden to 27 and 24 respectively (the per-iteration
leaderboard.json files each report their own local n_trials -- 15 and 12 --
per screen_batch.py's own automatic computation; this script answers the
queue task's separate instruction to report the DSR of the full 27/24
family jointly). Read-only: writes one small JSON file, does not touch
either iteration's own results.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "screen_batches"))

import h20260929_01_dip_rejudge as dip_batch  # noqa: E402
import h20260929_01_letf_flow_reversal as letf_batch  # noqa: E402
import screen_lane as lane  # noqa: E402

ALL_CANDIDATES = list(letf_batch.CANDIDATES) + list(dip_batch.CANDIDATES)
NON_PLACEBO = [c for c in ALL_CANDIDATES if not c.id.endswith("_RAND")]

assert len(ALL_CANDIDATES) == 27
assert len(NON_PLACEBO) == 24


def main() -> None:
    close, _open, leg_open, leg_close, rf = lane.load_batch_panel(ALL_CANDIDATES)
    shy_ret = (close[lane.CASH] / close[lane.CASH].shift(1) - 1.0).fillna(0.0)
    s3_ret10, _s3_turn10 = lane.s3_incumbent(close, leg_open, leg_close, lane.COST_BPS_PRIMARY)

    out: dict[str, dict] = {}
    for n_trials, label in ((27, "family_27_all"), (24, "family_24_non_placebo")):
        pool = ALL_CANDIDATES if n_trials == 27 else NON_PLACEBO
        for c in pool:
            result = lane.evaluate_candidate(
                c,
                close=close,
                leg_open=leg_open,
                leg_close=leg_close,
                rf=rf,
                shy_ret=shy_ret,
                s3_ret10=s3_ret10,
                n_trials=n_trials,
            )
            out.setdefault(c.id, {})[label] = result.get("dsr_anchor")
        print(f"{label} done", flush=True)

    (
        ROOT / "reports/research/iterations/h20260929_01_letf_flow_reversal" / "combined-dsr.json"
    ).write_text(json.dumps(out, indent=2), encoding="utf-8")
    (
        ROOT / "reports/research/iterations/h20260929_01_dip_rejudge" / "combined-dsr.json"
    ).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("wrote combined-dsr.json to both iteration directories")


if __name__ == "__main__":
    main()
