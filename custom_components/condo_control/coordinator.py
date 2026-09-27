"""Share one package poll across all entities for an account/property."""

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    CondoControlClient,
    CondoControlError,
    InvalidAuth,
    Package,
    parse_packages,
)
from .const import (
    CONF_POLL_INTERVAL,
    CONF_USER_ID,
    CONF_WORKSPACE_ID,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class CondoControlCoordinator(DataUpdateCoordinator[tuple[Package, ...]]):
    """Poll read-only data; never turn errors into a zero count."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: CondoControlClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                minutes=entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
            ),
        )
        self.client = client
        self.entry = entry
        self.units: tuple[str, ...] = ()
        self.last_success = None
        self._authenticated = False
        self._store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")

    async def async_restore(self) -> None:
        """Restore just the most recent valid snapshot across restarts."""
        cached = await self._store.async_load()
        if not isinstance(cached, dict):
            return
        try:
            packages = parse_packages(cached["response"])
            timestamp = dt_util.parse_datetime(cached["last_success"])
            units = cached["units"]
            if timestamp is None or timestamp.tzinfo is None:
                return
            if not isinstance(units, list) or any(
                not isinstance(u, str) for u in units
            ):
                return
        except CondoControlError, KeyError, TypeError, ValueError:
            return
        self.data = packages
        self.last_success = timestamp
        self.units = tuple(units)
        self.last_update_success = False

    async def _async_update_data(self) -> tuple[Package, ...]:
        try:
            if not self._authenticated:
                await self.client.login()
                workspace = await self.client.select_workspace(
                    self.entry.data[CONF_WORKSPACE_ID]
                )
                if workspace.user_id != self.entry.data[CONF_USER_ID]:
                    raise InvalidAuth("Resident identity changed")
                self.units = await self.client.get_units()
                self._authenticated = True
            packages = await self.client.get_packages()
        except InvalidAuth as err:
            self._authenticated = False
            raise ConfigEntryAuthFailed(str(err)) from err
        except CondoControlError as err:
            raise UpdateFailed(str(err)) from err
        self.last_success = dt_util.utcnow()
        await self._store.async_save(
            {
                "last_success": self.last_success.isoformat(),
                "units": list(self.units),
                "response": {
                    "PackageList": [
                        {
                            "PackageNumber": item.reference,
                            "Description": item.description,
                            "DateRecieved": item.received_at.isoformat(),
                            "IsPickedUp": item.is_picked_up,
                        }
                        for item in packages
                    ]
                },
            }
        )
        return packages
