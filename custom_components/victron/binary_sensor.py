"""Support for Victron Energy binary sensors."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    DOMAIN as BINARY_SENSOR_DOMAIN,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .base import VictronBaseEntityDescription
from .const import DOMAIN, BoolReadEntityType, register_info_dict
from .coordinator import victronEnergyDeviceUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Victron energy binary sensor entries."""
    _LOGGER.debug("Attempting to setup binary sensor entities")
    victron_coordinator: victronEnergyDeviceUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]

    descriptions: list[VictronEntityDescription] = []
    register_set = victron_coordinator.processed_data().get("register_set", {})

    for slave, register_ledger in register_set.items():
        for name in register_ledger:
            if name not in register_info_dict:
                continue
            for register_name, register_info in register_info_dict[name].items():
                if isinstance(register_info.entityType, BoolReadEntityType):
                    description = VictronEntityDescription(
                        key=register_name,
                        name=register_name.replace("_", " "),
                        slave=slave,
                    )
                    descriptions.append(description)

    entities = [VictronBinarySensor(victron_coordinator, description) for description in descriptions]
    async_add_entities(entities, True)


@dataclass
class VictronEntityDescription(
    BinarySensorEntityDescription, VictronBaseEntityDescription
):
    """Describes victron binary sensor entity."""


class VictronBinarySensor(CoordinatorEntity[victronEnergyDeviceUpdateCoordinator], BinarySensorEntity):
    """A binary sensor implementation for Victron energy device."""

    entity_description: VictronEntityDescription

    def __init__(
        self,
        coordinator: victronEnergyDeviceUpdateCoordinator,
        description: VictronEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self.description = description
        self._attr_device_class = description.device_class
        self._attr_name = description.name
        self.data_key = f"{description.slave}.{description.key}"

        self._attr_unique_id = f"{description.slave}_{description.key}"
        if description.slave not in (0, 100, 225):
            self.entity_id = f"{BINARY_SENSOR_DOMAIN}.{DOMAIN}_{description.key}_{description.slave}".lower()
        else:
            self.entity_id = f"{BINARY_SENSOR_DOMAIN}.{DOMAIN}_{description.key}".lower()

    @property
    def is_on(self) -> bool:
        """Return True if the binary sensor is on."""
        data = self.description.value_fn(
            self.coordinator.processed_data(),
            self.description.slave,
            self.description.key,
        )
        return bool(data) if data is not None else False

    @property
    def available(self) -> bool:
        if not self.coordinator.last_update_success or self.coordinator.processed_data() is None:
            return False
        availability = self.coordinator.processed_data().get("availability", {})
        return availability.get(self.data_key, False)

    @property
    def device_info(self) -> entity.DeviceInfo:
        """Return the device info."""
        slave_id = str(self.description.slave)
        return entity.DeviceInfo(
            identifiers={(DOMAIN, slave_id)},
            name=f"Victron Device {slave_id}",
            model=slave_id,
            manufacturer="Victron Energy",
        )

