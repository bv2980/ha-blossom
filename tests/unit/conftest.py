"""Load the HA-independent client without importing the HA integration."""

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "custom_components" / "blossom_energy"
package = types.ModuleType("blossom_test_client")
package.__path__ = [str(ROOT)]
sys.modules[package.__name__] = package
for module in ("api", "models"):
    name = f"blossom_test_client.{module}"
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{module}.py")
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[name] = loaded
    spec.loader.exec_module(loaded)
