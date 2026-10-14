"""One affected current-code check: native holding and actual entry error paths."""

# ruff: noqa: E402
import ast
import io
import json
import sys
import tokenize
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

P = Path(__file__).resolve().parents[2]
F = Path(__file__).resolve().parent
sys.path.insert(0, str(P / "code"))
sys.path.insert(0, str(F))
from consumer_admission import ROOT, bind, save
from continuation_admission import claim, rearm


def lint_literals(path):
    s = path.read_text()
    lines = s.splitlines(keepends=True)
    edits = []
    for t in tokenize.generate_tokens(io.StringIO(s).readline):
        if t.type != tokenize.STRING or t.start[0] != t.end[0] or len(t.string) < 85:
            continue
        try:
            v = ast.literal_eval(t.string)
        except (ValueError, SyntaxError):
            continue
        if not isinstance(v, str) or "\n" in v:
            continue
        chunks = []
        while len(v) > 70:
            cut = v.rfind(" ", 0, 65)
            if cut <= 0:
                break
            chunks.append(v[: cut + 1])
            v = v[cut + 1 :]
        chunks.append(v)
        if len(chunks) == 1:
            continue
        ind = " " * (len(lines[t.start[0] - 1]) - len(lines[t.start[0] - 1].lstrip()))
        value = "(\n" + "".join(ind + "    " + repr(c) + "\n" for c in chunks) + ind + ")"
        edits.append((t.start, t.end, value))
    for start, end, value in reversed(edits):
        i = start[0] - 1
        lines[i] = lines[i][: start[1]] + value + lines[i][end[1] :]
    path.write_text("".join(lines))


