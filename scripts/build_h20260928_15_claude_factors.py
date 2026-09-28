"""T-20260928-15: build the 8 Round-1 (+ up to 4 Round-2) Claude-authored
formulaic factors from existing PIT feature stores, write them to
``data/features/h20260928_15_claude_factors/``.

Card: ``reports/research/iterations/h20260928_15_claude_factor_batch/{direction-
review,candidate-manifest,hypotheses}``. Each factor's economic hypothesis,
cited source, exact formula, inputs, expected sign and preregistered
confidence are recorded in ``candidate-manifest.json``; this module is that
manifest's implementation, unchanged after preregistration (Round 1) or
after the frozen Round-2 revision.

Point-in-time rule
-------------------
Every input column used here (``daily_broad``, ``osap_price_broad``,
``sec_fundamentals_daily``, ``insider_broad``, ``short_interest``,
``short_volume_broad``) is already densely indexed by ``(symbol, trade_date)``
with ``trade_date`` as the store's own visibility date -- the same convention
every existing card in ``reports/research/signal-cards/`` already relies on
(e.g. ``comp_c4_mom_roe`` reads ``sec_fundamentals_daily:roe`` directly with
no extra lag). No row here uses a value that is not already visible as of its
own ``trade_date``. ``earnings_events`` (2024-01-03 onward only) is
dependency_skipped for this round: querying it showed zero coverage of the
2016-06-01..2023-12-29 SELECT window, so a factor built from it could never be
selected by the SELECT-ICIR rule on a fair basis; ``alpha158_broad`` is
dependency_skipped too (build never finished past 2016 ``_scratch`` batches,
no consolidated parquet exists), which affects the zoo side, not this module.

Each ``fNN_*`` function below takes a DuckDB connection with the needed source
tables already registered (or globbed directly from parquet) and returns one
``symbol, trade_date, value`` DataFrame; the SAME function runs unchanged over
the toy panel in ``tests/test_h20260928_15_claude_factors.py`` and over the
full history here, so the code under test is exactly the code that ships.
``candidate-manifest.json``'s ``code_sha256`` per candidate is
``hashlib.sha256(inspect.getsource(fn).encode()).hexdigest()``.

Usage
-----
    scripts/run_capped.sh --mem 1.8G -- uv run python \\
        scripts/build_h20260928_15_claude_factors.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FEATURES = ROOT / "data" / "features"
OUT_DIR = FEATURES / "h20260928_15_claude_factors"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DAILY_BROAD = str(FEATURES / "daily_broad" / "*.parquet")
OSAP_PRICE_BROAD = str(FEATURES / "osap_price_broad" / "*.parquet")
SEC_FUNDAMENTALS = str(FEATURES / "sec_fundamentals_daily" / "*.parquet")
INSIDER_BROAD = str(FEATURES / "insider_broad" / "*.parquet")
SHORT_INTEREST = str(FEATURES / "short_interest" / "*.parquet")
SHORT_VOLUME_BROAD = str(FEATURES / "short_volume_broad" / "*.parquet")


def _connect(memory_limit: str = "1200MB") -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{memory_limit}'")
    con.execute("SET threads=2")
    return con


# --------------------------------------------------------------- round 1: F01-F08


def f01_insider_short_confluence(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Insider net buying confirmed by short covering (falling days-to-cover).

    Source: Cohen/Malloy/Pomorski (2012, JF) on informed opportunistic
    insiders; Christophe/Ferri/Hsieh (2010, JFE) on informed short sellers.
    Two independently-informed trader groups converging is a stronger signal
    than either alone. Sign +1, confidence 0.50.
    """
    return con.execute(
        """
        WITH i AS (
            SELECT symbol, trade_date, net_buy_usd_60d
            FROM insider WHERE net_buy_usd_60d IS NOT NULL
        ), s AS (
            SELECT symbol, trade_date, dtc_change_vs_prior
            FROM short_interest WHERE dtc_change_vs_prior IS NOT NULL
        ), j AS (
            SELECT i.symbol, i.trade_date, i.net_buy_usd_60d, s.dtc_change_vs_prior
            FROM i JOIN s USING (symbol, trade_date)
        )
        SELECT symbol, trade_date,
            0.5 * PERCENT_RANK() OVER (PARTITION BY trade_date ORDER BY net_buy_usd_60d)
            + 0.5 * PERCENT_RANK() OVER (PARTITION BY trade_date ORDER BY -dtc_change_vs_prior)
            AS value
        FROM j
        """
    ).df()


