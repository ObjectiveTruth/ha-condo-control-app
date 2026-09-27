"""Package counts, details, and timestamps."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CondoControlConfigEntry
from .const import CONF_PROPERTY_TIME_ZONE, CONF_WORKSPACE_NAME
from .entity import CondoControlEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CondoControlConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        [
            PackagesWaitingSensor(entry),
            OldestPackageSensor(entry),
            LastUpdateSensor(entry),
        ]
    )


class PackagesWaitingSensor(CondoControlEntity, SensorEntity):
    _attr_translation_key = "packages_waiting"
    _attr_native_unit_of_measurement = "packages"
    _attr_suggested_display_precision = 0
    # Detailed descriptions can contain personal information and are not useful
    # as long-term statistics. They remain available in the current entity state.
    _unrecorded_attributes = frozenset({"packages"})

    def __init__(self, entry: CondoControlConfigEntry) -> None:
        super().__init__(entry, "packages_waiting")

    @property
    def native_value(self) -> int:
        return sum(not package.is_picked_up for package in self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict:
        packages = self.coordinator.data
        return {
            "property": self.entry.data[CONF_WORKSPACE_NAME],
            "units": list(self.coordinator.units),
            "returned_records": len(packages),
            "picked_up_records": sum(package.is_picked_up for package in packages),
            "packages": [package.as_attribute() for package in packages],
        }


class OldestPackageSensor(CondoControlEntity, SensorEntity):
    _attr_translation_key = "oldest_package_received"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, entry: CondoControlConfigEntry) -> None:
        super().__init__(entry, "oldest_package_received")

    @property
    def native_value(self) -> datetime | None:
        zone = ZoneInfo(self.entry.options[CONF_PROPERTY_TIME_ZONE])
        dates = [
            (
                package.received_at
                if package.received_at.tzinfo
                else package.received_at.replace(tzinfo=zone)
            ).astimezone(UTC)
            for package in self.coordinator.data
            if not package.is_picked_up
        ]
        return min(dates, default=None)


class LastUpdateSensor(CondoControlEntity, SensorEntity):
    _attr_translation_key = "last_successful_update"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: CondoControlConfigEntry) -> None:
        super().__init__(entry, "last_successful_update")

    @property
    def available(self) -> bool:
        """Retain the last successful timestamp during an outage."""
        return self.coordinator.last_success is not None

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.last_success
