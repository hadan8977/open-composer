"""Options mleg probe: fake broker client only, no network."""

from __future__ import annotations

import importlib.util
import json
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    "options_mleg_probe", Path(__file__).resolve().parents[1] / "scripts" / "options_mleg_probe.py"
)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)

TODAY = date(2026, 10, 7)
EXPIRY = (TODAY + timedelta(days=14)).isoformat()


class RejectError(Exception):
    status_code = 422


class FakeTrading:
    def __init__(self, mode="accept", cancel_polls=0, explode_once_on=None):
        self.mode, self.cancel_polls, self.explode_once_on = mode, cancel_polls, explode_once_on
        self.orders: dict[str, SimpleNamespace] = {}
        self.submitted: list[object] = []
        self.cancel_calls: list[str] = []
        self._pending: dict[str, int] = {}

    def get_account(self):
        return SimpleNamespace(
            options_trading_level=3,
            options_approved_level=3,
            options_buying_power="69721.55",
            status="active",
            trading_blocked=False,
            account_blocked=False,
            multiplier="4",
            buying_power="314904.36",
            id="secret-id",
        )

    def get_option_contracts(self, request):
        items = []
        for strike in range(650, 900, 5):
            for kind in ("put", "call"):
                items.append(
                    SimpleNamespace(
                        symbol=f"SPY{EXPIRY}{kind[0].upper()}{strike}",
                        expiration_date=EXPIRY,
                        strike_price=str(strike),
                        type=kind,
                        tradable=True,
                    )
                )
        return SimpleNamespace(option_contracts=items, next_page_token=None)

    def submit_order(self, request):
        self.submitted.append(request)
        if self.mode == "reject":
            raise RejectError("insufficient options level for mleg order")
        order = SimpleNamespace(
            id=f"id-{len(self.orders) + 1}",
            client_order_id=request.client_order_id,
            status="accepted",
            order_class="mleg",
            limit_price=request.limit_price,
            qty="1",
            legs=[
                SimpleNamespace(symbol=x.symbol, side=x.side, status="accepted")
                for x in request.legs
            ],
        )
        self.orders[request.client_order_id] = order
        return order

    def get_order_by_client_id(self, cid):
        if self.explode_once_on == cid:
            self.explode_once_on = None
            raise RuntimeError("network blip")
        order = self.orders[cid]
        if order.status == "pending_cancel":
            self._pending[cid] = self._pending.get(cid, 0) + 1
            if self._pending[cid] > self.cancel_polls:
                order.status = "canceled"
        return order

    def cancel_order_by_id(self, order_id):
        self.cancel_calls.append(order_id)
        for order in self.orders.values():
            if order.id == order_id:
                order.status = "pending_cancel" if self.cancel_polls else "canceled"


class FakeOptionData:
    def __init__(self, quoted=True):
        self.quoted = quoted

    def get_option_latest_quote(self, request):
        symbols = request.symbol_or_symbols
        if not self.quoted:
            return {}
        # puts closer to the money are dearer; calls cheap
        out = {}
        for symbol in symbols:
            strike = float(symbol.split("P")[-1] if "P" in symbol else symbol.split("C")[-1])
            mid = 1.0 + (strike - 700) / 100 if "P" in symbol else 0.1
            out[symbol] = SimpleNamespace(bid_price=mid - 0.01, ask_price=mid + 0.01)
        return out


def run(tmp_path, trading=None, data=None, submit=True, kill=None):
    trading = trading or FakeTrading()
    summary = probe.run_submit_test(
        trading,
        data or FakeOptionData(),
        lambda s: 770.0,
        tmp_path,
        submit=submit,
        kill_check=lambda: kill,
        today=TODAY,
        sleep=lambda _s: None,
    )
    return trading, summary


def test_account_options_prints_fields_not_the_id():
    fields = probe.account_options(FakeTrading())
    assert fields["options_trading_level"] == "3"
    assert fields["options_buying_power"] == "69721.55"  # decimals survive
    assert "id" not in fields and "secret-id" not in json.dumps(fields)


def test_leg_selection_is_five_dollars_wide_and_about_five_percent_otm():
    contracts = probe.list_contracts(FakeTrading(), "SPY", TODAY)
    legs = probe.select_legs(contracts, EXPIRY, 770.0)
    assert legs["short_put"][0] - legs["long_put"][0] == 5
    assert legs["long_call"][0] - legs["short_call"][0] == 5
    assert abs(legs["short_put"][0] / 770.0 - 0.95) < 0.01
    assert abs(legs["short_call"][0] / 770.0 - 1.05) < 0.01
    assert probe.pick_expiry(contracts, TODAY) == EXPIRY


