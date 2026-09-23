# ruff: noqa: E501 -- report-generator script: long provenance strings are kept verbatim
"""Mine published factor/anomaly libraries for recent-window performance.

I-20260923-01: before reproducing any anomaly on our own data, see which of
the hundreds of published factors actually made money recently, using the
*authors' own* up-to-date return series. This is a read-only screen: it
downloads official free files, computes descriptive stats in two fixed
recent windows, and writes a manifest + a stats table. It does not touch
strategy code, paper trading, or the 2026 holdout.

Sources (see module docstrings below per loader for the exact files/URLs):
  1. Kenneth French Data Library (factors + univariate decile sorts + 49 industries)
  2. AQR Datasets (BAB, QMJ, TSMOM, Value-and-Momentum-Everywhere)
  3. JKP Global Factor Data (jkpfactors.com; 153 factors + 13 themes, USA)
  4. Open Source Asset Pricing (openassetpricing.com; 212 predictor long-short)
  5. Hou-Xue-Zhang q-factor library (global-q.org; q5 factors + one testing
     portfolio, momentum deciles, as a bounded sample of what is offered)

HARD RULE: every series is truncated to date < 2026-01-01 immediately after
parsing, before any statistic is computed. The frozen protocol keeps
2026-01-01 onward as an untouched holdout; this script never prints,
computes, or stores a 2026 return. The one exception is metadata: the
"latest_date_in_file" field in the manifest records what the source file
actually contains (which may reach into 2026), because that is a fact about
the file, not a statistic about a return.

Windows (both inclusive, month-end dates):
  W_common = 2023-10-31 .. 2024-12-31 (15 months)
  W_select = 2023-10-31 .. 2025-12-31 (27 months)
A series that does not reach 2025-12-31 is reported for W_common only.

Sharpe convention (documented here because it is a judgment call, not a
literal per-series constant): the task brief asks for "Sharpe of excess
return over the FF RF" for every series. Applied literally, that would
double-subtract RF from series that are already zero-cost long-short
spreads (HML, momentum, BAB, JKP factors, OSAP predictors, ...), which
would understate their Sharpe by a roughly constant amount and distort
ranking versus market/long-only series. So: series that are already
excess/zero-investment by construction (class b long-short factors, and
Fama-French "Mkt-RF" / HXZ "R_MKT" which are already market-minus-RF) use
their own mean/vol directly. Series that are raw, not-yet-excess returns
(class a long-only portfolios: deciles, industries, the reconstructed total
market) have FF RF subtracted first. This is noted per row in stats.csv's
`excess_convention` column so it is auditable, not silently mechanical.

Run with: ./.venv/bin/python scripts/mine_factor_libraries.py
Machine constraints: 3.9 GB RAM, no AVX2. Polars crashes on import on this
box even with POLARS_SKIP_CPU_CHECK=1 (confirmed empirically: bare `import
polars` raises SIGILL before any CPU-check code can run), so this script
avoids polars and the `openassetpricing` PyPI package (which imports
polars) entirely, and talks to Google Drive directly with `requests`
instead -- this is explicitly allowed by the task brief ("either as the
site's CSV or through the openassetpricing PyPI package").
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw" / "factor_libraries"
OUT_DIR = REPO_ROOT / "reports" / "research" / "intel" / "sources" / "20260923-factor-libraries"
MANIFEST_PATH = OUT_DIR / "manifest.json"
STATS_PATH = OUT_DIR / "stats.csv"

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/98.0.4758.102 Safari/537.36 open-composer-research/1.0"
)

CUTOFF_2026 = pd.Timestamp("2026-01-01")
W_COMMON = (pd.Timestamp("2023-10-31"), pd.Timestamp("2024-12-31"))
W_SELECT = (pd.Timestamp("2023-10-31"), pd.Timestamp("2025-12-31"))
WINDOWS = {"W_common": W_COMMON, "W_select": W_SELECT}


def _utcnow_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Manifest bookkeeping
# ---------------------------------------------------------------------------


@dataclass
class ManifestEntry:
    source: str
    file: str
    url: str
    fetched_at: str
    sha256: str
    bytes: int
    latest_date_in_file: str | None
    parse_notes: str
    status: str = "ok"


MANIFEST: list[ManifestEntry] = []


def _record_manifest(
    source: str,
    dest: Path,
    url: str,
    fetched_at: str,
    latest_date: pd.Timestamp | None,
    parse_notes: str,
    status: str = "ok",
) -> None:
    data = dest.read_bytes() if dest.exists() else b""
    MANIFEST.append(
        ManifestEntry(
            source=source,
            file=str(dest.relative_to(REPO_ROOT)),
            url=url,
            fetched_at=fetched_at,
            sha256=_sha256_bytes(data) if data else "",
            bytes=len(data),
            latest_date_in_file=(
                latest_date.strftime("%Y-%m-%d") if latest_date is not None else None
            ),
            parse_notes=parse_notes,
            status=status,
        )
    )


def _record_failure(source: str, url: str, reason: str) -> None:
    MANIFEST.append(
        ManifestEntry(
            source=source,
            file="",
            url=url,
            fetched_at=_utcnow_iso(),
            sha256="",
            bytes=0,
            latest_date_in_file=None,
            parse_notes=reason,
            status="failed",
        )
    )


# ---------------------------------------------------------------------------
# Generic HTTP download with a two-attempt retry, per the task's failure policy
# ---------------------------------------------------------------------------


def fetch_url(
    session: requests.Session, url: str, dest: Path, attempts: int = 2
) -> tuple[bool, str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    last_err = ""
    for _ in range(attempts):
        try:
            resp = session.get(url, headers={"User-Agent": UA}, timeout=60)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            return True, _utcnow_iso()
        except Exception as exc:  # noqa: BLE001 - record and move on, per task policy
            last_err = f"{type(exc).__name__}: {exc}"
    return False, last_err


def gdrive_download(
    session: requests.Session, file_id: str, dest: Path, attempts: int = 2
) -> tuple[bool, str]:
    """Download a single public Google Drive file, handling the large-file
    virus-scan confirmation interstitial. Deliberately does not import the
    `openassetpricing` package (which imports polars) or its gdrive_parse
    module (same reason) -- this reimplements just the confirm-token hop.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    last_err = ""
    for _ in range(attempts):
        try:
            resp = session.get(
                "https://drive.google.com/uc",
                params={"id": file_id, "export": "download"},
                headers={"User-Agent": UA},
                timeout=60,
            )
            resp.raise_for_status()
            ctype = resp.headers.get("Content-Type", "")
            if "text/html" in ctype:
                text = resp.text
                if "Quota exceeded" in text or "uc-error-caption" in text:
                    last_err = "google drive: quota exceeded / access blocked for this file_id"
                    continue
                m_uuid = re.search(r'name="uuid" value="([^"]+)"', text)
                m_confirm = re.search(r'name="confirm" value="([^"]+)"', text)
                if m_uuid and m_confirm:
                    resp = session.get(
                        "https://drive.usercontent.google.com/download",
                        params={
                            "id": file_id,
                            "export": "download",
                            "confirm": m_confirm.group(1),
                            "uuid": m_uuid.group(1),
                        },
                        headers={"User-Agent": UA},
                        timeout=120,
                    )
                    resp.raise_for_status()
                    if "text/html" in resp.headers.get("Content-Type", ""):
                        last_err = (
                            "google drive: still HTML after confirm hop (quota or layout change)"
                        )
                        continue
                else:
                    last_err = "google drive: unexpected HTML response, no confirm/uuid form found"
                    continue
            dest.write_bytes(resp.content)
            return True, _utcnow_iso()
        except Exception as exc:  # noqa: BLE001
            last_err = f"{type(exc).__name__}: {exc}"
    return False, last_err


