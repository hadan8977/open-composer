"""Reference application of scorecard v2 to the six v1 variants (T-20261001-20).

Reads the T-08 close paths and writes
``reports/research/program/evaluation-standard-2026-10-01/v1-reference-scorecard.json``.  Reference
only: it changes no verdict of the frozen v1 contract (the standard, section 8).  No placebo exists
for v1, so placebo checks are reported as missing; V1 and V2 are not attested; M1 variants have no
signal-level series (the M0 composite is the equal-weight theme signal, not the M1 IC-weighted one),
so their signal t is missing.

    scripts/run_capped.sh --mem 1.5G -- uv run python scripts/score_v1_reference.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from open_composer.research import scorecard_v2 as sc  # noqa: E402

STAGE = ROOT / "reports/research/iterations/t20261001_book_v1/cache/stage2a"
REG = ROOT / "data/research/equity_book/regimes"
ETF = ROOT / "data/research/equity_book/etf_daily.parquet"
OUT = ROOT / "reports/research/program/evaluation-standard-2026-10-01/v1-reference-scorecard.json"
VARIANTS = ("M0_A", "M0_B", "M0_C", "M1_A", "M1_B", "M1_C")


def load_paths() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, crows = [], []
    for variant in VARIANTS:
        for k in range(5):
            hits = list(STAGE.glob(f"shard_*/{variant}_o{k}_close"))
            assert len(hits) == 1, (variant, k, hits)
            d = pd.read_parquet(hits[0] / "daily.parquet", columns=["trade_date", "net", "gross"])
            r = pd.read_parquet(hits[0] / "replays.parquet", columns=["trade_date", "net_cost2x"])
            rows.append(d.rename(columns={"trade_date": "date"}).assign(variant=variant, offset=k))
            crows.append(
                r.rename(columns={"trade_date": "date", "net_cost2x": "net"}).assign(
                    variant=variant, offset=k, gross=float("nan")
                )
            )
    return pd.concat(rows, ignore_index=True), pd.concat(crows, ignore_index=True)


def main() -> int:
    returns, cost2x = load_paths()
    etf = pd.read_parquet(ETF, columns=["trade_date", "symbol", "close"])
    close = etf.pivot(index="trade_date", columns="symbol", values="close").sort_index()
    bil = (close["BIL"] / close["BIL"].shift(1) - 1.0).fillna(0.0)  # as evaluate.load_rf_spy
    phases = json.loads((REG / "phases.json").read_text())["phases_recent"]
    state = pd.read_parquet(REG / "market_state.parquet")["state"]
    ls = pd.read_parquet(REG / "signal_ls_daily.parquet")["m0_composite"]
    signal = {v: ls for v in VARIANTS if v.startswith("M0")}
    out = sc.score_family(returns, cost2x, bil, phases, state, signal_ls=signal)
    out["label"] = (
        "REFERENCE ONLY (T-20261001-20): v2 recompute of the frozen v1 variants; changes no verdict"
    )
    out["inputs"] = {
        "paths": str(STAGE.relative_to(ROOT)),
        "variants": list(VARIANTS),
        "signal": "M0 composite long-short (signal_ls_daily.parquet) for M0_*; none for M1_*",
        "placebo": "missing (none was run for v1)",
        "attestations": "V1 and V2 not attested",
    }
    out["generated_at_utc"] = subprocess.check_output(
        ["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"], text=True
    ).strip()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, default=str) + "\n")
    f = out["family"]
    print(
        f"window {f['recent_window']} sessions {f['recent_sessions']}",
        f"corr {f['mean_pairwise_corr']:.3f} N_eff {f['n_eff']:.3f}",
        f"var_SR {f['var_sr_annual']:.4f} Emax {f['expected_max_null_sr_annual']:.3f}",
    )
    for v, c in out["variants"].items():
        d = c["dsr"]
        print(
            f"{v} SR {d['sr_annual']:.3f} PSR {d['psr0']:.3f} DSR {d['dsr']:.3f}",
            f"tier {c['tier']} robustness {c['robustness_score']}",
            f"vetoes {c['vetoes_triggered']} unassessed {c['vetoes_unassessed']}",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
