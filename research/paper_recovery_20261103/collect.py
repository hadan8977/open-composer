"""Read-only dated evidence capture. No order or account mutation methods exist."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from open_composer.book_paper.accounts import load_account_credentials
from open_composer.config import alpaca_api_key_id, alpaca_api_secret_key

OUT = ROOT / "reports/owner/paper-recovery-20261103/evidence"


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n")


def get(session, alias, name, endpoint, params=None):
    stem = OUT / alias / name
    if stem.with_suffix(".json").exists():
        return json.loads(stem.with_suffix(".json").read_text())
    at = datetime.now(UTC).isoformat()
    response = session.get(endpoint, params=params, timeout=35)
    stem.parent.mkdir(parents=True, exist_ok=True)
    stem.with_suffix(".raw").write_bytes(response.content)
    save(stem.with_suffix(".receipt.json"), {
        "method": "GET", "endpoint": endpoint, "params": params,
        "started_at": at, "received_at": datetime.now(UTC).isoformat(),
        "status_code": response.status_code,
        "sha256": hashlib.sha256(response.content).hexdigest(),
    })
    response.raise_for_status()
    data = response.json()
    save(stem.with_suffix(".json"), data)
    print(alias, name, response.status_code, len(response.content), flush=True)
    return data


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for file in ["runtime/paper/six/runtime-state.json", "runtime/paper/six/runtime-state.events.jsonl"]:
        target = OUT / Path(file).name
        if not target.exists():
            target.write_bytes((ROOT / file).read_bytes())
    load_dotenv(ROOT / ".env", override=False)
    aliases = {
        "legacy": (alpaca_api_key_id(), alpaca_api_secret_key()),
    }
    for alias, account, path in [
        ("six", "quant2", Path("/root/.config/open-composer/paper-validation-20261019.env")),
        ("quant1", "quant1", None), ("quant2", "quant2", None),
    ]:
        try:
            c = load_account_credentials(account, path)
            aliases[alias] = (c.key_id, c.secret_key)
        except Exception as exc:
            save(OUT / alias / "capture-error.json", {"error_type": type(exc).__name__})
    market = None
    all_symbols = set()
    for alias, (key, secret) in aliases.items():
        session = requests.Session()
        session.headers.update({"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret})
        base = "https://paper-api.alpaca.markets/v2"
        try:
            account = get(session, alias, "account", base + "/account")
            positions = get(session, alias, "positions", base + "/positions")
            all_symbols.update(p["symbol"] for p in positions)
            get(session, alias, "history", base + "/account/portfolio/history", {
                "date_start": "2026-09-30", "date_end": "2026-11-03",
                "timeframe": "1D", "extended_hours": "false", "cashflow_types": "ALL",
            })
            acts, token = [], None
            for page in range(100):
                params = {"after": "2026-09-01T00:00:00Z", "until": "2026-11-03T00:00:00Z", "direction": "asc", "page_size": 100}
                if token:
                    params["page_token"] = token
                data = get(session, alias, f"activities-{page:03}", base + "/account/activities", params)
                acts.extend(data)
                all_symbols.update(x["symbol"] for x in data if x.get("symbol"))
                if len(data) < 100:
                    break
                new = data[-1]["id"]
                assert new != token
                token = new
            else:
                raise ValueError("pagination exceeds bound")
            assert len({a["id"] for a in acts}) == len(acts)
            save(OUT / alias / "activities-all.json", acts)
            save(OUT / alias / "capture-summary.json", {
                "account_hash": hashlib.sha256(account["id"].encode()).hexdigest(),
                "activity_count": len(acts), "complete": True,
                "after": "2026-09-01T00:00:00Z", "until": "2026-11-03T00:00:00Z",
            })
            if alias == "legacy":
                market = session
        except Exception as exc:
            save(OUT / alias / "capture-error.json", {"error_type": type(exc).__name__, "message": str(exc)[:250]})
    if market is not None:
        # Same existing SIP entitlement; finite daily history solely for owned positions.
        symbols = sorted(all_symbols)
        save(OUT / "market-symbols.json", symbols)
        for block in range(0, len(symbols), 100):
            token = None
            for page in range(40):
                params = {"symbols": ",".join(symbols[block:block+100]), "start": "2026-09-01T04:00:00Z", "end": "2026-11-03T04:59:59Z", "timeframe": "1Day", "adjustment": "raw", "feed": "sip", "limit": 10000}
                if token:
                    params["page_token"] = token
                data = get(market, "market", f"raw-{block//100:03}-{page:03}", "https://data.alpaca.markets/v2/stocks/bars", params)
                token = data.get("next_page_token")
                if not token:
                    break
            else:
                raise ValueError("market pagination exceeds bound")


if __name__ == "__main__":
    main()