# ---------------------------------------------------------------------------
# Row records
# ---------------------------------------------------------------------------


@dataclass
class SeriesSpec:
    source: str
    series_id: str
    series_label: str
    weighting: str  # vw / ew / na
    klass: str  # a / b / c
    long_side: str  # high / low / n/a / composite / per-source-sign
    excess_mode: str  # "already_excess" / "subtract_rf"
    series: pd.Series  # decimal monthly returns, index = month-end Timestamp, already <2026


ROWS: list[dict] = []


def compute_and_record(spec: SeriesSpec, rf: pd.Series) -> None:
    s = spec.series.dropna()
    s = s[s.index < CUTOFF_2026]
    if s.empty:
        return
    for window_name, (start, end) in WINDOWS.items():
        sl = s[(s.index >= start) & (s.index <= end)]
        if sl.empty:
            continue
        # Only report W_select if the series actually reaches its end month;
        # otherwise a partial/truncated window would silently understate risk.
        if window_name == "W_select" and s.index.max() < end:
            continue
        if window_name == "W_common" and s.index.max() < start:
            continue
        n = len(sl)
        if n < 2:
            continue
        if spec.excess_mode == "subtract_rf":
            excess = sl - rf.reindex(sl.index)
        else:
            excess = sl
        excess = excess.dropna()
        if len(excess) < 2:
            continue
        ann_arith = sl.mean() * 12
        compounded = (1.0 + sl).prod()
        n_years = n / 12.0
        cagr = compounded ** (1.0 / n_years) - 1.0 if compounded > 0 else np.nan
        vol = sl.std(ddof=1) * np.sqrt(12)
        sharpe = (
            (excess.mean() * 12) / (excess.std(ddof=1) * np.sqrt(12))
            if excess.std(ddof=1) > 0
            else np.nan
        )
        cum = (1.0 + sl).cumprod()
        running_max = cum.cummax()
        dd = cum / running_max - 1.0
        max_dd = dd.min()
        ROWS.append(
            {
                "source": spec.source,
                "series_id": spec.series_id,
                "series_label": spec.series_label,
                "weighting": spec.weighting,
                "window": window_name,
                "class": spec.klass,
                "long_side": spec.long_side,
                "excess_convention": spec.excess_mode,
                "n_months": n,
                "ann_arith_return_pct": round(ann_arith * 100, 4),
                "ann_geo_return_pct": round(cagr * 100, 4) if pd.notna(cagr) else "",
                "ann_vol_pct": round(vol * 100, 4),
                "sharpe_excess_rf": round(float(sharpe), 4) if pd.notna(sharpe) else "",
                "max_drawdown_pct": round(max_dd * 100, 4),
            }
        )


# ---------------------------------------------------------------------------
# 1. Kenneth French Data Library
# ---------------------------------------------------------------------------

FRENCH_BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
FRENCH_DIR = RAW_DIR / "french"

MONTH_RE = re.compile(r"^\d{6}$")


