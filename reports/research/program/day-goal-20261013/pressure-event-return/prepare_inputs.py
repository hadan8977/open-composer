"""Bounded real input preparation; no return evaluation or strategy selection."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[5]
TASK = Path(__file__).resolve().parent
OUT = TASK / "inputs"
SYMBOLS = ["NIXT", "IWN", "IWM", "VBR", "IWV", "SPY", "QQQ", "RSP", "BIL"]
DATES = ["2024-09-10", "2025-04-03", "2025-09-10", "2026-09-10"]


def binding(path: Path) -> dict:
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def save(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    review = json.loads((TASK / "independent-plan-review.json").read_text())
    assert review["verdict"] == "approve_deep_plan"
    for name in ["scientific-plan.json", "execution-contract-proposed.json"]:
        assert binding(TASK / name)["sha256"] in {
            row["sha256"] for row in review["bindings"].values()
        }
    load_dotenv(ROOT / ".env", override=False)
    key = os.getenv("ALPACA_API_KEY_ID")
    secret = os.getenv("ALPACA_API_SECRET_KEY")
    assert key and secret, "Existing read-only market credentials unavailable"
    session = requests.Session()
    session.headers.update({"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret})
    ledger_path = OUT / "market-request-ledger.json"
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else []

    def fetch(name: str, url: str, params: dict) -> dict | None:
        old = next((row for row in ledger if row["name"] == name), None)
        path = OUT / (name + ".json")
        if old is not None:
            return json.loads(path.read_text()) if old.get("ok") else None
        assert len(ledger) < 12
        assert sum(row.get("bytes", 0) for row in ledger) < 10 * 1024**2
        row = {
            "name": name,
            "url": url,
            "params": params,
            "requested_at": datetime.now(UTC).isoformat(),
            "attempts": 1,
            "ok": False,
        }
        ledger.append(row)
        save(ledger_path, ledger)  # Failed requests also consume admission.
        try:
            with session.get(url, params=params, timeout=30, stream=True) as response:
                body = bytearray()
                for chunk in response.iter_content(65536):
                    body.extend(chunk)
                    if sum(r.get("bytes", 0) for r in ledger) + len(body) > 10 * 1024**2:
                        raise ValueError("Cumulative market response admission exceeded")
                row.update(status=response.status_code, bytes=len(body))
                if response.status_code == 200:
                    path.write_bytes(body)
                    row.update(ok=True, binding=binding(path))
                else:
                    row["error"] = f"HTTP {response.status_code}; no retry"
        except (requests.RequestException, ValueError) as exc:
            row["error"] = type(exc).__name__  # Never dump request headers/secrets.
        save(ledger_path, ledger)
        print(name, row.get("status"), row.get("bytes"), row["ok"], flush=True)
        return json.loads(path.read_text()) if row["ok"] else None

    rows = []
    for adjustment in ["raw", "all"]:
        result = fetch(
            f"bars_{adjustment}",
            "https://data.alpaca.markets/v2/stocks/bars",
            {
                "symbols": ",".join(SYMBOLS),
                "timeframe": "1Day",
                "start": "2024-09-01T00:00:00Z",
                "end": "2026-10-13T00:00:00Z",
                "adjustment": adjustment,
                "feed": "sip",
                "limit": 10000,
                "asof": "2026-10-12",
                "sort": "asc",
            },
        )
        if result is None:
            continue
        assert not result.get("next_page_token"), "Unexpected pagination; fixed admission"
        for symbol, bars in result["bars"].items():
            for bar in bars:
                rows.append({"symbol": symbol, "adjustment": adjustment, **bar})
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame["timestamp"] = pd.to_datetime(frame["t"], utc=True)
        frame["session"] = frame["timestamp"].dt.tz_convert("America/New_York").dt.date.astype(str)
        assert frame["session"].max() <= "2026-10-12"
        assert not frame.duplicated(["symbol", "adjustment", "session"]).any()
        assert frame[["o", "h", "l", "c"]].gt(0).all().all()
        frame.to_parquet(OUT / "daily-bars.parquet", index=False)
    for date in DATES:
        arrival = datetime.fromisoformat(date + "T09:45:00").replace(
            tzinfo=ZoneInfo("America/New_York")
        )
        quote_start = arrival.replace(second=50, minute=44)
        result = fetch(
            "quotes_" + date,
            "https://data.alpaca.markets/v2/stocks/NIXT/quotes",
            {
                "start": quote_start.astimezone(UTC).isoformat(),
                "end": arrival.replace(second=1).astimezone(UTC).isoformat(),
                "feed": "sip",
                "limit": 10000,
                "sort": "asc",
            },
        )
        if result is not None:
            assert not result.get("next_page_token"), "Quote window truncated"
        fetch(
            "trades_" + date,
            "https://data.alpaca.markets/v2/stocks/NIXT/trades",
            {
                "start": arrival.astimezone(UTC).isoformat(),
                "end": arrival.replace(minute=46).astimezone(UTC).isoformat(),
                "feed": "sip",
                "limit": 10000,
                "sort": "asc",
            },
        )
    fetch("asset_NIXT", "https://paper-api.alpaca.markets/v2/assets/NIXT", {})
    # Twelfth read is not used merely because capacity exists.
    summary = {
        "created_at": datetime.now(UTC).isoformat(),
        "requests": len(ledger),
        "bytes": sum(row.get("bytes", 0) for row in ledger),
        "failures": sum(not row["ok"] for row in ledger),
        "market_source": "actual Alpaca SIP HTTP responses, no fixtures or cache fallback",
        "economic_computation": False,
        "rows_by_symbol_adjustment": frame.groupby(["symbol", "adjustment"]).size().to_dict()
        if not frame.empty
        else {},
        "first_session": str(frame["session"].min()) if not frame.empty else None,
        "last_session": str(frame["session"].max()) if not frame.empty else None,
        "bindings": [binding(p) for p in sorted(OUT.glob("*.json"))],
    }
    summary["rows_by_symbol_adjustment"] = {
        ":".join(k): v for k, v in summary["rows_by_symbol_adjustment"].items()
    }
    if not frame.empty:
        summary["bindings"].append(binding(OUT / "daily-bars.parquet"))
    save(OUT / "input-acceptance.json", summary)
    state_path = TASK / "current-state.json"
    state = json.loads(state_path.read_text())
    state.update(
        status="real_inputs_prepared_implementation_pending",
        independent_plan_review=str((TASK / "independent-plan-review.json").relative_to(ROOT)),
        input_acceptance=str((OUT / "input-acceptance.json").relative_to(ROOT)),
        next_action=(
            "Implement bound complete application; independent implementation acceptance "
            "then native gates before evaluation"
        ),
    )
    state["cumulative"].update(
        market_api_requests=len(ledger), market_response_bytes=summary["bytes"]
    )
    save(state_path, state)
    print(
        json.dumps(
            {
                k: summary[k]
                for k in ["requests", "bytes", "failures", "first_session", "last_session"]
            }
        )
    )


if __name__ == "__main__":
    main()
