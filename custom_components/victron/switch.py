"""Support for victron energy switches."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.switch import (
    DOMAIN as SWITCH_DOMAIN,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .base import VictronWriteBaseEntityDescription
from .const import CONF_ADVANCED_OPTIONS, DOMAIN, SwitchWriteType, register_info_dict
from .coordinator import victronEnergyDeviceUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up victron switch devices."""
    victron_coordinator: victronEnergyDeviceUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]
    _LOGGER.debug("Attempting to setup switch entities")
    descriptions: list[VictronEntityDescription] = []

    options = {**config_entry.data, **config_entry.options}
    if options.get(CONF_ADVANCED_OPTIONS, False):
        register_set = victron_coordinator.processed_data().get("register_set", {})
        for slave, registerLedger in register_set.items():
            for name in registerLedger:
                if name not in register_info_dict:
                    continue
                for register_name, registerInfo in register_info_dict[name].items():
                    if isinstance(registerInfo.entityType, SwitchWriteType):
                        description = VictronEntityDescription(
                            key=register_name,
                            name=register_name.replace("_", " "),
                            slave=slave,
                            address=registerInfo.register,
                        )
                        descriptions.append(description)

    entities = [VictronSwitch(victron_coordinator, description) for description in descriptions]
    async_add_entities(entities)


@dataclass
class VictronEntityDescription(
    SwitchEntityDescription, VictronWriteBaseEntityDescription
):
    """Describes victron switch entity."""


class VictronSwitch(CoordinatorEntity[victronEnergyDeviceUpdateCoordinator], SwitchEntity):
    """Representation of a Victron switch."""

    entity_description: VictronEntityDescription

    def __init__(
        self,
        coordinator: victronEnergyDeviceUpdateCoordinator,
        description: VictronEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self.description = description
        self._attr_name = description.name
        self.data_key = f"{description.slave}.{description.key}"

        self._attr_unique_id = f"{description.slave}_{description.key}"
        if description.slave not in (0, 100, 225):
            self.entity_id = (
                f"{SWITCH_DOMAIN}.{DOMAIN}_{description.key}_{description.slave}".lower()
            )
        else:
            self.entity_id = f"{SWITCH_DOMAIN}.{DOMAIN}_{description.key}".lower()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the device."""
        self.coordinator.write_register(
            unit=self.description.slave, address=self.description.address, value=1
        )
        await self.coordinator.async_update_local_entry(self.data_key, 1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the device."""
        self.coordinator.write_register(
            unit=self.description.slave, address=self.description.address, value=0
        )
        await self.coordinator.async_update_local_entry(self.data_key, 0)

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
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