def _french_parse_blocks(csv_text: str) -> dict[str, pd.DataFrame]:
    """Split a French CSV into labeled monthly blocks.

    French's decile-sort files stack multiple blocks (VW monthly, EW
    monthly, VW annual, EW annual, number of firms, average firm size, ...)
    separated by blank lines and a text label. This walks the file, finds
    every contiguous run of rows whose first field is a bare YYYYMM (which
    the annual blocks, with bare 4-digit years, never match), and keys each
    run by the nearest preceding non-blank text line.
    """
    lines = csv_text.splitlines()
    n = len(lines)
    i = 0
    blocks: dict[str, pd.DataFrame] = {}
    while i < n:
        first_field = lines[i].split(",", 1)[0].strip()
        if MONTH_RE.match(first_field):
            header_idx = i - 1
            header_line = lines[header_idx] if header_idx >= 0 else ""
            has_header = header_line.strip().startswith(",")
            label_idx = (header_idx if has_header else i) - 1
            while label_idx >= 0 and not lines[label_idx].strip():
                label_idx -= 1
            label = lines[label_idx].strip() if label_idx >= 0 else f"block@{i}"
            if not label:
                label = f"block@{i}"
            j = i
            data_rows = []
            while j < n and MONTH_RE.match(lines[j].split(",", 1)[0].strip()):
                data_rows.append(lines[j])
                j += 1
            cols = [c.strip() for c in header_line.split(",")] if has_header else None
            df = pd.read_csv(io.StringIO("\n".join(data_rows)), header=None)
            if cols is not None and len(cols) == df.shape[1]:
                df.columns = cols
            else:
                df.columns = ["date"] + [f"col{k}" for k in range(1, df.shape[1])]
            df = df.rename(columns={df.columns[0]: "date"})
            df["date"] = pd.to_datetime(
                df["date"].astype(str), format="%Y%m"
            ) + pd.offsets.MonthEnd(0)
            df = df.set_index("date")
            key = label
            suffix = 2
            while key in blocks:
                key = f"{label} #{suffix}"
                suffix += 1
            blocks[key] = df
            i = j
        else:
            i += 1
    return blocks


def _pick_block(blocks: dict[str, pd.DataFrame], want_vw: bool) -> pd.DataFrame | None:
    deny = ("annual", "number of firms", "firm size", "prior returns", "sum of", "be/me")
    for label, df in blocks.items():
        low = label.lower()
        if any(d in low for d in deny):
            continue
        if "monthly" not in low:
            continue
        if want_vw and "value" in low and "weight" in low:
            return df
        if (not want_vw) and "equal" in low and "weight" in low:
            return df
    return None


def _clean_french_numeric(df: pd.DataFrame) -> pd.DataFrame:
    df = df.apply(pd.to_numeric, errors="coerce")
    df = df.mask(df <= -99.0)
    return df / 100.0


def _decile_rank(colname: str) -> int | None:
    c = colname.strip()
    if c in ("Lo 10", "Lo PRIOR"):
        return 1
    if c in ("Hi 10", "Hi PRIOR"):
        return 10
    m = (
        re.match(r"^Dec\s*(\d)$", c)
        or re.match(r"^(\d)-Dec$", c)
        or re.match(r"^PRIOR\s*(\d)$", c, re.IGNORECASE)
    )
    if m:
        return int(m.group(1))
    return None


def _french_download_csv(
    session: requests.Session, zip_stem: str
) -> tuple[str, pd.Timestamp | None, str] | None:
    """Download+unzip one French *_CSV.zip, return (csv_text, latest_date, note) or None on failure."""
    url = FRENCH_BASE + zip_stem + ".zip"
    dest = FRENCH_DIR / f"{zip_stem}.zip"
    ok, fetched_at_or_err = fetch_url(session, url, dest)
    if not ok:
        _record_failure("french", url, f"download failed twice: {fetched_at_or_err}")
        return None
    fetched_at = fetched_at_or_err
    try:
        with zipfile.ZipFile(dest) as zf:
            inner_name = zf.namelist()[0]
            csv_text = zf.read(inner_name).decode("latin-1")
    except Exception as exc:  # noqa: BLE001
        _record_failure("french", url, f"unzip/read failed: {exc}")
        return None
    # latest date across the whole raw text (any YYYYMM token), for manifest metadata only
    tokens = re.findall(r"(?:^|,)(\d{6})(?:,|$)", csv_text, re.MULTILINE)
    latest = None
    if tokens:
        try:
            latest = max(
                pd.Timestamp(t[:4] + "-" + t[4:] + "-01") + pd.offsets.MonthEnd(0)
                for t in set(tokens)
            )
        except ValueError:
            latest = None
    _record_manifest("french", dest, url, fetched_at, latest, f"zip->{inner_name}; block-parsed")
    return csv_text, latest, fetched_at


@dataclass
class FrenchDecileSpec:
    key: str
    zip_stem: str
    label: str
    long_side: str  # "high" or "low"
    direction_source: str


