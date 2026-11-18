"""One account-usage snapshot per existing research round; never changes authority.

Read-only RPC: https://learn.chatgpt.com/docs/app-server#6-rate-limits-chatgpt
No thread/turn, manager, reset-credit, timer or pause API is invoked.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from open_composer.research.agent_workflow import (  # noqa: E402
    completed_tokens,
    summarize_runs,
)


def weekly_windows(result: dict) -> list[dict]:
    buckets = result.get("rateLimitsByLimitId") or {
        result["rateLimits"].get("limitId") or "account": result["rateLimits"]
    }
    windows = []
    for limit_id, bucket in buckets.items():
        for window_name in ("primary", "secondary"):
            window = (bucket or {}).get(window_name)
            if not isinstance(window, dict) or window.get("windowDurationMins") != 10080:
                continue
            used = window["usedPercent"]
            if type(used) not in (int, float) or not 0 <= used <= 100:
                raise ValueError("Invalid weekly used percentage")
            reset = window.get("resetsAt")
            windows.append(
                {
                    "limit_id": str(limit_id),
                    "window": window_name,
                    "window_minutes": 10080,
                    "used_percent": used,
                    "remaining_percent": 100 - used,
                    "resets_at": reset,
                    "resets_at_utc": None
                    if reset is None
                    else datetime.fromtimestamp(reset, UTC).isoformat(),
                }
            )
    if not windows:
        raise ValueError("No identified weekly account window returned")
    return windows


def _default_popen(command, **kwargs):
    if os.name != "nt":
        return subprocess.Popen(command, **kwargs)
    from open_composer.research.platform_runtime import capped_process

    return capped_process(command, root=ROOT, mem="900M", cwd=ROOT, **kwargs)


def read_account_limits(timeout: float = 20, *, popen=None) -> dict:
    """Start `codex app-server`, issue exactly one read-only request, then kill it."""
    process = (popen or _default_popen)(
        ["codex", "app-server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # POSIX: kill the group below; ignored on Windows
    )
    lines = queue.Queue()

    def read_lines():  # a thread, because Windows cannot select() on pipes
        for line in iter(process.stdout.readline, b""):
            lines.put(line)
        lines.put(b"")

    def send(message):
        process.stdin.write((json.dumps(message) + "\n").encode())
        process.stdin.flush()

    reader = threading.Thread(target=read_lines, name="oc-account-usage-reader", daemon=True)
    with process:
        reader.start()
        try:
            send(
                {
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "clientInfo": {"name": "oc-research-usage", "version": "1"},
                        "capabilities": {"experimentalApi": True},
                    },
                }
            )
            deadline, requested = time.monotonic() + timeout, False
            while (remaining := deadline - time.monotonic()) > 0:
                try:
                    line = lines.get(timeout=remaining)
                except queue.Empty:
                    break
                if not line:
                    raise RuntimeError("Account-usage transport ended before a response")
                try:
                    response = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(response, dict):
                    continue
                if response.get("id") in (1, 2) and "error" in response:
                    raise RuntimeError("Account-usage RPC rejected; no authority change")
                if response.get("id") == 1 and not requested:
                    send({"method": "initialized", "params": {}})
                    send({"id": 2, "method": "account/rateLimits/read", "params": {}})
                    requested = True
                elif response.get("id") == 2 and requested:
                    return response["result"]
            raise TimeoutError("Account-usage read timed out")
        finally:
            if os.name == "nt":
                process.kill()  # a WindowsProcess kills its whole job
            else:
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
            reader.join(timeout=5)


def record_usage(root: Path, folder: Path, *, reader=None, timeout: float = 20) -> dict:
    """Read the account once per round; later calls only refresh local phase tokens."""
    folder = root / folder
    state = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    snapshot = folder / "usage.json"
    if snapshot.exists():
        report = json.loads(snapshot.read_text(encoding="utf-8"))
        report["completed_phase_tokens"] = completed_tokens(state)
    else:
        report = {
            "schema_version": 1,
            "run": folder.relative_to(root).as_posix(),
            "observed_at_utc": datetime.now(UTC).isoformat(),
            "account_usage": {
                "available": False,
                "method": "codex app-server account/rateLimits/read",
                "scope": "Shared authenticated account; not attributable to this project/round. "
                "Do not add percentages across limit buckets or infer dollars from phase tokens.",
            },
            "completed_phase_tokens": completed_tokens(state),
        }
        try:
            result = (reader or read_account_limits)(timeout)
            report["account_usage"].update(available=True, weekly_windows=weekly_windows(result))
        except (OSError, ValueError, KeyError, RuntimeError, MemoryError) as error:
            # Do not expose arbitrary provider/auth error messages here.
            report["account_usage"]["unavailable_reason"] = type(error).__name__
    snapshot.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--run", type=Path)
    source.add_argument("--summary", action="store_true", help="Summarize all saved runs; no RPC")
    parser.add_argument("--timeout-seconds", type=float, default=20)
    args = parser.parse_args()
    result = (
        summarize_runs(ROOT)
        if args.summary
        else record_usage(ROOT, args.run, timeout=args.timeout_seconds)
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
