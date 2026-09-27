"""One service device per resident account and property."""

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import CondoControlConfigEntry
from .const import CONF_USER_ID, CONF_WORKSPACE_ID, DOMAIN
from .coordinator import CondoControlCoordinator


class CondoControlEntity(CoordinatorEntity[CondoControlCoordinator]):
    _attr_has_entity_name = True

    @property
    def available(self) -> bool:
        """Keep the last valid snapshot through errors until a new one arrives."""
        return self.coordinator.data is not None

    def __init__(self, entry: CondoControlConfigEntry, key: str) -> None:
        super().__init__(entry.runtime_data)
        self.entry = entry
        identity = f"{entry.data[CONF_WORKSPACE_ID]}_{entry.data[CONF_USER_ID]}"
        self._attr_unique_id = f"{identity}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identity)},
            name=entry.title,
            manufacturer="Condo Control",
            model="Resident account",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://app.condocontrol.com/",
        )