def test_credit_limit_is_unfillable_and_falls_back_without_quotes():
    legs = {
        "short_put": (730, "P1"),
        "long_put": (725, "P2"),
        "short_call": (810, "C1"),
        "long_call": (815, "C2"),
    }
    mids = {"P1": 0.60, "P2": 0.50, "C1": 0.10, "C2": 0.05}
    credit, _ = probe.credit_limit("2leg", legs, mids)
    assert credit == pytest.approx(0.30)  # 3 x 0.10 mid credit
    credit, _ = probe.credit_limit("4leg", legs, mids)
    assert credit == pytest.approx(0.45)  # 3 x (0.10 + 0.05)
    rich = {"P1": 4.0, "P2": 0.5, "C1": 0.1, "C2": 0.05}
    assert probe.credit_limit("2leg", legs, rich)[0] == 4.5  # capped at 90% of the width
    credit, note = probe.credit_limit("2leg", legs, {"P1": None, "P2": None})
    assert credit == 4.0 and "no usable quote" in note


def test_default_is_read_only_plan(tmp_path):
    trading, summary = run(tmp_path, submit=False)
    assert trading.submitted == [] and summary["submitted"] is False
    rows = [
        json.loads(x)
        for x in (tmp_path / "reports/paper/options-probe/2026-10-07/probe.jsonl")
        .read_text()
        .splitlines()
    ]
    plans = [r for r in rows if r["step"] == "plan_only"]
    assert len(plans) == 2 and plans[0]["payload"]["order_class"] == "mleg"
    assert len(plans[1]["payload"]["legs"]) == 4


def test_kill_switch_blocks_submission(tmp_path):
    with pytest.raises(probe.ProbeError, match="refusing to submit"):
        run(tmp_path, kill="paper kill switch enabled: test")
    trading = FakeTrading()
    with pytest.raises(probe.ProbeError):
        run(tmp_path, trading=trading, kill="paper kill switch enabled: test")
    assert trading.submitted == []


def test_accepted_orders_are_cancelled_and_confirmed(tmp_path):
    trading, summary = run(tmp_path, trading=FakeTrading(cancel_polls=2))
    assert [r["structure"] for r in summary["results"]] == ["2leg", "4leg"]
    assert len(trading.submitted) == 2 and len(trading.cancel_calls) == 2
    two, four = trading.submitted
    assert len(two.legs) == 2 and len(four.legs) == 4
    assert two.client_order_id == "probe-mleg-20261007-2leg"
    assert four.client_order_id == "probe-mleg-20261007-4leg"
    assert str(two.order_class).lower().endswith("mleg") and str(
        two.time_in_force
    ).lower().endswith("day")
    assert two.qty == 1 and all(leg.ratio_qty == 1 for leg in four.legs)
    assert two.limit_price < 0 and abs(two.limit_price) >= 3 * 0.12  # credit far above the mid
    for result in summary["results"]:
        assert result["accepted"] and result["cancel_confirmed"]
        assert result["status_after_cancel"] == "canceled"
    assert all(o.status == "canceled" for o in trading.orders.values())
    text = (tmp_path / "reports/paper/options-probe/2026-10-07/summary.md").read_text()
    assert "cancel confirmed: True" in text and "secret-id" not in text


def test_rejection_reason_is_recorded_and_nothing_to_cancel(tmp_path):
    trading, summary = run(tmp_path, trading=FakeTrading(mode="reject"))
    assert trading.cancel_calls == []
    for result in summary["results"]:
        assert result["accepted"] is False
        assert result["rejection"]["status_code"] == 422
        assert "insufficient options level" in result["rejection"]["message"]
    assert (
        "rejection:" in (tmp_path / "reports/paper/options-probe/2026-10-07/summary.md").read_text()
    )


def test_any_failure_cancels_everything_this_script_placed(tmp_path):
    trading = FakeTrading(explode_once_on="probe-mleg-20261007-4leg")
    with pytest.raises(RuntimeError, match="network blip"):
        run(tmp_path, trading=trading)
    assert set(trading.orders) == {"probe-mleg-20261007-2leg", "probe-mleg-20261007-4leg"}
    assert all(o.status == "canceled" for o in trading.orders.values())
    rows = (tmp_path / "reports/paper/options-probe/2026-10-07/probe.jsonl").read_text()
    assert '"step": "aborted"' in rows


def test_cli_submit_test_without_the_flag_places_no_order(monkeypatch, tmp_path, capsys):
    trading = FakeTrading()
    monkeypatch.setattr(
        probe, "_real_clients", lambda: (trading, FakeOptionData(), lambda s: 770.0)
    )
    monkeypatch.setattr(probe, "ROOT", tmp_path)
    monkeypatch.setattr(probe, "date", date)
    assert probe.main(["submit-test"]) == 0
    assert trading.submitted == [] and trading.cancel_calls == []
    assert '"submitted": false' in capsys.readouterr().out
