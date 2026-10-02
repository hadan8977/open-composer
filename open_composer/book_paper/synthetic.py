"""Synthetic F1 target for the integration dry-run (not a research signal).

Picks names from the last day of the equity-book panel (U3000, tradeable, liquid, price >= 10),
alternates long and short in beta order so the overlay is beta-neutral by construction, and adds
the T-bill leg.  The book id starts with ``synthetic`` and ``submit_plan`` refuses such plans.
Run with ``python -m open_composer.book_paper.synthetic --account quant1``.
"""

from __future__ import annotations

import argparse
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from open_composer.book_paper.targets import (
    BookTarget,
    NameExposure,
    default_execution_date,
    now_utc_text,
    write_target_file,
)

SYNTHETIC_BOOK_ID = "synthetic_dryrun_t20261001_16:F1"


def synthetic_f1_target(
    root: Path,
    account: str,
    *,
    n_names: int = 150,
    name_weight: float = 0.005,
    equity_basis: float = 1_000_000.0,
    seed: int = 20261001,
    tbill: str = "SGOV",
    adv_rank_max: int = 1000,
    min_price: float = 10.0,
    panel_year: int = 2026,
) -> BookTarget:
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    panel_dir = root / "data" / "research" / "equity_book"
    columns = [
        "trade_date",
        "symbol",
        "close",
        "dollar_adv_21",
        "adv_rank",
        "mcap",
        "in_u3000",
        "ff48",
        "beta_252_spy",
        "vol_21",
        "is_tradeable",
    ]
    table = pq.read_table(panel_dir / "panel" / f"{panel_year}.parquet", columns=columns)
    last = pc.max(table["trade_date"]).as_py()
    frame = table.filter(pc.equal(table["trade_date"], last)).to_pandas()
    pool = frame[
        frame["in_u3000"]
        & frame["is_tradeable"]
        & (frame["adv_rank"] <= adv_rank_max)
        & (frame["close"] >= min_price)
    ].dropna(subset=["beta_252_spy", "ff48", "mcap", "vol_21", "dollar_adv_21"])
    if len(pool) < n_names:
        raise ValueError("not enough eligible names in the last panel day")
    pick = pool.sample(n=n_names, random_state=seed).sort_values("beta_252_spy")
    sides = np.array([1.0 if i % 4 in (0, 3) else -1.0 for i in range(n_names)])
    weights = {s: float(side * name_weight) for s, side in zip(pick["symbol"], sides, strict=True)}
    prices = {s: float(p) for s, p in zip(pick["symbol"], pick["close"], strict=True)}
    exposures = {
        row.symbol: NameExposure(
            beta=float(row.beta_252_spy),
            industry=f"ff48_{int(row.ff48):02d}",
            size=math.log(float(row.mcap)),
            dollar_adv_21=float(row.dollar_adv_21),
            vol_21=float(row.vol_21),
        )
        for row in pick.itertuples()
    }

    etf = pq.read_table(panel_dir / "etf_daily.parquet", columns=["trade_date", "symbol", "close"])
    sel = etf.filter(pc.and_(pc.equal(etf["symbol"], tbill), pc.equal(etf["trade_date"], last)))
    if sel.num_rows != 1:
        raise ValueError(f"no {tbill} close on the panel's last day")
    weights[tbill] = 1.0
    prices[tbill] = float(sel["close"][0].as_py())
    exposures[tbill] = NameExposure(beta=0.0, industry="tbill", size=0.0)

    decision = last.date() if hasattr(last, "date") else last
    return BookTarget(
        book_id=SYNTHETIC_BOOK_ID,
        account=account,
        form="F1",
        decision_date=decision,
        execution_date=default_execution_date(decision),
        equity_basis=equity_basis,
        core_symbol=tbill,
        weights=weights,
        reference_prices=prices,
        exposures=exposures,
        logged_at_utc=now_utc_text(datetime.now(UTC)),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", default="quant1")
    parser.add_argument("--n-names", type=int, default=150)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    target = synthetic_f1_target(root, args.account, n_names=args.n_names)
    path = write_target_file(root, target)
    print(
        f"wrote {path.relative_to(root)} names={len(target.stock_weights)} "
        f"decision_date={target.decision_date.isoformat()}"
    )


if __name__ == "__main__":
    main()
