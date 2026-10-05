from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import book_paper_cls_probe as probe  # noqa: E402

IN_WINDOW = datetime(2026, 10, 5, 18, 50, tzinfo=UTC)  # 14:50 New York
LATE = datetime(2026, 10, 5, 19, 55, tzinfo=UTC)  # 15:55 New York


def _args(mode: str, **kw) -> argparse.Namespace:
    base = dict(
        account="quant1",
        symbol="SPY",
        side="buy",
        qty=1,
        day=None,
        execute=False,
        require_position=None,
    )
    base.update(kw)
    return argparse.Namespace(mode=mode, **base)


class FakeClient:
    def __init__(self, fail: Exception | None = None) -> None:
        self.fail = fail
        self.sent: list = []

    def get_account(self):
        return SimpleNamespace(status="ACTIVE", shorting_enabled=True, multiplier="2")

    def get_asset(self, symbol):
        return SimpleNamespace(tradable=True, shortable=True, easy_to_borrow=True)

    def submit_order(self, request):
        if self.fail:
            raise self.fail
        self.sent.append(request)
        return SimpleNamespace(id="abc", status="accepted", client_order_id=request.client_order_id)

    def get_order_by_client_id(self, cid):
        return SimpleNamespace(id="abc", status="filled", filled_qty="1", filled_avg_price="650.1")


def _lines(tmp: Path, account: str = "quant1") -> list[dict]:
    path = probe.log_path(tmp, account, "2026-10-05")
    return [json.loads(x) for x in path.read_text().splitlines()]


def test_dry_submit_sends_nothing(tmp_path: Path) -> None:
    client = FakeClient()
    rc = probe.run(_args("submit"), client_factory=lambda a: client, now=IN_WINDOW, root=tmp_path)
    assert rc == 0 and client.sent == []
    assert _lines(tmp_path)[0]["result"].startswith("dry")


def test_late_submit_refused(tmp_path: Path) -> None:
    client = FakeClient()
    args = _args("submit", execute=True)
    rc = probe.run(args, client_factory=lambda a: client, now=LATE, root=tmp_path)
    assert rc == 2 and client.sent == []


def test_submit_records_order(tmp_path: Path, monkeypatch) -> None:
    import open_composer.adapters.broker.alpaca_paper as ap

    monkeypatch.setattr(ap, "_require_verified_paper_client", lambda c: None)
    client = FakeClient()
    args = _args("submit", execute=True)
    rc = probe.run(args, client_factory=lambda a: client, now=IN_WINDOW, root=tmp_path)
    assert rc == 0
    sent = client.sent[0]
    assert str(getattr(sent.time_in_force, "value", sent.time_in_force)) == "cls"
    assert sent.client_order_id == "probe-cls-quant1-2026-10-05-buy-spy"
    assert _lines(tmp_path)[0]["order"]["status"] == "accepted"


def test_submit_error_is_recorded(tmp_path: Path, monkeypatch) -> None:
    import open_composer.adapters.broker.alpaca_paper as ap

    monkeypatch.setattr(ap, "_require_verified_paper_client", lambda c: None)
    client = FakeClient(fail=RuntimeError('{"code":42210000,"message":"cls not allowed"}'))
    args = _args("submit", execute=True)
    rc = probe.run(args, client_factory=lambda a: client, now=IN_WINDOW, root=tmp_path)
    assert rc == 3
    rec = _lines(tmp_path)[0]
    assert rec["result"] == "submit_error" and "cls not allowed" in rec["error"]


def test_status_and_account(tmp_path: Path) -> None:
    client = FakeClient()
    probe.run(_args("status"), client_factory=lambda a: client, now=IN_WINDOW, root=tmp_path)
    probe.run(_args("account"), client_factory=lambda a: client, now=IN_WINDOW, root=tmp_path)
    recs = _lines(tmp_path)
    assert recs[0]["order"]["status"] == "filled"
    assert recs[1]["account_fields"]["shorting_enabled"] is True


def test_close_requires_the_probe_position(tmp_path: Path, monkeypatch) -> None:
    import open_composer.adapters.broker.alpaca_paper as ap

    monkeypatch.setattr(ap, "_require_verified_paper_client", lambda c: None)
    client = FakeClient()
    client.get_open_position = lambda symbol: (_ for _ in ()).throw(RuntimeError("no position"))
    args = _args("submit", execute=True, side="sell", require_position=1.0)
    rc = probe.run(args, client_factory=lambda a: client, now=IN_WINDOW, root=tmp_path)
    assert rc == 4 and client.sent == []
    client.get_open_position = lambda symbol: SimpleNamespace(qty="1")
    rc = probe.run(args, client_factory=lambda a: client, now=IN_WINDOW, root=tmp_path)
    assert rc == 0 and len(client.sent) == 1
