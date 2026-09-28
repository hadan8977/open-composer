"""Modal app: train a Jiang-Kelly-Xiu (2023) chart-image CNN (I20/R5) and
report an out-of-sample kill-test verdict.

Exploratory kill test only -- not a strategy promotion. See
``reports/research/harvest/directions.jsonl`` row ``dir:chart_image_cnn_jkx_replication``
and ``reports/research/iterations/cnn_chart_i20r5_2026-09-28/report.md``.

Attribution: the OHLC/MA/volume image-rendering layout (I20: 64x60px, price
panel 51 rows / volume panel 13 rows, 3px/day, OHLC bar + open/close ticks +
20-day MA line) and the CNN architecture (3 conv blocks, 5x3 kernel, 64/128/256
channels, BatchNorm, LeakyReLU, MaxPool(2,1), dropout 0.5, Xavier init) follow
Jiang, Kelly & Xiu (2023, J. Finance) Appendix A and the independent MIT
replication at github.com/George-hardworking/reimaging-price-trends-replication-and-extension
(``src/data/images.py``, ``src/models/cnn.py``). This file is an independent,
simplified re-implementation for this repo's own SIP daily-bar data -- not a
copy of that repo's code -- with two deliberate deviations from that repo's
fidelity to the paper, documented inline and in the report: (1) the MA line
is drawn as a vectorized "step" fill between consecutive days' rows rather
than a Bresenham diagonal, and (2) prices are used directly (not chain-adjusted
via a separate total-return series) because this repo's SIP daily bars are
already split-adjusted (verified against known splits; see report.md).

Self-contained: this Modal app builds its own image (Python 3.12, torch,
polars, pyarrow, numpy) and does not use ``scripts/modal_app.py`` /
``scripts/modal_run.py``'s generic uv-project-image template, because torch is
not (and should not become) a project dependency of the CLI/dashboard image.

OOS rendering fix (2026-09-28): the first full run trained fine but then spent
80 minutes in OOS inference and hit its 120-min timeout with the trained
weights never saved -- it looped over ~1,700 OOS dates and, per date, called
the image renderer on ~4,000 *different-symbol* rows (~6.8M near-single-row
render calls; training was fast because those rows were grouped by symbol).
Fix, in five functions instead of one:
  * ``train`` renders training images, trains, and immediately saves
    ``state_dict``/pixel mean+std/history to the ``oc-data`` volume under
    ``models/cnn_i20r5/<mode>/`` (``volume.commit()``) before returning.
  * ``oos`` loads that checkpoint, builds the *entire* OOS row table in one
    vectorized filter+join (every trading day from OOS_START on; each day's
    rebalance offset is its position in the full calendar mod 5 -- exactly
    ``_rebalance_grid``'s semantics -- so every day is predicted once), sorts
    by symbol, and splits into ~200k-row chunks at symbol boundaries (a
    symbol's whole OOS history -- at most ~1,700 rows -- always fits in one
    chunk, so each symbol still gets exactly one batched render call, just
    now covering its full history instead of one row at a time). Each chunk
    is rendered by a pool of ``N_OOS_WORKERS`` forked worker processes (the
    per-symbol numpy arrays are inherited via fork/copy-on-write, never
    pickled), GPU-predicted in ``GPU_BATCH_SIZE`` batches, and immediately
    appended as a parquet part + ``volume.commit()`` -- so a timeout never
    loses finished work, and a rerun skips any chunk already on the volume.
  * ``bench`` (CPU-only, cheap) measures render throughput on a small slice
    with the same code path and projects the full OOS wall time, to be run
    once before the real ``oos`` launch.
  * ``full`` simply calls ``train`` then ``oos`` in the same container (the
    checkpoint is committed to the volume before OOS starts either way).
Model spec, universe, labels, periods, portfolio rules and the kill verdict
(everything above ``_train_and_save`` in this file) are unchanged by this fix.

Usage (spend guard first, every launch; timeout= must equal the checked
minutes):
    python3 scripts/modal_budget.py check --job cnn-i20r5-smoke --cpu 2 \\
        --memory-gib 6 --timeout-min 15
    modal run scripts/modal_cnn_chart.py --mode smoke

    python3 scripts/modal_budget.py check --job cnn-i20r5-bench --cpu 8 \\
        --memory-gib 8 --timeout-min 15
    modal run scripts/modal_cnn_chart.py --mode bench

    python3 scripts/modal_budget.py check --job cnn-i20r5-train --cpu 8 \\
        --memory-gib 32 --timeout-min 60 --gpu T4
    modal run --detach scripts/modal_cnn_chart.py --mode train

    python3 scripts/modal_budget.py check --job cnn-i20r5-oos --cpu 8 \\
        --memory-gib 32 --timeout-min 60 --gpu T4
    modal run --detach scripts/modal_cnn_chart.py --mode oos
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import modal

# ---------------------------------------------------------------------------
# App / image / volume
# ---------------------------------------------------------------------------

APP_NAME = "oc-cnn-i20r5"
VOLUME_MOUNT = "/mnt/oc-data"
THREADS = 16  # 8 Modal cores == 16 vCPU

_THREAD_ENV = {
    "POLARS_MAX_THREADS": str(THREADS),
    "OMP_NUM_THREADS": str(THREADS),
    "MKL_NUM_THREADS": str(THREADS),
    "TORCH_NUM_THREADS": str(THREADS),
    "POLARS_SKIP_CPU_CHECK": "1",
}

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("numpy==2.1.3", "polars==1.17.1", "pyarrow==18.1.0")
    .pip_install(
        "torch==2.5.1",
        index_url="https://download.pytorch.org/whl/cu121",
    )
)

volume = modal.Volume.from_name("oc-data", create_if_missing=True)

app = modal.App(APP_NAME)

# ---------------------------------------------------------------------------
# Spec constants (fixed before any result was seen; do not tune on 2020+ data)
# ---------------------------------------------------------------------------

MIN_CLOSE = 3.0
MIN_DOLLAR_ADV = 1_000_000.0
ADV_LOOKBACK_DAYS = 21
WINDOW_DAYS = 20
HORIZON_DAYS = 5
PRICE_ROWS, VOLUME_ROWS = 51, 13  # I20 layout: height 64 = 51 + 13, per JKX
IMG_HEIGHT = PRICE_ROWS + VOLUME_ROWS
IMG_WIDTH = WINDOW_DAYS * 3
MIN_HIST_ROWS = WINDOW_DAYS + WINDOW_DAYS - 1  # 39: 20-day MA valid on every window day

TRAIN_START = "2016-03-01"
TRAIN_END = "2019-12-31"
OOS_START = "2020-01-01"

REPORT_PERIODS = {
    "2020": ("2020-01-01", "2020-12-31"),
    "2021_2023": ("2021-01-01", "2023-12-31"),
    "2024_plus": ("2024-01-08", "2099-01-01"),
}
KILL_PERIOD = "2021_2023"

COST_BPS_PER_SIDE = (10.0, 20.0)
TRAIN_VAL_SPLIT_SEED = 0
TORCH_SEED = 0
BATCH_SIZE = 128
ADAM_LR = 1e-5
MAX_EPOCHS = 60
EARLY_STOP_PATIENCE = 5  # epochs without val-loss improvement
TRAIN_TIME_BUDGET_SEC = 50 * 60  # measured from pipeline start; train() has its
# own 60-min function timeout now (OOS is a separate function/container), so
# this leaves a 10-min buffer for checkpoint save + teardown.
NW_LAGS = 4

# OOS rendering/inference (2026-09-28 rewrite -- see module docstring "OOS
# rendering fix" below; does not touch any constant above this point).
N_OOS_WORKERS = 15  # CPU worker processes for parallel image rendering
OOS_CHUNK_ROWS = 200_000  # checkpoint granularity: rows per parquet part
GPU_BATCH_SIZE = 8192  # inference batch size once images are rendered

DATA_GLOBS = [
    f"{VOLUME_MOUNT}/data/sip/daily/*/shard-*.parquet",
    f"{VOLUME_MOUNT}/data/sip-delisted/daily/*.parquet",
]


# ---------------------------------------------------------------------------
# Data loading + universe + labels (polars, vectorized)
# ---------------------------------------------------------------------------


def _load_panel(symbol_prefix_subset: list[str] | None, date_lo: str, date_hi: str):
    import polars as pl

    lf = pl.scan_parquet(DATA_GLOBS, glob=True).select(
        [
            pl.col("symbol"),
            pl.col("timestamp").cast(pl.Date).alias("date"),
            pl.col("open").cast(pl.Float64),
            pl.col("high").cast(pl.Float64),
            pl.col("low").cast(pl.Float64),
            pl.col("close").cast(pl.Float64),
            pl.col("volume").cast(pl.Float64),
        ]
    )
    lf = lf.filter(
        ~pl.col("symbol").str.contains(r"[./]")
        & (pl.col("date") >= pl.lit(date_lo).str.to_date())
        & (pl.col("date") <= pl.lit(date_hi).str.to_date())
    )
    if symbol_prefix_subset is not None:
        lf = lf.filter(pl.col("symbol").is_in(symbol_prefix_subset))
    df = lf.collect()
    # Sanity clip: a single-day bad high/low print (observed once, on the
    # NVDA 2024-06-10 10:1 split day: high=195.61 vs open/close ~120, while
    # open/close/volume are already split-adjusted and continuous across the
    # split -- see report.md "Data adjustment"). Clamp intraday extremes to
    # within +/-15% of that day's own open/close so one bad tick cannot
    # dominate a whole 20-day image's min-max price scaling.
    df = df.with_columns(
        [
            pl.min_horizontal(
                pl.col("high"), pl.max_horizontal(pl.col("open"), pl.col("close")) * 1.15
            ).alias("high"),
            pl.max_horizontal(
                pl.col("low"), pl.min_horizontal(pl.col("open"), pl.col("close")) * 0.85
            ).alias("low"),
        ]
    )
    df = df.sort(["symbol", "date"])
    dv = (pl.col("close") * pl.col("volume")).alias("dollar_volume")
    df = df.with_columns(dv)
    df = df.with_columns(
        [
            pl.col("dollar_volume")
            .rolling_median(window_size=ADV_LOOKBACK_DAYS, min_periods=ADV_LOOKBACK_DAYS)
            .over("symbol")
            .alias("dv_med21"),
            pl.col("close")
            .rolling_mean(window_size=WINDOW_DAYS, min_periods=WINDOW_DAYS)
            .over("symbol")
            .alias("sma20"),
            pl.int_range(0, pl.len()).over("symbol").alias("row_idx"),
            pl.col("open").shift(-1).over("symbol").alias("entry_open_next"),
            pl.col("close").shift(-HORIZON_DAYS).over("symbol").alias("exit_close_5"),
            pl.col("close").shift(-HORIZON_DAYS).over("symbol").alias("fwd_close5"),
        ]
    )
    df = df.with_columns(
        [
            ((pl.col("close") >= MIN_CLOSE) & (pl.col("dv_med21") >= MIN_DOLLAR_ADV)).alias(
                "eligible"
            ),
            (pl.col("exit_close_5") / pl.col("entry_open_next") - 1.0).alias("port_ret_5"),
            (pl.col("fwd_close5") / pl.col("close") - 1.0).alias("cc_ret_5"),
        ]
    )
    df = df.with_columns(
        pl.when(pl.col("fwd_close5").is_null())
        .then(None)
        .when(pl.col("cc_ret_5") > 0)
        .then(1)
        .otherwise(0)
        .cast(pl.Int8)
        .alias("label")
    )
    return df


def _global_calendar(df) -> list:
    import polars as pl

    return sorted(df.select(pl.col("date").unique()).to_series().to_list())


def _rebalance_grid(calendar: list, offset: int) -> set:
    return set(calendar[offset::5])


# ---------------------------------------------------------------------------
# Image rendering (fully vectorized over a (B, 20) sample batch)
# ---------------------------------------------------------------------------


def render_batch(open_b, high_b, low_b, close_b, vol_b, sma_b):
    """Render a batch of I20 images. Inputs are float64 arrays shape (B, 20)
    (NaN for missing history days); returns uint8 array (B, 64, 60).

    Vectorized re-implementation of the JKX image layout: OHLC bar (open tick
    / high-low bar / close tick, 3px/day) in the top 51 rows, volume bars in
    the bottom 13 rows, 20-day MA drawn as a vertical step-fill between each
    pair of consecutive days (see module docstring for why this differs from
    a true Bresenham diagonal).
    """
    import numpy as np

    b = open_b.shape[0]
    img = np.zeros((b, IMG_HEIGHT, IMG_WIDTH), dtype=np.uint8)

    finite = np.isfinite
    stacked = np.concatenate(
        [a[finite(a)] for a in (open_b, high_b, low_b, close_b) if finite(a).any()]
    )
    if stacked.size == 0:
        return img

    # Per-sample min/max (each row of the batch scaled independently).
    def per_row_minmax(*arrs):
        mins = []
        maxs = []
        for a in arrs:
            m = np.where(finite(a), a, np.nan)
            mins.append(np.nanmin(m, axis=1))
            maxs.append(np.nanmax(m, axis=1))
        return np.nanmin(np.stack(mins), axis=0), np.nanmax(np.stack(maxs), axis=0)

    pmin, pmax = per_row_minmax(open_b, high_b, low_b, close_b)
    prange = pmax - pmin
    prange = np.where((~finite(prange)) | (prange <= 0), 1e-6, prange)

    def to_row(vals, clip=True):
        norm = (vals - pmin[:, None]) / prange[:, None]
        if clip:
            norm = np.clip(np.nan_to_num(norm, nan=0.0), 0.0, 1.0)
        return np.round((1.0 - norm) * (PRICE_ROWS - 1))

    days = np.arange(WINDOW_DAYS)
    col_open = days * 3
    col_bar = days * 3 + 1
    col_close = days * 3 + 2

    hi_r = to_row(high_b)
    lo_r = to_row(low_b)
    top = np.minimum(hi_r, lo_r)
    bot = np.maximum(hi_r, lo_r)
    bar_valid = finite(high_b) & finite(low_b)

    row_idx = np.arange(PRICE_ROWS)[None, :, None]  # (1, rows, 1)
    top3 = top[:, None, :]
    bot3 = bot[:, None, :]
    bar_mask = bar_valid[:, None, :] & (row_idx >= top3) & (row_idx <= bot3)
    # scatter into full image at the bar columns
    for d in range(WINDOW_DAYS):
        img[:, :PRICE_ROWS, col_bar[d]] |= (bar_mask[:, :, d] * 255).astype(np.uint8)

    op_r = to_row(open_b)
    cl_r = to_row(close_b)
    ok_o = bar_valid & finite(open_b)
    ok_c = bar_valid & finite(close_b)
    rows_o = np.clip(op_r, 0, PRICE_ROWS - 1).astype(np.intp)
    rows_c = np.clip(cl_r, 0, PRICE_ROWS - 1).astype(np.intp)
    bi = np.arange(b)
    for d in range(WINDOW_DAYS):
        sel = ok_o[:, d]
        img[bi[sel], rows_o[sel, d], col_open[d]] = 255
        sel = ok_c[:, d]
        img[bi[sel], rows_c[sel, d], col_close[d]] = 255

    # Volume panel (bottom VOLUME_ROWS rows).
    vol_ok = finite(vol_b) & (vol_b > 0)
    vmax = np.where(vol_ok, vol_b, 0.0).max(axis=1)
    vmax = np.where(vmax <= 0, 1.0, vmax)
    vol_norm = np.clip(np.where(vol_ok, vol_b / vmax[:, None], 0.0), 0.0, 1.0)
    vol_h = np.where(vol_ok, np.maximum(1, np.round(vol_norm * (VOLUME_ROWS - 1))), 0).astype(
        np.intp
    )
    vol_row_idx = np.arange(VOLUME_ROWS)[None, :, None] + PRICE_ROWS
    start_row = IMG_HEIGHT - 1
    end_row = np.maximum(PRICE_ROWS, start_row - vol_h + 1)  # (b, 20)
    end_row3 = end_row[:, None, :]
    vmask = vol_ok[:, None, :] & (vol_row_idx >= end_row3) & (vol_row_idx <= start_row)
    for d in range(WINDOW_DAYS):
        img[:, PRICE_ROWS:IMG_HEIGHT, col_bar[d]] |= (vmask[:, :, d] * 255).astype(np.uint8)

    # 20-day MA: point per day + vertical step-fill between consecutive days.
    ma_ok = finite(sma_b)
    ma_r = to_row(sma_b, clip=False)
    ma_r_c = np.clip(ma_r, 0, PRICE_ROWS - 1).astype(np.intp)
    in_panel = ma_ok & (ma_r >= 0) & (ma_r < PRICE_ROWS)
    for d in range(WINDOW_DAYS):
        sel = in_panel[:, d]
        img[bi[sel], ma_r_c[sel, d], col_open[d]] = 255
        img[bi[sel], ma_r_c[sel, d], col_bar[d]] = 255
        img[bi[sel], ma_r_c[sel, d], col_close[d]] = 255
    for d in range(1, WINDOW_DAYS):
        both = in_panel[:, d - 1] & in_panel[:, d]
        if not both.any():
            continue
        r0 = ma_r_c[both, d - 1]
        r1 = ma_r_c[both, d]
        lo = np.minimum(r0, r1)
        hi = np.maximum(r0, r1)
        sub_bi = bi[both]
        for row_idx2 in range(PRICE_ROWS):
            m = (row_idx2 >= lo) & (row_idx2 <= hi)
            if m.any():
                img[sub_bi[m], row_idx2, col_bar[d]] = 255

    return img


def build_windows_for_symbol(dates, opens, highs, lows, closes, vols, smas, idxs):
    """Slice the trailing 20-day window ending at each row index in `idxs`
    (0-indexed within this symbol's own sorted rows)."""
    import numpy as np
    from numpy.lib.stride_tricks import sliding_window_view

    def windows(arr):
        sw = sliding_window_view(arr, WINDOW_DAYS)  # shape (n-19, 20)
        starts = np.asarray(idxs) - (WINDOW_DAYS - 1)
        return sw[starts]

    return (
        windows(opens),
        windows(highs),
        windows(lows),
        windows(closes),
        windows(vols),
        windows(smas),
    )


# ---------------------------------------------------------------------------
# CNN (PriceTrendCNN, I20: 3 blocks, 5x3 kernel, 64/128/256 channels)
# ---------------------------------------------------------------------------


def build_model():
    import torch
    import torch.nn as nn

    class Block(nn.Module):
        def __init__(self, cin, cout, stride, dilation):
            super().__init__()
            pad = (2 * dilation[0], 1 * dilation[1])
            self.conv = nn.Conv2d(
                cin, cout, kernel_size=(5, 3), stride=stride, dilation=dilation, padding=pad
            )
            self.bn = nn.BatchNorm2d(cout)
            self.act = nn.LeakyReLU(0.01)
            self.pool = nn.MaxPool2d(kernel_size=(2, 1), stride=(2, 1), ceil_mode=True)

        def forward(self, x):
            return self.pool(self.act(self.bn(self.conv(x))))

    class PriceTrendCNN(nn.Module):
        def __init__(self):
            super().__init__()
            self.b1 = Block(1, 64, stride=(3, 1), dilation=(2, 1))
            self.b2 = Block(64, 128, stride=(1, 1), dilation=(1, 1))
            self.b3 = Block(128, 256, stride=(1, 1), dilation=(1, 1))
            with torch.no_grad():
                dummy = torch.zeros(1, 1, IMG_HEIGHT, IMG_WIDTH)
                flat = self.b3(self.b2(self.b1(dummy))).numel()
            self.flat_size = flat
            self.dropout = nn.Dropout(0.5)
            self.fc = nn.Linear(flat, 2)
            for m in self.modules():
                if isinstance(m, (nn.Conv2d, nn.Linear)):
                    nn.init.xavier_uniform_(m.weight)
                    if m.bias is not None:
                        nn.init.zeros_(m.bias)

        def forward(self, x):
            x = self.b1(x)
            x = self.b2(x)
            x = self.b3(x)
            x = x.flatten(1)
            x = self.dropout(x)
            return self.fc(x)

    return PriceTrendCNN()


# ---------------------------------------------------------------------------
# Stats helpers (Newey-West, rank IC) -- pure numpy, no scipy/statsmodels.
# ---------------------------------------------------------------------------


def newey_west_tstat(x, lags: int = NW_LAGS) -> tuple[float, float]:
    import numpy as np

    x = np.asarray(x, dtype=np.float64)
    x = x[np.isfinite(x)]
    n = x.size
    if n < 3:
        return float("nan"), float("nan")
    mean = x.mean()
    u = x - mean
    gamma0 = (u @ u) / n
    var = gamma0
    for lag in range(1, min(lags, n - 1) + 1):
        cov = (u[lag:] @ u[:-lag]) / n
        weight = 1.0 - lag / (lags + 1)
        var += 2.0 * weight * cov
    se = (var / n) ** 0.5
    if se <= 0 or not np.isfinite(se):
        return mean, float("nan")
    return mean, mean / se


def rank_ic(pred, actual) -> float:
    import numpy as np

    pred = np.asarray(pred, dtype=np.float64)
    actual = np.asarray(actual, dtype=np.float64)
    mask = np.isfinite(pred) & np.isfinite(actual)
    pred, actual = pred[mask], actual[mask]
    if pred.size < 5:
        return float("nan")
    rp = pred.argsort().argsort().astype(np.float64)
    ra = actual.argsort().argsort().astype(np.float64)
    rp -= rp.mean()
    ra -= ra.mean()
    denom = (rp @ rp) ** 0.5 * (ra @ ra) ** 0.5
    if denom == 0:
        return float("nan")
    return float((rp @ ra) / denom)


def max_drawdown(returns) -> float:
    import numpy as np

    equity = np.cumprod(1.0 + np.asarray(returns, dtype=np.float64))
    peak = np.maximum.accumulate(equity)
    dd = equity / peak - 1.0
    return float(dd.min()) if dd.size else float("nan")


def annualize_return(returns, trading_days_span: float) -> float:
    import numpy as np

    total = float(np.prod(1.0 + np.asarray(returns, dtype=np.float64)) - 1.0)
    if trading_days_span <= 0:
        return float("nan")
    return float((1.0 + total) ** (252.0 / trading_days_span) - 1.0)


def sharpe_ratio(returns, periods_per_year: float) -> float:
    import numpy as np

    r = np.asarray(returns, dtype=np.float64)
    r = r[np.isfinite(r)]
    if r.size < 2 or r.std(ddof=1) == 0:
        return float("nan")
    return float(r.mean() / r.std(ddof=1) * (periods_per_year**0.5))


# ---------------------------------------------------------------------------
# Portfolio construction + metrics (runs inside the container; only the
# small aggregated tables below are returned to the local box -- the raw
# per-symbol-date prediction table (millions of rows for the full run) never
# leaves the container, since this box has 3.9 GB RAM).
# ---------------------------------------------------------------------------


def _decile_tercile(pred_df):
    """Add per-(date,offset) decile of p_up and tercile of dv_med21."""
    import polars as pl

    return pred_df.with_columns(
        [
            (
                (pl.col("p_up").rank(method="ordinal").over(["date", "offset"]) - 1)
                / pl.len().over(["date", "offset"])
                * 10
            )
            .floor()
            .clip(0, 9)
            .cast(pl.Int8)
            .alias("decile"),
            (
                (pl.col("dv_med21").rank(method="ordinal").over(["date", "offset"]) - 1)
                / pl.len().over(["date", "offset"])
                * 3
            )
            .floor()
            .clip(0, 2)
            .cast(pl.Int8)
            .alias("tercile"),
        ]
    )


def _period_mask(dates, lo: str, hi: str):
    import datetime as _dt

    lo_d = _dt.date.fromisoformat(lo)
    hi_d = _dt.date.fromisoformat(hi)
    return [(lo_d <= d <= hi_d) for d in dates]


def _per_date_frame(pred_df, offset: int):
    """One row per rebalance date (for a given offset): EW decile10/1/universe
    returns, cross-sectional rank IC, and decile-10 turnover vs the prior
    date (within this same offset's grid)."""
    import polars as pl

    sub = pred_df.filter(pl.col("offset") == offset)
    groups = sub.partition_by("date", maintain_order=True)
    rows = []
    prev_d10: set = set()
    for g in groups:
        d = g["date"][0]
        p_up = g["p_up"].to_numpy()
        cc = g["cc_ret_5"].to_numpy()
        port = g["port_ret_5"].to_numpy()
        decile = g["decile"].to_numpy()
        tercile = g["tercile"].to_numpy()
        symbols = g["symbol"].to_list()
        d10_mask = decile == 9
        d1_mask = decile == 0
        d10_syms = {s for s, m in zip(symbols, d10_mask, strict=True) if m}
        turnover = (
            float("nan") if not prev_d10 else len(d10_syms - prev_d10) / max(len(d10_syms), 1)
        )
        prev_d10 = d10_syms
        tercile_rets = {}
        for t in (0, 1, 2):
            m = d10_mask & (tercile == t)
            tercile_rets[t] = float(port[m].mean()) if m.any() else float("nan")
        rows.append(
            {
                "date": d,
                "ew_d10": float(port[d10_mask].mean()) if d10_mask.any() else float("nan"),
                "ew_d1": float(port[d1_mask].mean()) if d1_mask.any() else float("nan"),
                "ew_universe": float(port.mean()) if port.size else float("nan"),
                "n_universe": int(port.size),
                "rank_ic": rank_ic(p_up, cc),
                "turnover_d10": turnover,
                "d10_tercile_low": tercile_rets[0],
                "d10_tercile_mid": tercile_rets[1],
                "d10_tercile_high": tercile_rets[2],
            }
        )
    if not rows:
        return pl.DataFrame(
            schema={
                "date": pl.Date,
                "ew_d10": pl.Float64,
                "ew_d1": pl.Float64,
                "ew_universe": pl.Float64,
                "n_universe": pl.Int64,
                "rank_ic": pl.Float64,
                "turnover_d10": pl.Float64,
                "d10_tercile_low": pl.Float64,
                "d10_tercile_mid": pl.Float64,
                "d10_tercile_high": pl.Float64,
            }
        )
    return pl.DataFrame(rows)


def _apply_cost(gross_returns, turnovers, cost_bps: float):
    import numpy as np

    g = np.asarray(gross_returns, dtype=np.float64)
    t = np.asarray(turnovers, dtype=np.float64)
    t = np.where(np.isfinite(t), t, 0.0)  # first period of the series: no prior turnover
    drag = t * 2.0 * (cost_bps / 10000.0)
    return g - drag


def _period_table(per_date, spy_df, period_lo: str, period_hi: str) -> dict:
    import numpy as np

    dates = per_date["date"].to_list()
    mask = _period_mask(dates, period_lo, period_hi)
    if not any(mask):
        return {"n_periods": 0}
    idx = [i for i, m in enumerate(mask) if m]
    span_days = (dates[idx[-1]] - dates[idx[0]]).days if len(idx) > 1 else 5
    trading_days_span = max(span_days * 252.0 / 365.25, 5.0)

    ew_d10 = per_date["ew_d10"].to_numpy()[idx]
    ew_d1 = per_date["ew_d1"].to_numpy()[idx]
    ew_universe = per_date["ew_universe"].to_numpy()[idx]
    turnover_d10 = per_date["turnover_d10"].to_numpy()[idx]
    rank_ics = per_date["rank_ic"].to_numpy()[idx]
    tlow = per_date["d10_tercile_low"].to_numpy()[idx]
    tmid = per_date["d10_tercile_mid"].to_numpy()[idx]
    thigh = per_date["d10_tercile_high"].to_numpy()[idx]

    period_dates = [dates[i] for i in idx]
    spy_map = dict(zip(spy_df["date"].to_list(), spy_df["port_ret_5"].to_list(), strict=True))
    spy_rets = np.array([spy_map.get(d, float("nan")) for d in period_dates])

    periods_per_year = 252.0 / 5.0
    d10_net10 = _apply_cost(ew_d10, turnover_d10, 10.0)
    d10_net20 = _apply_cost(ew_d10, turnover_d10, 20.0)
    excess_mean, excess_t = newey_west_tstat(ew_d10 - ew_universe)
    ic_mean, ic_t = newey_west_tstat(rank_ics[np.isfinite(rank_ics)])

    def block(returns):
        return {
            "annualized_return": annualize_return(returns[np.isfinite(returns)], trading_days_span),
            "sharpe": sharpe_ratio(returns, periods_per_year),
            "max_drawdown": max_drawdown(returns[np.isfinite(returns)]),
        }

    return {
        "n_periods": len(idx),
        "date_range": [str(period_dates[0]), str(period_dates[-1])],
        "long_only_top_decile_gross": block(ew_d10),
        "long_only_top_decile_net_10bp": block(d10_net10),
        "long_only_top_decile_net_20bp": block(d10_net20),
        "long_short_d10_minus_d1_gross": block(ew_d10 - ew_d1),
        "universe_equal_weight": block(ew_universe),
        "spy_buy_and_hold": block(spy_rets),
        "mean_turnover_oneway_d10": float(np.nanmean(turnover_d10)),
        "decile10_minus_universe_excess_weekly_mean": excess_mean,
        "decile10_minus_universe_excess_newey_west_t": excess_t,
        "rank_ic_mean": ic_mean,
        "rank_ic_newey_west_t": ic_t,
        "top_decile_by_dollar_volume_tercile_net_10bp": {
            "low_liquidity": block(_apply_cost(tlow, turnover_d10, 10.0)),
            "mid_liquidity": block(_apply_cost(tmid, turnover_d10, 10.0)),
            "high_liquidity": block(_apply_cost(thigh, turnover_d10, 10.0)),
        },
    }


def _compute_results(pred_df, spy_df, offsets_run: list[int], log) -> dict:
    import numpy as np

    pred_df = _decile_tercile(pred_df)
    per_date_by_offset = {o: _per_date_frame(pred_df, o) for o in offsets_run}
    primary = per_date_by_offset[0]

    tables = {
        name: _period_table(primary, spy_df, lo, hi) for name, (lo, hi) in REPORT_PERIODS.items()
    }

    offset_sharpes = {}
    for o in offsets_run:
        pd_o = per_date_by_offset[o]
        if pd_o.height == 0:
            continue
        ew_d10 = pd_o["ew_d10"].to_numpy()
        turnover = pd_o["turnover_d10"].to_numpy()
        net10 = _apply_cost(ew_d10, turnover, 10.0)
        offset_sharpes[o] = sharpe_ratio(net10, 252.0 / 5.0)
    median_sharpe = (
        float(np.nanmedian(list(offset_sharpes.values()))) if offset_sharpes else float("nan")
    )

    kill_tbl = tables.get(KILL_PERIOD, {})
    excess_t = kill_tbl.get("decile10_minus_universe_excess_newey_west_t", float("nan"))
    d10_sharpe_10bp = kill_tbl.get("long_only_top_decile_net_10bp", {}).get("sharpe", float("nan"))
    universe_sharpe = kill_tbl.get("universe_equal_weight", {}).get("sharpe", float("nan"))
    pass_t = np.isfinite(excess_t) and excess_t >= 2.0
    pass_sharpe = (
        np.isfinite(d10_sharpe_10bp)
        and np.isfinite(universe_sharpe)
        and (d10_sharpe_10bp > universe_sharpe)
    )
    verdict = "PASS" if (pass_t and pass_sharpe) else "FAIL"
    log(
        f"kill verdict={verdict} period={KILL_PERIOD} excess_t={excess_t} "
        f"d10_sharpe_10bp={d10_sharpe_10bp} universe_sharpe={universe_sharpe}"
    )

    return {
        "period_tables": tables,
        "rebalance_offset_median_sharpe_net_10bp": {
            "per_offset": {str(k): v for k, v in offset_sharpes.items()},
            "median": median_sharpe,
        },
        "kill_verdict": {
            "period": KILL_PERIOD,
            "rule": (
                "decile10_minus_universe_excess_t>=2 AND "
                "long_only_top_decile_net_10bp.sharpe>universe_equal_weight.sharpe"
            ),
            "decile10_minus_universe_excess_t": excess_t,
            "long_only_top_decile_net_10bp_sharpe": d10_sharpe_10bp,
            "universe_equal_weight_sharpe": universe_sharpe,
            "verdict": verdict,
        },
    }


# ---------------------------------------------------------------------------
# Shared panel/calendar/symbol-array loading (train and oos each call this
# independently in their own container -- see module docstring).
# ---------------------------------------------------------------------------


def _dataset_params(subset: bool) -> dict:
    if subset:
        symbols = [
            "AAPL",
            "MSFT",
            "AMZN",
            "GOOGL",
            "META",
            "NVDA",
            "TSLA",
            "SPY",
            "JPM",
            "V",
            "UNH",
            "HD",
            "PG",
            "MA",
            "DIS",
            "BAC",
            "XOM",
            "CVX",
            "KO",
            "PEP",
            "ADBE",
            "CRM",
            "NFLX",
            "INTC",
            "AMD",
            "CSCO",
            "PFE",
            "MRK",
            "WMT",
            "T",
            "VZ",
            "ABT",
            "TMO",
            "COST",
            "AVGO",
            "TXN",
            "QCOM",
            "ORCL",
            "IBM",
            "GE",
        ]
        date_lo, date_hi = "2018-06-01", "2020-06-30"
        train_start, train_end, oos_start = "2018-09-01", "2019-12-31", "2020-01-01"
    else:
        symbols = None
        date_lo, date_hi = "2016-01-01", "2026-12-31"
        train_start, train_end, oos_start = TRAIN_START, TRAIN_END, OOS_START
    return {
        "symbols": symbols,
        "date_lo": date_lo,
        "date_hi": date_hi,
        "train_start": train_start,
        "train_end": train_end,
        "oos_start": oos_start,
    }


def _load_panel_and_calendar(subset: bool, log):
    params = _dataset_params(subset)
    log(f"loading panel subset={subset} range=({params['date_lo']},{params['date_hi']})")
    df = _load_panel(params["symbols"], params["date_lo"], params["date_hi"])
    log(f"panel rows={df.height} symbols={df.select('symbol').n_unique()}")
    calendar = _global_calendar(df)
    log(f"calendar days={len(calendar)} first={calendar[0]} last={calendar[-1]}")
    return df, calendar, params


def _build_sym_arrays(df) -> dict:
    sym_arrays: dict[str, dict] = {}
    for sym, part in (
        df.select(["symbol", "date", "open", "high", "low", "close", "volume", "sma20"])
        .partition_by("symbol", as_dict=True)
        .items()
    ):
        s = sym[0] if isinstance(sym, tuple) else sym
        part = part.sort("date")
        sym_arrays[s] = {
            "open": part["open"].to_numpy(),
            "high": part["high"].to_numpy(),
            "low": part["low"].to_numpy(),
            "close": part["close"].to_numpy(),
            "volume": part["volume"].to_numpy(),
            "sma20": part["sma20"].to_numpy(),
        }
    return sym_arrays


def _render_rows_single_process(rows_df, sym_arrays: dict):
    """Original (training-side, unchanged) renderer: groups a row batch by
    symbol so each symbol's rows in this batch get one render_batch call.
    Training was never the bottleneck (590k rows rendered fine in the first
    run), so this path is untouched."""
    import numpy as np

    n = rows_df.height
    images = np.zeros((n, IMG_HEIGHT, IMG_WIDTH), dtype=np.uint8)
    syms = rows_df["symbol"].to_list()
    idxs = rows_df["row_idx"].to_list()
    by_symbol: dict[str, list[int]] = {}
    for pos, s in enumerate(syms):
        by_symbol.setdefault(s, []).append(pos)
    for s, positions in by_symbol.items():
        arrs = sym_arrays[s]
        sym_idxs = [idxs[p] for p in positions]
        ob, hb, lb, cb, vb, mb = build_windows_for_symbol(
            None,
            arrs["open"],
            arrs["high"],
            arrs["low"],
            arrs["close"],
            arrs["volume"],
            arrs["sma20"],
            sym_idxs,
        )
        batch_imgs = render_batch(ob, hb, lb, cb, vb, mb)
        for j, p in enumerate(positions):
            images[p] = batch_imgs[j]
    return images


# ---------------------------------------------------------------------------
# Checkpoint persistence (volume: models/cnn_i20r5/<mode>/)
# ---------------------------------------------------------------------------


def _checkpoint_dir(mode: str) -> Path:
    return Path(VOLUME_MOUNT) / "models" / "cnn_i20r5" / mode


def _oos_preds_dir(mode: str) -> Path:
    return Path(VOLUME_MOUNT) / "reports" / "cnn_i20r5" / "oos_preds" / mode


def _save_checkpoint(
    mode: str, model, pixel_mean: float, pixel_std: float, meta: dict, log
) -> dict:
    import torch

    d = _checkpoint_dir(mode)
    d.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), d / "checkpoint.pt")
    full_meta = {
        "pixel_mean": pixel_mean,
        "pixel_std": pixel_std,
        **meta,
        "spec_constants": {
            "IMG_HEIGHT": IMG_HEIGHT,
            "IMG_WIDTH": IMG_WIDTH,
            "WINDOW_DAYS": WINDOW_DAYS,
            "HORIZON_DAYS": HORIZON_DAYS,
            "TRAIN_START": TRAIN_START,
            "TRAIN_END": TRAIN_END,
            "OOS_START": OOS_START,
        },
    }
    (d / "train_meta.json").write_text(json.dumps(full_meta, indent=2, default=str))
    volume.commit()
    log(f"checkpoint saved and committed: {d / 'checkpoint.pt'}")
    return full_meta


