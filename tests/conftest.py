"""Home Assistant fixtures."""

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.condo_control.api import Workspace, parse_packages
from custom_components.condo_control.const import DOMAIN

WORKSPACE = Workspace(100, "Harbour Example", 200, "Alex Example", True)
OTHER_WORKSPACE = Workspace(101, "Garden Example", 201, "Alex Example", True)
ROWS = {
    "PackageList": [
        {
            "PackageNumber": 501,
            "Description": "Small box stored at parcel desk",
            "DateRecieved": "2026-09-25T13:38:00",
            "IsPickedUp": False,
        },
        {
            "PackageNumber": 502,
            "Description": "Envelope",
            "DateRecieved": "2026-09-24T12:00:00",
            "IsPickedUp": True,
        },
    ]
}
DATA = {
    "email": "alex@example.com",
    "password": "test-password",
    "workspace_id": 100,
    "workspace_name": "Harbour Example",
    "user_id": 200,
    "name": "Alex Example",
}
OPTIONS = {"poll_interval": 5, "property_time_zone": "America/Toronto"}


@pytest.fixture(autouse=True)
def enable_custom(enable_custom_integrations):
    """Load this repository's integration rather than only core components."""


@pytest.fixture
def entry():
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="100_200",
        title="Alex Example — Harbour Example",
        data=DATA,
        options=OPTIONS,
    )


@pytest.fixture
def client():
    mock = AsyncMock()
    mock.list_workspaces.return_value = [WORKSPACE]
    mock.select_workspace.return_value = WORKSPACE
    mock.get_units.return_value = ("101",)
    mock.get_packages.return_value = parse_packages(ROWS)
    with (
        patch("custom_components.condo_control.CondoControlClient", return_value=mock),
        patch(
            "custom_components.condo_control.config_flow.CondoControlClient",
            return_value=mock,
        ),
    ):
        yield mock
