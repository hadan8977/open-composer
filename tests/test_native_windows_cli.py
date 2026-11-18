"""Windows research help must not import the Linux book-paper runtime."""
import os
import sys

import pytest
from typer.testing import CliRunner

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Native Windows entry-point boundary")


def test_research_help_does_not_import_linux_book_runtime():
    from open_composer.cli import app

    result = CliRunner().invoke(app, ["research", "--help"])
    assert result.exit_code == 0, result.output
    assert "Usage" in result.output
    assert "open_composer.book_paper.cli" not in sys.modules


def test_root_help_remains_available():
    from open_composer.cli import app

    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0, result.output
    assert "research" in result.output and "book-paper" in result.output


@pytest.mark.parametrize("args", [
    ["book-paper"],
    ["book-paper", "submit", "--account", "quant1"],
    ["book-paper", "status", "--account", "quant1"],
])
def test_book_paper_is_explicitly_unavailable_before_linux_runtime_import(args):
    from open_composer.cli import app

    result = CliRunner().invoke(app, args)
    assert result.exit_code == 2
    assert "VPS" in result.output
    assert "open_composer.book_paper.cli" not in sys.modules
