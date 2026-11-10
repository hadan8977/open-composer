"""Build and e-mail the owner's daily or weekly report (`docs/owner-reporting.zh.md`).

    uv run python scripts/owner_report.py daily            # preview, prints the markdown
    uv run python scripts/owner_report.py auto --send      # cron: Sunday (UTC) weekly, else daily
    uv run python scripts/owner_report.py weekly --send --force
    uv run python scripts/owner_report.py tables           # business-named trading tables
    uv run python scripts/owner_report.py lint <file.md>   # internal codes, paths, long brackets
    uv run python scripts/owner_report.py health <event-id> # actual report artifact, no send

The body is the writer's plain-language report (`reports/owner/daily/<UTC date>.zh.md`,
weekly `reports/owner/weekly/<ISO week>.zh.md`) or, when it is missing, a short
data-only fallback.  Round logs, task ids and run health go out as an attachment.
The markdown is always saved to ``logs/owner-report/<kind>-<UTC date>.md`` (the
attachment next to it as ``-log.md``).  A sent marker
``logs/owner-report/sent-<kind>-<UTC date>.json`` stops a second send on the same day
unless ``--force``.  Exit codes: 0 ok or already sent, 1 lint found errors, 2 mail
config missing or invalid, 3 the SMTP send failed.  No model call, no broker call.
"""

from __future__ import annotations

import argparse
import json
import smtplib
import ssl
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from open_composer.notifications.email_smtp import (  # noqa: E402
    MailConfigError,
    build_message,
    load_mail_config,
    send_message,
)
from open_composer.reports.owner_digest import (  # noqa: E402
    collect_digest,
    digest_subject,
    markdown_to_html,
    render_candidates,
    render_digest,
    render_internal_log,
    render_paper_section,
)
from open_composer.reports.owner_health import report_event_health  # noqa: E402
from open_composer.reports.owner_style import (  # noqa: E402
    format_findings,
    lint_errors,
    lint_owner_text,
)

OUT_DIR = ROOT / "logs" / "owner-report"
EXIT_LINT, EXIT_CONFIG, EXIT_SEND = 1, 2, 3

# Transient transport errors get two more tries (10-07 01:00 UTC: Gmail closed the TLS
# session mid-handshake, SSLEOFError, and the daily report was not sent). Authentication
# and other SMTP response errors are not retried.
SEND_RETRY_ERRORS: tuple[type[BaseException], ...] = (
    ssl.SSLError,
    smtplib.SMTPServerDisconnected,
    smtplib.SMTPConnectError,
    ConnectionError,
    TimeoutError,
)
SEND_BACKOFF_SECONDS = (20.0, 60.0)


def send_with_retry(config, message, *, sender=send_message, sleep=time.sleep) -> int:
    """Send, retrying transient transport errors; returns the number of attempts used."""
    attempts = len(SEND_BACKOFF_SECONDS) + 1
    for attempt in range(1, attempts + 1):
        try:
            sender(config, message)
            return attempt
        except SEND_RETRY_ERRORS as exc:
            if attempt == attempts:
                raise
            wait = SEND_BACKOFF_SECONDS[attempt - 1]
            print(
                f"send attempt {attempt} failed: {type(exc).__name__}; retrying in {wait:.0f}s",
                file=sys.stderr,
            )
            sleep(wait)
    raise AssertionError("unreachable")


def resolve_kind(kind: str, now: datetime) -> str:
    if kind != "auto":
        return kind
    return "weekly" if now.astimezone(UTC).weekday() == 6 else "daily"


def run_lint(path: Path) -> int:
    findings = lint_owner_text(path.read_text(encoding="utf-8"))
    print(format_findings(findings))
    return EXIT_LINT if any(item.level == "error" for item in findings) else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("kind", choices=("daily", "weekly", "auto", "tables", "lint", "health"))
    ap.add_argument("path", nargs="?", type=Path, help="lint: the markdown file to check")
    ap.add_argument("--send", action="store_true", help="e-mail it (default: print only)")
    ap.add_argument("--force", action="store_true", help="send even if today's marker exists")
    ap.add_argument("--mail-env", type=Path, default=None, help="mail config file (KEY=VALUE)")
    ap.add_argument("--now", default=None, help="ISO time to report as of (tests, backfills)")
    args = ap.parse_args(argv)

    if args.kind == "health":
        if args.path is None:
            ap.error("health needs an event id")
        health = report_event_health(ROOT, str(args.path))
        print(json.dumps(health, ensure_ascii=False, indent=2))
        return 0 if health["status"] in {"written", "not_authorized"} else 1

    if args.kind == "lint":
        if args.path is None:
            ap.error("lint needs a file path")
        return run_lint(args.path)

    now = datetime.fromisoformat(args.now) if args.now else datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    if args.kind == "tables":
        data = collect_digest(ROOT, now, "daily")
        lines = render_paper_section(data)
        candidates = render_candidates(data)
        if candidates:
            lines.extend(["", "### 实盘候选", "", *candidates])
        print("\n".join(lines))
        return 0

    kind = resolve_kind(args.kind, now)
    stamp = f"{kind}-{now.astimezone(UTC):%Y-%m-%d}"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    marker = OUT_DIR / f"sent-{stamp}.json"

    data = collect_digest(ROOT, now, kind)
    text = render_digest(data)
    log_text = render_internal_log(data)
    subject = digest_subject(data)
    (OUT_DIR / f"{stamp}.md").write_text(text, encoding="utf-8")
    (OUT_DIR / f"{stamp}-log.md").write_text(log_text, encoding="utf-8")
    written = data.weekly_path if kind == "weekly" else data.daily_path
    errors = lint_errors(text)
    print(
        f"{now.astimezone(UTC):%Y-%m-%dT%H:%M:%SZ} {subject} "
        f"(body: {written or 'fallback'}; lint errors {len(errors)})"
    )
    if errors:  # still send: the owner gets a report every day; the log shows what to fix
        print(format_findings(errors), file=sys.stderr)
    if not args.send:
        print(text)
        return 0
    if marker.exists() and not args.force:
        print(f"already sent ({marker.name}); use --force to send again")
        return 0
    try:
        config = load_mail_config(args.mail_env)
    except MailConfigError as exc:
        print(f"mail config: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    attachment = (f"运行记录-{stamp}.md", log_text)
    message = build_message(config, subject, text, markdown_to_html(text), [attachment])
    try:
        send_with_retry(config, message)
    except Exception as exc:  # report the class and message only; never the config
        print(f"send failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_SEND
    marker.write_text(
        json.dumps(
            {
                "sent_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "subject": subject,
                "body": written or "fallback",
                "lint_errors": len(errors),
                "recipients": len(config.recipients),
                "message_id": message["Message-ID"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"sent to {len(config.recipients)} recipient(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