def _load_checkpoint(mode: str, device, log):
    import torch

    d = _checkpoint_dir(mode)
    meta = json.loads((d / "train_meta.json").read_text())
    model = build_model().to(device)
    state = torch.load(d / "checkpoint.pt", map_location=device)
    model.load_state_dict(state)
    model.eval()
    log(f"checkpoint loaded from {d}")
    return model, meta


# ---------------------------------------------------------------------------
# Train stage
# ---------------------------------------------------------------------------


def _train_and_save(*, subset: bool, mode: str, log) -> dict:
    import numpy as np
    import polars as pl
    import torch

    torch.set_num_threads(THREADS)
    t0 = time.time()

    df, calendar, params = _load_panel_and_calendar(subset, log)
    hist_ok = pl.col("row_idx") >= MIN_HIST_ROWS

    def grid_dates(offset: int, lo: str, hi: str) -> set:
        import datetime as _dt

        lo_d = _dt.date.fromisoformat(lo)
        hi_d = _dt.date.fromisoformat(hi)
        return {d for d in _rebalance_grid(calendar, offset) if lo_d <= d <= hi_d}

    train_grid = grid_dates(0, params["train_start"], params["train_end"])
    base_cols = ["symbol", "date", "row_idx", "label", "port_ret_5", "cc_ret_5", "dv_med21"]

    def sample_rows(dates: set):
        return df.filter(
            pl.col("date").is_in(list(dates))
            & pl.col("eligible")
            & hist_ok
            & pl.col("label").is_not_null()
        ).select(base_cols)

    train_rows_all = sample_rows(train_grid)
    log(f"train-pool sample rows={train_rows_all.height}")

    rng = np.random.default_rng(TRAIN_VAL_SPLIT_SEED)
    n_pool = train_rows_all.height
    perm = rng.permutation(n_pool)
    n_train = int(n_pool * 0.7)
    train_idx_mask = np.zeros(n_pool, dtype=bool)
    train_idx_mask[perm[:n_train]] = True

    sym_arrays = _build_sym_arrays(df)

    log("rendering training images")
    train_pool_images = _render_rows_single_process(train_rows_all, sym_arrays)
    train_pool_labels = train_rows_all["label"].to_numpy().astype(np.int64)
    log(f"training images shape={train_pool_images.shape}")

    train_images = train_pool_images[train_idx_mask]
    train_labels = train_pool_labels[train_idx_mask]
    val_images = train_pool_images[~train_idx_mask]
    val_labels = train_pool_labels[~train_idx_mask]
    log(f"train n={len(train_images)} val n={len(val_images)}")

    pixel_mean = float(train_images.mean())
    pixel_std = float(train_images.std()) or 1.0

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch.manual_seed(TORCH_SEED)
    model = build_model().to(device)
    log(f"model flat_size={model.flat_size} device={device}")
    criterion = torch.nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=ADAM_LR)
    use_amp = device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    def to_tensor(imgs):
        return torch.from_numpy((imgs.astype(np.float32) - pixel_mean) / pixel_std).unsqueeze(1)

    train_x = to_tensor(train_images)
    train_y = torch.from_numpy(train_labels)
    val_x = to_tensor(val_images)
    val_y = torch.from_numpy(val_labels)

    def run_epoch(x, y, train_flag: bool) -> float:
        n = x.shape[0]
        idx = torch.randperm(n) if train_flag else torch.arange(n)
        total = 0.0
        nb = 0
        model.train(train_flag)
        for start in range(0, n, BATCH_SIZE):
            b_idx = idx[start : start + BATCH_SIZE]
            xb = x[b_idx].to(device)
            yb = y[b_idx].to(device)
            if train_flag:
                optimizer.zero_grad(set_to_none=True)
            with (
                torch.set_grad_enabled(train_flag),
                torch.autocast(device_type=device.type, dtype=torch.float16, enabled=use_amp),
            ):
                logits = model(xb)
                loss = criterion(logits.float(), yb)
            if train_flag:
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
            total += float(loss.item())
            nb += 1
        return total / max(nb, 1)

    max_epochs = 5 if subset else MAX_EPOCHS
    patience = 2 if subset else EARLY_STOP_PATIENCE
    best_val = float("inf")
    stale = 0
    best_state = None
    history = []
    stopped_for_time = False
    for epoch in range(1, max_epochs + 1):
        tr_loss = run_epoch(train_x, train_y, True)
        va_loss = run_epoch(val_x, val_y, False)
        history.append({"epoch": epoch, "train_loss": tr_loss, "val_loss": va_loss})
        log(f"epoch={epoch} train_loss={tr_loss:.6f} val_loss={va_loss:.6f}")
        if va_loss < best_val:
            best_val = va_loss
            stale = 0
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
        else:
            stale += 1
            if stale >= patience:
                log(f"early stop at epoch={epoch}")
                break
        if time.time() - t0 > TRAIN_TIME_BUDGET_SEC:
            stopped_for_time = True
            log(f"training time budget reached at epoch={epoch}")
            break
    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()

    meta = {
        "subset": subset,
        "mode": mode,
        "train_wall_time_sec": time.time() - t0,
        "device": str(device),
        "train_n": int(len(train_images)),
        "val_n": int(len(val_images)),
        "training_history": history,
        "stopped_for_time": stopped_for_time,
        "mixed_precision": use_amp,
        "best_val_loss": best_val,
        "calendar_span": [str(calendar[0]), str(calendar[-1])],
    }
    full_meta = _save_checkpoint(mode, model, pixel_mean, pixel_std, meta, log)
    log(f"train stage done in {time.time() - t0:.1f}s")
    return full_meta


