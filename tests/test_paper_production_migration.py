"""Offline ledger relocation and versioned-source boundaries; no broker clients."""

import ast
import fcntl
import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from open_composer.market_sessions import us_equity_session_dates
from open_composer.paper_runtime import migrate, source_loader
from open_composer.paper_runtime.paths import LEGACY, RUNTIME

MAINTENANCE = datetime(2026, 10, 28, 4, tzinfo=UTC)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket

    def denied(*args, **kwargs):
        raise AssertionError("production migration checks cannot access a broker or data source")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


@pytest.fixture
def legacy(tmp_path):
    old = tmp_path / LEGACY
    (old / "targets").mkdir(parents=True)
    state = dict(
        books={"BASE": {"positions": {"AAPL": 11}, "consumed_ids": ["never-replay"]}},
        orders={"pending-id": {"status": "unknown"}},
        baseline={"BASE": {"path": "historical-checkpoint"}},
        risk={"BASE": {"killed": True}},
    )
    (old / "runtime-state.json").write_text(json.dumps(state) + "\n")
    (old / "runtime-state.events.jsonl").write_text('{"signal_id":"original-signal"}\n')
    (old / "owner-authorization.json").write_text('{"paper_only":true,"id":"same-authority"}')
    for policy in migrate.POLICIES:
        (old / "targets" / (policy + ".json")).write_text(json.dumps(dict(policy=policy)))
    return tmp_path


def offline(root):
    return migrate.migrate(root, apply=True, now=MAINTENANCE, stopped_check=lambda: None)


def test_copy_preserves_every_byte_and_retains_originals(legacy):
    expected = migrate.inventory(legacy)
    assert migrate.migrate(legacy)["status"] == "plan_only"
    assert not (legacy / RUNTIME).exists()
    result = offline(legacy)
    assert result["status"] == "copied_and_verified"
    for name in expected:
        assert (legacy / LEGACY / name).read_bytes() == (legacy / RUNTIME / name).read_bytes()
    assert migrate.inventory(legacy) == expected


def test_rerun_never_overwrites_progressed_ledger(legacy):
    offline(legacy)
    state = legacy / RUNTIME / "runtime-state.json"
    state.write_text('{"new_fill":"after-migration"}')
    result = offline(legacy)
    assert result["status"] == "already_migrated_no_overwrite"
    assert json.loads(state.read_text()) == {"new_fill": "after-migration"}


def test_refuse_active_lock_partial_destination_and_rth(legacy):
    with (legacy / LEGACY / "runtime-state.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            offline(legacy)
    with pytest.raises(ValueError, match="outside"):
        migrate.migrate(
            legacy,
            apply=True,
            now=datetime(2026, 10, 28, 14, tzinfo=UTC),
            stopped_check=lambda: None,
        )
    (legacy / RUNTIME).mkdir()
    with pytest.raises(ValueError, match="unmarked"):
        offline(legacy)


def test_source_change_during_copy_never_publishes(legacy, monkeypatch):
    original = migrate.shutil.copy2

    def changed(source, target):
        result = original(source, target)
        if source.name == "owner-authorization.json":
            source.write_text('{"paper_only":true,"id":"changed-during-copy"}')
        return result

    monkeypatch.setattr(migrate.shutil, "copy2", changed)
    with pytest.raises(ValueError, match="changed during migration"):
        offline(legacy)
    assert not (legacy / RUNTIME).exists()
    assert list((legacy / RUNTIME).parent.glob(".six-migration-*"))


def test_frozen_loader_reads_and_executes_only_versioned_bytes(tmp_path, monkeypatch):
    root, package = tmp_path / "repo", tmp_path / "package"
    relative = Path("reports/research/program/fixture/math.py")
    body = (
        b"from pathlib import Path\ndef f(x): return x * 1.25 + 2\n"
        b"def own(): return Path(__file__).read_bytes()\n"
    )
    package.mkdir()
    (package / "math.py").write_bytes(body)
    monkeypatch.setattr(source_loader, "PACKAGE", package)
    monkeypatch.setattr(
        source_loader,
        "FILES",
        {
            str(relative): dict(
                package_path="math.py", bytes=len(body), sha256=hashlib.sha256(body).hexdigest()
            )
        },
    )
    module = source_loader.load_source("migration_math", root / relative, root=root)
    assert module.f(4) == 7
    assert module.own() == body
    assert module.__file__ == str(root / relative)
    assert not (root / relative).exists()
    (package / "math.py").write_bytes(body + b"# changed")
    with pytest.raises(ValueError, match="hash differs"):
        source_loader.load_source("migration_math_changed", root / relative, root=root)
    with pytest.raises(KeyError):
        source_loader.load_source("unlisted", root / relative.with_name("other.py"), root=root)


def test_manifest_and_frozen_math_preserve_accepted_h5_calendar():
    from open_composer.paper_runtime.six import formation_continuity as formation

    for name in source_loader.FILES:
        source_loader.source_bytes(name)
    path = Path("reports/research/program/paper-launch-20min-20261021/formation_continuity.py")
    body = source_loader.source_bytes(path)
    node = next(
        n for n in ast.parse(body).body if isinstance(n, ast.FunctionDef) and n.name == "phase"
    )
    namespace = dict(
        date=date,
        timedelta=timedelta,
        us_equity_session_dates=us_equity_session_dates,
        require=formation.require,
    )
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(path), "exec"
        ),
        namespace,
    )
    for day in ("2026-10-23", "2026-10-27", "2026-10-30", "2026-11-03"):
        assert formation.phase(day) == namespace["phase"](day)
    assert formation.phase("2026-10-27")["next_application"] == "2026-11-02"


