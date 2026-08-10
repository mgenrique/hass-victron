"""Support for victron energy slider number entities."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.components.number import (
    DOMAIN as NUMBER_DOMAIN,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .base import VictronWriteBaseEntityDescription
from .const import (
    CONF_AC_CURRENT_LIMIT,
    CONF_AC_SYSTEM_VOLTAGE,
    CONF_ADVANCED_OPTIONS,
    CONF_DC_CURRENT_LIMIT,
    CONF_DC_SYSTEM_VOLTAGE,
    CONF_NUMBER_OF_PHASES,
    CONF_USE_SLIDERS,
    DOMAIN,
    UINT16_MAX,
    SliderWriteType,
    register_info_dict,
)
from .coordinator import victronEnergyDeviceUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up victron number devices."""
    victron_coordinator: victronEnergyDeviceUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]
    _LOGGER.debug("Attempting to setup number entities")
    descriptions: list[VictronEntityDescription] = []

    options = {**config_entry.data, **config_entry.options}
    advanced_options = options.get(CONF_ADVANCED_OPTIONS, False)
    use_sliders = options.get(CONF_USE_SLIDERS, True)

    if advanced_options:
        register_set = victron_coordinator.processed_data().get("register_set", {})
        for slave, registerLedger in register_set.items():
            for name in registerLedger:
                if name not in register_info_dict:
                    continue
                for register_name, registerInfo in register_info_dict[name].items():
                    if isinstance(registerInfo.entityType, SliderWriteType):
                        description = VictronEntityDescription(
                            key=register_name,
                            name=register_name.replace("_", " "),
                            slave=slave,
                            native_unit_of_measurement=registerInfo.unit,
                            mode=NumberMode.SLIDER if use_sliders else NumberMode.BOX,
                            native_min_value=determine_min_value(
                                registerInfo.unit,
                                options,
                                registerInfo.entityType.powerType,
                                registerInfo.entityType.negative,
                            ),
                            native_max_value=determine_max_value(
                                registerInfo.unit,
                                options,
                                registerInfo.entityType.powerType,
                            ),
                            entity_category=EntityCategory.CONFIG,
                            address=registerInfo.register,
                            scale=registerInfo.scale,
                            native_step=registerInfo.step,
                        )
                        descriptions.append(description)

    entities = [VictronNumber(victron_coordinator, description) for description in descriptions]
    async_add_entities(entities)


def determine_min_value(
    unit: str | None, options: dict[str, Any], powerType: str | None, negative: bool
) -> float:
    if unit == PERCENTAGE:
        return 0
    elif unit == UnitOfElectricPotential.VOLT:
        dc_sys_voltage = float(options.get(CONF_DC_SYSTEM_VOLTAGE, 12))
        series_type = dc_sys_voltage / 3  # statically based on lifepo4 cells
        return series_type * 2.5
    elif unit == UnitOfPower.WATT:
        if negative:
            ac_voltage = float(options.get(CONF_AC_SYSTEM_VOLTAGE, 230))
            num_phases = float(options.get(CONF_NUMBER_OF_PHASES, 1))
            ac_limit = float(options.get(CONF_AC_CURRENT_LIMIT, 16))
            dc_voltage = float(options.get(CONF_DC_SYSTEM_VOLTAGE, 12))
            dc_limit = float(options.get(CONF_DC_CURRENT_LIMIT, 50))

            min_value = (
                (ac_voltage * num_phases * ac_limit)
                if powerType == "AC"
                else (dc_voltage * dc_limit)
            )
            return float(-round(min_value / 100) * 100)
        return 0
    elif unit == UnitOfElectricCurrent.AMPERE:
        if negative:
            if powerType == "AC":
                return -float(options.get(CONF_AC_CURRENT_LIMIT, 16))
            elif powerType == "DC":
                return -float(options.get(CONF_DC_CURRENT_LIMIT, 50))
        return 0
    return 0


