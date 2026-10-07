# ruff: noqa: E501
"""T-20261007-02 frozen rules: event qualification, theme maps, main grid, costs. Imported by the
registration, data and run scripts; its sha256 is recorded in the candidate manifest."""

from __future__ import annotations

import re

WINDOW_START = "2024-01-08"  # recent window (evaluation standard v2)
EXTRA_V4_START = (
    "2023-01-02"  # Kalshi release events from 2023 only used for the V4 crash diagnostic
)

# ---- Release type (R): Kalshi macro release moments --------------------------------------------
R_CLASSES = {
    "KXCPI": "CPI",
    "KXPAYROLLS": "NFP",
    "KXGDP": "GDP",
    "KXFED": "FOMC",
    "KXJOBLESSCLAIMS": "CLAIMS",
    "KXPCECORE": "PCE",
    "KXISMPMI": "ISM_MFG",
    "KXISMSERVICES": "ISM_SVC",
    "KXADP": "ADP",
    "KXJOLTSOPEN": "JOLTS",
}
R_CORE = ("CPI", "NFP", "GDP", "FOMC")
R_RELEASE_TIME_ET = {
    "CPI": "08:30",
    "NFP": "08:30",
    "GDP": "08:30",
    "FOMC": "14:00",
    "CLAIMS": "08:30",
    "PCE": "08:30",
    "ISM_MFG": "10:00",
    "ISM_SVC": "10:00",
    "ADP": "08:15",
    "JOLTS": "10:00",
}
# +1: a higher expected print (or higher expected policy rate) is hawkish (short TLT); -1: higher is dovish (weak labor)
R_HAWKISH_SIGN = {
    "CPI": 1,
    "NFP": 1,
    "GDP": 1,
    "FOMC": 1,
    "CLAIMS": -1,
    "PCE": 1,
    "ISM_MFG": 1,
    "ISM_SVC": 1,
    "ADP": 1,
    "JOLTS": 1,
}
R_MIN_EVENTS_PER_CLASS = (
    20  # a class enters the pooled set only with >= 20 valid events since 2024-01-08
)
R_MAX_CANDLE_AGE_H = 48
R_SIGNALS = (
    "R1_revision",
    "R2_gap_to_baseline",
)  # R1: E(T-) - E(T-24h); R2: E(T-) - previous settled value
R_HORIZONS_MIN = (5, 30, 120)
R_ASSET = "TLT"  # hawkish (higher expected print / rate) -> short TLT, all classes
R_SECONDARY = ("SPY", "QQQ", "IWM")  # report-only, not in the main grid
R_WARMUP_EVENTS = 6  # per class: first six events set the expanding-median threshold
R_MIN_USABLE_STRIKES = 3

# ---- Jump type (J): Polymarket odds jumps --------------------------------------------------------
J_THETA_PP = (3, 5, 8)
J_HORIZONS_MIN = (15, 60, 240)
J_MODES = ("continue", "reverse")
J_MIN_MARKET_VOLUME = 300_000
J_MAX_MARKETS = 700
J_EXCLUDE_TAGS = {"geopolitics"}
J_NEAR_END_HOURS = 24
J_PRICE_BOUNDS = (0.02, 0.98)
J_DEDUP_HOURS = 4
J_DECISION_WINDOW_ET = ("08:00", "19:30")  # weekdays only; minute bars cover 04:00-20:00 ET
J_EXIT_CAP_ET = "19:55"
FETCH_CHUNK_DAYS = 14

