import sys
from pathlib import Path

import pytest

# The HA test plugin ships its own `custom_components` package: extend its path with ours.
import custom_components  # noqa: E402

_OURS = str(Path(__file__).resolve().parents[2] / "custom_components")
if _OURS not in custom_components.__path__:
    custom_components.__path__.append(_OURS)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def _mock_frontend(hass):
    from pytest_homeassistant_custom_component.common import mock_component

    mock_component(hass, "frontend")
    yield