def f02_opportunistic_insider_signal(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Opportunistic-minus-routine insider buy count.

    Source: Cohen/Malloy/Pomorski (2012, JF): opportunistic insider trades
    carry all the predictive power; routine trades carry none. Isolates that
    distinction, which the project's existing insider_cluster_buy card
    (simple buyer-count>=2 event rule) does not. Sign +1, confidence 0.60.
    """
    return con.execute(
        """
        WITH i AS (
            SELECT symbol, trade_date, opportunistic_buy_60d, routine_buy_60d
            FROM insider
            WHERE opportunistic_buy_60d IS NOT NULL AND routine_buy_60d IS NOT NULL
        )
        SELECT symbol, trade_date,
            PERCENT_RANK() OVER (PARTITION BY trade_date ORDER BY opportunistic_buy_60d)
            - PERCENT_RANK() OVER (PARTITION BY trade_date ORDER BY routine_buy_60d)
            AS value
        FROM i
        """
    ).df()


def f03_trading_activity_surge(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Recent trade-count surge relative to its own baseline.

    Source: Gervais/Kaniel/Mingelgrin (2001, JF), the high-volume return
    premium; secondary support Chordia/Subrahmanyam/Anshuman (2001, JFE) on
    trading-activity dynamics. A genuinely new construction (trade COUNT
    ratio, not $ volume level which is already a control, and not the
    refuted overnight/intraday return decomposition). Sign +1, confidence
    0.50.
    """
    return con.execute(
        """
        SELECT symbol, trade_date,
            trade_count_5d_mean / NULLIF(trade_count_21d_mean, 0) AS value
        FROM daily
        WHERE trade_count_5d_mean IS NOT NULL AND trade_count_21d_mean IS NOT NULL
            AND trade_count_21d_mean > 0
        """
    ).df()


def f04_sue_short_confirmation(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Positive earnings surprise not opposed by short-volume pressure.

    Source: Diether/Lee/Werner (2009, RFS): informed short sellers trade
    against overpricing. High SUE with low/falling relative short pressure
    is a stronger drift signal than SUE alone. Differs from the refuted T-14
    mechanism (SUE re-dated to the 8-K acceptance timestamp): no redating
    here, SUE stays at its existing sec_fundamentals_daily visibility date;
    the new element is the short-volume confirmation gate. Sign +1,
    confidence 0.50.
    """
    return con.execute(
        """
        WITH f AS (
            SELECT symbol, trade_date, sue_eps FROM fundamentals WHERE sue_eps IS NOT NULL
        ), sv AS (
            SELECT symbol, trade_date, short_volume_ratio_zscore_21
            FROM short_volume WHERE short_volume_ratio_zscore_21 IS NOT NULL
        ), j AS (
            SELECT f.symbol, f.trade_date, f.sue_eps, sv.short_volume_ratio_zscore_21
            FROM f JOIN sv USING (symbol, trade_date)
        )
        SELECT symbol, trade_date,
            PERCENT_RANK() OVER (PARTITION BY trade_date ORDER BY sue_eps)
            - PERCENT_RANK() OVER (PARTITION BY trade_date ORDER BY short_volume_ratio_zscore_21)
            AS value
        FROM j
        """
    ).df()


def f05_quality_liquidity_trend(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Gross profitability confirmed by improving intraday liquidity.

    Source: Novy-Marx (2013) gross profitability (already a locally-tested
    standalone factor, ``gross_profitability`` card) combined with a falling
    5d/21d intraday-Amihud ratio (improving liquidity), per the investor-
    recognition/liquidity-discovery channel (Merton 1987; Amihud 2002).
    Exploratory interaction (confidence 0.40): each ingredient is separately
    well-grounded but their combination is not a literature result found
    this pass. Sign +1.
    """
    return con.execute(
        """
        WITH f AS (
            SELECT symbol, trade_date, gross_profitability
            FROM fundamentals WHERE gross_profitability IS NOT NULL
        ), d AS (
            SELECT symbol, trade_date,
                amihud_intraday_5d_mean / NULLIF(amihud_intraday_21d_mean, 0)
                    AS illiquidity_ratio
            FROM daily
            WHERE amihud_intraday_5d_mean IS NOT NULL AND amihud_intraday_21d_mean IS NOT NULL
                AND amihud_intraday_21d_mean > 0
        ), j AS (
            SELECT f.symbol, f.trade_date, f.gross_profitability, d.illiquidity_ratio
            FROM f JOIN d USING (symbol, trade_date)
        )
        SELECT symbol, trade_date,
            0.5 * PERCENT_RANK() OVER (PARTITION BY trade_date ORDER BY gross_profitability)
            + 0.5 * PERCENT_RANK() OVER (PARTITION BY trade_date ORDER BY -illiquidity_ratio)
            AS value
        FROM j
        """
    ).df()


def f06_momentum_short_confirmation(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """12-1 momentum confirmed by low relative short-volume pressure.

    Source: Diether/Lee/Werner (2009, RFS); Christophe/Ferri/Hsieh (2010,
    JFE): momentum winners with few informed bears opposing the trend have
    more durable momentum. Sign +1, confidence 0.50.
    """
    return con.execute(
        """
        WITH m AS (
            SELECT symbol, trade_date, momentum_252_21 FROM daily
            WHERE momentum_252_21 IS NOT NULL
        ), sv AS (
            SELECT symbol, trade_date, short_volume_ratio_zscore_21
            FROM short_volume WHERE short_volume_ratio_zscore_21 IS NOT NULL
        ), j AS (
            SELECT m.symbol, m.trade_date, m.momentum_252_21, sv.short_volume_ratio_zscore_21
            FROM m JOIN sv USING (symbol, trade_date)
        )
        SELECT symbol, trade_date,
            PERCENT_RANK() OVER (PARTITION BY trade_date ORDER BY momentum_252_21)
            - PERCENT_RANK() OVER (PARTITION BY trade_date ORDER BY short_volume_ratio_zscore_21)
            AS value
        FROM j
        """
    ).df()


def f07_accruals_cashflow_confirmation(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Low accruals confirmed by a high cash-conversion ratio.

    Source: Sloan (1996), already a locally-tested standalone factor
    (``accruals`` card); adds operating_cash_flow / abs(net_income) as a
    cash-conversion confirmation (Richardson et al.'s accrual-reliability
    elaboration in spirit, not literally reproduced). net_income near zero
    is clipped to |net_income| >= 1% of total_assets before dividing, to
    avoid a handful of extreme outliers dominating the rank -- a design
    choice fixed here, before any IC is computed, not tuned after results.
    Sign +1, confidence 0.55.
    """
    return con.execute(
        """
        WITH f AS (
            SELECT symbol, trade_date, accruals, operating_cash_flow, net_income, total_assets
            FROM fundamentals
            WHERE accruals IS NOT NULL AND operating_cash_flow IS NOT NULL
                AND net_income IS NOT NULL AND total_assets IS NOT NULL AND total_assets > 0
        ), c AS (
            SELECT symbol, trade_date, accruals,
                operating_cash_flow
                    / GREATEST(ABS(net_income), 0.01 * total_assets) AS cash_conversion
            FROM f
        )
        SELECT symbol, trade_date,
            0.5 * PERCENT_RANK() OVER (PARTITION BY trade_date ORDER BY -accruals)
            + 0.5 * PERCENT_RANK() OVER (PARTITION BY trade_date ORDER BY cash_conversion)
            AS value
        FROM c
        """
    ).df()


def f08_earnings_recency_gated_insider_buying(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Insider net buying gated to shortly after a fundamentals report.

    Source: Ke/Huddart/Petroni (2003, JAE): insiders trade on private
    knowledge of near-term earnings trajectory -- freshest right after they
    have seen the full report. Disclosed as a one-sided extrapolation: the
    paper's own tested direction is pre-decline SELLING, not post-report
    BUYING (see this task's source card
    ``ke_huddart_petroni_2003_insiders_future_earnings``). Sign +1,
    confidence 0.50.
    """
    return con.execute(
        """
        WITH i AS (
            SELECT symbol, trade_date, net_buy_usd_60d FROM insider
            WHERE net_buy_usd_60d IS NOT NULL
        ), f AS (
            SELECT symbol, trade_date, days_since_report FROM fundamentals
            WHERE days_since_report IS NOT NULL AND days_since_report <= 10
        )
        SELECT i.symbol, i.trade_date, i.net_buy_usd_60d AS value
        FROM i JOIN f USING (symbol, trade_date)
        """
    ).df()


ROUND1 = {
    "F01_insider_short_confluence": f01_insider_short_confluence,
    "F02_opportunistic_insider_signal": f02_opportunistic_insider_signal,
    "F03_trading_activity_surge": f03_trading_activity_surge,
    "F04_sue_short_confirmation": f04_sue_short_confirmation,
    "F05_quality_liquidity_trend": f05_quality_liquidity_trend,
    "F06_momentum_short_confirmation": f06_momentum_short_confirmation,
    "F07_accruals_cashflow_confirmation": f07_accruals_cashflow_confirmation,
    "F08_earnings_recency_gated_insider_buying": f08_earnings_recency_gated_insider_buying,
}

# --------------------------------------------------------------- round 2: F09-F12
#
# Preregistered from Round 1's SELECT-window (2016-06-01..2023-12-29) IC
# feedback only (reports/research/iterations/h20260928_15_claude_factor_batch/
# select-results.json), before any TEST-window number was computed. SELECT
# |21d rank ICIR| by factor: F08 0.215 (sign negative -- insider buying
# shortly after a report predicted LOWER returns, opposite the round-1
# hypothesis), F05 0.164, F07 0.149, F01 0.145 (also sign-negative), F03
# 0.129, F06 0.019, F02 0.015, F04 0.002. Two patterns motivate Round 2: (a)
# fundamentals-quality factors (F05, F07, and the zoo's own top SELECT
# performers card_roe 0.233 and card_gross_profitability 0.209) are
# consistently the strongest theme in this universe/window; (b) the
# short_volume_broad-gated interactions (F04, F06) are the weakest, while the
# same "confirmation" idea built from daily_broad-only ingredients (F01, F03)
# did much better -- motivating a swap of the confirming ingredient rather
# than another short-volume gate.


def f09_insider_short_confluence_dollar_weighted(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Revision of F01: up-weight the dollar-value insider-buying component
    (0.7) over the short-covering component (0.3). Round-1 F01 (0.145 SELECT
    ICIR) beat F02's pure opportunistic/routine COUNT decomposition (0.015)
    by a wide margin, suggesting the dollar-weighted net_buy_usd_60d
    ingredient itself carries most of F01's signal; this reweighting tests
    that directly rather than treating the two components as equally
    informative. Same sources as F01 (Cohen/Malloy/Pomorski 2012;
    Christophe/Ferri/Hsieh 2010). Sign +1 (this round's hypothesis; the
    runner fixes the actually-used sign from SELECT independently).
    Confidence 0.50.
    """
    return con.execute(
        """
        WITH i AS (
            SELECT symbol, trade_date, net_buy_usd_60d
            FROM insider WHERE net_buy_usd_60d IS NOT NULL
        ), s AS (
            SELECT symbol, trade_date, dtc_change_vs_prior
            FROM short_interest WHERE dtc_change_vs_prior IS NOT NULL
        ), j AS (
            SELECT i.symbol, i.trade_date, i.net_buy_usd_60d, s.dtc_change_vs_prior
            FROM i JOIN s USING (symbol, trade_date)
        )
        SELECT symbol, trade_date,
            0.7 * PERCENT_RANK() OVER (PARTITION BY trade_date ORDER BY net_buy_usd_60d)
            + 0.3 * PERCENT_RANK() OVER (PARTITION BY trade_date ORDER BY -dtc_change_vs_prior)
            AS value
        FROM j
        """
    ).df()


def f10_quality_composite_roe_profitability_accruals(
    con: duckdb.DuckDBPyConnection,
) -> pd.DataFrame:
    """New: a direct three-way quality composite (ROE, gross profitability,
    low accruals), equal-weighted percentile ranks.

    Source: the same fundamentals-quality theme behind Novy-Marx (2013) and
    Sloan (1996), already the project's own strongest local cards this round
    (card_roe SELECT ICIR 0.233, card_gross_profitability 0.209) and behind
    this batch's own F05/F07 (0.164/0.149) -- Round 1 diluted each quality
    signal with a second, weaker ingredient (a liquidity trend for F05, a
    cash-conversion ratio for F07); this factor tests the plain three-way
    quality combination on its own, without a diluting second ingredient.
    Sign +1. Confidence 0.55.
    """
    return con.execute(
        """
        SELECT symbol, trade_date,
            (PERCENT_RANK() OVER (PARTITION BY trade_date ORDER BY roe)
            + PERCENT_RANK() OVER (PARTITION BY trade_date ORDER BY gross_profitability)
            + PERCENT_RANK() OVER (PARTITION BY trade_date ORDER BY -accruals)) / 3.0
            AS value
        FROM fundamentals
        WHERE roe IS NOT NULL AND gross_profitability IS NOT NULL AND accruals IS NOT NULL
        """
    ).df()


def f11_momentum_activity_surge_confirmation(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Revision of F06: replace the short_volume_broad confirmation gate
    (SELECT ICIR 0.019, the batch's weakest) with F03's trading-activity-
    surge ratio (SELECT ICIR 0.129, the batch's third-strongest, and built
    from daily_broad only -- full 2016+ coverage, unlike short_volume_
    broad's 2018-08 start). Source: same momentum literature as F06
    (Diether/Lee/Werner 2009) plus Gervais/Kaniel/Mingelgrin (2001) for the
    activity-surge ingredient (F03's own source). Sign +1. Confidence 0.50.
    """
    return con.execute(
        """
        SELECT symbol, trade_date,
            0.5 * PERCENT_RANK() OVER (PARTITION BY trade_date ORDER BY momentum_252_21)
            + 0.5 * PERCENT_RANK() OVER (PARTITION BY trade_date ORDER BY
                trade_count_5d_mean / NULLIF(trade_count_21d_mean, 0))
            AS value
        FROM daily
        WHERE momentum_252_21 IS NOT NULL AND trade_count_5d_mean IS NOT NULL
            AND trade_count_21d_mean IS NOT NULL AND trade_count_21d_mean > 0
        """
    ).df()


def f12_post_earnings_insider_buying_bad_news_gate(
    con: duckdb.DuckDBPyConnection,
) -> pd.DataFrame:
    """Revision of F08: restrict the post-report insider-buying window to
    NEGATIVE earnings surprises only (sue_eps < 0).

    Round-1 F08 was the batch's strongest SELECT signal (|ICIR| 0.215) but
    with the sign opposite the original hypothesis -- insider buying shortly
    after a report predicted LOWER, not higher, future returns. Rather than
    silently flipping the sign on the same unconditional construction, this
    factor tests a sharper, directly-motivated re-hypothesis: is the
    negative relationship concentrated in insiders buying shortly after BAD
    news (a "catching a falling knife" or "insiders defending the stock"
    pattern), where continued underperformance would be the more
    intuitive/economically sensible reading of a negative sign. Source: Ke/
    Huddart/Petroni (2003), unchanged. Sign +1 (this round's new hypothesis:
    even restricted to bad-news buying, the sign could go either way, and is
    left to the SELECT-window fix rather than presumed). Confidence 0.45
    (deliberately lower than F08's 0.50: this is a post-hoc-motivated,
    narrower re-hypothesis, not an independently pre-existing literature
    claim about the bad-news subset specifically).
    """
    return con.execute(
        """
        WITH i AS (
            SELECT symbol, trade_date, net_buy_usd_60d FROM insider
            WHERE net_buy_usd_60d IS NOT NULL
        ), f AS (
            SELECT symbol, trade_date, days_since_report, sue_eps FROM fundamentals
            WHERE days_since_report IS NOT NULL AND days_since_report <= 10
                AND sue_eps IS NOT NULL AND sue_eps < 0
        )
        SELECT i.symbol, i.trade_date, i.net_buy_usd_60d AS value
        FROM i JOIN f USING (symbol, trade_date)
        """
    ).df()


ROUND2: dict[str, object] = {
    "F09_insider_short_confluence_dollar_weighted": f09_insider_short_confluence_dollar_weighted,
    "F10_quality_composite_roe_profitability_accruals": (
        f10_quality_composite_roe_profitability_accruals
    ),
    "F11_momentum_activity_surge_confirmation": f11_momentum_activity_surge_confirmation,
    "F12_post_earnings_insider_buying_bad_news_gate": (
        f12_post_earnings_insider_buying_bad_news_gate
    ),
}


def register_sources(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"CREATE OR REPLACE VIEW daily AS SELECT * FROM read_parquet('{DAILY_BROAD}')")
    con.execute(
        f"CREATE OR REPLACE VIEW osap AS SELECT * FROM read_parquet('{OSAP_PRICE_BROAD}', "
        "union_by_name=true)"
    )
    con.execute(
        f"CREATE OR REPLACE VIEW fundamentals AS SELECT * FROM read_parquet('{SEC_FUNDAMENTALS}', "
        "union_by_name=true)"
    )
    con.execute(
        f"CREATE OR REPLACE VIEW insider AS SELECT * FROM read_parquet('{INSIDER_BROAD}', "
        "union_by_name=true)"
    )
    con.execute(
        f"CREATE OR REPLACE VIEW short_interest AS SELECT * FROM read_parquet('{SHORT_INTEREST}', "
        "union_by_name=true)"
    )
    con.execute(
        "CREATE OR REPLACE VIEW short_volume AS SELECT * FROM read_parquet("
        f"'{SHORT_VOLUME_BROAD}', union_by_name=true)"
    )


def build_all(out_dir: Path = OUT_DIR) -> list[Path]:
    """One small parquet per factor (``symbol, trade_date, value``), written
    and freed immediately -- a fresh, low-memory-limit DuckDB connection per
    factor, no wide merge held in Python memory. This is what makes the build
    safe inside the box's 1.8G cgroup cap (an earlier all-in-one-connection,
    accumulate-then-merge version was OOM-killed by the kernel on the fourth
    factor, confirmed via ``journalctl``/``dmesg`` -- ``memory cgroup out of
    memory: killed process ... python3``). Each factor's own SQL/formula is
    unchanged; only this orchestration changed."""
    t0 = time.monotonic()
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, fn in {**ROUND1, **ROUND2}.items():
        out_path = out_dir / f"{name}.parquet"
        started = time.monotonic()
        con = _connect(memory_limit="700MB")
        try:
            register_sources(con)
            df = fn(con).rename(columns={"value": name})
        finally:
            con.close()
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        df = df.sort_values(["trade_date", "symbol"]).reset_index(drop=True)
        df.to_parquet(out_path, index=False)
        print(
            f"[build_h20260928_15] {name}: {len(df):,} rows written to "
            f"{out_path.relative_to(ROOT)} in {time.monotonic() - started:.0f}s",
            flush=True,
        )
        written.append(out_path)
        del df
    print(
        f"[build_h20260928_15] {len(written)} factor files written in {time.monotonic() - t0:.0f}s",
        flush=True,
    )
    return written


if __name__ == "__main__":
    build_all()