# theme -> (regex on lower-case "event title | market question", yes_up_sign for the primary ETF, primary ETF, exclusion regex)
THEMES = {
    "TARIFF_ESC": (
        r"tariff",
        -1,
        "SPY",
        r"lower|reduc|cut|remov|deal|agree|pause|strike|against|exempt|visit|meet|egg|revenue|supreme court|price of|between",
    ),
    "TARIFF_DEESC": (
        r"(lower|reduc|cut|remov|pause|exempt)[^?]*tariff|tariff[^?]*(lower|reduc|cut|remov|pause|exempt)|trade deal",
        +1,
        "SPY",
        r"egg|revenue|visit|meet",
    ),
    "FED_EASE": (
        r"(decreas|cut|lower)[^?]*(interest rates?|bps)|fed rate cut by",
        +1,
        "TLT",
        r"how many|\d+ (or more |fed )*(rate )?cuts|ecb|boj|bank of|rba|boe|japan|canada|uk |china|brazil|india",
    ),
    "FED_HIKE": (
        r"(increas|hike|raise)[^?]*(interest rates?|bps)|fed rate hike by",
        -1,
        "TLT",
        r"how many|ecb|boj|bank of|rba|boe|japan|canada|uk |china|brazil|india|decreas",
    ),
    "RECESSION": (r"recession", -1, "SPY", r"japan|uk |europe|china|canada|germany"),
    "SHUTDOWN": (r"shutdown|funding lapse|appropriations lapse", -1, "SPY", r"end|reopen"),
    "ELECTION_GOP": (
        r"^(presidential election winner|popular vote winner|balance of power|which party will win the (house|senate)|which party wins the (house|senate)|house winner|senate winner|presidential election: )[^|]*\|.*(republican|trump|gop)",
        +1,
        "IWM",
        r"state|texas|florida|ohio|georgia|nevada|arizona|wisconsin|michigan|pennsylvania|north carolina|new |virginia|minnesota|iowa|alaska|montana|maine|vice|cabinet|nominee",
    ),
    "ELECTION_DEM": (
        r"^(presidential election winner|popular vote winner|balance of power|which party will win the (house|senate)|which party wins the (house|senate)|house winner|senate winner|presidential election: )[^|]*\|.*(democrat|harris|biden)",
        -1,
        "IWM",
        r"state|texas|florida|ohio|georgia|nevada|arizona|wisconsin|michigan|pennsylvania|north carolina|new |virginia|minnesota|iowa|alaska|montana|maine|vice|cabinet|nominee",
    ),
}
THEME_ORDER = list(THEMES)


def theme_of(title: str, question: str) -> str | None:
    text = f"{title} | {question}".lower()
    for name in THEME_ORDER:
        pat, _sign, _etf, excl = THEMES[name]
        if re.search(pat, text) and not re.search(excl, text):
            return name
    return None


# ---- Costs (reuse of the T-20261006-15 ETF model; extended-hours extras are unmeasured priors) ----
TICK_CENTS_1 = {"SPY", "QQQ", "IWM", "TLT", "XLF", "XLE", "XLK", "XLV", "XLY", "XLP", "XLI", "XLU"}


def one_way_cost_bp(
    symbol: str, price: float, sell: bool, minute_et: int, stress: float = 1.0
) -> float:
    """minute_et = minutes after midnight New York time of the fill bar."""
    tick = 1.0 if symbol in TICK_CENTS_1 else 2.0
    spread = 0.5 * tick * 0.01 / price * 1e4
    extra = 0.0
    if minute_et < 9 * 60 + 30 or minute_et >= 15 * 60 + 55:
        extra += 3.0 if symbol in {"SPY", "QQQ", "IWM", "TLT"} else 6.0  # extended hours
    elif minute_et < 9 * 60 + 45:
        extra += 1.0
    return stress * (spread + extra) + 0.02 + (0.206 if sell else 0.0)


# ---- Main grid (<= 30 trading variants, counted for DSR) ----------------------------------------
def main_grid() -> list[dict]:
    g = []
    for s in R_SIGNALS:
        for h in R_HORIZONS_MIN:
            g.append(
                {"type": "R", "signal": s, "horizon_min": h, "asset": R_ASSET, "classes": "pooled"}
            )
    for th in J_THETA_PP:
        for h in J_HORIZONS_MIN:
            for m in J_MODES:
                g.append(
                    {
                        "type": "J",
                        "theta_pp": th,
                        "horizon_min": h,
                        "mode": m,
                        "asset": "theme_primary",
                    }
                )
    return g
