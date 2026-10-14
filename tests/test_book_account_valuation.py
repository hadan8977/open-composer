import json
from datetime import UTC, date, datetime
from types import SimpleNamespace

from open_composer.book_paper.account_valuation import capture_account_valuation


def test_missing_plan_account_mark_never_manufactures_strategy_ledger_or_ids(tmp_path):
    calls = []

    class Client:
        def get_account(self):
            calls.append("get_account")
            return SimpleNamespace(id="PRIVATE_ACCOUNT_ID", equity="1000.01", cash="100")

        def get_clock(self):
            calls.append("get_clock")
            return SimpleNamespace(timestamp=datetime(2026, 10, 14, 1, tzinfo=UTC))

    path = capture_account_valuation(tmp_path, "quant1", date(2026, 10, 13), client=Client())
    result = json.loads(path.read_text())
    assert calls == ["get_account", "get_clock"]
    assert "PRIVATE_ACCOUNT_ID" not in path.read_text()
    assert result["requested_ledger_date"] == "2026-10-13"
    assert result["strategy_attribution"] is None
    assert not result["historical_fills_reconstructed"]
    assert not (tmp_path / "reports/paper/book/quant1/daily/2026-10-13.json").exists()
