"""Support for Victron energy button sensors."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.button import (
    DOMAIN as BUTTON_DOMAIN,
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .base import VictronWriteBaseEntityDescription
from .const import CONF_ADVANCED_OPTIONS, DOMAIN, ButtonWriteType, register_info_dict
from .coordinator import victronEnergyDeviceUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Victron energy button entries."""
    _LOGGER.debug("Attempting to setup button entities")
    victron_coordinator: victronEnergyDeviceUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]
    descriptions: list[VictronEntityDescription] = []

    options = {**config_entry.data, **config_entry.options}
    if options.get(CONF_ADVANCED_OPTIONS, False):
        register_set = victron_coordinator.processed_data().get("register_set", {})
        for slave, registerLedger in register_set.items():
            for name in registerLedger:
                if name not in register_info_dict:
                    continue
                for register_name, registerInfo in register_info_dict[name].items():
                    if isinstance(registerInfo.entityType, ButtonWriteType):
                        description = VictronEntityDescription(
                            key=register_name,
                            name=register_name.replace("_", " "),
                            slave=slave,
                            device_class=ButtonDeviceClass.RESTART,
                            address=registerInfo.register,
                        )
                        descriptions.append(description)

    entities = [VictronButton(victron_coordinator, description) for description in descriptions]
    async_add_entities(entities, True)


@dataclass
class VictronEntityDescription(
    ButtonEntityDescription, VictronWriteBaseEntityDescription
):
    """Describes victron button entity."""


class VictronButton(CoordinatorEntity[victronEnergyDeviceUpdateCoordinator], ButtonEntity):
    """A button implementation for Victron energy device."""

    entity_description: VictronEntityDescription

    def __init__(
        self,
        coordinator: victronEnergyDeviceUpdateCoordinator,
        description: VictronEntityDescription,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self.entity_description = description
        self.description = description
        self._attr_device_class = description.device_class
        self._attr_name = description.name
        self.data_key = f"{description.slave}.{description.key}"

        self._attr_unique_id = f"{description.slave}_{description.key}"
        if description.slave not in (0, 100, 225):
            self.entity_id = f"{BUTTON_DOMAIN}.{DOMAIN}_{description.key}_{description.slave}".lower()
        else:
            self.entity_id = f"{BUTTON_DOMAIN}.{DOMAIN}_{description.key}".lower()

    async def async_press(self) -> None:
        """Handle the button press."""
        self.coordinator.write_register(
            unit=self.description.slave, address=self.description.address, value=1
        )

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