def test_migration_preserves_numerical_bodies_and_entire_lstm_inference_body():
    from open_composer.paper_runtime.six import produce_targets

    class NormalizePaths(ast.NodeTransformer):
        def visit_Call(self, node):
            node = self.generic_visit(node)
            if isinstance(node.func, ast.Name) and node.func.id == "runtime_root":
                return ast.Name(id="OLD", ctx=ast.Load())
            if isinstance(node.func, ast.Name) and node.func.id == "source_bytes":
                return ast.Call(
                    func=ast.Attribute(value=node.args[0], attr="read_text", ctx=ast.Load()),
                    args=[],
                    keywords=[],
                )
            node.keywords = [
                k
                for k in node.keywords
                if not (
                    k.arg == "strict"
                    and isinstance(k.value, ast.Constant)
                    and k.value.value is False
                )
            ]
            return node

        def visit_Attribute(self, node):
            node = self.generic_visit(node)
            if (
                isinstance(node.value, ast.Name)
                and node.value.id == "timezone"
                and node.attr == "utc"
            ):
                return ast.Name(id="UTC", ctx=ast.Load())
            return node

        def visit_Name(self, node):
            if node.id == "_actions":
                node.id = "actions"
            return node

    legacy = "reports/research/program/paper-launch-20min-20261021/"
    old = ast.parse(source_loader.source_bytes(legacy + "produce_targets.py"))
    new = ast.parse(Path(produce_targets.__file__).read_text())
    for name in ("prepare", "prepare_core", "target", "dated", "session_clocks"):
        nodes = [
            next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
            for tree in (old, new)
        ]
        assert ast.dump(NormalizePaths().visit(nodes[0])) == ast.dump(
            NormalizePaths().visit(nodes[1])
        )

    def inference(tree):
        start = next(
            i
            for i, n in enumerate(tree.body)
            if isinstance(n, ast.Expr)
            and isinstance(n.value, ast.Call)
            and isinstance(n.value.func, ast.Attribute)
            and n.value.func.attr == "set_num_threads"
        )
        return ast.dump(ast.Module(body=tree.body[start:], type_ignores=[]))

    old = ast.parse(source_loader.source_bytes(legacy + "lstm_infer.py"))
    new = ast.parse((Path(produce_targets.__file__).parent / "lstm_infer.py").read_text())
    assert inference(old) == inference(new)


def test_entry_commands_use_versioned_modules_and_pinned_inference():
    from open_composer.paper_runtime.six.run_dated_refresh import commands

    rows = commands(Path("/tmp/offline-staging"), "2026-10-28")
    assert [name for name, cap, cmd in rows] == [
        "source",
        "prepare",
        "inference",
        "assemble",
        "finish",
    ]
    assert [cap for name, cap, cmd in rows] == [100, 600, 700, 200, 200]
    for name, _cap, cmd in rows:
        assert cmd[1] == "-m" and cmd[2].startswith("open_composer.paper_runtime.six.")
        if name == "inference":
            assert cmd[0] == "/usr/bin/python3.12"


def test_active_base_dependency_imports_execute_from_package():
    from open_composer.paper_runtime.six import produce_targets as producer

    with producer.ni.future_modules():
        for name, path in (
            ("features", producer.ni.FUTURE / "features.py"),
            ("retained", producer.ni.FUTURE / "retained_sources.py"),
            ("bridge", producer.ni.BASE / "bridge.py"),
        ):
            module = source_loader.load_source("migration_" + name, path, root=producer.REPO)
            assert isinstance(module.__loader__, source_loader.FrozenLoader)
            assert module.__file__ == str(path)


def test_missing_relocated_ledger_cannot_initialize_new_capital(tmp_path, monkeypatch):
    import sys

    from open_composer.intraday_runner import six_paper_service

    config = tmp_path / "service.json"
    config.write_text(
        json.dumps(
            dict(
                authorization="runtime/paper/six/owner-authorization.json",
                targets_root="runtime/paper/six/targets",
            )
        )
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "six",
            "--root",
            str(tmp_path),
            "--config",
            str(config),
            "--state",
            str(tmp_path / RUNTIME / "runtime-state.json"),
        ],
    )
    with pytest.raises(ValueError, match="migration is required"):
        six_paper_service.main()
    assert not (tmp_path / RUNTIME).exists()