# ---------------------------------------------------------------------------
# OOS stage: parallel chunked rendering + checkpointed predictions
# ---------------------------------------------------------------------------

# Set by the parent right before the worker pool is created (fork start
# method => copy-on-write inheritance, never pickled). Read-only in workers.
_SYM_ARRAYS_FOR_FORK: dict | None = None


def _oos_render_worker(task):
    """Runs in a forked worker process. `task` is a list of
    (symbol, positions_local_to_chunk, row_idxs) triplets assigned to this
    worker; each symbol's rows in this chunk are rendered in one
    build_windows_for_symbol + render_batch call, exactly as the training
    path does, just now covering that symbol's *whole* OOS history in this
    chunk instead of one row at a time."""
    import numpy as np

    positions_out: list[int] = []
    images_parts = []
    for sym, positions, idxs in task:
        arrs = _SYM_ARRAYS_FOR_FORK[sym]
        ob, hb, lb, cb, vb, mb = build_windows_for_symbol(
            None,
            arrs["open"],
            arrs["high"],
            arrs["low"],
            arrs["close"],
            arrs["volume"],
            arrs["sma20"],
            idxs,
        )
        images_parts.append(render_batch(ob, hb, lb, cb, vb, mb))
        positions_out.extend(positions)
    if images_parts:
        images = np.concatenate(images_parts, axis=0)
    else:
        images = np.zeros((0, IMG_HEIGHT, IMG_WIDTH), dtype=np.uint8)
    return positions_out, images


