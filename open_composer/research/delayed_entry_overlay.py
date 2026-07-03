from __future__ import annotations

import re
from dataclasses import dataclass

_LABEL_RE = re.compile(
    r"^delayed_entry:delay(?P<delay>\d+)"
    r"(?:_symbols(?P<symbols>[A-Za-z0-9-]+))?"
    r"_base\[(?P<base>.+)\]$"
)


@dataclass(frozen=True)
class DelayedEntryOverlay:
    delay_minutes: int
    base_route_label: str
    covered_symbols: tuple[str, ...] = ("TQQQ",)

    @property
    def time_rule(self) -> str:
        if self.delay_minutes <= 0:
            return "regular_session_open"
        return f"regular_session_open_plus_{self.delay_minutes}m"

    @property
    def label(self) -> str:
        symbols = (
            "" if self.covered_symbols == ("TQQQ",) else "_symbols" + "-".join(self.covered_symbols)
        )
        base = self.base_route_label.replace("post_drawdown_reentry:", "pdr:")
        return f"delayed_entry:delay{self.delay_minutes}{symbols}_base[{base}]"

    @property
    def holding_mode(self) -> str:
        return "open_to_open"


def delayed_entry_overlay_from_label(label: str) -> DelayedEntryOverlay:
    match = _LABEL_RE.fullmatch(label)
    if match is None:
        raise ValueError(f"unsupported delayed-entry route label: {label}")
    delay_minutes = int(match.group("delay"))
    if delay_minutes < 0:
        raise ValueError(f"unsupported delayed-entry delay_minutes={delay_minutes}")
    symbols_raw = match.group("symbols")
    covered_symbols = (
        tuple(item.upper() for item in symbols_raw.split("-") if item) if symbols_raw else ("TQQQ",)
    )
    if not covered_symbols:
        raise ValueError("delayed-entry overlay requires at least one covered symbol")
    return DelayedEntryOverlay(
        delay_minutes=delay_minutes,
        covered_symbols=covered_symbols,
        base_route_label=_expand_base_label(match.group("base")),
    )


def is_delayed_entry_label(label: str | None) -> bool:
    return bool(label and label.startswith("delayed_entry:"))


def _expand_base_label(label: str) -> str:
    if label.startswith("pdr:"):
        return "post_drawdown_reentry:" + label.removeprefix("pdr:")
    return label
