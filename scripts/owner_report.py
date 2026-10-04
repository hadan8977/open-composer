"""Build and e-mail the owner's daily or weekly report (`docs/owner-reporting.zh.md`).

    uv run python scripts/owner_report.py daily            # preview, prints the markdown
    uv run python scripts/owner_report.py auto --send      # cron: Sunday (UTC) weekly, else daily
    uv run python scripts/owner_report.py weekly --send --force

The markdown is always saved to ``logs/owner-report/<kind>-<UTC date>.md``.  A sent
marker ``logs/owner-report/sent-<kind>-<UTC date>.json`` stops a second send on the
same day unless ``--force``.  Exit codes: 0 ok or already sent, 2 mail config
missing or invalid, 3 the SMTP send failed.  No model call, no broker call.
"""

from __future__ import annotations

import argparse
import json
import sys
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
    render_digest,
)

OUT_DIR = ROOT / "logs" / "owner-report"
EXIT_CONFIG, EXIT_SEND = 2, 3


def resolve_kind(kind: str, now: datetime) -> str:
    if kind != "auto":
        return kind
    return "weekly" if now.astimezone(UTC).weekday() == 6 else "daily"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("kind", choices=("daily", "weekly", "auto"))
    ap.add_argument("--send", action="store_true", help="e-mail it (default: print only)")
    ap.add_argument("--force", action="store_true", help="send even if today's marker exists")
    ap.add_argument("--mail-env", type=Path, default=None, help="mail config file (KEY=VALUE)")
    ap.add_argument("--now", default=None, help="ISO time to report as of (tests, backfills)")
    args = ap.parse_args(argv)

    now = datetime.fromisoformat(args.now) if args.now else datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    kind = resolve_kind(args.kind, now)
    stamp = f"{kind}-{now.astimezone(UTC):%Y-%m-%d}"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    marker = OUT_DIR / f"sent-{stamp}.json"

    data = collect_digest(ROOT, now, kind)
    text = render_digest(data)
    subject = digest_subject(data)
    (OUT_DIR / f"{stamp}.md").write_text(text, encoding="utf-8")
    print(f"{now.astimezone(UTC):%Y-%m-%dT%H:%M:%SZ} {subject}")
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
    message = build_message(config, subject, text, markdown_to_html(text))
    try:
        send_message(config, message)
    except Exception as exc:  # report the class and message only; never the config
        print(f"send failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_SEND
    marker.write_text(
        json.dumps(
            {
                "sent_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "subject": subject,
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
