"""Pure-Python tests: import the HA-free modules directly (no HA needed)."""

import importlib.util
import sys
import types
from pathlib import Path

PKG = "cloudless_rmv_pure"
ROOT = Path(__file__).parent.parent / "custom_components" / "cloudless_rmv"


def _load() -> None:
    if PKG in sys.modules:
        return
    pkg = types.ModuleType(PKG)
    pkg.__path__ = [str(ROOT)]
    sys.modules[PKG] = pkg
    for name in ("const", "budget", "client", "parser"):
        spec = importlib.util.spec_from_file_location(f"{PKG}.{name}", ROOT / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f"{PKG}.{name}"] = mod
        spec.loader.exec_module(mod)


_load()