FRENCH_DECILE_SPECS = [
    FrenchDecileSpec(
        "MOM_D",
        "10_Portfolios_Prior_12_2_CSV",
        "10 Portfolios Formed on Prior (2-12) Return (Momentum)",
        "high",
        "french factor file header: Mom = High minus Low prior-return portfolios",
    ),
    FrenchDecileSpec(
        "ST_REV_D",
        "10_Portfolios_Prior_1_0_CSV",
        "10 Portfolios Formed on Short-Term Reversal (Prior 1-1)",
        "low",
        "french factor file header: ST_Rev = Low minus High prior-return portfolios",
    ),
    FrenchDecileSpec(
        "LT_REV_D",
        "10_Portfolios_Prior_60_13_CSV",
        "10 Portfolios Formed on Long-Term Reversal (Prior 13-60)",
        "low",
        "french factor file header: LT_Rev = Low minus High prior-return portfolios",
    ),
    FrenchDecileSpec(
        "OP_D",
        "Portfolios_Formed_on_OP_CSV",
        "10 Portfolios Formed on Operating Profitability",
        "high",
        "french f-f_5_factors_2x3 detail page: RMW = Robust minus Weak OP",
    ),
    FrenchDecileSpec(
        "INV_D",
        "Portfolios_Formed_on_INV_CSV",
        "10 Portfolios Formed on Investment",
        "low",
        "french f-f_5_factors_2x3 detail page: CMA = Conservative(low Inv) minus Aggressive(high Inv)",
    ),
    FrenchDecileSpec(
        "AC_D",
        "Portfolios_Formed_on_AC_CSV",
        "10 Portfolios Formed on Accruals",
        "low",
        "standard accrual anomaly (Sloan 1996); not independently re-verified against a French text page today",
    ),
    FrenchDecileSpec(
        "NI_D",
        "Portfolios_Formed_on_NI_CSV",
        "10 Portfolios Formed on Net Share Issues",
        "low",
        "task brief",
    ),
    FrenchDecileSpec(
        "VAR_D",
        "Portfolios_Formed_on_VAR_CSV",
        "10 Portfolios Formed on Variance",
        "low",
        "task brief",
    ),
    FrenchDecileSpec(
        "RESVAR_D",
        "Portfolios_Formed_on_RESVAR_CSV",
        "10 Portfolios Formed on Residual Variance",
        "low",
        "same low-volatility-anomaly convention as Variance (task brief)",
    ),
    FrenchDecileSpec(
        "BETA_D",
        "Portfolios_Formed_on_BETA_CSV",
        "10 Portfolios Formed on Market Beta",
        "low",
        "standard betting-against-beta anomaly (Frazzini-Pedersen 2014); not independently re-verified today",
    ),
    FrenchDecileSpec(
        "EP_D",
        "Portfolios_Formed_on_E-P_CSV",
        "10 Portfolios Formed on E/P",
        "high",
        "standard value/earnings-yield convention",
    ),
    FrenchDecileSpec(
        "CFP_D",
        "Portfolios_Formed_on_CF-P_CSV",
        "10 Portfolios Formed on CF/P",
        "high",
        "standard value/cashflow-yield convention",
    ),
    FrenchDecileSpec(
        "DP_D",
        "Portfolios_Formed_on_D-P_CSV",
        "10 Portfolios Formed on D/P",
        "high",
        "standard value/dividend-yield convention",
    ),
    FrenchDecileSpec(
        "ME_D",
        "Portfolios_Formed_on_ME_CSV",
        "10 Portfolios Formed on Size (ME)",
        "low",
        "standard size anomaly (Banz 1981); not independently re-verified today",
    ),
    FrenchDecileSpec(
        "BEME_D",
        "Portfolios_Formed_on_BE-ME_CSV",
        "10 Portfolios Formed on Book-to-Market",
        "high",
        "french f-f_5_factors_2x3 detail page: HML = High minus Low B/M",
    ),
]


def load_french(session: requests.Session, rf_out: dict) -> None:
    # -- FF5 (also the source of the uniform RF series) --------------------
    res = _french_download_csv(session, "F-F_Research_Data_5_Factors_2x3_CSV")
    if res is None:
        return
    csv_text, _latest, _fetched = res
    blocks = _french_parse_blocks(csv_text)
    ff5 = next(iter(blocks.values()))
    ff5 = _clean_french_numeric(ff5)
    ff5 = ff5[ff5.index < CUTOFF_2026]
    rf = ff5["RF"]
    rf_out["rf"] = rf

    mkt_rf = ff5["Mkt-RF"]
    compute_and_record(
        SeriesSpec(
            "french",
            "FF_MktRF",
            "US Market minus RF (Fama-French)",
            "vw",
            "c",
            "n/a",
            "already_excess",
            mkt_rf,
        ),
        rf,
    )
    compute_and_record(
        SeriesSpec(
            "french", "FF_RF", "US 1-Month T-Bill (RF)", "na", "c", "n/a", "already_excess", rf
        ),
        rf,
    )
    total_mkt = mkt_rf + rf
    compute_and_record(
        SeriesSpec(
            "french",
            "FF_TotalMkt",
            "US Total Market (CRSP VW, reconstructed Mkt-RF + RF)",
            "vw",
            "a",
            "n/a",
            "subtract_rf",
            total_mkt,
        ),
        rf,
    )
    five_factor_defs = [
        ("SMB", "Small Minus Big (size)", "small"),
        ("HML", "High Minus Low (value, B/M)", "high B/M"),
        ("RMW", "Robust Minus Weak (operating profitability)", "high OP"),
        ("CMA", "Conservative Minus Aggressive (investment)", "low investment"),
    ]
    for col, label, side in five_factor_defs:
        compute_and_record(
            SeriesSpec("french", f"FF_{col}", label, "vw", "b", side, "already_excess", ff5[col]),
            rf,
        )

    # -- standalone Mom / ST_Rev / LT_Rev factor files ----------------------
    for key, zip_stem, label, side in [
        ("Mom", "F-F_Momentum_Factor_CSV", "Momentum factor (Mom, UMD)", "high"),
        ("ST_Rev", "F-F_ST_Reversal_Factor_CSV", "Short-Term Reversal factor", "low"),
        ("LT_Rev", "F-F_LT_Reversal_Factor_CSV", "Long-Term Reversal factor", "low"),
    ]:
        res = _french_download_csv(session, zip_stem)
        if res is None:
            continue
        csv_text, _latest, _fetched = res
        blocks = _french_parse_blocks(csv_text)
        df = next(iter(blocks.values()))
        df = _clean_french_numeric(df)
        df = df[df.index < CUTOFF_2026]
        series = df.iloc[:, 0]
        compute_and_record(
            SeriesSpec(
                "french", f"FF_{key}Factor", label, "vw", "b", side, "already_excess", series
            ),
            rf,
        )

    # -- 49 industry portfolios ---------------------------------------------
    res = _french_download_csv(session, "49_Industry_Portfolios_CSV")
    if res is not None:
        csv_text, _latest, _fetched = res
        blocks = _french_parse_blocks(csv_text)
        for want_vw, weighting in [(True, "vw"), (False, "ew")]:
            df = _pick_block(blocks, want_vw)
            if df is None:
                continue
            df = _clean_french_numeric(df)
            df = df[df.index < CUTOFF_2026]
            for col in df.columns:
                name = col.strip()
                if not name:
                    continue
                compute_and_record(
                    SeriesSpec(
                        "french",
                        f"IND49_{name}",
                        f"49 Industries: {name}",
                        weighting,
                        "a",
                        "n/a",
                        "subtract_rf",
                        df[col],
                    ),
                    rf,
                )

    # -- univariate decile sorts ---------------------------------------------
    for spec in FRENCH_DECILE_SPECS:
        res = _french_download_csv(session, spec.zip_stem)
        if res is None:
            continue
        csv_text, _latest, _fetched = res
        blocks = _french_parse_blocks(csv_text)
        for want_vw, weighting in [(True, "vw"), (False, "ew")]:
            df = _pick_block(blocks, want_vw)
            if df is None:
                continue
            df = _clean_french_numeric(df)
            df = df[df.index < CUTOFF_2026]
            ranks: dict[int, str] = {}
            for col in df.columns:
                r = _decile_rank(col)
                if r is not None:
                    ranks[r] = col
            for rank, col in ranks.items():
                side_tag = "Hi" if rank == 10 else ("Lo" if rank == 1 else str(rank))
                compute_and_record(
                    SeriesSpec(
                        "french",
                        f"{spec.key}_decile{rank:02d}",
                        f"{spec.label} - decile {rank} ({side_tag})",
                        weighting,
                        "a",
                        "n/a",
                        "subtract_rf",
                        df[col],
                    ),
                    rf,
                )
            if 1 in ranks and 10 in ranks:
                if spec.long_side == "high":
                    spread = df[ranks[10]] - df[ranks[1]]
                else:
                    spread = df[ranks[1]] - df[ranks[10]]
                compute_and_record(
                    SeriesSpec(
                        "french",
                        f"{spec.key}_spread",
                        f"{spec.label} - top minus bottom decile (long={spec.long_side}; {spec.direction_source})",
                        weighting,
                        "b",
                        spec.long_side,
                        "already_excess",
                        spread,
                    ),
                    rf,
                )


