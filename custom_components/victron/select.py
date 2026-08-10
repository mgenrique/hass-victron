"""Support for Victron energy switches."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import logging
from typing import Any

from homeassistant.components.select import (
    DOMAIN as SELECT_DOMAIN,
    SelectEntity,
    SelectEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .base import VictronWriteBaseEntityDescription
from .const import CONF_ADVANCED_OPTIONS, DOMAIN, SelectWriteType, register_info_dict
from .coordinator import victronEnergyDeviceUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up victron select devices."""
    victron_coordinator: victronEnergyDeviceUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]
    _LOGGER.debug("Attempting to setup select entities")
    descriptions: list[VictronEntityDescription] = []

    options = {**config_entry.data, **config_entry.options}
    if options.get(CONF_ADVANCED_OPTIONS, False):
        register_set = victron_coordinator.processed_data().get("register_set", {})
        for slave, registerLedger in register_set.items():
            for name in registerLedger:
                if name not in register_info_dict:
                    continue
                for register_name, registerInfo in register_info_dict[name].items():
                    if isinstance(registerInfo.entityType, SelectWriteType):
                        description = VictronEntityDescription(
                            key=register_name,
                            name=register_name.replace("_", " "),
                            slave=slave,
                            options_enum=registerInfo.entityType.options,
                            address=registerInfo.register,
                        )
                        descriptions.append(description)

    entities = [VictronSelect(victron_coordinator, description) for description in descriptions]
    async_add_entities(entities)


@dataclass
class VictronEntityDescription(
    SelectEntityDescription, VictronWriteBaseEntityDescription
):
    """Describes victron select entity."""

    options_enum: type[Enum] | None = None


class VictronSelect(CoordinatorEntity[victronEnergyDeviceUpdateCoordinator], SelectEntity):
    """Representation of a Victron select entity."""

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
            self.entity_id = f"{SELECT_DOMAIN}.{DOMAIN}_{description.key}_{description.slave}".lower()
        else:
            self.entity_id = f"{SELECT_DOMAIN}.{DOMAIN}_{description.key}".lower()

    @property
    def current_option(self) -> str | None:
        val = self.description.value_fn(
            self.coordinator.processed_data(),
            self.description.slave,
            self.description.key,
        )
        if val is None or self.description.options_enum is None:
            return None
        try:
            return self.description.options_enum(val).name
        except (ValueError, KeyError):
            return None

    @property
    def options(self) -> list[str]:
        if self.description.options_enum is None:
            return []
        return [option.name for option in self.description.options_enum]

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if (
            self.description.options_enum is None
            or option not in self.description.options_enum.__members__
        ):
            return

        enum_val = int(self.description.options_enum[option].value)
        self.coordinator.write_register(
            unit=self.description.slave,
            address=self.description.address,
            value=self.coordinator.encode_scaling(enum_val, "", 0),
        )
        await self.coordinator.async_update_local_entry(self.data_key, enum_val)

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

