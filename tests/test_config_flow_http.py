"""Exercise form serialization through the same HTTP API as the HA frontend."""

from unittest.mock import patch

from homeassistant.setup import async_setup_component

from custom_components.condo_control.const import DOMAIN

from .conftest import OPTIONS
from .test_config_flow import CREDENTIALS

FLOW_URL = "/api/config/config_entries/flow"
OPTIONS_URL = "/api/config/config_entries/options/flow"


async def test_setup_forms_over_http(hass, hass_client, client):
    """Successful login must render the next form instead of returning HTTP 500."""
    assert await async_setup_component(hass, "config", {})
    http = await hass_client()
    response = await http.post(FLOW_URL, json={"handler": DOMAIN})
    assert response.status == 200
    form = await response.json()
    assert form["step_id"] == "user"
    url = f"{FLOW_URL}/{form['flow_id']}"

    response = await http.post(url, json=CREDENTIALS)
    assert response.status == 200
    form = await response.json()
    assert form["step_id"] == "property"
    fields = {field["name"]: field for field in form["data_schema"]}
    assert "poll_interval" in fields
    assert "property_time_zone" in fields

    response = await http.post(
        url,
        json={"workspace_id": "100", **OPTIONS, "property_time_zone": "Not/AZone"},
    )
    assert response.status == 400
    assert "property_time_zone" in (await response.json())["errors"]

    with patch("custom_components.condo_control.async_setup_entry", return_value=True):
        response = await http.post(
            url, json={"workspace_id": "100", **OPTIONS, "poll_interval": 10}
        )
        assert response.status == 200
        assert (await response.json())["type"] == "create_entry"
        await hass.async_block_till_done()
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.options == {**OPTIONS, "poll_interval": 10}


async def test_options_form_over_http(hass, hass_client, client, entry):
    """The time-zone field must also render and validate in Configure."""
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, "config", {})
    http = await hass_client()
    response = await http.post(OPTIONS_URL, json={"handler": entry.entry_id})
    assert response.status == 200
    form = await response.json()
    assert form["step_id"] == "init"
    with patch.object(hass.config_entries, "async_reload", return_value=True) as reload:
        response = await http.post(
            f"{OPTIONS_URL}/{form['flow_id']}",
            json={"poll_interval": 15, "property_time_zone": "America/Vancouver"},
        )
        assert response.status == 200
        assert (await response.json())["type"] == "create_entry"
        await hass.async_block_till_done()
    assert entry.options == {
        "poll_interval": 15,
        "property_time_zone": "America/Vancouver",
    }
    reload.assert_awaited_once_with(entry.entry_id)
