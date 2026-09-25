"""Enable real HA fixtures when the optional HA test environment is installed."""

import importlib.util

if importlib.util.find_spec("pytest_homeassistant_custom_component"):
    pytest_plugins = ["pytest_homeassistant_custom_component"]
