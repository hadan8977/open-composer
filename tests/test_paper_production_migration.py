"""Versioned-source boundaries of the six-policy paper runtime; no broker clients."""

import ast
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from open_composer.market_sessions import us_equity_session_dates
from open_composer.paper_runtime import source_loader
from open_composer.paper_runtime.paths import RUNTIME


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket

    def denied(*args, **kwargs):
        raise AssertionError("production migration checks cannot access a broker or data source")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def test_frozen_loader_executes_package_copy_under_historical_path(tmp_path, monkeypatch):
    root, package = tmp_path / "repo", tmp_path / "package"
    relative = Path("reports/research/program/fixture/math.py")
    body = (
        b"from pathlib import Path\ndef f(x): return x * 1.25 + 2\n"
        b"def own(): return Path(__file__).read_bytes()\n"
    )
    (package / "fixture").mkdir(parents=True)
    (package / "fixture/math.py").write_bytes(body)
    monkeypatch.setattr(source_loader, "FROZEN", package)
    module = source_loader.load_source("migration_math", root / relative, root=root)
    assert module.f(4) == 7
    assert module.own() == body
    assert module.__file__ == str(root / relative)
    assert not (root / relative).exists()
    with pytest.raises(FileNotFoundError):
        source_loader.load_source("unlisted", root / relative.with_name("other.py"), root=root)


def test_frozen_math_preserves_accepted_h5_calendar():
    from open_composer.paper_runtime.six import formation_continuity as formation

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


def test_entry_commands_use_versioned_modules_and_pinned_inference():
    from open_composer.paper_runtime.six.run_dated_refresh import commands

    rows = commands(Path("/tmp/offline-staging"), "2026-10-28")
    assert [name for name, cap, cmd in rows] == [
        "source",
        "prepare",
        "inference",
        "finish",
    ]
    assert [cap for name, cap, cmd in rows] == [100, 600, 700, 200]
    for name, _cap, cmd in rows:
        assert cmd[1] == "-m" and cmd[2].startswith("open_composer.paper_runtime.six.")
        if name == "inference":
            assert Path(cmd[0]).as_posix() == "/usr/bin/python3.12"


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
    with pytest.raises(ValueError, match="state is missing"):
        six_paper_service.main()
    assert not (tmp_path / RUNTIME).exists()
