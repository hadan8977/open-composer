"""Offline tests; no relay, credentials or LLM required."""

from __future__ import annotations

import fcntl
import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import hadan_availability_watch as watcher  # noqa: E402

NOW = datetime(2026, 10, 12, 3, tzinfo=UTC)  # Monday 11:00 Beijing.
CONFIG = json.loads((watcher.ROOT / "config/hadan-availability-watch.json").read_text())


def ready(now=NOW):
    return {
        "probe_result": "completed",
        "online": True,
        "preflight_ok": True,
        "worker_status": "ready",
        "usage_ok": True,
        "usage_bytes": 4 * (1 << 30),
        "usage_gib": 4.0,
        "root_ok": True,
        "paused": False,
        "hard_off": False,
        "worker_updated_at_utc": watcher.iso(now),
    }


def admitted_hold(*, research=True, training=False):
    return {
        "research_paused": False,
        "hadan": {
            "research_allowed": research,
            "availability_monitoring": {"authorized": True},
        },
        "training": {"training_allowed": training},
    }


class AvailabilityTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        control = self.root / "reports/research/control"
        control.mkdir(parents=True)
        (control / "owner-compute-hold.json").write_text(json.dumps(admitted_hold()))

    def test_ready_requires_every_condition_and_no_training(self):
        result = watcher.summarize(ready(), NOW, CONFIG)
        self.assertTrue(result["ready_as_of_probe"])
        self.assertFalse(result["training_allowed"])
        self.assertFalse(result["automatic_dispatch"])
        for field, value in (
            ("online", False),
            ("preflight_ok", False),
            ("worker_status", "paused"),
            ("worker_status", "hard_off"),
            ("worker_status", "offline"),
            ("worker_status", "unknown"),
            ("usage_ok", False),
            ("usage_bytes", 50 * (1 << 30)),
            ("usage_bytes", 51 * (1 << 30)),
            ("usage_bytes", None),
            ("usage_bytes", -1),
            ("usage_bytes", True),
            ("usage_bytes", 1.0),
            ("usage_bytes", float("nan")),
            ("usage_bytes", float("inf")),
            ("usage_bytes", 1 << 10000),
            ("root_ok", False),
            ("paused", True),
            ("hard_off", True),
            ("worker_updated_at_utc", watcher.iso(NOW - timedelta(seconds=121))),
            ("worker_updated_at_utc", watcher.iso(NOW + timedelta(seconds=31))),
            ("worker_updated_at_utc", None),
            ("probe_result", "timeout"),
        ):
            with self.subTest(field=field, value=value):
                probe = ready()
                probe[field] = value
                self.assertFalse(watcher.summarize(probe, NOW, CONFIG)["ready_as_of_probe"])

    def test_changes_due_and_recovery_are_local_only(self):
        calls = []

        def probe(timeout):
            calls.append(timeout)
            return ready()

        first = watcher.watch(self.root, CONFIG, now=NOW, probe=probe)
        self.assertTrue(first["coordination_requested"])
        self.assertEqual(
            watcher.watch(self.root, CONFIG, now=NOW + timedelta(minutes=14), probe=probe)[
                "action"
            ],
            "not_due",
        )
        self.assertEqual(len(calls), 1)
        paused = ready(NOW + timedelta(minutes=15))
        paused.update(worker_status="paused", paused=True)
        watcher.watch(self.root, CONFIG, now=NOW + timedelta(minutes=15), probe=lambda _: paused)
        recovered = watcher.watch(
            self.root,
            CONFIG,
            now=NOW + timedelta(minutes=30),
            probe=lambda _: ready(NOW + timedelta(minutes=30)),
        )
        self.assertTrue(recovered["coordination_requested"])
        events = (self.root / CONFIG["event_path"]).read_text().splitlines()
        self.assertEqual(len(events), 3)
        unchanged = watcher.watch(
            self.root,
            CONFIG,
            now=NOW + timedelta(minutes=45),
            probe=lambda _: ready(NOW + timedelta(minutes=45)),
        )
        self.assertFalse(unchanged["coordination_requested"])
        self.assertEqual(len((self.root / CONFIG["event_path"]).read_text().splitlines()), 3)

    def test_cadence_weekends_and_owner_hold(self):
        self.assertEqual(watcher.interval_minutes(NOW, CONFIG), 15)
        self.assertEqual(watcher.interval_minutes(NOW - timedelta(days=1), CONFIG), 60)
        self.assertEqual(watcher.interval_minutes(NOW + timedelta(hours=8), CONFIG), 60)
        (self.root / "reports/research/control/owner-compute-hold.json").write_text("{}")
        result = watcher.watch(self.root, CONFIG, now=NOW, probe=lambda _: ready())
        self.assertEqual(result["action"], "authorization_skipped")
        self.assertFalse(result["coordination_requested"])

    def test_pause_unknown_and_observation_denial_never_probe(self):
        hold_path = self.root / "reports/research/control/owner-compute-hold.json"
        paused = admitted_hold(training=True)
        paused["research_paused"] = True
        denied = admitted_hold(training=True)
        denied["hadan"]["availability_monitoring"]["authorized"] = False
        unknown = admitted_hold(training=True)
        del unknown["research_paused"]
        for content in (
            None,
            "{broken",
            "[]",
            "{}",
            json.dumps(paused),
            json.dumps(denied),
            json.dumps(unknown),
        ):
            with self.subTest(content=content):
                if content is None:
                    hold_path.unlink(missing_ok=True)
                else:
                    hold_path.write_text(content)
                with patch.object(watcher, "run_probe") as probe:
                    result = watcher.watch(self.root, CONFIG, now=NOW, probe=probe)
                probe.assert_not_called()
                self.assertEqual(result["action"], "authorization_skipped")
                self.assertFalse(result["training_allowed"])
                self.assertFalse(result["coordination_requested"])

    def test_current_pause_is_checked_before_cached_not_due(self):
        watcher.watch(self.root, CONFIG, now=NOW, probe=lambda _: ready())
        hold = admitted_hold(training=True)
        hold["research_paused"] = True
        (self.root / "reports/research/control/owner-compute-hold.json").write_text(
            json.dumps(hold)
        )
        with patch.object(watcher, "run_probe") as probe:
            result = watcher.watch(self.root, CONFIG, now=NOW + timedelta(minutes=1), probe=probe)
        probe.assert_not_called()
        self.assertEqual(result["action"], "authorization_skipped")
        self.assertFalse(result["training_authorized"])

    def test_observation_permission_does_not_grant_research_or_training(self):
        hold = admitted_hold(research=False, training=True)
        (self.root / "reports/research/control/owner-compute-hold.json").write_text(
            json.dumps(hold)
        )
        with patch.object(watcher, "run_probe", return_value=ready()) as probe:
            result = watcher.watch(self.root, CONFIG, now=NOW, probe=probe)
        probe.assert_called_once()
        self.assertTrue(result["ready_as_of_probe"])
        self.assertFalse(result["research_authorized"])
        self.assertFalse(result["training_authorized"])
        self.assertFalse(result["training_allowed"])
        self.assertFalse(result["coordination_requested"])
        self.assertEqual(result["coordination_scope"], "availability_observation_only")

    def test_permission_revoked_during_probe_cannot_coordinate(self):
        hold_path = self.root / "reports/research/control/owner-compute-hold.json"
        hold_path.write_text(json.dumps(admitted_hold(training=True)))

        def probe(_):
            hold = admitted_hold(training=True)
            hold["research_paused"] = True
            hold_path.write_text(json.dumps(hold))
            return ready()

        result = watcher.watch(self.root, CONFIG, now=NOW, probe=probe)
        self.assertFalse(result["training_allowed"])
        self.assertFalse(result["coordination_requested"])

    def test_child_entry_checks_authorization_before_remote_preflight(self):
        from open_composer.remote import windows_worker

        with patch.object(watcher, "ROOT", self.root):
            (self.root / "reports/research/control/owner-compute-hold.json").write_text("{}")
            with patch.object(windows_worker, "worker_preflight") as preflight:
                with patch("builtins.print"):
                    watcher.probe_child()
            preflight.assert_not_called()

    def test_exact_bytes_accept_a_below_limit_usage_rounded_to_50_gib(self):
        probe = ready()
        probe.update(usage_bytes=watcher.USAGE_LIMIT_BYTES - 1, usage_gib=50.0)
        result = watcher.summarize(probe, NOW, CONFIG)
        self.assertTrue(result["ready_as_of_probe"])

    def test_training_correction_coordinates_an_already_ready_worker(self):
        first = watcher.watch(self.root, CONFIG, now=NOW, probe=lambda _: ready())
        self.assertFalse(first["training_authorized"])
        self.assertFalse(first["training_allowed"])
        hold_path = self.root / "reports/research/control/owner-compute-hold.json"
        hold = admitted_hold(training=True)
        hold_path.write_text(json.dumps(hold))
        later = NOW + timedelta(minutes=15)
        result = watcher.watch(self.root, CONFIG, now=later, probe=lambda _: ready(later))
        self.assertTrue(result["training_authorized"])
        self.assertTrue(result["training_allowed"])
        self.assertTrue(result["coordination_requested"])
        self.assertEqual(
            result["coordination_scope"], "already_authorized_research_including_training"
        )
        self.assertFalse(result["automatic_dispatch"])
        hold["training"]["training_allowed"] = False
        hold_path.write_text(json.dumps(hold))
        later += timedelta(minutes=15)
        result = watcher.watch(self.root, CONFIG, now=later, probe=lambda _: ready(later))
        self.assertFalse(result["training_allowed"])
        self.assertFalse(result["coordination_requested"])

    def test_training_authorization_preserves_device_and_freshness_controls(self):
        hold_path = self.root / "reports/research/control/owner-compute-hold.json"
        hold_path.write_text(json.dumps(admitted_hold(training=True)))
        for index, (field, value) in enumerate(
            (
                ("paused", True),
                ("hard_off", True),
                ("worker_status", "unknown"),
                ("usage_bytes", 50 * (1 << 30)),
                ("usage_ok", False),
                ("root_ok", False),
                ("preflight_ok", False),
                ("worker_updated_at_utc", watcher.iso(NOW - timedelta(seconds=121))),
            )
        ):
            with self.subTest(field=field):
                later = NOW + timedelta(minutes=15 * index)
                probe = ready(later)
                probe[field] = value
                result = watcher.watch(self.root, CONFIG, now=later, probe=lambda _, p=probe: p)
                self.assertTrue(result["training_authorized"])
                self.assertFalse(result["training_allowed"])
                self.assertFalse(result["coordination_requested"])
                self.assertFalse(result["automatic_dispatch"])

    def test_overlap_never_probes(self):
        lock_path = self.root / CONFIG["lock_path"]
        with lock_path.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = watcher.watch(
                self.root, CONFIG, now=NOW, probe=lambda _: self.fail("overlap probed")
            )
        self.assertEqual(result["action"], "overlap_skipped")

    def test_no_raw_credentials_or_errors_persist(self):
        secret = "https://app.paseo.sh/#offer=secret-credential"
        payload = {
            "ok": True,
            "contract": {"offer_file": secret},
            "stderr": secret,
            "remote": {
                "worker_status": {
                    "status": secret,
                    "root": secret,
                    "usage_gib": secret,
                    "updated_at_utc": secret,
                }
            },
        }
        filtered = watcher.safe_probe(payload)
        filtered.update(probe_result="completed", stdout=secret, error=secret)
        watcher.watch(self.root, CONFIG, now=NOW, probe=lambda _: filtered)
        for name in ("state_path", "event_path"):
            text = (self.root / CONFIG[name]).read_text()
            self.assertNotIn("secret-credential", text)
            self.assertNotIn("offer_file", text)
            self.assertNotIn("stdout", text)

    def test_timeout_kills_group_once_and_discards_stdout(self):
        import subprocess

        class Process:
            pid = 123
            calls = 0

            def communicate(self, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise subprocess.TimeoutExpired("probe", 1, output="secret-credential")
                return "secret-credential", None

        process = Process()
        with patch.object(watcher.subprocess, "Popen", return_value=process) as popen:
            with patch.object(watcher.os, "killpg") as kill:
                result = watcher.run_probe(1)
        self.assertEqual(result, {"probe_result": "timeout"})
        self.assertEqual(popen.call_count, 1)
        self.assertEqual(kill.call_count, 1)
        self.assertTrue(popen.call_args.kwargs["start_new_session"])


if __name__ == "__main__":
    unittest.main()
