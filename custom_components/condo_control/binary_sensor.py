"""Whether any package is still waiting, whoever ultimately picks it up."""

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CondoControlConfigEntry
from .entity import CondoControlEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CondoControlConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        [PackageWaitingBinarySensor(entry), UpdateSuccessfulSensor(entry)]
    )


class PackageWaitingBinarySensor(CondoControlEntity, BinarySensorEntity):
    _attr_translation_key = "package_waiting"

    def __init__(self, entry: CondoControlConfigEntry) -> None:
        super().__init__(entry, "package_waiting")

    @property
    def is_on(self) -> bool:
        return any(not package.is_picked_up for package in self.coordinator.data)


class UpdateSuccessfulSensor(CondoControlEntity, BinarySensorEntity):
    _attr_translation_key = "last_update_successful"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: CondoControlConfigEntry) -> None:
        super().__init__(entry, "last_update_successful")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success
