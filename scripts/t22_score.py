# ruff: noqa: E501
"""T-20261006-22 scorecard: scorecard_v2.score_family over the 24 main cells (contract.md section 16).

    uv run python scripts/t22_score.py
Reads ``<store>/results/{A,B,offsets,offsets_stress}``, ``placebo.json``, ``whole_share.json``,
``checks.json``; writes ``<store>/results/scorecard.json``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from open_composer.research import scorecard_v2 as sc  # noqa: E402
from open_composer.research.equity_book.evaluate import load_rf_spy  # noqa: E402
from scripts import t22_run as R  # noqa: E402

END = "2026-09-15"
REG = ROOT / "data/research/equity_book/regimes"
CHECKS = ROOT / "reports/research/iterations/t20261006_22_st_reversal/checks.json"


def series(tag: str, cell: str, col: str, a: str, b: str) -> pd.Series:
    d = pd.read_parquet(R.RES / tag / f"{cell}.parquet")[[col]]
    return d.loc[a:b, col]


def main() -> None:
    sel = json.loads((R.RES / "selected.json").read_text())
    cells = sorted(f.stem for f in (R.RES / "A").glob("R_U*.parquet"))
    stress_ok = all((R.RES / "B" / f"{c}.parquet").exists() for c in cells)
    rows = []
    for c in cells:
        for off, (tagr, tags) in {0: ("A", "B")}.items():
            if c == sel["cell_id"] and sel["H"] == 5 and (R.RES / "offsets").exists():
                continue
            net_r, gross_r = (
                series(tagr, c, "net", "2024-01-08", END),
                series(tagr, c, "gross", "2024-01-08", END),
            )
            if stress_ok:
                net_s, gross_s = (
                    series(tags, c, "net", "2017-10-02", "2023-08-31"),
                    series(tags, c, "gross", "2017-10-02", "2023-08-31"),
                )
                net_r, gross_r = pd.concat([net_s, net_r]), pd.concat([gross_s, gross_r])
            rows.append(
                pd.DataFrame(
                    {
                        "date": net_r.index,
                        "variant": c,
                        "offset": off,
                        "net": net_r.to_numpy(),
                        "gross": gross_r.to_numpy(),
                    }
                )
            )
    if sel["H"] == 5 and (R.RES / "offsets").exists():
        for k in range(5):
            name = f"OFF{k}_{sel['cell_id']}"
            n = series("offsets", name, "net", "2024-01-08", END)
            g = series("offsets", name, "gross", "2024-01-08", END)
            if (R.RES / "offsets_stress" / f"{name}.parquet").exists():
                n = pd.concat(
                    [series("offsets_stress", name, "net", "2017-10-02", "2023-08-31"), n]
                )
                g = pd.concat(
                    [series("offsets_stress", name, "gross", "2017-10-02", "2023-08-31"), g]
                )
            rows.append(
                pd.DataFrame(
                    {
                        "date": n.index,
                        "variant": sel["cell_id"],
                        "offset": k,
                        "net": n.to_numpy(),
                        "gross": g.to_numpy(),
                    }
                )
            )
    returns = pd.concat(rows, ignore_index=True)
    cost2x = returns.copy()
    cost2x["net"] = 2.0 * returns["net"] - returns["gross"]  # gross - 2 * (gross - net)
    rf, _ = load_rf_spy()
    phases = json.loads((REG / "phases.json").read_text())["phases_recent"]
    state = pd.read_parquet(REG / "market_state.parquet")["state"]
    pl = (
        json.loads((R.RES / "placebo.json").read_text())
        if (R.RES / "placebo.json").exists()
        else None
    )
    placebo = (
        {sel["cell_id"]: {"net": list(pl["net"].values()), "gross": list(pl["gross"].values())}}
        if pl
        else {}
    )
    checks = json.loads(CHECKS.read_text()) if CHECKS.exists() else {}
    share = (
        json.loads((R.RES / "whole_share.json").read_text())
        if (R.RES / "whole_share.json").exists()
        else {}
    )
    attest = {
        c: {
            "V1": bool(checks.get("all_pass")),
            "V2": bool(share.get("v2_pass")) if c == sel["cell_id"] else False,
        }
        for c in cells
    }
    sig_ls = {sel["cell_id"]: series("A", sel["cell_id"], "gross", "2024-01-08", END)}
    card = sc.score_family(
        returns,
        cost2x,
        rf,
        phases,
        state,
        signal_ls=sig_ls,
        placebo=placebo,
        attestations=attest,
        n_trials=24,
        end=END,
    )
    (R.RES / "scorecard.json").write_text(json.dumps(card, indent=1, default=str))
    v = card["variants"][sel["cell_id"]]
    print(
        json.dumps(
            {
                "family": card["family"],
                "selected": sel["cell_id"],
                "tier": v.get("tier"),
                "dsr": v.get("main", {}).get("dsr") or v.get("dsr"),
                "keys": list(v.keys()),
            },
            indent=1,
            default=str,
        )[:3000]
    )


if __name__ == "__main__":
    main()