def _partition_into_buckets(chunk_rows, n_workers: int) -> list:
    """Greedy bin-pack whole symbols (by row count) across n_workers buckets
    -- a symbol is never split across buckets, so it still gets exactly one
    render_batch call, just handled by one worker process."""
    groups = chunk_rows.partition_by("symbol", as_dict=True)
    items = []
    for sym, part in groups.items():
        s = sym[0] if isinstance(sym, tuple) else sym
        items.append((s, part["pos"].to_list(), part["row_idx"].to_list()))
    items.sort(key=lambda t: -len(t[1]))
    buckets: list[list] = [[] for _ in range(n_workers)]
    totals = [0] * n_workers
    for sym, positions, idxs in items:
        j = min(range(n_workers), key=lambda k: totals[k])
        buckets[j].append((sym, positions, idxs))
        totals[j] += len(positions)
    return [b for b in buckets if b]


def _render_chunk_parallel(chunk_rows, executor, n_workers: int):
    import numpy as np

    chunk_rows = chunk_rows.with_row_index("pos")
    tasks = _partition_into_buckets(chunk_rows, n_workers)
    chunk_images = np.zeros((chunk_rows.height, IMG_HEIGHT, IMG_WIDTH), dtype=np.uint8)
    futures = [executor.submit(_oos_render_worker, t) for t in tasks]
    for fut in futures:
        positions_out, imgs = fut.result()
        if positions_out:
            chunk_images[np.array(positions_out, dtype=np.intp)] = imgs
    return chunk_images


