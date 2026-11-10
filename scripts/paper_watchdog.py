"""Keep the six-policy paper service alive and current.

Two jobs, both safe to run from cron:

``--health``  Read ``runtime/paper/six/runtime-state.json``. If the heartbeat is
              stale (default 900 s) or the unit is not active, restart the unit
              (rate limited) and re-check. Report blocked policies and stale
              targets without touching them: those need a human decision.

``--refresh`` After 00:20 UTC on a session, make sure the six dated targets exist
              for today. It calls the runtime's own launcher
              (``run_dated_refresh.poll_refresh``), so the launch receipt, source
              reuse and publish path are exactly the ones the service uses; it
              never invents a packet. If the day's attempt already exists it says
              so instead of replaying (a failed packet is a human decision).

Exit code 0 = healthy/current, 2 = needs attention. Every run appends one JSON
line so a silent outage leaves a trail.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "runtime/paper/six/runtime-state.json"
TARGETS = ROOT / "runtime/paper/six/targets"
RUNS = ROOT / "reports/paper/diagnostics/dated-target-refresh"
UNIT = "oc-six-paper-validation.service"
POLICIES = ("BASE", "H5", "LSTM", "BASE_STATE_BUDGET", "MULTI_EQUAL", "MULTI_HIERARCHICAL")
RATE_FILE = ROOT / "runtime/paper/six/restart-rate.json"
MAX_RESTARTS_PER_HOUR = 3
ALERT_FILE = ROOT / "runtime/paper/six/alert-rate.json"
ALERT_COOLDOWN_HOURS = 6
MAIL_ENV = Path("/root/.config/open-composer/report-mail.env")


def now_utc() -> datetime:
    return datetime.now(UTC)


def stamp(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def unit_state() -> str:
    out = subprocess.run(
        ["systemctl", "is-active", UNIT], capture_output=True, text=True, check=False
    )
    return out.stdout.strip() or "unknown"


def restarts_last_hour(now: datetime) -> list[str]:
    try:
        rows = json.loads(RATE_FILE.read_text())
    except (OSError, ValueError):
        rows = []
    cut = now - timedelta(hours=1)
    return [r for r in rows if stamp(r) and stamp(r) > cut]


def record_restart(now: datetime) -> None:
    rows = restarts_last_hour(now) + [now.isoformat()]
    RATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    RATE_FILE.write_text(json.dumps(rows))


def recently_alerted(title: str, now: datetime) -> bool:
    try:
        rows = json.loads(ALERT_FILE.read_text())
    except (OSError, ValueError):
        return False
    cut = now - timedelta(hours=ALERT_COOLDOWN_HOURS)
    return any(r.get("title") == title and stamp(r.get("at")) and stamp(r.get("at")) > cut for r in rows)


def remember_alert(title: str, severity: str, now: datetime) -> None:
    try:
        rows = [
            r
            for r in json.loads(ALERT_FILE.read_text())
            if stamp(r.get("at")) and stamp(r.get("at")) > now - timedelta(days=2)
        ]
    except (OSError, ValueError):
        rows = []
    rows.append(dict(at=now.isoformat(), title=title, severity=severity))
    ALERT_FILE.parent.mkdir(parents=True, exist_ok=True)
    ALERT_FILE.write_text(json.dumps(rows))


def notify(title: str, body: str, severity: str = "warn") -> dict:
    """Repo record plus an e-mail to the owner channel, deduplicated per title."""
    outcome = dict(record="skipped", email="skipped")
    try:
        from open_composer.notifications import safe_dispatch_notification

        safe_dispatch_notification(
            kind="system_alert",
            severity=severity,  # type: ignore[arg-type]
            title=title,
            body=body,
            metadata={"source": "paper_watchdog"},
            root=ROOT,
        )
        outcome["record"] = "ok"
    except Exception as exc:  # never let alerting break the check
        outcome["record"] = f"failed:{type(exc).__name__}"
    now = now_utc()
    if recently_alerted(title, now):
        outcome["email"] = f"suppressed (same alert within {ALERT_COOLDOWN_HOURS}h)"
        return outcome
    try:
        from open_composer.notifications.email_smtp import (
            build_message,
            load_mail_config,
            send_message,
        )

        config = load_mail_config(MAIL_ENV)
        subject = f"[open-composer][paper] {severity.upper()}: {title}"
        message = build_message(config, subject, body)
        send_message(config, message)
        remember_alert(title, severity, now)
        outcome["email"] = "sent"
    except Exception as exc:
        outcome["email"] = f"failed:{type(exc).__name__}: {str(exc)[:120]}"
    return outcome


def health(args) -> dict:
    now = now_utc()
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    beat = stamp(state.get("heartbeat_at"))
    age = None if beat is None else (now - beat).total_seconds()
    active = unit_state()
    report = dict(
        at=now.isoformat(),
        mode="health",
        unit=active,
        heartbeat_at=state.get("heartbeat_at"),
        heartbeat_age_s=None if age is None else round(age),
        status=state.get("status"),
        policies={k: (v or {}).get("status") for k, v in (state.get("policy_status") or {}).items()},
        stale_targets=[
            p
            for p in POLICIES
            if str(json.loads((TARGETS / f"{p}.json").read_text()).get("application_day"))
            != str(expected_application_day(now))
        ]
        if TARGETS.is_dir()
        else [],
        restarted=False,
    )
    unhealthy = (age is None or age > args.stale_after) or active != "active"
    if unhealthy and args.fix:
        recent = restarts_last_hour(now)
        if len(recent) >= MAX_RESTARTS_PER_HOUR:
            report["restart_skipped"] = f"{len(recent)} restarts in the last hour"
        else:
            record_restart(now)
            action = "restart" if active == "active" else "start"
            subprocess.run(["systemctl", action, UNIT], check=False)
            report["restarted"] = True
            report["restart_action"] = action
            deadline = now + timedelta(seconds=args.wait)
            while now_utc() < deadline:
                subprocess.run(["sleep", "5"], check=False)
                fresh = json.loads(STATE.read_text()) if STATE.exists() else {}
                beat2 = stamp(fresh.get("heartbeat_at"))
                if beat2 and beat2 > (beat or datetime.min.replace(tzinfo=UTC)):
                    report["heartbeat_after_restart"] = fresh.get("heartbeat_at")
                    report["recovered"] = True
                    break
            unhealthy = not report.get("recovered", False)
    report["healthy"] = not unhealthy
    if unhealthy:
        blocked = {k: v for k, v in report["policies"].items() if v == "blocked"}
        report["alert"] = notify(
            "Six-policy paper service needs attention",
            "\n".join(
                [
                    f"unit={active}",
                    f"heartbeat_age_s={report['heartbeat_age_s']}",
                    f"heartbeat_at={report['heartbeat_at']}",
                    f"blocked={sorted(blocked)}",
                    f"stale_targets={report['stale_targets']}",
                    f"restarted={report.get('restarted')} recovered={report.get('recovered')}",
                    f"at={report['at']}",
                ]
            ),
            severity="red",
        )
    return report


def expected_application_day(now: datetime):
    """The application day a 00:2x UTC check should already see published."""
    from open_composer.market_sessions import us_equity_session_dates

    days = us_equity_session_dates((now - timedelta(days=15)).date(), now.date())
    if not days:
        return None
    if now.date() in days and now.hour * 60 + now.minute >= 20:
        return now.date()
    past = [d for d in days if d < now.date()]
    return past[-1] if past else None


def refresh(args) -> dict:
    from open_composer.paper_runtime.six.run_dated_refresh import poll_refresh

    now = now_utc()
    expected = expected_application_day(now)
    report = dict(at=now.isoformat(), mode="refresh", expected_application_day=str(expected))
    if expected is None:
        report.update(skipped="no session in the window")
        return report
    current = {
        p: json.loads((TARGETS / f"{p}.json").read_text()).get("application_day")
        for p in POLICIES
        if (TARGETS / f"{p}.json").exists()
    }
    if set(current.values()) == {str(expected)} and len(current) == len(POLICIES):
        report.update(targets=current, result="already current")
        return report
    report["before"] = current
    if (RUNS / str(expected)).exists():
        exit_row = RUNS / str(expected) / "refresh-exit.json"
        report.update(
            result="today's attempt already exists; no replay",
            attempt_status=json.loads(exit_row.read_text()).get("status") if exit_row.exists() else None,
        )
        report["alert"] = notify(
            "Six-policy daily refresh needs attention",
            f"application_day={expected}\n{json.dumps(report, indent=1, default=str)[:1500]}",
            severity="red",
        )
        return report
    job = poll_refresh(None, now=now)
    report["launched"] = job is not None
    if job is not None:
        try:
            report["exit_code"] = job.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            report["exit_code"] = "timeout"
    after = {
        p: json.loads((TARGETS / f"{p}.json").read_text()).get("application_day")
        for p in POLICIES
        if (TARGETS / f"{p}.json").exists()
    }
    report["after"] = after
    report["result"] = "complete" if set(after.values()) == {str(expected)} and len(after) == len(POLICIES) else "incomplete"
    if report["result"] != "complete":
        report["alert"] = notify(
            "Six-policy daily refresh incomplete",
            f"application_day={expected}\n{json.dumps(report, indent=1, default=str)[:1500]}",
            severity="red",
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--health", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--fix", action="store_true", help="restart/start the unit when unhealthy")
    parser.add_argument("--stale-after", type=int, default=900)
    parser.add_argument("--wait", type=int, default=90)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--log", type=Path, default=ROOT / "logs/paper_watchdog.jsonl")
    args = parser.parse_args()
    if args.health == args.refresh:
        parser.error("choose exactly one of --health or --refresh")
    report = health(args) if args.health else refresh(args)
    line = json.dumps(report, default=str)
    print(line)
    args.log.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open("a") as stream:
        stream.write(line + "\n")
    if args.health:
        return 0 if report.get("healthy") else 2
    return 0 if report.get("result") in {"already current", "complete", None} else 2


if __name__ == "__main__":
    raise SystemExit(main())