# ---------------------------------------------------------------------------
# 2. AQR Datasets
# ---------------------------------------------------------------------------

AQR_DIR = RAW_DIR / "aqr"
AQR_BASE = "https://www.aqr.com/-/media/AQR/Documents/Insights/Data-Sets/"

AQR_FILES = [
    (
        "Betting-Against-Beta-Equity-Factors-Monthly.xlsx",
        "BAB Factors",
        18,
        "USA",
        "BAB_USA",
        "Betting Against Beta (USA)",
        "low beta",
    ),
    (
        "Quality-Minus-Junk-Factors-Monthly.xlsx",
        "QMJ Factors",
        18,
        "USA",
        "QMJ_USA",
        "Quality Minus Junk (USA)",
        "high quality",
    ),
]


def load_aqr(session: requests.Session, rf: pd.Series) -> None:
    for fname, sheet, header_row, col, series_id, label, side in AQR_FILES:
        url = AQR_BASE + fname
        dest = AQR_DIR / fname
        ok, fetched_or_err = fetch_url(session, url, dest)
        if not ok:
            _record_failure("aqr", url, f"download failed twice: {fetched_or_err}")
            continue
        fetched_at = fetched_or_err
        try:
            df = pd.read_excel(dest, sheet_name=sheet, header=header_row, engine="openpyxl")
        except Exception as exc:  # noqa: BLE001
            _record_failure("aqr", url, f"read_excel failed: {exc}")
            continue
        date_col = df.columns[0]
        df[date_col] = pd.to_datetime(df[date_col]) + pd.offsets.MonthEnd(0)
        df = df.set_index(date_col)
        latest = df.index.max()
        _record_manifest(
            "aqr",
            dest,
            url,
            fetched_at,
            latest,
            f"sheet={sheet}, header_row={header_row}, column={col}",
        )
        series = df[col]
        series = series[series.index < CUTOFF_2026]
        compute_and_record(
            SeriesSpec("aqr", series_id, label, "vw", "b", side, "already_excess", series),
            rf,
        )

    # Time-Series Momentum: single-sheet, no country columns, headline diversified factor.
    url = AQR_BASE + "Time-Series-Momentum-Factors-Monthly.xlsx"
    dest = AQR_DIR / "Time-Series-Momentum-Factors-Monthly.xlsx"
    ok, fetched_or_err = fetch_url(session, url, dest)
    if not ok:
        _record_failure("aqr", url, f"download failed twice: {fetched_or_err}")
    else:
        fetched_at = fetched_or_err
        try:
            df = pd.read_excel(dest, sheet_name="TSMOM Factors", header=17, engine="openpyxl")
            date_col = df.columns[0]
            df[date_col] = pd.to_datetime(df[date_col]) + pd.offsets.MonthEnd(0)
            df = df.set_index(date_col)
            latest = df.index.max()
            _record_manifest(
                "aqr",
                dest,
                url,
                fetched_at,
                latest,
                "sheet=TSMOM Factors, header_row=17, column=TSMOM (diversified, equal-vol-weighted across asset classes)",
            )
            series = df["TSMOM"]
            series = series[series.index < CUTOFF_2026]
            compute_and_record(
                SeriesSpec(
                    "aqr",
                    "TSMOM_diversified",
                    "Time Series Momentum (diversified factor)",
                    "na",
                    "b",
                    "trend-following (long winners / short losers per asset)",
                    "already_excess",
                    series,
                ),
                rf,
            )
        except Exception as exc:  # noqa: BLE001
            _record_failure("aqr", url, f"read_excel failed: {exc}")

    # Value and Momentum Everywhere: US stock value + momentum long-short factors.
    url = AQR_BASE + "Value-and-Momentum-Everywhere-Factors-Monthly.xlsx"
    dest = AQR_DIR / "Value-and-Momentum-Everywhere-Factors-Monthly.xlsx"
    ok, fetched_or_err = fetch_url(session, url, dest)
    if not ok:
        _record_failure("aqr", url, f"download failed twice: {fetched_or_err}")
        return
    fetched_at = fetched_or_err
    try:
        df = pd.read_excel(dest, sheet_name="VME Factors", header=21, engine="openpyxl")
        date_col = df.columns[0]
        df[date_col] = pd.to_datetime(df[date_col]) + pd.offsets.MonthEnd(0)
        df = df.set_index(date_col)
        latest = df.index.max()
        _record_manifest(
            "aqr",
            dest,
            url,
            fetched_at,
            latest,
            "sheet=VME Factors, header_row=21, columns=VALLS_VME_US90/MOMLS_VME_US90",
        )
        for col, series_id, label, side in [
            (
                "VALLS_VME_US90",
                "VME_VAL_US",
                "Value and Momentum Everywhere: US stock Value",
                "high value (cheap)",
            ),
            (
                "MOMLS_VME_US90",
                "VME_MOM_US",
                "Value and Momentum Everywhere: US stock Momentum",
                "high momentum",
            ),
        ]:
            series = df[col]
            series = series[series.index < CUTOFF_2026]
            compute_and_record(
                SeriesSpec("aqr", series_id, label, "na", "b", side, "already_excess", series),
                rf,
            )
    except Exception as exc:  # noqa: BLE001
        _record_failure("aqr", url, f"read_excel failed: {exc}")


