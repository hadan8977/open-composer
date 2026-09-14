"""``oc paper schedule-suggest`` support (Step 14 plan section 1, item 4).

Prints (never installs) the crontab line appropriate for a StrategySpec's
``timeframe``, routed through the generic ``scripts/run_bar_cycle.py``
runner. An agent may never touch the live crontab -- installing a cron entry
requires the user's own explicit sign-off, per this repo's own rule -- so
this module only ever returns text for a human to review and install by
hand.

Lives in ``open_composer.execution`` (not ``scripts/``) deliberately:
``scripts/*.py`` are entry-point wrappers that import from the
``open_composer`` package, not the other way around, and
``open_composer.cli`` should not need the ``scripts`` implicit namespace
package to expose a CLI command.
"""

from __future__ import annotations

from pathlib import Path

from open_composer.config import project_root
from open_composer.models.strategy_spec import StrategySpec

#: {timeframe: cron schedule field} -- daily matches the existing live cron
#: convention exactly (23:00 UTC Mon-Fri, one hour after the nightly archive
#: update -- see ``us_model_ranking_portfolio_top50``/
#: ``us_recent_high_return_top50``'s installed crontab entries); intraday
#: timeframes poll every 30 minutes across the regular US session (13:00-
#: 21:30 UTC covers both EDT and EST session hours with margin on both
#: ends). Idempotency (BarCycleRunner tracks the last processed
#: ``bar_close_ts`` in engine state) means polling more often than a bar
#: actually closes is always a harmless no-op, so one shared 30-minute
#: cadence is deliberately reused for 5m/15m/30m/1h/4h rather than a
#: differently-tuned line per timeframe.
_CRON_SUGGESTIONS: dict[str, str] = {
    "daily": "0 23 * * 1-5",
    "5m": "*/30 13-21 * * 1-5",
    "15m": "*/30 13-21 * * 1-5",
    "30m": "*/30 13-21 * * 1-5",
    "1h": "*/30 13-21 * * 1-5",
    "4h": "*/30 13-21 * * 1-5",
}


def suggest_crontab_line(spec_path: Path, spec: StrategySpec, *, root: Path | None = None) -> str:
    """The crontab line (or, for ``1m``, process-supervisor guidance)
    appropriate for ``spec.timeframe`` -- printed only, never installed.
    """
    base = root or project_root()
    try:
        spec_rel = spec_path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        spec_rel = str(spec_path)
    command = (
        f'cd {base} && export PATH="$HOME/.local/bin:$PATH" && '
        f"export UV_CACHE_DIR=/tmp/open-composer-uv-cache && "
        f"./scripts/run_capped.sh --mem 1.8G -- uv run python scripts/run_bar_cycle.py "
        f"--spec {spec_rel} >> logs/{spec.name}_bar_cycle_cron.log 2>&1"
    )
    if spec.timeframe == "1m":
        return (
            "1m has no fixed cron line -- cron's 1-minute granularity plus per-invocation "
            "process startup overhead makes a persistent poller the better fit here. Run "
            "under a process supervisor (systemd/supervisor), e.g.:\n"
            f"  cd {base} && uv run python scripts/run_bar_cycle.py --spec {spec_rel} "
            "--follow --poll-seconds 60"
        )
    if spec.timeframe == "weekly":
        return (
            "weekly is not supported by ArchiveBarSource/AlpacaBarSource's session-anchoring "
            "logic yet (out of scope for Step 14) -- no schedule to suggest."
        )
    schedule = _CRON_SUGGESTIONS.get(spec.timeframe)
    if schedule is None:
        return f"no schedule suggestion for timeframe={spec.timeframe!r}"
    return f"{schedule} {command}"