def _predict_probs(model, device, use_amp: bool, pixel_mean: float, pixel_std: float, images):
    import numpy as np
    import torch

    n = images.shape[0]
    probs = np.zeros(n, dtype=np.float64)
    for start in range(0, n, GPU_BATCH_SIZE):
        batch = images[start : start + GPU_BATCH_SIZE]
        x = torch.from_numpy((batch.astype(np.float32) - pixel_mean) / pixel_std).unsqueeze(1)
        x = x.to(device)
        with (
            torch.no_grad(),
            torch.autocast(device_type=device.type, dtype=torch.float16, enabled=use_amp),
        ):
            p = torch.softmax(model(x).float(), dim=-1)[:, 1].cpu().numpy()
        probs[start : start + len(p)] = p
    return probs


def _build_oos_row_table(df, calendar: list, oos_start: str, subset: bool):
    """One vectorized filter + join over the whole panel (not one filter per
    date, and not one loop per offset): every eligible row from oos_start to
    the last calendar date, with its rebalance offset = the position of its
    date in the FULL calendar mod 5 (exactly `_rebalance_grid`'s semantics,
    so the 5 offsets still partition every OOS trading day and each day is
    predicted exactly once), sorted by symbol so chunking never splits a
    symbol's rows across chunks."""
    import datetime as _dt

    import polars as pl

    hist_ok = pl.col("row_idx") >= MIN_HIST_ROWS
    oos_start_d = _dt.date.fromisoformat(oos_start)
    offset_df = pl.DataFrame(
        {"date": calendar, "offset": [i % 5 for i in range(len(calendar))]}
    ).with_columns(pl.col("date").cast(pl.Date), pl.col("offset").cast(pl.Int64))
    rows = (
        df.filter(
            (pl.col("date") >= pl.lit(oos_start_d))
            & pl.col("eligible")
            & hist_ok
            & pl.col("port_ret_5").is_not_null()
        )
        .select(["symbol", "date", "row_idx", "port_ret_5", "cc_ret_5", "dv_med21"])
        .join(offset_df, on="date", how="left")
    )
    if subset:
        # Mirrors the pre-fix subset smoke test, which only ever predicted
        # offset 0 -- keeps the smoke test's expectations comparable.
        rows = rows.filter(pl.col("offset") == 0)
    return rows.sort(["symbol", "date"])