def determine_max_value(
    unit: str | None, options: dict[str, Any], powerType: str | None
) -> float:
    if unit == PERCENTAGE:
        return 100
    elif unit == UnitOfElectricPotential.VOLT:
        dc_sys_voltage = float(options.get(CONF_DC_SYSTEM_VOLTAGE, 12))
        series_type = dc_sys_voltage / 3
        return series_type * 3.65
    elif unit == UnitOfPower.WATT:
        ac_voltage = float(options.get(CONF_AC_SYSTEM_VOLTAGE, 230))
        num_phases = float(options.get(CONF_NUMBER_OF_PHASES, 1))
        ac_limit = float(options.get(CONF_AC_CURRENT_LIMIT, 16))
        dc_voltage = float(options.get(CONF_DC_SYSTEM_VOLTAGE, 12))
        dc_limit = float(options.get(CONF_DC_CURRENT_LIMIT, 50))

        max_value = (
            (ac_voltage * num_phases * ac_limit)
            if powerType == "AC"
            else (dc_voltage * dc_limit)
        )
        return float(round(max_value / 100) * 100)
    elif unit == UnitOfElectricCurrent.AMPERE:
        if powerType == "AC":
            return float(options.get(CONF_AC_CURRENT_LIMIT, 16))
        elif powerType == "DC":
            return float(options.get(CONF_DC_CURRENT_LIMIT, 50))
    return 100


@dataclass
class VictronNumberMixin:
    """A class that describes number entities."""

    scale: int | float | None = None
    mode: NumberMode | None = None


@dataclass
class VictronNumberStep:
    native_step: float = 0


@dataclass
class VictronEntityDescription(
    NumberEntityDescription,
    VictronWriteBaseEntityDescription,
    VictronNumberMixin,
    VictronNumberStep,
):
    key: str | None = None


class VictronNumber(CoordinatorEntity[victronEnergyDeviceUpdateCoordinator], NumberEntity):
    """Victron number."""

    entity_description: VictronEntityDescription

    def __init__(
        self,
        coordinator: victronEnergyDeviceUpdateCoordinator,
        description: VictronEntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self.description = description
        self._attr_name = description.name
        self.data_key = f"{description.slave}.{description.key}"

        self._attr_unique_id = f"{description.slave}_{description.key}"
        if description.slave not in (0, 100, 225):
            self.entity_id = f"{NUMBER_DOMAIN}.{DOMAIN}_{description.key}_{description.slave}"
        else:
            self.entity_id = f"{NUMBER_DOMAIN}.{DOMAIN}_{description.key}"

        self._attr_mode = description.mode or NumberMode.BOX

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        raw_val = value
        if raw_val < 0:
            raw_val = UINT16_MAX + raw_val
        encoded = self.coordinator.encode_scaling(
            raw_val,
            self.description.native_unit_of_measurement,
            self.description.scale or 1,
        )
        self.coordinator.write_register(
            unit=self.description.slave,
            address=self.description.address,
            value=encoded,
        )
        await self.coordinator.async_update_local_entry(self.data_key, value)

    @property
    def native_value(self) -> float | None:
        """Return the state of the entity."""
        value = self.description.value_fn(
            self.coordinator.processed_data(),
            self.description.slave,
            self.description.key,
        )
        if value is None:
            return None
        if isinstance(value, (int, float)):
            if value > round(UINT16_MAX / 2):
                value = value - UINT16_MAX
            return float(value)
        return None

    @property
    def native_step(self) -> float | None:
        if self.description.mode != NumberMode.SLIDER:
            return None
        if self.description.native_step and self.description.native_step > 0:
            return self.description.native_step
        max_val = self.native_max_value
        min_val = self.native_min_value
        gap = max_val - min_val
        if gap >= 3000:
            return 100
        elif gap > 100:
            return 10
        else:
            return 1

    @property
    def native_min_value(self) -> float:
        return float(self.description.native_min_value or 0)

    @property
    def native_max_value(self) -> float:
        return float(self.description.native_max_value or 100)

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

