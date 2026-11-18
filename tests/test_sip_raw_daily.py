from datetime import UTC, datetime

import pytest

from open_composer.adapters.data import sip_parquet
from scripts import update_sip_raw_daily as daily


def test_daily_publishes_only_closed_sessions_and_resumes(tmp_path, monkeypatch):
    monkeypatch.setattr(sip_parquet, "MARKET_DATA", tmp_path)
    seed = tmp_path / "sip-raw-recent" / "request-plan.json"
    seed.parent.mkdir()
    seed.write_text('{"symbols":["AAPL"]}', encoding="utf-8")
    archive = tmp_path / sip_parquet.RAW_UPDATE_VERSION

    class Reply:
        headers = {}

        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self.payload

    class Alpaca:
        calls = []
        fail = True

        def get(self, url, *, params, timeout):
            self.calls.append((url, dict(params)))
            if url == daily.ASSETS_URL:
                return Reply([{"symbol": "NEW"}])
            if params["timeframe"] == "1Min" and self.fail:
                raise OSError("connection lost")
            daily_bar = params["timeframe"] == "1Day"
            symbol = "NEW" if "page_token" in params else "AAPL"
            day = "2026-11-18"
            stamp = f"{day}T{('05:00' if daily_bar else '20:59')}:00Z"
            bar = {"t": stamp, "o": 1, "h": 2, "l": 1, "c": 2, "v": 3, "n": 1, "vw": 1.5}
            return Reply(
                {
                    "bars": {symbol: [bar]},
                    "next_page_token": "next" if symbol == "AAPL" else None,
                }
            )

    api = Alpaca()
    assert daily.update(api, tmp_path, datetime(2026, 11, 18, 21, 0, tzinfo=UTC)) == []
    assert api.calls == []

    ready = datetime(2026, 11, 18, 21, 20, tzinfo=UTC)
    with pytest.raises(OSError, match="connection lost"):
        daily.update(api, tmp_path, ready)
    assert not (archive / "2026-11-18").exists()

    api.calls.clear()
    api.fail = False
    (manifest,) = daily.update(api, tmp_path, ready)
    assert manifest["rows"] == {"daily": 2, "minute": 2}
    queries = [params for url, params in api.calls if url == daily.BARS_URL]
    assert [query["timeframe"] for query in queries] == ["1Min", "1Min"]
    assert all(query["symbols"] == "AAPL,NEW" and query["adjustment"] == "raw" for query in queries)
    frame = sip_parquet.load_sip_bars(["AAPL", "NEW"], frequency="minute", adjustment="raw")
    assert frame["symbol"].tolist() == ["AAPL", "NEW"]
    assert frame["source_version"].unique().tolist() == ["sip-raw-daily"]
    assert daily.update(api, tmp_path, ready) == []