def _build_oos_chunks(oos_rows) -> list:
    """Split the symbol-sorted OOS row table into ~OOS_CHUNK_ROWS-row chunks
    at symbol boundaries. A symbol's total OOS row count is at most ~1,700
    (one row per OOS trading day), far below the chunk size, so no symbol is
    ever split across two chunks."""
    import polars as pl

    groups = oos_rows.partition_by("symbol", as_dict=True, maintain_order=True)
    chunks = []
    current: list = []
    current_n = 0
    for _sym, part in groups.items():
        current.append(part)
        current_n += part.height
        if current_n >= OOS_CHUNK_ROWS:
            chunks.append(pl.concat(current) if len(current) > 1 else current[0])
            current = []
            current_n = 0
    if current:
        chunks.append(pl.concat(current) if len(current) > 1 else current[0])
    return chunks


def _oos_part_path(mode: str, chunk_id: int) -> Path:
    return _oos_preds_dir(mode) / f"part-{chunk_id:04d}.parquet"


def _existing_oos_chunk_ids(mode: str) -> set:
    d = _oos_preds_dir(mode)
    if not d.is_dir():
        return set()
    out = set()
    for p in sorted(d.glob("part-*.parquet")):
        try:
            out.add(int(p.stem.split("-")[1]))
        except (IndexError, ValueError):
            continue
    return out