def main(job):
    claim(job, "offline_input")
    import subprocess

    files = [P / "code/continuation_admission.py", *F.glob("*.py")]
    for f in files:
        lint_literals(f)
    r = subprocess.run(
        [str(ROOT / ".venv/bin/ruff"), "format", *map(str, files)], capture_output=True, text=True
    )
    assert r.returncode == 0, r.stdout + r.stderr
    r = subprocess.run(
        [str(ROOT / ".venv/bin/ruff"), "check", "--fix", *map(str, files)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    for f in files:
        ast.parse(f.read_text())
    r = subprocess.run(
        [str(ROOT / ".venv/bin/oc"), "spec", "validate", str(F / "StrategySpec.yaml")],
        capture_output=True,
        text=True,
    )
    (F / "v3-spec-validation.log").write_text(r.stdout + r.stderr)
    assert r.returncode == 0, r.stdout + r.stderr
    rearm(job)
    from decimal import Decimal

    from decision_system import read_parameters
    from gap_events import gap_minute, holding_phase
    from gap_native_engine import make_engine
    from gap_source import Observation, integer_ns, qualify_gap
    from nautilus_trader.model.identifiers import ClientId
    from verify_feed_reuse import source
    from verify_shared_feed import snapshot

    checks = []
    engines = 0
    result_folder = F / (job + "-verification")
    result_folder.mkdir(exist_ok=False)

    # Test source quote safety rejection with current strengthened identity/R0
    # conditions and actual stopout classification, before any real data run.
    def q(at, price="9.8"):
        return Observation(
            "quotes",
            at,
            0,
            str(at),
            ("R",),
            "A",
            "synthetic",
            str((at, price)),
            bid=Decimal(price),
            ask=Decimal(price),
            bid_size_raw_units=Decimal(100),
            ask_size_raw_units=Decimal(100),
        )

    qa = dict(source_query_and_page_QA=True, source_provenance="fully_synthetic_inert")
    for label, candidate, prior_close, ema9, ordinal, depthprice in [
        ("holding_noFrame_partial", "P_EMA", 9.0, 9.5, 1, "9.8"),
        ("time_failure_noFrame", "P_SYSTEM", 9.98, 9.5, 3, "9.8"),
        ("protect_reject_current", "P_SYSTEM", 10.1, 9.5, 1, "9.6"),
        ("ask_spread_guard", "P_SYSTEM", 10.1, 9.5, 1, "9.8"),
    ]:
        packets = (
            source()[:1]
            if label in {"protect_reject_current", "ask_spread_guard"}
            else source()[:2]
        )
        e, s = make_engine(
            read_parameters(F / "StrategySpec.yaml"),
            candidate,
            "market",
            20,
            dict(spec="synthetic", input="synthetic", contract="synthetic", cell=label),
        )
        engines += 1
        try:
            from native_events5 import native_month

            for packet in packets:
                b, t, c, _ = native_month([packet], "O-H-L-C", {}, None)
                e.add_data(b)
                e.add_data(t)
                e.add_data(c, client_id=ClientId("MARTIN"))
                e.run(streaming=True)
                e.clear_data()
            if label == "protect_reject_current":
                # Existing held stop triggers first; current terminal safeguard
                # then reconciles any rejected resized protection by native exit.
                pass
            third = deepcopy(source()[1] if label == "protect_reject_current" else packets[-1])
            third["start"] = (
                __import__("datetime").datetime.fromisoformat(third["start"])
                + timedelta(days=ordinal)
            ).isoformat()
            if label in {"protect_reject_current", "ask_spread_guard"}:
                third["start"] = source()[1]["start"]
                ordinal = 0
            third["session"] = third["start"][:10]
            third["ordinal"] = ordinal
            third["minute"] = 0
            third["frames"] = []
            third["prices"] = [r for r in third["prices"] if r["symbol"] != "SOFI"]
            third["missing"] = ["SOFI"]
            at = integer_ns(third["start"])
            observations = (
                q(at - 10**9, depthprice),
                q(at + 10 * 10**9, depthprice),
                q(at + 40 * 10**9, depthprice),
            )
            if label == "ask_spread_guard":
                from dataclasses import replace

                observations = tuple(replace(ob, ask=Decimal("10.03")) for ob in observations)
                # Midpoint 9.915 passes reference10 * 1.002; ask10.03 fails.
            window = qualify_gap(
                "SOFI",
                at,
                at + 60 * 10**9,
                observations,
                qa,
            )
            b, t, c, _ = gap_minute(third, "O-H-L-C", {}, None, {"SOFI": window})
            rows = [
                dict(
                    symbol=symbol,
                    day=third["session"],
                    status="observed_causal_previous_vendor_daily",
                    available_at=(
                        __import__("datetime").datetime.fromisoformat(third["start"])
                        - timedelta(hours=15)
                    ).isoformat(),
                    prior_daily_close=prior_close,
                    prior_daily_ema9=ema9,
                )
                for symbol in ("COIN", "GME", "LMND", "SMCI", "SOFI", "SOUN")
            ]
            if label not in {"protect_reject_current", "ask_spread_guard"}:
                c.append(holding_phase(third, {third["session"]: rows}))
            if b:
                e.add_data(b)
            if t:
                e.add_data(t)
            e.add_data(c, client_id=ClientId("MARTIN"))
            e.run(streaming=True)
            e.clear_data()
            e.end()
            report = snapshot(s)
            save(result_folder / (label + "-current-native.json"), report)
            assert not s.book.path_unknown, label
            assert s.policy.states["SOFI"].quantity == 0, label
            if label == "holding_noFrame_partial":
                assert any(a["action"] == "full_holding_exit_remaining_native" for a in s.audit)
            if label == "protect_reject_current":
                assert any(
                    a["action"] == "terminal_protective_rejection_safety_exit" for a in s.audit
                )
                assert s.policy.states["SOFI"].status == "stopped"
                assert s.policy.states["SOFI"].last_stopout_at is not None
            if label == "time_failure_noFrame":
                assert any(
                    a["action"] == "causal_official_daily_holding_exit"
                    and s.native_intents[a["intent_id"]].reason == "no_followthrough"
                    for a in s.audit
                ), s.audit
            if label == "ask_spread_guard":
                assert any(a["action"] == "guarded_open_nonfill" for a in s.audit), s.audit
                assert not s.book.lots
            checks.append(label)
        finally:
            e.dispose()
    # Main source error branches run with a fake transport and isolated ledger;
    # they cannot touch actual request accounting, credentials, or source files.
    import httpx
    import source_entry

    query = json.loads((F / "source-scope.json").read_text())["requests"][0]
    query = deepcopy(query)
    query["id"] = "synthetic_branch"
    query.pop("cache_pages", None)

    def body(clock, token=None):
        return json.dumps(
            dict(
                quotes={query["symbol"]: [dict(t=clock, bp=10, ap=10, bs=1, **{"as": 1}, c=["R"])]},
                next_page_token=token,
            )
        ).encode()

    valid = query["params"]["start"]
    from contextlib import nullcontext

    cases = [
        ("invalid_timestamp", [body("INVALID")], 1, False),
        ("valid_null", [body(valid)], 1, True),
        ("valid_two_pages", [body(valid, "next"), body(valid)], 2, True),
        ("repeated_token", [body(valid, "next"), body(valid, "next")], 2, False),
    ]
    for label, bodies, expected, success in cases:
        folder = F / ("inert-entry-" + job + "-" + label)
        folder.mkdir(exist_ok=False)
        save(
            folder / "cumulative-accounting.json",
            dict(
                original_market_requests_used=80,
                new_market_requests=6,
                original_market_entity_bytes_used=55315470,
                new_market_entity_bytes=144192,
            ),
        )
        calls = []

        class Response:
            status_code = 200
            headers = {}

            def __init__(self, data):
                self.data = data

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def iter_bytes(self, chunk_size):
                yield self.data

        class Client:
            base_url = httpx.URL("https://data.alpaca.markets/v2")

            def stream(self, *args, calls=calls, bodies=bodies, **kwargs):
                calls.append(kwargs["params"])
                return Response(bodies[len(calls) - 1])

        fake = SimpleNamespace(_client=Client(), close=lambda: None)
        scope = dict(requests=[query])
        proof = dict(bootstrap_source_ids=[query["id"]])
        with (
            patch.object(source_entry, "P", folder),
            patch.object(source_entry, "OUT", folder / "raw"),
            patch.object(source_entry, "admitted_scope", return_value=(scope, proof)),
            patch.object(source_entry, "current_grant", return_value=None),
            patch.object(source_entry, "remaining", return_value=100),
            patch.object(source_entry, "locked_ledger", side_effect=lambda: nullcontext()),
            patch(
                "open_composer.adapters.data.alpaca_snapshot._stock_data_client", return_value=fake
            ),
            patch("open_composer.cli._load_env", return_value=None),
        ):
            ok = False
            try:
                source_entry.request_window(
                    job, query["id"], causal_release=dict(kind="bootstrap_source_QA")
                )
                ok = True
            except (ValueError, AssertionError):
                pass
            assert len(calls) == expected and ok == success, (label, calls, ok)
        checks.append("actual_entry_fake_" + label)
    # Native actual-source and standalone financial entry cannot run by giving
    # a component/nojob receipt or old r6 resource grant.
    from gap_adapter import actual_admission

    try:
        actual_admission(None, F / "independent-review.json")
    except ValueError:
        checks.append("standalone_nojob_refused")
    else:
        raise AssertionError("standalone bypass")
    # Exact quote coordinate after the known SMCI split: no rounding to4dp.
    from dataclasses import replace

    from gap_events import quote_data

    ob = replace(q(1730467860000000123), bid=Decimal("34.1234"), ask=Decimal("34.1235"))
    _, tick = quote_data("SMCI", ob, 0.1, 100, 0)
    assert str(tick.bid_price) == "3.41234" and str(tick.ask_price) == "3.41235"
    assert tick.ts_event == ob.event_ns
    checks.append("split_quote_exact5dp_integer_clock")
    import gzip
    from collections import Counter

    from compact_output import flush

    fake_strategy = SimpleNamespace(
        audit=[dict(action="signal", intent_id="retained")],
        snapshots=[
            dict(at_ns=i, equity=v, daily_close=i in (2, 5))
            for i, v in enumerate((100, 120, 90, 130, 80, 110))
        ],
        policy=SimpleNamespace(
            states={
                "SOFI": SimpleNamespace(
                    audit=[
                        dict(at="2024-11-01T13:31:00Z", reason="watch", state="watch"),
                        dict(at="2024-11-01T13:32:00Z", reason="watch", state="watch"),
                        dict(at="2024-11-01T13:33:00Z", order_id="exact", filled_quantity=3),
                    ]
                )
            }
        ),
    )
    flush(fake_strategy, result_folder, "compact", Counter())
    summary = json.loads((result_folder / "compact-minute-summary.json").read_text())
    assert summary["end_minute_NAV_count"] == 6 and summary["daily_NAV_count"] == 2
    assert summary["internal_end_minute_max_drawdown"] == 1 - 80 / 130
    assert summary["maximum"] == 130 and summary["minimum"] == 80
    rows = [json.loads(r) for r in gzip.open(result_folder / "compact-policy.jsonl.gz")]
    assert len(rows) == 2 and rows[0]["order_id"] == "exact" and rows[1]["count"] == 2
    assert (
        json.loads(gzip.open(result_folder / "compact-audit.jsonl.gz").read())["intent_id"]
        == "retained"
    )
    checks.append("compact_outputs_preserve_signals_reports_daily_and_extrema")
    save(
        F / "current-diff-verification.json",
        dict(
            checks=checks,
            native_engines=engines,
            actual_HTTP=0,
            actual_source_native_replays=0,
            current_files=[bind(f) for f in files],
            synthetic_native_reference_counts=8,
            old8_reused_not_claimed_current_full_byte_replay=True,
        ),
    )


if __name__ == "__main__":
    main(sys.argv[1])
