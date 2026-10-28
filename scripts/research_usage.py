"""One account-usage snapshot per existing research round; never changes authority.

Read-only RPC: https://learn.chatgpt.com/docs/app-server#6-rate-limits-chatgpt
No thread/turn, manager, reset-credit, timer or pause API is invoked.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
import selectors
import signal
import subprocess
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens")


def now() -> str:
    return datetime.now(UTC).isoformat()


def weekly_windows(result: dict) -> list[dict]:
    buckets = result.get("rateLimitsByLimitId")
    if not isinstance(buckets, dict) or not buckets:
        bucket = result.get("rateLimits")
        if not isinstance(bucket, dict):
            raise ValueError("Account rate-limit windows unavailable")
        buckets = {bucket.get("limitId") or "account": bucket}
    windows = []
    for limit_id, bucket in buckets.items():
        if not isinstance(bucket, dict):
            continue
        for window_name in ("primary", "secondary"):
            window = bucket.get(window_name)
            if not isinstance(window, dict) or window.get("windowDurationMins") != 10080:
                continue
            used = window.get("usedPercent")
            if (
                not isinstance(used, (int, float))
                or isinstance(used, bool)
                or not math.isfinite(used)
                or not 0 <= used <= 100
            ):
                raise ValueError("Invalid weekly used percentage")
            reset = window.get("resetsAt")
            if reset is not None and (not isinstance(reset, int) or isinstance(reset, bool)):
                raise ValueError("Invalid weekly reset timestamp")
            windows.append(
                {
                    "limit_id": str(limit_id),
                    "window": window_name,
                    "window_minutes": 10080,
                    "used_percent": used,
                    "remaining_percent": 100 - used,
                    "resets_at": reset,
                    "resets_at_utc": datetime.fromtimestamp(reset, UTC).isoformat()
                    if reset is not None
                    else None,
                }
            )
    if not windows:
        raise ValueError("No identified weekly account window returned")
    return windows


def read_account_limits(timeout: float = 20, *, popen=None) -> dict:
    """Initialize a finite stdio client and issue exactly one read-only request."""
    if not math.isfinite(timeout) or not 0 < timeout <= 60:
        raise ValueError("Usage timeout must be finite and at most60 seconds")
    popen = subprocess.Popen if popen is None else popen
    process = None
    selector = selectors.DefaultSelector()
    try:
        process = popen(
            ["codex", "app-server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
            start_new_session=True,
        )
        selector.register(process.stdout, selectors.EVENT_READ)

        def send(message):
            process.stdin.write((json.dumps(message) + "\n").encode())
            process.stdin.flush()

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
        deadline, pending, requested = time.monotonic() + timeout, b"", False
        while (remaining := deadline - time.monotonic()) > 0:
            if not selector.select(timeout=min(1, remaining)):
                continue
            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk:
                raise RuntimeError("Account-usage transport ended before a response")
            pending += chunk
            if len(pending) > 2_000_000:
                raise ValueError("Account-usage response exceeded the finite buffer")
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                try:
                    response = json.loads(line)
                except json.JSONDecodeError:
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
                    result = response.get("result")
                    if not isinstance(result, dict):
                        raise ValueError("Account-usage RPC returned no result object")
                    return result
        raise TimeoutError("Account-usage read timed out")
    finally:
        selector.close()
        if process is not None:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            for stream in (process.stdin, process.stdout):
                if stream is not None:
                    stream.close()


def completed_tokens(state: dict) -> dict:
    phases, totals, missing = {}, {}, []
    for name, phase in state.get("phases", {}).items():
        if not isinstance(phase, dict) or (
            phase.get("exit_code") is None and phase.get("status") not in ("complete", "blocked")
        ):
            continue
        usage = phase.get("usage")
        tokens = {
            key: usage[key]
            for key in TOKEN_FIELDS
            if isinstance(usage, dict)
            and isinstance(usage.get(key), int)
            and not isinstance(usage[key], bool)
            and usage[key] >= 0
        }
        phases[name] = tokens
        if len(tokens) != len(TOKEN_FIELDS):
            missing.append(name)
        for key, count in tokens.items():
            totals[key] = totals.get(key, 0) + count
    return {
        "source": "run.json completed-phase usage events",
        "by_phase": phases,
        "observed_totals": totals,
        "phases_with_missing_fields": missing,
        "scope": "Completed phases in this round only; ongoing lead and other sessions excluded. "
        "Cached input is part of input, not an additional token total. Missing usage is unknown.",
    }


def existing_run(root: Path, folder: Path) -> tuple[Path, dict]:
    root, folder = root.resolve(), (root / folder).resolve()
    if not folder.is_relative_to(root):
        raise ValueError("Usage requires an existing run inside this repository")
    parts = folder.relative_to(root).parts
    if len(parts) != 4 or parts[0] != "research" or parts[2] != "runs" or not folder.is_dir():
        raise ValueError("Use an existing research/<direction>/runs/<id> directory")
    state = json.loads((folder / "run.json").read_text())
    if state.get("direction") != parts[1] or state.get("run_id") != parts[3]:
        raise ValueError("Run identity does not match its directory")
    return folder, state


def record_usage(root: Path, folder: Path, *, reader=None, timeout: float = 20) -> dict:
    """Reuse an immutable snapshot, including an unavailable/interrupted reading."""
    folder, state = existing_run(root, folder)
    with (folder / ".usage.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Usage measurement already running for this round") from exc
        snapshot = folder / "usage.json"
        if snapshot.exists():
            return json.loads(snapshot.read_text())
        attempt = folder / "usage-attempt.json"
        report = {
            "schema_version": 1,
            "run": str(folder.relative_to(root.resolve())),
            "observed_at_utc": now(),
            "account_usage": {
                "available": False,
                "method": "codex app-server account/rateLimits/read",
                "scope": "Shared authenticated account; not attributable to this project/round. "
                "Do not add percentages across limit buckets or infer dollars from phase tokens.",
            },
            "completed_phase_tokens": completed_tokens(state),
            "authority_changed": False,
            "automatic_stop": False,
        }
        if attempt.exists():
            report["account_usage"]["unavailable_reason"] = "previous_measurement_incomplete"
        else:
            with attempt.open("x") as output:
                json.dump({"started_at_utc": now(), "helper_pid": os.getpid()}, output)
                output.flush()
                os.fsync(output.fileno())
            try:
                result = (read_account_limits if reader is None else reader)(timeout)
                report["account_usage"].update(
                    available=True, weekly_windows=weekly_windows(result)
                )
            except (OSError, ValueError, RuntimeError, TimeoutError, OverflowError) as error:
                # Do not expose arbitrary provider/auth error messages or read credentials here.
                report["account_usage"]["unavailable_reason"] = type(error).__name__
        temporary = folder / "usage.json.tmp"
        with temporary.open("w") as output:
            json.dump(report, output, indent=2, allow_nan=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(snapshot)
        return report


def main() -> int:
    def interrupted(signum, _frame):
        raise InterruptedError(f"Usage helper interrupted by signal{signum}")

    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=20)
    args = parser.parse_args()
    print(json.dumps(record_usage(ROOT, args.run, timeout=args.timeout_seconds), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
