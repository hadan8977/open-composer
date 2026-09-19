"""The slim cockpit entrypoint must stay slim, and must refuse a wildcard bind.

``oc cockpit serve`` pays ~135MB for the Typer app's module-scope imports before
any cockpit code runs; ``python -m open_composer.cockpit`` exists so the 24/7
service path does not. Measured on this box: 95MB slim vs 156MB via ``oc``.
"""

from __future__ import annotations

import subprocess
import sys

from open_composer.cockpit.__main__ import UNSAFE_HOSTS, build_parser, main

HEAVY_MODULES = ("pandas", "lightgbm", "sklearn", "duckdb", "alpaca", "nautilus_trader", "openai")


def test_parser_defaults_to_loopback() -> None:
    args = build_parser().parse_args([])
    assert args.host == "127.0.0.1"
    assert args.port == 8770


def test_main_refuses_wildcard_hosts(capsys) -> None:
    for host in sorted(UNSAFE_HOSTS):
        assert main(["--host", host]) == 1
        assert "Refusing to bind" in capsys.readouterr().err


def test_entrypoint_does_not_import_the_cli_or_the_heavy_stack() -> None:
    """Importing the entrypoint must not drag in the CLI's dependency graph.

    This is the property that keeps the daemon at ~95MB; if someone adds a
    module-scope import of open_composer.cli (or of the heavy research stack)
    here or in open_composer.cockpit.app, the resident cost silently doubles.
    """
    code = (
        "import sys;"
        "import open_composer.cockpit.__main__;"
        "from open_composer.cockpit.app import create_app;"
        "create_app();"
        "leaked=[m for m in ('open_composer.cli',)+"
        f"{HEAVY_MODULES!r} if m in sys.modules];"
        "print(','.join(leaked))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "", f"cockpit import leaked heavy modules: {result.stdout}"
