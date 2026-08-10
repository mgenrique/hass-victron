"""Support for Victron energy sensors."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.sensor import (
    DOMAIN as SENSOR_DOMAIN,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .base import VictronBaseEntityDescription
from .const import (
    CONF_ADVANCED_OPTIONS,
    DOMAIN,
    BoolReadEntityType,
    ReadEntityType,
    TextReadEntityType,
    register_info_dict,
)
from .coordinator import victronEnergyDeviceUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Victron energy sensor entries."""
    _LOGGER.debug("Attempting to setup sensor entities")
    victron_coordinator: victronEnergyDeviceUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]

    descriptions: list[VictronEntityDescription] = []
    register_set = victron_coordinator.processed_data().get("register_set", {})
    advanced_options = config_entry.options.get(
        CONF_ADVANCED_OPTIONS, config_entry.data.get(CONF_ADVANCED_OPTIONS, False)
    )

    for slave, registerLedger in register_set.items():
        for name in registerLedger:
            if name not in register_info_dict:
                continue
            for register_name, registerInfo in register_info_dict[name].items():
                if advanced_options:
                    if not isinstance(
                        registerInfo.entityType, ReadEntityType
                    ) or isinstance(registerInfo.entityType, BoolReadEntityType):
                        continue

                description = VictronEntityDescription(
                    key=register_name,
                    name=register_name.replace("_", " "),
                    native_unit_of_measurement=registerInfo.unit,
                    state_class=registerInfo.determine_stateclass(),
                    slave=slave,
                    device_class=determine_victron_device_class(
                        register_name, registerInfo.unit
                    ),
                    entity_type=registerInfo.entityType
                    if isinstance(registerInfo.entityType, TextReadEntityType)
                    else None,
                )
                descriptions.append(description)

    entities = [VictronSensor(victron_coordinator, description) for description in descriptions]
    async_add_entities(entities, True)


def determine_victron_device_class(name: str, unit: str | None) -> SensorDeviceClass | None:
    if unit == PERCENTAGE and "soc" in name:
        return SensorDeviceClass.BATTERY
    elif unit == PERCENTAGE:
        return None
    elif unit in [member.value for member in UnitOfPower]:
        return SensorDeviceClass.POWER
    elif unit in [member.value for member in UnitOfEnergy]:
        return SensorDeviceClass.ENERGY
    elif unit == UnitOfFrequency.HERTZ:
        return SensorDeviceClass.FREQUENCY
    elif unit == UnitOfTime.SECONDS:
        return SensorDeviceClass.DURATION
    elif unit in [member.value for member in UnitOfTemperature]:
        return SensorDeviceClass.TEMPERATURE
    elif unit in [member.value for member in UnitOfVolume]:
        return SensorDeviceClass.VOLUME_STORAGE
    elif unit in [member.value for member in UnitOfSpeed]:
        if "meteo" in name:
            return SensorDeviceClass.WIND_SPEED
        return SensorDeviceClass.SPEED
    elif unit in [member.value for member in UnitOfPressure]:
        return SensorDeviceClass.PRESSURE
    elif unit == UnitOfElectricPotential.VOLT:
        return SensorDeviceClass.VOLTAGE
    elif unit == UnitOfElectricCurrent.AMPERE:
        return SensorDeviceClass.CURRENT
    return None


@dataclass
class VictronEntityDescription(SensorEntityDescription, VictronBaseEntityDescription):
    """Describes victron sensor entity."""

    entity_type: ReadEntityType | None = None


class VictronSensor(CoordinatorEntity[victronEnergyDeviceUpdateCoordinator], SensorEntity):
    """Representation of a Victron energy sensor."""

    entity_description: VictronEntityDescription

    def __init__(
        self,
        coordinator: victronEnergyDeviceUpdateCoordinator,
        description: VictronEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self.description = description
        self._attr_device_class = description.device_class
        self._attr_name = description.name
        self._attr_native_unit_of_measurement = description.native_unit_of_measurement
        self._attr_state_class = description.state_class
        self.entity_type = description.entity_type

        self._attr_unique_id = f"{description.slave}_{description.key}"
        if description.slave not in (0, 100, 225):
            self.entity_id = (
                f"{SENSOR_DOMAIN}.{DOMAIN}_{description.key}_{description.slave}"
            )
        else:
            self.entity_id = f"{SENSOR_DOMAIN}.{DOMAIN}_{description.key}"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Get the latest data and updates the states."""
        try:
            if self.available:
                data = self.description.value_fn(
                    self.coordinator.processed_data(),
                    self.description.slave,
                    self.description.key,
                )
                if self.entity_type is not None and isinstance(
                    self.entity_type, TextReadEntityType
                ):
                    if data in set(item.value for item in self.entity_type.decodeEnum):
                        self._attr_native_value = self.entity_type.decodeEnum(
                            data
                        ).name.split("_DUPLICATE")[0]
                    else:
                        if data in (65535, 65535.0, 32767, 32767.0, 2147483647, 2147483647.0):
                            self._attr_native_value = None
                        else:
                            self._attr_native_value = None
                            _LOGGER.debug(
                                "The reported value %s for entity %s is not decodable",
                                data,
                                self._attr_name,
                            )
                else:
                    self._attr_native_value = data
            else:
                self._attr_native_value = None

            self.async_write_ha_state()
        except (TypeError, IndexError, KeyError):
            _LOGGER.debug("Failed to retrieve value for %s", self._attr_name)
            self._attr_native_value = None
            self.async_write_ha_state()

    @property
    def available(self) -> bool:
        if not self.coordinator.last_update_success or self.coordinator.processed_data() is None:
            return False
        availability = self.coordinator.processed_data().get("availability", {})
        full_key = f"{self.description.slave}.{self.description.key}"
        return availability.get(full_key, False)

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