# ---------------------------------------------------------------------------
# 3. JKP Global Factor Data
# ---------------------------------------------------------------------------

JKP_DIR = RAW_DIR / "jkp"
JKP_S3_BASE = "https://jkpfactors-data.s3.amazonaws.com/public"


def load_jkp(session: requests.Session, rf: pd.Series) -> None:
    # official dropdown label map (value -> human label), used only for report readability
    label_map: dict[str, str] = {}
    avail_url = f"{JKP_S3_BASE}/availability.json"
    avail_dest = JKP_DIR / "availability.json"
    ok, fetched_or_err = fetch_url(session, avail_url, avail_dest)
    if ok:
        _record_manifest(
            "jkp",
            avail_dest,
            avail_url,
            fetched_or_err,
            None,
            "dropdown label map only, not a return series",
        )
        try:
            data = json.loads(avail_dest.read_text())
            for group in data.get("dropdown_options", {}).get("themes", []):
                for opt in group.get("options", []):
                    label_map[opt["value"]] = opt["label"]
        except Exception:  # noqa: BLE001
            pass

    specs = [
        ("all_factors", "factors", "b"),
        ("all_themes", "themes", "b"),
    ]
    for theme_value, kind, klass in specs:
        url = f"{JKP_S3_BASE}/%5Busa%5D_%5B{theme_value}%5D_%5Bmonthly%5D_%5Bvw_cap%5D.zip"
        dest = JKP_DIR / f"usa_{theme_value}_monthly_vwcap.zip"
        ok, fetched_or_err = fetch_url(session, url, dest)
        if not ok:
            _record_failure("jkp", url, f"download failed twice: {fetched_or_err}")
            continue
        fetched_at = fetched_or_err
        try:
            with zipfile.ZipFile(dest) as zf:
                inner = zf.namelist()[0]
                df = pd.read_csv(zf.open(inner))
        except Exception as exc:  # noqa: BLE001
            _record_failure("jkp", url, f"unzip/read failed: {exc}")
            continue
        df["date"] = pd.to_datetime(df["date"]) + pd.offsets.MonthEnd(0)
        latest = df["date"].max()
        _record_manifest(
            "jkp",
            dest,
            url,
            fetched_at,
            latest,
            f"weighting=vw_cap (site default, capped value-weighted); zip->{inner}",
        )
        direction_col = "direction" if "direction" in df.columns else None
        for name, grp in df.groupby("name"):
            grp = grp.set_index("date")["ret"]
            grp = grp[grp.index < CUTOFF_2026]
            if direction_col:
                d = df.loc[df["name"] == name, "direction"]
                dval = d.iloc[0] if len(d) else None
                side = f"as coded, direction={int(dval)}" if pd.notna(dval) else "n/a"
            else:
                side = "composite of member factors (already directional)"
            human = label_map.get(name, name)
            compute_and_record(
                SeriesSpec(
                    "jkp",
                    f"{kind}_{name}",
                    f"JKP {('factor' if kind == 'factors' else 'theme')}: {human} ({name})",
                    "vw_cap",
                    klass,
                    side,
                    "already_excess",
                    grp,
                ),
                rf,
            )


# ---------------------------------------------------------------------------
# 4. Open Source Asset Pricing
# ---------------------------------------------------------------------------

OSAP_DIR = RAW_DIR / "osap"
OSAP_WIDE_FILE_ID = "10sOryk_ddjkXagaajTKUk1nwJs2ZLRiI"  # "Monthly long-short returns of 212 predictors following OPs (wide csv)"
OSAP_SIGNALDOC_FILE_ID = "1Sev9s6cPFUGgxp1pFiej0lGzpsMqJCI2"  # "Signal Documentation csv file"


