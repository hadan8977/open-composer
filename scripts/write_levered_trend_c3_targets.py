"""Publish the frozen lt-20261119-5-1 Quant1 sleeve target from SIP daily ALL bars."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime, time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from open_composer.adapters.data.sip_parquet import load_sip_bars  # noqa: E402
from open_composer.adapters.execution.rotation_overlay import realized_annual_vol  # noqa: E402
from open_composer.book_paper.plan import write_json_atomic  # noqa: E402
from open_composer.market_sessions import (  # noqa: E402
    NEW_YORK,
    next_us_equity_session,
    us_equity_session_dates,
)
from open_composer.paper_freshness import latest_completed_us_equity_session  # noqa: E402

TARGETS = ROOT / "reports/paper/book/quant1/sleeves/levered_trend_c3/targets"
HISTORY_START = date(2025, 1, 1)


def load_closes(day: date, sip_root: Path | None) -> pd.DataFrame:
    bars = load_sip_bars(
        ["QQQ", "TQQQ"],
        start=datetime.combine(HISTORY_START, time.min, NEW_YORK),
        end=datetime.combine(day, time.max, NEW_YORK),
        root=sip_root,
        allow_missing=False,
    )
    bars["session"] = bars["timestamp"].dt.tz_convert(NEW_YORK).dt.date
    return bars.pivot(index="session", columns="symbol", values="close")


def write_target(day: date, closes: pd.DataFrame, output: Path) -> Path:
    closes = closes.loc[:day]
    if (
        list(closes.index) != list(us_equity_session_dates(HISTORY_START, day))
        or len(closes) < 200
        or not closes.gt(0).all().all()
    ):
        raise ValueError(f"incomplete SIP ALL decision history for {day}")
    ratio = closes.QQQ / closes.QQQ.rolling(200).mean()
    gate = bool(ratio.where(ratio.gt(1.01) | ratio.lt(0.99)).ffill().gt(1.01).iloc[-1])
    vol = float(realized_annual_vol(closes.TQQQ.pct_change(), 21)[-1])
    risk = (min(1.0, 0.40 / vol) if vol else 1.0) if gate else 0.0

    prior = max((p for p in output.glob("20??-??-??.json") if p.stem < str(day)), default=None)
    hold = False
    if prior is not None:
        last_risk = json.loads(prior.read_text(encoding="utf-8"))["weights"]["TQQQ"]
        hold = gate == (last_risk > 0) and abs(risk - last_risk) <= 0.10
        if hold:
            risk = last_risk

    return write_json_atomic(
        output / f"{day}.json",
        {
            "decision_date": str(day),
            "execution_date": str(next_us_equity_session(day)),
            "weights": {"TQQQ": risk, "BIL": 1.0 - risk},
            "hold": hold,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sip-root", type=Path, help="Quant1 source root's data/sip directory")
    parser.add_argument("--decision-date", type=date.fromisoformat)
    parser.add_argument("--output-dir", type=Path, default=TARGETS)
    args = parser.parse_args()
    completed = latest_completed_us_equity_session(datetime.now(UTC))
    day = args.decision_date or completed
    if day > completed:
        raise ValueError(f"decision session {day} has not closed")
    if not (args.output_dir / f"{day}.json").exists():
        print(write_target(day, load_closes(day, args.sip_root), args.output_dir))


if __name__ == "__main__":
    main()
