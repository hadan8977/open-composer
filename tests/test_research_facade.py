"""``open_composer.research`` resolves its public names lazily (PEP 562).

The facade used to eagerly import 42 submodules (about 5 s / 200 MB on the
research box) on every CLI call and cron cycle; these tests keep the
laziness honest and make sure every advertised name still resolves.
"""

from __future__ import annotations

import importlib
import subprocess
import sys

import pytest

import open_composer.research as research


def test_every_public_name_resolves_to_its_owning_module() -> None:
    assert set(research.__all__) == set(research._EXPORTS)
    for name in research.__all__:
        owner = importlib.import_module(research._EXPORTS[name])
        assert getattr(research, name) is getattr(owner, name)
    assert set(research.__all__) <= set(dir(research))


def test_unknown_attribute_still_raises_attribute_error() -> None:
    missing = "definitely_not_a_research_symbol"
    with pytest.raises(AttributeError, match=missing):
        getattr(research, missing)


def test_importing_the_package_and_kernel_does_not_load_ml_libraries() -> None:
    code = (
        "import sys\n"
        "import open_composer.research\n"
        "import open_composer.research.kernel.loop\n"
        "loaded = [m for m in ('sklearn', 'lightgbm', 'nautilus_trader') if m in sys.modules]\n"
        "print(','.join(loaded))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, timeout=120
    )
    assert result.stdout.strip() == "", result.stdout
