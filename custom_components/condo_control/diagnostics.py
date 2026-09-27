"""Allowlisted diagnostics without account details, descriptions, or credentials."""

from homeassistant.core import HomeAssistant

from . import CondoControlConfigEntry
from .const import CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: CondoControlConfigEntry
) -> dict:
    coordinator = entry.runtime_data
    return {
        "poll_interval_minutes": entry.options.get(
            CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
        ),
        "last_update_success": coordinator.last_update_success,
        "returned_records": len(coordinator.data)
        if coordinator.data is not None
        else 0,
        "waiting_records": (
            sum(not item.is_picked_up for item in coordinator.data)
            if coordinator.data is not None
            else None
        ),
    }
