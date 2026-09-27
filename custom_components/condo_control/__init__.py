"""Condo Control resident package tracking."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .api import CondoControlClient
from .const import DOMAIN
from .coordinator import CondoControlCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
type CondoControlConfigEntry = ConfigEntry[CondoControlCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: CondoControlConfigEntry
) -> bool:
    client = CondoControlClient(
        async_get_clientsession(hass),
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
    )
    coordinator = CondoControlCoordinator(hass, entry, client)
    await coordinator.async_restore()
    if coordinator.data is None:
        await coordinator.async_config_entry_first_refresh()
    else:
        await coordinator.async_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: CondoControlConfigEntry
) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Forget this account's cached package details when removing its entry."""
    await Store(hass, 1, f"{DOMAIN}.{entry.entry_id}").async_remove()
