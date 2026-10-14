"""Executable fields for the frozen context contract; no IO or fitting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from decision_system import Frame, Support


def percentile_rank(values: dict[str, float]) -> dict[str, float]:
    n = len(values)
    return (
        {
            key: (
                sum(x < v for x in values.values()) + (sum(x == v for x in values.values()) + 1) / 2
            )
            / n
            for key, v in values.items()
        }
        if n
        else {}
    )


def leadership(snapshot: dict[str, dict], at: datetime) -> tuple[list[str], dict[str, float]]:
    eligible = {
        symbol: row
        for symbol, row in snapshot.items()
        if row.get("status") == "observed"
        and row["available_at"] <= at
        and row["average_dollar_volume"] >= 1_000_000
        and row["adr"] > 0
    }
    r = [
        percentile_rank({s: row[k] for s, row in eligible.items()})
        for k in ("return30", "prior_return", "adr")
    ]
    score = {s: 0.5 * r[0][s] + 0.3 * r[1][s] + 0.2 * r[2][s] for s in eligible}
    ranked = sorted(eligible, key=lambda s: (-score[s], -eligible[s]["average_dollar_volume"], s))
    return ranked[:3], score


def market_state(index_snapshot: dict[str, dict], at: datetime) -> str:
    rows = [index_snapshot.get(s) for s in ("QQQ", "IWM")]
    if any(r is None or r.get("status") != "observed" or r["available_at"] > at for r in rows):
        return "unknown"
    if all(
        r["close"] >= r["ema"][9]
        and r["ema"][9] > r["previous_ema"][9]
        and r["ema"][9] >= r["ema"][21]
        for r in rows
    ):
        return "strong"
    if all(r["close"] < r["ema"][21] and r["ema"][9] < r["previous_ema"][9] for r in rows):
        return "weak"
    return "neutral"


@dataclass
class Epoch:
    id: str
    origin: datetime | None
    known_at: datetime
    floor: float | None
    born_session: int
    origin_session: int
    breakout_level: float | None
    first_touch_session: int | None = None
    last_daily_observation: datetime | None = None
    floor_failures: int = 0
    invalid: bool = False
    ineligible_snapshots: int = 0


class ContextProducer:
    def __init__(self):
        self.epochs: dict[str, Epoch] = {}
        self.watch_until: dict[str, int] = {}
        self.previous_strength: dict[str, str] = {}
        self.last_snapshot: datetime | None = None
        self.invalidated_origins: dict[str, set[datetime]] = {}
        self.last_eligible: dict[str, bool] = {}

    def apply_split(self, symbol: str, ratio: float):
        epoch = self.epochs.get(symbol)
        if epoch is not None:
            if epoch.floor is not None:
                epoch.floor /= ratio
            if epoch.breakout_level is not None:
                epoch.breakout_level /= ratio

    def prior_session_update(self, snapshot: dict[str, dict], at: datetime, session: int):
        # Called once for a common prior-session snapshot, never once per
        # candidate. This prevents repeated snapshot calls extending retention.
        if self.last_snapshot is not None and at <= self.last_snapshot:
            raise ValueError("prior snapshot must advance once per scheduled session")
        top, scores = leadership(snapshot, at)
        for symbol, row in snapshot.items():
            if row.get("status") != "observed" or row["available_at"] > at:
                continue
            if (
                row["strength"] == "lead"
                and self.previous_strength.get(symbol) != "lead"
                and row["return30"] > 0
            ):
                self.watch_until[symbol] = session + 10
            self.previous_strength[symbol] = row["strength"]
            current = self.epochs.get(symbol)
            if current is not None and current.last_daily_observation != row["available_at"]:
                current.ineligible_snapshots = (
                    0 if symbol in scores else current.ineligible_snapshots + 1
                )
                current.floor_failures = (
                    current.floor_failures + 1
                    if current.floor is not None and row["close"] < current.floor
                    else 0
                )
                current.last_daily_observation = row["available_at"]
                current.invalid = current.invalid or (
                    current.floor_failures >= 2
                    or session - current.origin_session >= 60
                    or (current.origin is None and current.ineligible_snapshots >= 3)
                )
                if current.invalid and current.origin is not None:
                    self.invalidated_origins.setdefault(symbol, set()).add(current.origin)
            origin = row.get("base_start")
            recognition = row.get("base_recognized_at")
            if origin is not None and (
                recognition is None or recognition > at or recognition < origin
            ):
                raise ValueError("proper base needs its original causal pivot recognition")
            origin_session = row.get("base_origin_session")
            if origin is not None and origin_session is None:
                if row.get("base_age") is None:
                    raise ValueError(
                        "proper base needs original session or prior-snapshot base age"
                    )
                origin_session = session - 1 - row["base_age"]
            fresh_base = (
                origin is not None
                and origin not in self.invalidated_origins.get(symbol, set())
                and session - origin_session < 60
                and (
                    current is None
                    or current.origin is None
                    or (current.invalid and origin > current.origin)
                )
            )
            fallback = (
                origin is None
                and symbol in scores
                and (
                    current is None
                    or (
                        current.invalid
                        and current.origin is None
                        and not self.last_eligible.get(symbol, False)
                    )
                )
            )
            if fresh_base or fallback:
                origin_key = (
                    origin.isoformat() if fresh_base else "leader-incarnation:" + at.isoformat()
                )
                known = recognition if fresh_base else at
                key = f"{symbol}:{origin_key}:{known.isoformat()}:context-v1"
                self.epochs[symbol] = Epoch(
                    key,
                    origin if fresh_base else None,
                    known,
                    row.get("base_floor") if fresh_base else None,
                    session,
                    origin_session if fresh_base else session,
                    row.get("base_breakout_level") if fresh_base else None,
                    last_daily_observation=row["available_at"],
                )
            self.last_eligible[symbol] = symbol in scores
        self.last_snapshot = at
        kept = [
            s
            for s, until in self.watch_until.items()
            if until >= session
            and s in snapshot
            and snapshot[s].get("status") == "observed"
            and snapshot[s]["average_dollar_volume"] >= 1_000_000
        ]
        return set(top + kept), scores

    def observe_touch(self, symbol, daily, lower, session_index):
        epoch = self.epochs[symbol]
        radius = 0.15 * daily["adr"] * lower["close"]
        constructive = bool(daily["shape_ok"]) or (
            epoch.breakout_level is not None and daily["close"] > epoch.breakout_level
        )
        if (
            not epoch.invalid
            and constructive
            and epoch.first_touch_session is None
            and any(
                lower["low"] <= daily["ema"][n] + radius and lower["close"] >= daily["ema"][n]
                for n in (9, 21, 50)
            )
        ):
            epoch.first_touch_session = session_index
        return (
            epoch.first_touch_session is not None and session_index - epoch.first_touch_session < 3
        )

    def compile_frame(
        self,
        *,
        symbol: str,
        daily: dict,
        hourly: dict | None,
        weekly: dict | None,
        indexes: dict[str, dict],
        watchlist: set[str],
        lower: dict,
        previous_lower: dict,
        session: str,
        session_index: int,
        anchors: tuple,
        past_minute_volume: float,
        pause_sessions: int,
        completed_sessions_since_entry: int = 0,
    ) -> Frame:
        start, end = lower["start"], lower["end"]
        if symbol not in self.epochs or daily["available_at"] > start:
            raise ValueError("missing known epoch or daily context")
        if previous_lower["end"] > start or previous_lower["duration"] != lower["duration"]:
            raise ValueError("previous bar must be complete in selected timeframe")
        if hourly is None or hourly.get("status") != "observed" or hourly["available_at"] > start:
            raise ValueError("required hourly context unavailable; no daily substitution")
        epoch = self.epochs[symbol]
        if epoch.known_at > start:
            raise ValueError("epoch recognition is not yet available at lower bar start")
        used = [daily["available_at"], hourly["available_at"], epoch.known_at]
        supports = [
            Support(f"daily:ema:{n}", daily["ema"][n], daily["available_at"]) for n in (9, 21, 50)
        ]
        supports.extend(
            Support(f"hourly:ema:{n}", hourly["ema"][n], hourly["available_at"]) for n in (9, 21)
        )
        if (
            weekly is not None
            and weekly.get("status") == "observed"
            and weekly["available_at"] <= start
        ):
            supports.extend(
                Support(f"weekly:ema:{n}", weekly["ema"][n], weekly["available_at"])
                for n in (9, 21)
            )
            used.append(weekly["available_at"])
        if epoch.breakout_level is not None:
            supports.append(Support("pivot:" + epoch.id, epoch.breakout_level, epoch.known_at))
        first_retest = self.observe_touch(symbol, daily, lower, session_index)
        return Frame(
            symbol,
            end,
            start,
            session,
            epoch.id,
            lower["minute"],
            lower["duration"],
            lower["close"],
            lower["low"],
            previous_lower["high"],
            previous_lower["low"],
            lower["day_low"],
            daily["adr"],
            daily["ema"][9],
            daily["ema"][21],
            daily["close"],
            max(used),
            symbol in watchlist,
            market_state(indexes, start),
            bool(daily["shape_ok"]),
            first_retest,
            tuple(dict.fromkeys(supports)),
            anchors,
            completed_sessions_since_entry=completed_sessions_since_entry,
            past_minute_volume=past_minute_volume,
            active_data_complete=lower["complete"],
            base_breakout_level=epoch.breakout_level,
            sessions_since_risk_pause=pause_sessions,
            ema9_previous=daily["previous_ema"][9],
            ema21_previous=daily["previous_ema"][21],
            epoch_valid=not epoch.invalid,
        )
