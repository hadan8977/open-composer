"""Bounded Daniel--Moskowitz published-decile method diagnostic.

The `qualify` command is source intake, not an economic run. `evaluate` requires
an independent, exact implementation admission supplied after this file is frozen.
No security-level, cost, cash-book, or promotion claim is made here.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import tarfile
import time
import zipfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
AUTHOR = HERE / "sources/dm-published-portfolios-201402.tar.gz"
FRENCH = ROOT / "reports/research/program/regime-french-source-20261010-1917/official-daily.zip"
AUTHOR_SHA = "32139ee0ad2daba2a7e5c7c071285a6cce9dfacf6dc7b99444f8f41bfeeefd36"
FRENCH_SHA = "2f29e22546069914890a712680a6f81f3680ebc3543b52864484d209ca13a7db"
IDS = (
    "S0_STATIC_WML",
    "S1_CVOL",
    "S2_INVVAR",
    "S3_DM_MEAN",
    "S4_WINNER_STATIC",
    "S5_WINNER_INVVAR",
    "S6_WINNER_MEAN",
)
FIRST = 193401
LAST = 201303


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def _ym(date: int) -> int:
    return date // 100


def _date(date: int) -> None:
    datetime.strptime(str(date), "%Y%m%d")


def author_rows(member: str) -> tuple[np.ndarray, np.ndarray, dict]:
    dates: list[int] = []
    returns: list[list[float]] = []
    counts: list[list[int]] = []
    sentinel = defaultdict(int)
    with tarfile.open(AUTHOR, "r:gz") as tar:
        handle = tar.extractfile(member)
        if handle is None:
            raise ValueError(f"missing exact author member {member}")
        prev_date, decile_row, count_row = None, [], []
        for number, raw in enumerate(handle, 1):
            parts = raw.decode("ascii").split()
            if len(parts) != 5:
                raise ValueError(f"{member}:{number}: five-column schema expected")
            date, rank = int(parts[0]), int(parts[1])
            ret, cap, n = float(parts[2]), float(parts[3]), int(parts[4])
            _date(date)
            if not math.isfinite(ret) or not math.isfinite(cap) or cap <= 0 or n <= 0:
                raise ValueError(f"{member}:{number}: nonfinite/invalid cap/count")
            if abs(ret) >= 0.99 or ret in (-99.0, -999.0):
                sentinel[str(ret)] += 1
            if date != prev_date:
                if prev_date is not None:
                    if len(decile_row) != 10:
                        raise ValueError(f"{member}:{number}: missing decile")
                    returns.append(decile_row)
                    counts.append(count_row)
                if dates and date <= dates[-1]:
                    raise ValueError(f"{member}:{number}: date ordering")
                dates.append(date)
                decile_row, count_row, prev_date = [], [], date
            if rank != len(decile_row) + 1:
                raise ValueError(f"{member}:{number}: decile identity/order")
            decile_row.append(ret)
            count_row.append(n)
        if len(decile_row) != 10:
            raise ValueError(f"{member}: incomplete last date")
        returns.append(decile_row)
        counts.append(count_row)
    a = np.asarray(returns, dtype=float)
    c = np.asarray(counts, dtype=int)
    if np.any(a <= -1) or np.any(a > 100):
        raise ValueError(f"{member}: invalid/sentinel return; do not silently drop")
    return (
        np.asarray(dates, dtype=int),
        a,
        {
            "rows": int(a.size),
            "dates": len(dates),
            "first": dates[0],
            "last": dates[-1],
            "return_min": float(a.min()),
            "return_max": float(a.max()),
            "count_min": int(c.min()),
            "sentinel_candidates": dict(sentinel),
        },
    )


def french_daily() -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    dates, mkt, rf = [], [], []
    with zipfile.ZipFile(FRENCH) as archive:
        if archive.namelist() != ["F-F_Research_Data_Factors_daily.csv"]:
            raise ValueError("unexpected French member inventory")
        raw = archive.read("F-F_Research_Data_Factors_daily.csv").decode("utf-8-sig")
    version = raw.splitlines()[:5]
    reader = csv.reader(io.StringIO(raw))
    for row in reader:
        if len(row) < 5 or not row[0].strip().isdigit() or len(row[0].strip()) != 8:
            continue
        date = int(row[0].strip())
        _date(date)
        if dates and date <= dates[-1]:
            raise ValueError("French daily date ordering")
        vals = [float(x.strip()) for x in row[1:5]]
        if any(not math.isfinite(x) or abs(x) >= 99 for x in vals):
            raise ValueError(f"French sentinel/nonfinite {date}")
        dates.append(date)
        mkt.append(vals[0] / 100.0)  # French CSV fields are PERCENT, author decimals.
        rf.append(vals[3] / 100.0)
    return (
        np.asarray(dates),
        np.asarray(mkt),
        np.asarray(rf),
        {
            "version_header": version,
            "rows": len(dates),
            "first": dates[0],
            "last": dates[-1],
            "mkt_excess_min": min(mkt),
            "mkt_excess_max": max(mkt),
            "rf_min": min(rf),
            "rf_max": max(rf),
        },
    )


def qualify() -> dict:
    begin = time.monotonic()
    if sha(AUTHOR) != AUTHOR_SHA or sha(FRENCH) != FRENCH_SHA:
        raise ValueError("archive hash changed from Root accepted scope")
    md, mr, mi = author_rows("txt/m_m_pt_tot.txt")
    dd, dr, di = author_rows("txt/d_m_pt_tot.txt")
    fd, fm, fr, fi = french_daily()
    full_fd, full_fm, full_fr = fd.copy(), fm.copy(), fr.copy()
    if any(x != 10 for x in (mr.shape[1], dr.shape[1])):
        raise ValueError("decile count")
    daily_months = np.asarray([_ym(int(x)) for x in dd])
    month_keys = np.asarray([_ym(int(x)) for x in md])
    if len(set(month_keys)) != len(md):
        raise ValueError("duplicate author month")
    if set(daily_months) != set(month_keys):
        raise ValueError("author daily/monthly month mismatch")
    fpos = {int(d): i for i, d in enumerate(fd)}
    missing = [int(d) for d in dd if int(d) not in fpos]
    extra = [int(d) for d in fd if FIRST <= _ym(int(d)) <= LAST and int(d) not in set(dd)]
    if missing:
        raise ValueError(f"French RF/market lacks {len(missing)} author days; first={missing[:5]}")
    fi_idx = np.asarray([fpos[int(d)] for d in dd], dtype=int)
    fm, fr = fm[fi_idx], fr[fi_idx]
    j_by_month = {int(k): np.flatnonzero(daily_months == k) for k in month_keys}
    residuals, daycounts, month_end_neq = [], [], []
    monthly_rf = []
    for i, k in enumerate(month_keys):
        ix = j_by_month[int(k)]
        daycounts.append(len(ix))
        residuals.append(np.prod(1 + dr[ix], axis=0) - 1 - mr[i])
        monthly_rf.append(float(np.prod(1 + fr[ix]) - 1))
        if int(dd[ix[-1]]) != int(md[i]):
            month_end_neq.append([int(k), int(md[i]), int(dd[ix[-1]])])
    residuals = np.asarray(residuals)
    abs_res = np.abs(residuals)
    by_decile = [
        {
            "decile": j + 1,
            "median_abs": float(np.median(abs_res[:, j])),
            "p95_abs": float(np.quantile(abs_res[:, j], 0.95)),
            "max_abs": float(abs_res[:, j].max()),
            "months_gt_5bp": int(np.sum(abs_res[:, j] > 0.0005)),
        }
        for j in range(10)
    ]
    exact = {
        "author_archive": AUTHOR_SHA,
        "french_daily_archive": FRENCH_SHA,
        "author_monthly_member": "txt/m_m_pt_tot.txt",
        "author_daily_member": "txt/d_m_pt_tot.txt",
        "french_member": "F-F_Research_Data_Factors_daily.csv",
    }
    report = {
        "schema_version": 1,
        "type": "source_input_qualification",
        "as_of_utc": datetime.now(UTC).isoformat(),
        "owner": "b497883a-0236-422c-929b-f9b5998fff83",
        "input_hashes": exact,
        "units": {
            "author": "decimal simple return, five decimal places",
            "french": "percent CSV converted /100 to decimal daily simple return",
            "wml_monthly": "D10_monthly-D1_monthly",
            "wml_daily_variance": "variance of D10_daily-D1_daily",
            "rf": "French revised 202608 CRSP/CIZ vintage; NOT exact original paper Table7 RF",
        },
        "author_monthly": mi,
        "author_daily": di,
        "french_daily": fi,
        "calendar": {
            "monthly_count": len(md),
            "author_daily_count": len(dd),
            "matched_french_days": len(fi_idx),
            "french_extra_days_in_evaluation_window": len(extra),
            "french_extra_first": extra[:8],
            "month_end_mismatches": month_end_neq[:20],
            "month_end_mismatch_count": len(month_end_neq),
            "daily_days_per_month_min": min(daycounts),
            "daily_days_per_month_max": max(daycounts),
        },
        "daily_monthly_decile_reconstruction": {
            "by_decile": by_decile,
            "overall_median_abs": float(np.median(abs_res)),
            "overall_p95_abs": float(np.quantile(abs_res, 0.95)),
            "overall_max_abs": float(abs_res.max()),
            "count_gt_5bp": int(np.sum(abs_res > 0.0005)),
            "count_gt_10bp": int(np.sum(abs_res > 0.001)),
            "note": (
                "Diagnostic; author daily/monthly rebalance conventions may differ. "
                "Monthly labels are never replaced by compounded daily series."
            ),
        },
        "source_orientation": {
            "winner": "D10",
            "loser": "D1",
            "wml": "D10-D1",
            "paper_table_1_caption_conflict": (
                "Table1 caption reverses long/short deciles; body winner 15.3, "
                "loser -2.5 and short-loser crash identify D10-D1."
            ),
        },
        "monthly_rf_min": min(monthly_rf),
        "monthly_rf_max": max(monthly_rf),
        "qualification_wall_seconds": round(time.monotonic() - begin, 3),
        "ols_fit_attempts": 0,
        "stock_rows": 0,
        "cloud_USD": 0,
    }
    write_json(HERE / "source-input-qualification.json", report)
    np.savez_compressed(
        HERE / "qualified-source.npz",
        month_dates=md,
        month_deciles=mr,
        daily_dates=dd,
        daily_deciles=dr,
        daily_mkt_excess=fm,
        daily_rf=fr,
        french_full_dates=full_fd,
        french_full_mkt_excess=full_fm,
        french_full_rf=full_fr,
        month_rf=np.asarray(monthly_rf),
    )
    report["derived_input_sha256"] = sha(HERE / "qualified-source.npz")
    write_json(HERE / "source-input-qualification.json", report)
    return report


def evaluate(admission: Path) -> dict:
    """Execute only after Root independent implementation/native admission."""
    receipt = json.loads(admission.read_text())
    if (
        receipt.get("verdict") != "admit_source_full_fits"
        or receipt.get("reviewer") == "b497883a-0236-422c-929b-f9b5998fff83"
    ):
        raise PermissionError("source full fits not independently admitted")
    if receipt.get("implementation_sha256") != sha(HERE / "source-implementation-manifest.json"):
        raise PermissionError("implementation binding changed")
    if receipt.get("qualified_input_sha256") != sha(HERE / "qualified-source.npz"):
        raise PermissionError("qualified input binding changed")
    from open_composer.research.iteration_dossier import validate_iteration_dossier

    iteration_dir = ROOT / "reports/research/iterations/eq_role_source_20261013"
    assessment = json.loads((iteration_dir / "knowledge-assessment.json").read_text())
    if assessment.get("status") != "ok" or assessment.get("external_brief_sha256") != sha(
        iteration_dir / "external-brief.json"
    ):
        raise PermissionError("native source knowledge gate not accepted")
    gate = validate_iteration_dossier("eq_role_source_20261013", ROOT, stage="pre-backtest")
    if gate.status != "ok":
        raise PermissionError(f"native source iteration gate blocked: {gate.blocked}")
    return _run_source_method()


def _rollvar(values: np.ndarray, right_exclusive: int) -> float:
    if right_exclusive < 126:
        return math.nan
    return float(np.var(values[right_exclusive - 126 : right_exclusive], ddof=1))


def _sharpe(values: np.ndarray) -> float:
    sd = float(np.std(values, ddof=1))
    return float(np.sqrt(12) * np.mean(values) / sd) if sd > 0 else math.nan


def _fit_mean(y: np.ndarray, x: np.ndarray) -> tuple[float, float, bool]:
    """One counted OLS attempt; rank deficient x gets the predeclared mean-only fit."""
    if len(y) < 7 or not np.all(np.isfinite(y)) or not np.all(np.isfinite(x)):
        raise ValueError("unmatured/nonfinite OLS history")
    if np.std(x) < 1e-14:
        return float(np.mean(y)), 0.0, True
    design = np.column_stack((np.ones(len(y)), x))
    beta, _, rank, _ = np.linalg.lstsq(design, y, rcond=None)
    if rank != 2:
        return float(np.mean(y)), 0.0, True
    return float(beta[0]), float(beta[1]), False


def _joint_block_intervals(
    pairs: list[tuple[np.ndarray, np.ndarray]], seed: int = 2026101300
) -> list[dict]:
    """Simultaneous paired 3-month block intervals for the two fixed Sharpe gaps."""
    if not pairs or any(len(a) != len(b) for a, b in pairs) or len({len(a) for a, _ in pairs}) != 1:
        raise ValueError("unpaired source series")
    rng = np.random.default_rng(seed)
    n = len(pairs[0][0])
    reps = np.empty((1000, len(pairs)))
    for z in range(1000):
        start = rng.integers(0, n - 2, size=(n + 2) // 3)
        ix = np.concatenate([np.arange(i, i + 3) for i in start])[:n]
        for j, (a, b) in enumerate(pairs):
            reps[z, j] = _sharpe(a[ix]) - _sharpe(b[ix])
    observed = np.asarray([_sharpe(a) - _sharpe(b) for a, b in pairs])
    radius = float(np.quantile(np.max(np.abs(reps - observed), axis=1), 0.95))
    return [
        {
            "observed_annualized_sharpe_gap": float(gap),
            "simultaneous_family_95_interval": [float(gap - radius), float(gap + radius)],
            "unadjusted_percentile_95_interval": [
                float(np.quantile(reps[:, j], 0.025)),
                float(np.quantile(reps[:, j], 0.975)),
            ],
            "block_months": 3,
            "replicates": 1000,
            "seed": seed,
            "family_size": len(pairs),
        }
        for j, gap in enumerate(observed)
    ]


def _run_source_method() -> dict:
    begin = time.monotonic()
    data = np.load(HERE / "qualified-source.npz")
    md, mr = data["month_dates"], data["month_deciles"]
    dd, dr = data["daily_dates"], data["daily_deciles"]
    fm, fr = data["daily_mkt_excess"], data["daily_rf"]
    full_fd = data["french_full_dates"]
    full_fm = data["french_full_mkt_excess"]
    full_fr = data["french_full_rf"]
    monthly_rf = data["month_rf"]
    month_keys = md // 100
    day_keys = dd // 100
    daily_wml = dr[:, 9] - dr[:, 0]
    daily_win_excess = dr[:, 9] - fr
    month_wml = mr[:, 9] - mr[:, 0]
    month_win_excess = mr[:, 9] - monthly_rf
    x = np.full(len(md), math.nan)
    vw, vwin, ib, prior_last_day = [np.full(len(md), math.nan) for _ in range(4)]
    french_months = full_fd // 100
    french_total_by_month = {
        int(key): float(np.prod(1 + (full_fm + full_fr)[french_months == key]) - 1)
        for key in np.unique(french_months)
    }
    daily_end = []
    for key in month_keys:
        ix = np.flatnonzero(day_keys == key)
        if len(ix) == 0:
            raise ValueError(f"missing author daily month {key}")
        daily_end.append(int(ix[-1]))
    for i, key in enumerate(month_keys):
        if i < 1:
            continue
        cutoff = daily_end[i - 1] + 1  # previous month last day; never include target month
        prior_last_day[i] = int(dd[cutoff - 1])
        vw[i] = _rollvar(daily_wml, cutoff)
        vwin[i] = _rollvar(daily_win_excess, cutoff)
        market_v = _rollvar(fm, cutoff)
        keys = sorted(k for k in french_total_by_month if k < key)
        if len(keys) >= 24:
            trailing_total = np.prod([1 + french_total_by_month[k] for k in keys[-24:]]) - 1
            ib[i] = float(trailing_total < 0)
            x[i] = ib[i] * market_v
    train0 = int(np.flatnonzero(month_keys >= 192707)[0])
    eval_ix = np.flatnonzero((month_keys >= FIRST) & (month_keys <= LAST))
    if len(eval_ix) != 951 or month_keys[eval_ix[0]] != FIRST or month_keys[eval_ix[-1]] != LAST:
        raise ValueError("unexpected 1934:01-2013:03 evaluation coverage")
    results = np.empty((len(eval_ix), 7))
    weights = np.empty((len(eval_ix), 7))
    fallback = [0, 0]
    fit_attempts = 0
    coefficients = []
    for row, i in enumerate(eval_ix):
        if not np.all(np.isfinite([x[i], vw[i], vwin[i]])) or min(vw[i], vwin[i]) <= 0:
            raise ValueError(f"invalid lagged inputs {md[i]}")
        history = slice(train0, i)
        y_w, y_win, x_hist = month_wml[history], month_win_excess[history], x[history]
        # French starts July 1926, so 1927:07 cannot have 24 observed months.
        # Train only on fully identified x and log the resulting source gap.
        valid = np.isfinite(x_hist)
        if valid.sum() < 7:
            raise ValueError("insufficient causally identified source history")
        a_w, b_w, fallback_w = _fit_mean(y_w[valid], x_hist[valid])
        a_win, b_win, fallback_win = _fit_mean(y_win[valid], x_hist[valid])
        fit_attempts += 2
        fallback[0] += fallback_w
        fallback[1] += fallback_win
        if fit_attempts > 2200:
            raise RuntimeError("cumulative source fit cap exceeded")
        mu_w = a_w + b_w * x[i]
        mu_win = a_win + b_win * x[i]
        weights[row] = [
            1,
            1 / math.sqrt(vw[i]),
            1 / vw[i],
            mu_w / vw[i],
            1,
            1 / vwin[i],
            mu_win / vwin[i],
        ]
        results[row] = weights[row] * np.asarray([month_wml[i]] * 4 + [month_win_excess[i]] * 3)
        coefficients.append(
            [int(md[i]), a_w, b_w, a_win, b_win, mu_w, mu_win, int(ib[i]), int(prior_last_day[i])]
        )
    # Same S3/S2 weight difference, fixed D10 and -D1 legs; RF cancels exactly.
    dw = weights[:, 3] - weights[:, 2]
    winner_leg = dw * (mr[eval_ix, 9] - monthly_rf[eval_ix])
    loser_leg = dw * (-(mr[eval_ix, 0] - monthly_rf[eval_ix]))
    identity_max = float(np.max(np.abs((winner_leg + loser_leg) - (results[:, 3] - results[:, 2]))))
    if identity_max > 1e-8:
        raise AssertionError("same-weight WML leg identity failed")
    negative_w = weights[:, 3] < 0
    candidate_rows = []
    for j, name in enumerate(IDS):
        w = weights[:, j]
        val = results[:, j]
        candidate_rows.append(
            {
                "candidate_id": name,
                "months": len(val),
                "gross_mean_monthly_unscaled": float(np.mean(val)),
                "gross_vol_monthly_unscaled": float(np.std(val, ddof=1)),
                "gross_annualized_sharpe": _sharpe(val),
                "weight_min": float(np.min(w)),
                "weight_median": float(np.median(w)),
                "weight_p95": float(np.quantile(w, 0.95)),
                "weight_max": float(np.max(w)),
                "negative_weight_months": int(np.sum(w < 0)),
                "gross_oriented_not_cash_book": True,
            }
        )
    intervals = _joint_block_intervals(
        [(results[:, 3], results[:, 2]), (results[:, 6], results[:, 5])]
    )
    output = {
        "schema_version": 1,
        "type": "published_source_method_diagnostic",
        "as_of_utc": datetime.now(UTC).isoformat(),
        "claim_scope": (
            "published author decile portfolios; gross method and target transportability only"
        ),
        "input_sha256": sha(HERE / "qualified-source.npz"),
        "source_rf_vintage": "202608 revised CRSP/CIZ; not exact original Table7",
        "training": {
            "nominal_start": "1927:07",
            "first_fully_identified_x": int(month_keys[np.flatnonzero(np.isfinite(x))[0]]),
            "reason": (
                "24-month bear indicator unavailable at 1927:07 from French "
                "daily starting 1926:07; unidentifiable x excluded, not filled"
            ),
            "end_each_fit": "t-1",
            "fit_attempts": fit_attempts,
            "rank_deficient_mean_only_fits": fallback,
        },
        "evaluation": {
            "first": FIRST,
            "last": LAST,
            "months": len(eval_ix),
            "IB_months": int(np.sum(ib[eval_ix])),
            "IB_zero_months": int(np.sum(ib[eval_ix] == 0)),
        },
        "candidate_results": candidate_rows,
        "paired_sharpe_differences": {
            "S3_minus_S2": intervals[0],
            "S6_minus_S5": intervals[1],
        },
        "S3_minus_S2_same_weight_leg_identity": {
            "max_abs_error": identity_max,
            "winner_excess_leg_mean": float(np.mean(winner_leg)),
            "short_loser_excess_leg_mean": float(np.mean(loser_leg)),
            "sum_mean": float(np.mean(winner_leg + loser_leg)),
            "negative_S3_weight_months": int(np.sum(negative_w)),
            "negative_S3_weight_winner_leg_mean": float(np.mean(winner_leg[negative_w]))
            if np.any(negative_w)
            else None,
            "negative_S3_weight_short_loser_leg_mean": float(np.mean(loser_leg[negative_w]))
            if np.any(negative_w)
            else None,
            "note": "Algebraic attribution, not unique short-loser causal proof.",
        },
        "source_net": None,
        "stock_net": None,
        "paper_ready": False,
        "promotion_eligible": False,
        "resource_use": {
            "OLS_fit_attempts": fit_attempts,
            "wall_seconds_this_command": round(time.monotonic() - begin, 3),
            "cloud_USD": 0,
        },
    }
    np.savez_compressed(
        HERE / "source-evaluation-arrays.npz",
        month_dates=md[eval_ix],
        returns=results,
        weights=weights,
        coefficients=np.asarray(coefficients),
        winner_leg=winner_leg,
        short_loser_leg=loser_leg,
    )
    output["evaluation_arrays_sha256"] = sha(HERE / "source-evaluation-arrays.npz")
    write_json(HERE / "source-results.json", output)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("qualify", "evaluate"))
    parser.add_argument("--admission", type=Path)
    args = parser.parse_args()
    result = qualify() if args.command == "qualify" else evaluate(args.admission)
    print(
        json.dumps(
            {
                "type": result["type"],
                "months": result.get("calendar", {}).get("monthly_count"),
                "sha256": sha(HERE / "source-input-qualification.json"),
            },
            ensure_ascii=False,
        )
    )