def _gdrive_download_with_cache_fallback(
    session: requests.Session, file_id: str, dest: Path
) -> tuple[bool, str]:
    """Try a fresh Google Drive download; if it fails and a prior successful
    download already sits on disk, reuse that cached copy instead of losing
    the whole series to a transient failure. Google Drive's public-file
    quota for large files has been observed to be flaky across repeated
    fetches of the same file_id within a short window (see the OSAP decile
    zips, which failed outright, and this wide CSV, which succeeded on
    several earlier runs today and then hit "Quota exceeded" on a later
    run of this same script with no code change). The fallback is honest
    about what happened: fetched_at reflects the cached file's own mtime,
    not the current time, and the caller's manifest note says so.
    """
    ok, fetched_or_err = gdrive_download(session, file_id, dest)
    if ok:
        return True, fetched_or_err
    if dest.exists() and dest.stat().st_size > 0:
        cached_at = datetime.fromtimestamp(dest.stat().st_mtime, tz=UTC).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        return (
            True,
            f"CACHED(reused prior successful download from {cached_at}; fresh attempt this run failed: {fetched_or_err})",
        )
    return False, fetched_or_err


def load_osap(session: requests.Session, rf: pd.Series) -> None:
    desc_map: dict[str, str] = {}
    sd_dest = OSAP_DIR / "OSAP_SignalDoc.csv"
    ok, fetched_or_err = _gdrive_download_with_cache_fallback(
        session, OSAP_SIGNALDOC_FILE_ID, sd_dest
    )
    if ok:
        _record_manifest(
            "osap",
            sd_dest,
            f"https://drive.google.com/file/d/{OSAP_SIGNALDOC_FILE_ID}/view",
            fetched_or_err,
            None,
            "signal documentation (acronym -> long description, sign); not a return series",
        )
        try:
            sd = pd.read_csv(sd_dest)
            desc_map = dict(zip(sd["Acronym"], sd["LongDescription"], strict=False))
        except Exception:  # noqa: BLE001
            pass
    else:
        _record_failure("osap", "SignalDoc.csv (gdrive)", fetched_or_err)

    wide_dest = OSAP_DIR / "OSAP_PredictorPortsFull_wide.csv"
    ok, fetched_or_err = _gdrive_download_with_cache_fallback(session, OSAP_WIDE_FILE_ID, wide_dest)
    if not ok:
        _record_failure("osap", "PredictorPortsFull wide csv (gdrive)", fetched_or_err)
        return
    fetched_at = fetched_or_err
    try:
        df = pd.read_csv(wide_dest)
    except Exception as exc:  # noqa: BLE001
        _record_failure("osap", "PredictorPortsFull wide csv (gdrive)", f"read_csv failed: {exc}")
        return
    df["date"] = pd.to_datetime(df["date"]) + pd.offsets.MonthEnd(0)
    df = df.set_index("date")
    latest = df.index.max()
    _record_manifest(
        "osap",
        wide_dest,
        f"https://drive.google.com/file/d/{OSAP_WIDE_FILE_ID}/view",
        fetched_at,
        latest,
        (
            "release 2025.10 (per global folder Release Notes 2025.10.docx); wide long-short predictor panel, "
            "values already in percent (/100 applied); decile/quintile alt-weighting zips "
            "(PredictorAltPorts_DecilesVW.zip etc.) were attempted and hit Google Drive 'Quota exceeded' twice "
            "(failed download, see failed entries below) -- out of scope for this pass, long-short panel retained"
        ),
    )
    df = df / 100.0
    df = df[df.index < CUTOFF_2026]
    for col in df.columns:
        series = df[col]
        label = desc_map.get(col, col)
        compute_and_record(
            SeriesSpec(
                "osap",
                f"OSAP_{col}",
                f"OSAP predictor: {label} ({col})",
                "na",
                "b",
                "per original paper (OSAP sign convention)",
                "already_excess",
                series,
            ),
            rf,
        )

    # Record the attempted-and-failed decile zip as an honest manifest entry (quota exceeded twice).
    _record_failure(
        "osap",
        "https://drive.google.com/uc?export=download&id=1_1WWZqilrt1gleeyAFwjv5aobd0QRbS3 (PredictorAltPorts_DecilesVW.zip)",
        "google drive 'Quota exceeded' on both the virus-scan-confirm hop and a retry with a fresh uuid; "
        "same failure mode on PredictorAltPorts_DecilesEW.zip (different file_id) -- this looks like a "
        "site-wide Drive quota on large (>25MB) files in this release, not a bug in the request. Long-short "
        "wide CSV and SignalDoc.csv are both <1MB and downloaded cleanly with no confirmation step.",
    )


# ---------------------------------------------------------------------------
# 5. Hou-Xue-Zhang q-factor library
# ---------------------------------------------------------------------------

HXZ_DIR = RAW_DIR / "hxz"
HXZ_BASE = "https://global-q.org/uploads/1/2/2/6/122679606/"


