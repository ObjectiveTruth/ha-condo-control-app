"""Verify devices, sensor lifecycle, pickup changes, and outages in HA Core."""

from dataclasses import replace
from datetime import timedelta

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.condo_control.api import (
    CannotConnect,
    InvalidAuth,
    InvalidResponse,
)
from custom_components.condo_control.const import DOMAIN
from custom_components.condo_control.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import DATA, OPTIONS, WORKSPACE


def entity_id(hass, platform, unique_id):
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)


async def setup(hass, entry):
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def enable_timestamp(hass, entry):
    """Opt into the diagnostic timestamp using the entity registry."""
    last_id = entity_id(hass, "sensor", "100_200_last_successful_update")
    er.async_get(hass).async_update_entity(last_id, disabled_by=None)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    return last_id


async def test_entities_and_pickup(hass, client, entry):
    await setup(hass, entry)
    count_id = entity_id(hass, "sensor", "100_200_packages_waiting")
    binary_id = entity_id(hass, "binary_sensor", "100_200_package_waiting")
    oldest_id = entity_id(hass, "sensor", "100_200_oldest_package_received")
    state = hass.states.get(count_id)
    assert state.state == "1"
    assert len(state.attributes["packages"]) == 2
    assert state.attributes["packages"][0]["reference"] == 501
    assert hass.states.get(binary_id).state == "on"
    assert hass.states.get(oldest_id).state == "2026-09-25T17:38:00+00:00"
    assert entry.runtime_data.update_interval == timedelta(minutes=5)
    registry = er.async_get(hass)
    timestamp_id = entity_id(hass, "sensor", "100_200_last_successful_update")
    assert (
        registry.async_get(timestamp_id).disabled_by
        is er.RegistryEntryDisabler.INTEGRATION
    )
    assert hass.states.get(timestamp_id) is None
    assert entry.runtime_data.last_success is not None
    status_id = entity_id(hass, "binary_sensor", "100_200_last_update_successful")
    assert registry.async_get(status_id).disabled_by is None
    assert hass.states.get(status_id).state == "on"
    client.get_packages.return_value = tuple(
        replace(item, is_picked_up=True) for item in client.get_packages.return_value
    )
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(count_id).state == "0"
    assert hass.states.get(binary_id).state == "off"
    assert hass.states.get(oldest_id).state == "unknown"
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert hass.states.get(count_id).state == "unavailable"


async def test_outage_and_recovery(hass, client, entry):
    await setup(hass, entry)
    count_id = entity_id(hass, "sensor", "100_200_packages_waiting")
    last_id = await enable_timestamp(hass, entry)
    last_success = hass.states.get(last_id).state
    for error in (CannotConnect("Offline"), InvalidResponse("Missing package list")):
        client.get_packages.side_effect = error
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(count_id).state == "1"
        assert (
            hass.states.get(
                entity_id(hass, "binary_sensor", "100_200_last_update_successful")
            ).state
            == "off"
        )
        assert hass.states.get(last_id).state == last_success
    client.get_packages.side_effect = None
    client.get_packages.return_value = ()
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(count_id).state == "0"


async def test_two_residents_get_separate_devices(hass, client, entry):
    await setup(hass, entry)
    client.select_workspace.return_value = replace(WORKSPACE, user_id=300)
    second = MockConfigEntry(
        domain=DOMAIN,
        unique_id="100_300",
        title="Sam Example — Harbour Example",
        data={**DATA, "email": "sam@example.com", "user_id": 300},
        options=OPTIONS,
    )
    await setup(hass, second)
    devices = dr.async_get(hass)
    first_device = devices.async_get_device_by_identifier(
        (DOMAIN, "100_200"), entry.entry_id
    )
    second_device = devices.async_get_device_by_identifier(
        (DOMAIN, "100_300"), second.entry_id
    )
    assert first_device and second_device
    assert first_device.id != second_device.id
    assert entity_id(hass, "sensor", "100_300_packages_waiting")


async def test_expired_credentials_trigger_reauth(hass, client, entry):
    await setup(hass, entry)
    client.get_packages.side_effect = InvalidAuth("Session rejected")
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert any(flow["context"]["source"] == "reauth" for flow in flows)


async def test_diagnostics_exclude_personal_data(hass, client, entry):
    await setup(hass, entry)
    data = await async_get_config_entry_diagnostics(hass, entry)
    assert data["waiting_records"] == 1
    text = str(data)
    for value in ("test-password", "alex@", "Alex", "Harbour", "Small box", "501"):
        assert value not in text


async def test_cached_reading_survives_reload_during_outage(hass, client, entry):
    await setup(hass, entry)
    count_id = entity_id(hass, "sensor", "100_200_packages_waiting")
    last_id = await enable_timestamp(hass, entry)
    previous_time = hass.states.get(last_id).state
    client.login.side_effect = CannotConnect("Offline")
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(count_id).state == "1"
    assert hass.states.get(last_id).state == previous_time
    status = entity_id(hass, "binary_sensor", "100_200_last_update_successful")
    assert hass.states.get(status).state == "off"
    client.login.side_effect = None
    client.get_packages.return_value = ()
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(count_id).state == "0"
    assert hass.states.get(status).state == "on"


async def test_first_failure_never_creates_zero(hass, client, entry):
    from homeassistant.config_entries import ConfigEntryState

    entry.add_to_hass(hass)
    client.get_packages.side_effect = CannotConnect("Offline")
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state == ConfigEntryState.SETUP_RETRY
    assert not entity_id(hass, "sensor", "100_200_packages_waiting")


async def test_cache_removed_with_account(hass, client, entry, hass_storage):
    await setup(hass, entry)
    key = f"{DOMAIN}.{entry.entry_id}"
    assert key in hass_storage
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert key not in hass_storage


async def test_auth_failure_after_restart_retains_reading(hass, client, entry):
    await setup(hass, entry)
    client.login.side_effect = InvalidAuth("Credentials rejected")
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    count_id = entity_id(hass, "sensor", "100_200_packages_waiting")
    assert hass.states.get(count_id).state == "1"
    assert any(
        flow["context"]["source"] == "reauth"
        for flow in hass.config_entries.flow.async_progress()
    )


async def test_refresh_button_uses_coordinator(hass, client, entry):
    await setup(hass, entry)
    button_id = entity_id(hass, "button", "100_200_refresh")
    calls = client.get_packages.await_count
    await hass.services.async_call(
        "button", "press", {"entity_id": button_id}, blocking=True
    )
    await hass.async_block_till_done()
    assert client.get_packages.await_count == calls + 1
