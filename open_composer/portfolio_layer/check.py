"""Read-only limit check for one account (exit code non-zero when a limit is breached)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from . import exposure as E
from . import registry as G

ROOT = G.ROOT


@dataclass
class Check:
    name: str
    value: float | str | None
    limit: float | str | None
    status: str  # ok | BREACH | info | unknown
    note: str = ""


def _cmp(
    name: str, value: float | None, limit: float | None, absolute: bool = True, note: str = ""
) -> Check:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return Check(name, None, limit, "unknown", note or "no data")
    if limit is None:
        return Check(name, round(float(value), 4), None, "info", note)
    v = abs(value) if absolute else value
    return Check(
        name, round(float(value), 4), limit, "ok" if v <= limit + 1e-12 else "BREACH", note
    )


def account_equity(account: str, root: Path = ROOT) -> tuple[float | None, str]:
    if account == "main":
        p = root / "reports/paper/account.json"
        return (
            (float(json.loads(p.read_text())["equity"]), str(p.relative_to(root)))
            if p.exists()
            else (None, "missing")
        )
    f = E.latest_file(root / f"reports/paper/book/{account}/plans")
    if not f:
        return None, "missing"
    d = json.loads(f.read_text())
    return float(d.get("equity_live") or d.get("equity_basis")), str(f.relative_to(root))


def run_check(account: str, root: Path = ROOT) -> list[Check]:
    reg = G.load_registry(root / "config/portfolio-layer/sleeves.json")
    lim = json.loads((root / "config/portfolio-layer/limits.json").read_text())
    al = lim["accounts"][account]
    sl = [s for s in G.sleeves(reg) if s.account == account]
    out: list[Check] = []
    equity, src = account_equity(account, root)
    out.append(Check("account equity (USD)", equity, None, "info", src))
    if equity is None:
        return out + [Check("equity", None, None, "unknown", "cannot size limits")]
    active = [s for s in sl if s.status in G.ACTIVE_STATUSES]
    cap_total = sum(s.capital_usd for s in active)
    out.append(
        _cmp(
            "sum of sleeve capital / equity",
            cap_total / equity,
            al["gross_max"],
            note="registry capital",
        )
    )
    for s in active:
        if s.status == G.OBSERVATION:
            out.append(
                _cmp(
                    f"observation sleeve {s.id} capital / equity",
                    s.capital_usd / equity,
                    lim["observation_capital_share_max"],
                )
            )
    # live configuration vs registry
    if account == "quant1":
        f = E.latest_file(root / "reports/paper/book/quant1/plans")
        basis = json.loads(f.read_text())["equity_basis"] if f else None
        f1 = next((s for s in active if s.id == "F1"), None)
        if f1 and basis:
            ok = abs(f1.capital_usd - basis) < 1.0
            out.append(
                Check(
                    "registry F1 capital = plan equity_basis",
                    f1.capital_usd,
                    basis,
                    "ok" if ok else "BREACH",
                    "registry out of date" if not ok else "",
                )
            )
    if account == "quant2":
        cfg = yaml.safe_load((root / "config/intraday/runner-quant2.yaml").read_text())
        run_cap = float(sum(s["capital_usd"] for s in cfg["strategies"]))
        reg_cap = sum(s.capital_usd for s in active)
        out.append(
            Check(
                "registry sleeve capital = runner capital_usd",
                reg_cap,
                run_cap,
                "ok" if abs(reg_cap - run_cap) < 1 else "BREACH",
            )
        )
        gross = float(cfg["account_caps"]["max_gross_notional_usd"]) / equity
        out.append(_cmp("intraday gross cap / equity (runner)", gross, al["gross_max"]))
    # exposures
    if account == "quant1":
        t = E.latest_file(root / "reports/paper/book/quant1/targets")
        if t is None:
            out.append(Check("targets", None, None, "unknown", "no targets file"))
        else:
            ex = E.book_target_exposure(t, root)
            out.append(
                _cmp(
                    "gross (long+short, / equity)",
                    ex["gross"],
                    al["gross_max"],
                    note=f"targets {ex['decision_date']}",
                )
            )
            out.append(
                Check(
                    "risk model age at decision date (days)",
                    ex["risk_model_age_days"],
                    None,
                    "info",
                    f"saved model {ex['risk_model_date']}; exposures below use it",
                )
            )
            out.append(
                _cmp(
                    "net beta",
                    ex["beta"],
                    al["beta_abs_max"],
                    note=f"modelled share of gross {ex['modelled_share_of_gross']:.2f}",
                )
            )
            for k, v in ex["style"].items():
                if k in al["style_abs_max"]:
                    out.append(_cmp(f"style {k}", v, al["style_abs_max"][k]))
            worst = max(ex["industry_net"].items(), key=lambda kv: abs(kv[1]))
            out.append(
                _cmp(f"industry net (worst: {worst[0]})", worst[1], al["industry_net_abs_max"])
            )
    elif account == "main":
        lev = lim["etf_leverage"]
        ex = E.positions_exposure(root / "reports/paper/positions.json", equity, lev, lim["themes"])
        out.append(
            _cmp(
                "gross market value (Reg T basis, / equity)",
                ex["gross"],
                al["gross_max"],
                note="positions.json",
            )
        )
        out.append(
            _cmp(
                "gross economic (ETF leverage applied, / equity)",
                ex["gross_economic"],
                None,
                note="info",
            )
        )
        for name, lim_t in (al["theme_max_fraction_of_equity"] or {}).items():
            out.append(_cmp(f"theme {name} (effective, / equity)", ex["themes"][name], lim_t))
    if account in ("main", "quant2"):
        fr = E.load_factor_returns(root=root)
        tot: dict[str, float] = {}
        for s in active:
            if not s.has_series:
                continue
            b = E.regression_betas(G.load_returns(s, root), fr, lim["regression_window_days"])
            for k, v in b.items():
                tot[k] = tot.get(k, 0.0) + s.capital_usd / equity * (0.0 if np.isnan(v) else v)
        for k, v in tot.items():
            lim_k = al["beta_abs_max"] if k == "market" else al["style_abs_max"].get(k)
            out.append(
                _cmp(
                    f"regression {k} loading (sleeve capital weighted)",
                    v,
                    lim_k,
                    note="return regression, 252d",
                )
            )
    return out


def exit_code(checks: list[Check]) -> int:
    if any(c.status == "BREACH" for c in checks):
        return 1
    return 0


def format_checks(account: str, checks: list[Check]) -> str:
    rows = [f"portfolio_layer check --account {account}", "status  | check | value | limit | note"]
    for c in checks:
        rows.append(f"{c.status:7} | {c.name} | {c.value} | {c.limit} | {c.note}")
    rows.append(f"result: {'BREACH' if exit_code(checks) else 'ok'}")
    return "\n".join(rows)