def load_hxz(session: requests.Session, rf: pd.Series) -> None:
    url = HXZ_BASE + "q5_factors_monthly_2025.csv"
    dest = HXZ_DIR / "q5_factors_monthly_2025.csv"
    ok, fetched_or_err = fetch_url(session, url, dest)
    if not ok:
        _record_failure("hxz", url, f"download failed twice: {fetched_or_err}")
        return
    fetched_at = fetched_or_err
    try:
        df = pd.read_csv(dest)
    except Exception as exc:  # noqa: BLE001
        _record_failure("hxz", url, f"read_csv failed: {exc}")
        return
    df["date"] = pd.to_datetime(
        df["year"].astype(str) + "-" + df["month"].astype(str) + "-01"
    ) + pd.offsets.MonthEnd(0)
    df = df.set_index("date")
    latest = df.index.max()
    _record_manifest(
        "hxz",
        dest,
        url,
        fetched_at,
        latest,
        "q5 monthly factors, percent -> /100 applied; R_MKT treated as already market-minus-RF per q-factor convention",
    )
    df = df[[c for c in df.columns if c.startswith("R_")]] / 100.0
    df = df[df.index < CUTOFF_2026]
    q5_defs = [
        (
            "R_MKT",
            "HXZ_MKT",
            "q-factor Market (R_MKT, already excess of RF)",
            "c",
            "n/a",
            "already_excess",
        ),
        ("R_ME", "HXZ_ME", "q-factor Size (R_ME)", "b", "small", "already_excess"),
        ("R_IA", "HXZ_IA", "q-factor Investment (R_IA)", "b", "low investment", "already_excess"),
        ("R_ROE", "HXZ_ROE", "q-factor ROE (profitability)", "b", "high ROE", "already_excess"),
        (
            "R_EG",
            "HXZ_EG",
            "q-factor Expected Growth (R_EG)",
            "b",
            "high expected growth",
            "already_excess",
        ),
    ]
    for col, series_id, label, klass, side, mode in q5_defs:
        if col not in df.columns:
            continue
        compute_and_record(
            SeriesSpec("hxz", series_id, label, "na", klass, side, mode, df[col]), rf
        )

    # One representative testing portfolio: R11 momentum deciles (formation months t-12..t-2,
    # 1-month holding = the HXZ analogue of French's Prior(2-12) decile sort). The mom/inv/prof
    # zips each bundle 30-60 related-but-distinct sorts; out of scope to process all of them here.
    zip_url = HXZ_BASE + "mom_monthly_2025.zip"
    zip_dest = HXZ_DIR / "mom_monthly_2025.zip"
    ok, fetched_or_err = fetch_url(session, zip_url, zip_dest)
    if not ok:
        _record_failure("hxz", zip_url, f"download failed twice: {fetched_or_err}")
        return
    fetched_at = fetched_or_err
    member = "mom_monthly_2025/portf_r11_1_monthly_2025.csv"
    try:
        with zipfile.ZipFile(zip_dest) as zf:
            names = zf.namelist()
            match = next((n for n in names if n.endswith("portf_r11_1_monthly_2025.csv")), None)
            if match is None:
                _record_failure(
                    "hxz", zip_url, f"member {member} not found in zip (has {len(names)} members)"
                )
                return
            port = pd.read_csv(zf.open(match))
    except Exception as exc:  # noqa: BLE001
        _record_failure("hxz", zip_url, f"unzip/read failed: {exc}")
        return
    port["date"] = pd.to_datetime(
        port["year"].astype(str) + "-" + port["month"].astype(str) + "-01"
    ) + pd.offsets.MonthEnd(0)
    _record_manifest(
        "hxz",
        zip_dest,
        zip_url,
        fetched_at,
        port["date"].max(),
        (
            f"extracted member {match} only (R11 = prior return formed on months t-12..t-2, 1-month holding, "
            "decile rank 1=low..10=high, value-weighted only); the other ~59 member files in this zip "
            "(and the inv_/prof_/fric_/intan_/vvg_/me_* zips) were not processed -- out of scope for this pass"
        ),
    )
    port = port.set_index("date")
    port["ret_vw"] = port["ret_vw"] / 100.0
    port = port[port.index < CUTOFF_2026]
    ranks = {}
    for rank, grp in port.groupby("rank_R11_1"):
        ranks[int(rank)] = grp["ret_vw"]
    for rank, series in ranks.items():
        side_tag = "Hi" if rank == 10 else ("Lo" if rank == 1 else str(rank))
        compute_and_record(
            SeriesSpec(
                "hxz",
                f"R11_decile{rank:02d}",
                f"HXZ testing portfolio: R11 momentum decile {rank} ({side_tag})",
                "vw",
                "a",
                "n/a",
                "subtract_rf",
                series,
            ),
            rf,
        )
    if 1 in ranks and 10 in ranks:
        common_idx = ranks[10].index.intersection(ranks[1].index)
        spread = ranks[10].reindex(common_idx) - ranks[1].reindex(common_idx)
        compute_and_record(
            SeriesSpec(
                "hxz",
                "R11_spread",
                "HXZ testing portfolio: R11 momentum decile, top minus bottom (long=high, standard momentum convention)",
                "vw",
                "b",
                "high",
                "already_excess",
                spread,
            ),
            rf,
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for d in [FRENCH_DIR, AQR_DIR, JKP_DIR, OSAP_DIR, HXZ_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    session = requests.Session()

    rf_holder: dict[str, pd.Series] = {}
    load_french(session, rf_holder)
    rf = rf_holder.get("rf")
    if rf is None:
        raise RuntimeError(
            "Fama-French RF series failed to load; cannot compute excess returns for any source."
        )

    load_aqr(session, rf)
    load_jkp(session, rf)
    load_osap(session, rf)
    load_hxz(session, rf)

    stats_df = pd.DataFrame(ROWS)
    stats_df = stats_df.sort_values(["source", "series_id", "window"]).reset_index(drop=True)
    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    stats_df.to_csv(STATS_PATH, index=False)

    manifest_out = {
        "generated_at": _utcnow_iso(),
        "no_2026_rule": "every return series is truncated to date < 2026-01-01 before any statistic is computed; latest_date_in_file is file metadata and may reach into 2026",
        "windows": {
            "W_common": [W_COMMON[0].strftime("%Y-%m-%d"), W_COMMON[1].strftime("%Y-%m-%d")],
            "W_select": [W_SELECT[0].strftime("%Y-%m-%d"), W_SELECT[1].strftime("%Y-%m-%d")],
        },
        "files": [vars(m) for m in MANIFEST],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest_out, indent=2, ensure_ascii=False))

    n_ok = sum(1 for m in MANIFEST if m.status == "ok")
    n_failed = sum(1 for m in MANIFEST if m.status == "failed")
    print(f"wrote {STATS_PATH} ({len(stats_df)} rows)")
    print(f"wrote {MANIFEST_PATH} ({n_ok} files ok, {n_failed} failed)")
    for m in MANIFEST:
        if m.status == "failed":
            print(f"  FAILED [{m.source}] {m.url}: {m.parse_notes}")


if __name__ == "__main__":
    main()
