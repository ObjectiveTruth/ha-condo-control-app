"""Exercise real Home Assistant flows, including the one-property picker."""

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.condo_control.api import (
    CannotConnect,
    InvalidAuth,
    TwoFactorRequired,
)
from custom_components.condo_control.const import DOMAIN

from .conftest import OPTIONS, OTHER_WORKSPACE, WORKSPACE

CREDENTIALS = {"email": "alex@example.com", "password": "test-password"}


async def start_flow(hass, client):
    return await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data=CREDENTIALS,
    )


async def test_single_property_still_requires_confirmation(hass, client):
    result = await start_flow(hass, client)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "property"
    choices = result["data_schema"].schema["workspace_id"].config["options"]
    assert choices == [{"value": "100", "label": "Harbour Example"}]
    with patch("custom_components.condo_control.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"workspace_id": "100", **OPTIONS}
        )
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Alex Example — Harbour Example"
    assert result["result"].unique_id == "100_200"
    assert result["options"] == OPTIONS
    assert "access_token" not in result["data"]


async def test_multiple_properties(hass, client):
    client.list_workspaces.return_value = [WORKSPACE, OTHER_WORKSPACE]
    client.select_workspace.return_value = OTHER_WORKSPACE
    result = await start_flow(hass, client)
    assert len(result["data_schema"].schema["workspace_id"].config["options"]) == 2
    with patch("custom_components.condo_control.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"workspace_id": "101", "name": "Alex", **OPTIONS}
        )
        await hass.async_block_till_done()
    assert result["result"].unique_id == "101_201"
    assert result["title"] == "Alex — Garden Example"


async def test_duplicate_account_property(hass, client, entry):
    entry.add_to_hass(hass)
    result = await start_flow(hass, client)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"workspace_id": "100", **OPTIONS}
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize(
    ("exception", "key"),
    [
        (InvalidAuth, "invalid_auth"),
        (CannotConnect, "cannot_connect"),
        (TwoFactorRequired, "two_factor_required"),
    ],
)
async def test_login_errors(hass, client, exception, key):
    client.login.side_effect = exception
    result = await start_flow(hass, client)
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": key}


async def test_no_properties(hass, client):
    client.list_workspaces.return_value = []
    result = await start_flow(hass, client)
    assert result["reason"] == "no_workspaces"


async def test_reauth_updates_existing_entry(hass, client, entry):
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    assert result["step_id"] == "reauth_confirm"
    with patch.object(hass.config_entries, "async_reload", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**CREDENTIALS, "password": "replacement-password"}
        )
        await hass.async_block_till_done()
    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == "replacement-password"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_reauth_rejects_other_resident(hass, client, entry):
    entry.add_to_hass(hass)
    client.select_workspace.return_value = OTHER_WORKSPACE
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CREDENTIALS
    )
    assert result["reason"] == "unique_id_mismatch"


async def test_options_reload(hass, client, entry):
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    with patch.object(hass.config_entries, "async_reload", return_value=True) as reload:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {**OPTIONS, "poll_interval": 15}
        )
        await hass.async_block_till_done()
    assert entry.options["poll_interval"] == 15
    reload.assert_awaited_once_with(entry.entry_id)
