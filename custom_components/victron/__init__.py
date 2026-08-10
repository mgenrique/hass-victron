"""The victron integration."""

from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_HOST, CONF_INTERVAL, CONF_PORT, DOMAIN, SCAN_REGISTERS
from .coordinator import victronEnergyDeviceUpdateCoordinator as Coordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
]


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up victron from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    host = config_entry.options.get(CONF_HOST) or config_entry.data.get(CONF_HOST, "localhost")
    port = config_entry.options.get(CONF_PORT) or config_entry.data.get(CONF_PORT, 502)
    scan_registers = config_entry.data.get(SCAN_REGISTERS) or config_entry.options.get(SCAN_REGISTERS, {})
    interval = config_entry.options.get(CONF_INTERVAL) or config_entry.data.get(CONF_INTERVAL, 30)

    coordinator = Coordinator(
        hass,
        host=host,
        port=port,
        decodeInfo=scan_registers,
        interval=interval,
    )

    hass.data[DOMAIN][config_entry.entry_id] = coordinator

    await coordinator.async_config_entry_first_refresh()
    config_entry.async_on_unload(config_entry.add_update_listener(update_listener))
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    ):
        coordinator: Coordinator = hass.data[DOMAIN].pop(config_entry.entry_id, None)
        if coordinator and coordinator.api:
            await hass.async_add_executor_job(coordinator.api.disconnect)

    return unload_ok


async def update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Update listener."""
    await hass.config_entries.async_reload(config_entry.entry_id)