def _run_oos(*, subset: bool, mode: str, log) -> str:
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor

    import polars as pl
    import torch

    global _SYM_ARRAYS_FOR_FORK

    torch.set_num_threads(THREADS)
    t_start = time.time()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, train_meta = _load_checkpoint(mode, device, log)
    pixel_mean = train_meta["pixel_mean"]
    pixel_std = train_meta["pixel_std"]
    use_amp = device.type == "cuda"

    df, calendar, params = _load_panel_and_calendar(subset, log)
    sym_arrays = _build_sym_arrays(df)
    _SYM_ARRAYS_FOR_FORK = sym_arrays

    oos_rows = _build_oos_row_table(df, calendar, params["oos_start"], subset)
    total_rows = oos_rows.height
    log(f"oos row table rows={total_rows}")
    chunks = _build_oos_chunks(oos_rows)
    n_chunks = len(chunks)
    log(f"oos chunks={n_chunks} chunk_target_rows={OOS_CHUNK_ROWS}")

    existing = _existing_oos_chunk_ids(mode)
    log(f"resuming: {len(existing)}/{n_chunks} chunks already on volume")

    n_workers = min(2, N_OOS_WORKERS) if subset else N_OOS_WORKERS
    fork_ctx = multiprocessing.get_context("fork")
    executor = ProcessPoolExecutor(max_workers=n_workers, mp_context=fork_ctx)

    rows_done = sum(chunks[i].height for i in range(n_chunks) if i in existing)
    render_t0 = time.time()
    try:
        for chunk_id, chunk_rows in enumerate(chunks):
            if chunk_id in existing:
                continue
            c0 = time.time()
            images = _render_chunk_parallel(chunk_rows, executor, n_workers)
            render_elapsed = time.time() - c0
            probs = _predict_probs(model, device, use_amp, pixel_mean, pixel_std, images)
            predict_elapsed = time.time() - c0 - render_elapsed
            result_df = chunk_rows.select(
                ["date", "symbol", "offset", "port_ret_5", "cc_ret_5", "dv_med21"]
            ).with_columns(pl.Series("p_up", probs, dtype=pl.Float64))
            part_path = _oos_part_path(mode, chunk_id)
            part_path.parent.mkdir(parents=True, exist_ok=True)
            result_df.write_parquet(part_path)
            volume.commit()
            rows_done += chunk_rows.height
            elapsed = time.time() - render_t0
            rate = rows_done / elapsed if elapsed > 0 else float("nan")
            remaining = total_rows - rows_done
            eta_min = (remaining / rate / 60.0) if rate > 0 else float("nan")
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            log(
                f"[{now}] chunk={chunk_id}/{n_chunks - 1} rows={chunk_rows.height} "
                f"render_sec={render_elapsed:.1f} predict_sec={predict_elapsed:.1f} "
                f"cum_rows={rows_done}/{total_rows} rows_per_sec={rate:.1f} "
                f"eta_min={eta_min:.1f} wall_min={(time.time() - t_start) / 60.0:.1f}"
            )
    finally:
        executor.shutdown(wait=True)

    log("all chunks rendered; reading back predictions from volume")
    part_glob = str(_oos_preds_dir(mode) / "part-*.parquet")
    pred_df = pl.read_parquet(part_glob)
    log(f"pred_df rows={pred_df.height}")

    spy_df = df.filter(pl.col("symbol") == "SPY").select(["date", "port_ret_5"])
    offsets_run = sorted(pred_df["offset"].unique().to_list())
    log("computing portfolio metrics")
    portfolio = _compute_results(pred_df, spy_df, offsets_run, log)

    meta = {
        **train_meta,
        "oos_wall_time_sec": time.time() - t_start,
        "oos_device": str(device),
        "n_oos_predictions": int(pred_df.height),
        "offsets_run": offsets_run,
        "n_oos_chunks": n_chunks,
        "n_oos_workers": n_workers,
        "oos_chunk_target_rows": OOS_CHUNK_ROWS,
        "gpu_batch_size": GPU_BATCH_SIZE,
    }
    result = {"meta": meta, "portfolio": portfolio}
    log(f"oos stage done in {(time.time() - t_start) / 60.0:.1f} min")
    return _to_json(result, mode)


