"""Lightweight test bootstrap for the Vestel AC integration tests.

The integration's __init__.py imports the whole Home Assistant core, which
these unit tests deliberately do NOT install: the code under test
(custom_components/vestel_ac/api.py) only depends on aiohttp and the
stdlib. To import it without executing that __init__.py, register stub
package modules that point at the real directories on disk.
"""

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG_DIR = ROOT / "custom_components"
INTEGRATION_DIR = PKG_DIR / "vestel_ac"


def _register_stub_package(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules[name] = module


_register_stub_package("custom_components", PKG_DIR)
_register_stub_package("custom_components.vestel_ac", INTEGRATION_DIR)