# ---------------------------------------------------------------------------
# Pre-launch render-throughput benchmark (CPU only, cheap; run before the
# real GPU `oos` launch to confirm the projected full OOS time fits comfortably).
# ---------------------------------------------------------------------------


def _bench_render_throughput(log) -> str:
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor

    global _SYM_ARRAYS_FOR_FORK

    t0 = time.time()
    # Uses the toy (subset) panel purely to get real symbols/rows through the
    # exact production code path (fork pool, bucket packing, render_batch) --
    # per-image render cost is fixed by the 64x60 image size, not by which
    # symbols or how much history is loaded, so this measurement is valid to
    # scale up to the real run's row count.
    df, calendar, params = _load_panel_and_calendar(True, log)
    sym_arrays = _build_sym_arrays(df)
    _SYM_ARRAYS_FOR_FORK = sym_arrays
    # subset=False here so ALL 5 offsets (not just offset 0) feed the bench,
    # for a more representative row/symbol mix.
    oos_rows = _build_oos_row_table(df, calendar, params["oos_start"], subset=False)
    chunks = _build_oos_chunks(oos_rows)
    log(f"bench: rows={oos_rows.height} chunks={len(chunks)}")

    n_workers = N_OOS_WORKERS
    fork_ctx = multiprocessing.get_context("fork")
    executor = ProcessPoolExecutor(max_workers=n_workers, mp_context=fork_ctx)
    rendered = 0
    render_t0 = time.time()
    try:
        for chunk_rows in chunks:
            _render_chunk_parallel(chunk_rows, executor, n_workers)
            rendered += chunk_rows.height
    finally:
        executor.shutdown(wait=True)
    elapsed = time.time() - render_t0
    rate = rendered / elapsed if elapsed > 0 else float("nan")
    # Real full-scale OOS row count, from the prior full run's own log
    # (panel rows=19,422,550; calendar days=2,698; ~1,700 OOS trading days x
    # ~4,000 eligible rows/day -- confirmed directly by `oos`'s own
    # `_build_oos_row_table` log line on the real launch).
    full_scale_rows_estimate = 6_800_000
    projected_min = (full_scale_rows_estimate / rate / 60.0) if rate > 0 else float("nan")
    result = {
        "bench_rows_rendered": rendered,
        "bench_elapsed_sec": elapsed,
        "bench_rows_per_sec": rate,
        "n_workers": n_workers,
        "full_scale_rows_estimate": full_scale_rows_estimate,
        "projected_full_oos_minutes": projected_min,
        "fits_45min_budget": bool(rate > 0 and projected_min < 45.0),
        "total_bench_wall_sec": time.time() - t0,
    }
    log(f"bench result: {json.dumps(result)}")
    return _to_json(result, "bench")


# ---------------------------------------------------------------------------
# Serialization (unchanged): JSON in the container, copy kept on the volume.
# ---------------------------------------------------------------------------


def _to_json(result: dict, mode: str) -> str:
    """Serialize inside the container (numpy -> plain Python) and keep a copy
    on the volume, so the local side needs no numpy and a late local failure
    cannot lose a finished run."""

    def _plain(obj):
        if hasattr(obj, "item") and callable(obj.item):
            try:
                return obj.item()
            except (ValueError, TypeError):
                pass
        if hasattr(obj, "tolist"):
            return obj.tolist()
        return str(obj)

    text = json.dumps(result, indent=2, default=_plain)
    dest = Path(VOLUME_MOUNT) / "reports" / "cnn_i20r5" / f"{mode}_result.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text)
    volume.commit()
    return text


# ---------------------------------------------------------------------------
# Modal functions
# ---------------------------------------------------------------------------


@app.function(
    image=image,
    cpu=2,
    memory=int(6 * 1024),
    timeout=int(15 * 60),
    volumes={VOLUME_MOUNT: volume},
    env=_THREAD_ENV,
)
def smoke() -> str:
    def log(msg):
        print(f"[smoke] {msg}", flush=True)

    _train_and_save(subset=True, mode="smoke", log=log)
    return _run_oos(subset=True, mode="smoke", log=log)


@app.function(
    image=image,
    cpu=8,
    memory=int(8 * 1024),
    timeout=int(15 * 60),
    volumes={VOLUME_MOUNT: volume},
    env=_THREAD_ENV,
)
def bench() -> str:
    def log(msg):
        print(f"[bench] {msg}", flush=True)

    return _bench_render_throughput(log)


@app.function(
    image=image,
    cpu=8,
    memory=int(32 * 1024),
    timeout=int(60 * 60),
    gpu="T4",
    volumes={VOLUME_MOUNT: volume},
    env=_THREAD_ENV,
)
def train() -> str:
    def log(msg):
        print(f"[train] {msg}", flush=True)

    meta = _train_and_save(subset=False, mode="full", log=log)
    return json.dumps(meta, indent=2, default=str)


@app.function(
    image=image,
    cpu=8,
    memory=int(32 * 1024),
    timeout=int(60 * 60),
    gpu="T4",
    volumes={VOLUME_MOUNT: volume},
    env=_THREAD_ENV,
)
def oos() -> str:
    def log(msg):
        print(f"[oos] {msg}", flush=True)

    return _run_oos(subset=False, mode="full", log=log)


@app.function(
    image=image,
    cpu=8,
    memory=int(32 * 1024),
    timeout=int(120 * 60),
    gpu="T4",
    volumes={VOLUME_MOUNT: volume},
    env=_THREAD_ENV,
)
def full() -> str:
    def log(msg):
        print(f"[full] {msg}", flush=True)

    _train_and_save(subset=False, mode="full", log=log)
    return _run_oos(subset=False, mode="full", log=log)


@app.local_entrypoint()
def main(mode: str = "smoke", out: str = "reports/research/control/scratch/cnn_i20r5") -> None:
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    fns = {"smoke": smoke, "bench": bench, "train": train, "oos": oos, "full": full}
    if mode not in fns:
        raise SystemExit(f"unknown mode: {mode}")
    t0 = time.time()
    result = json.loads(fns[mode].remote())
    wall = time.time() - t0
    if isinstance(result, dict):
        result["_local_wall_time_sec"] = wall
    (out_dir / f"{mode}_result.json").write_text(json.dumps(result, indent=2, default=str))
    print(f"wrote {out_dir / f'{mode}_result.json'} wall={wall:.1f}s")
