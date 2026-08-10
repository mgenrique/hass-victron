from __future__ import annotations

import logging
import struct
from collections import OrderedDict
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    UINT16,
    UINT32,
    INT16,
    INT32,
    STRING,
    RegisterInfo,
    register_info_dict,
)
from .hub import VictronHub

_LOGGER = logging.getLogger(__name__)


class VictronPayloadDecoder:
    """Decodes 16-bit Modbus registers into Python data types in Big-Endian order."""

    def __init__(self, registers: list[int], start_register: int = 0) -> None:
        self._registers = registers
        self._start_register = start_register
        self._bytes = struct.pack(f">{len(registers)}H", *registers)

    def decode_16bit_uint(self, register: int) -> int:
        offset = (register - self._start_register) * 2
        if offset < 0 or offset + 2 > len(self._bytes):
            return 0
        return struct.unpack_from(">H", self._bytes, offset)[0]

    def decode_16bit_int(self, register: int) -> int:
        offset = (register - self._start_register) * 2
        if offset < 0 or offset + 2 > len(self._bytes):
            return 0
        return struct.unpack_from(">h", self._bytes, offset)[0]

    def decode_32bit_uint(self, register: int) -> int:
        offset = (register - self._start_register) * 2
        if offset < 0 or offset + 4 > len(self._bytes):
            return 0
        return struct.unpack_from(">I", self._bytes, offset)[0]

    def decode_32bit_int(self, register: int) -> int:
        offset = (register - self._start_register) * 2
        if offset < 0 or offset + 4 > len(self._bytes):
            return 0
        return struct.unpack_from(">i", self._bytes, offset)[0]

    def decode_string(self, register: int, length: int) -> str:
        offset = (register - self._start_register) * 2
        if offset < 0 or offset >= len(self._bytes):
            return ""
        raw = self._bytes[offset : min(offset + length, len(self._bytes))]
        return raw.split(b"\x00")[0].decode("utf-8", errors="replace").strip()


class victronEnergyDeviceUpdateCoordinator(DataUpdateCoordinator):
    """Gather data for the energy device."""

    api: VictronHub

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int | str,
        decodeInfo: dict,
        interval: int,
    ) -> None:
        """Initialize Update Coordinator."""
        super().__init__(
            hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=interval)
        )
        self.api = VictronHub(host, int(port))
        self.api.connect()
        self.decodeInfo = decodeInfo
        self.interval = interval

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch all device and sensor data from api."""
        self.logger.debug("Fetching victron data: %s", self.decodeInfo)

        parsed_data = OrderedDict()
        unavailable_entities = OrderedDict()

        if self.data is None:
            self.data = {"data": OrderedDict(), "availability": OrderedDict()}

        # Ensure hub connection before polling
        connected = await self.hass.async_add_executor_job(self.api.connect)
        if not connected:
            _LOGGER.warning("Could not connect to Victron hub at %s:%s", self.api.host, self.api.port)

        for unit, registerInfo in self.decodeInfo.items():
            for name in registerInfo:
                if name not in register_info_dict:
                    continue

                reg_def = register_info_dict[name]
                try:
                    data = await self.fetch_registers(unit, reg_def)
                except Exception as err:
                    _LOGGER.warning("Exception fetching registers for unit %s, name %s: %s", unit, name, err)
                    data = None

                is_error = (
                    data is None
                    or (hasattr(data, "isError") and data.isError())
                    or not hasattr(data, "registers")
                    or data.registers is None
                )

                if is_error:
                    for key in reg_def.keys():
                        full_key = f"{unit}.{key}"
                        unavailable_entities[full_key] = False

                    _LOGGER.debug(
                        "No valid data returned for entities of slave: %s (register set: %s). Modbus response: %r",
                        unit,
                        name,
                        data,
                    )
                else:
                    parsed_data.update(self.parse_register_data(data, reg_def, unit))
                    for key in reg_def.keys():
                        full_key = f"{unit}.{key}"
                        unavailable_entities[full_key] = True

        return {
            "register_set": self.decodeInfo,
            "data": parsed_data,
            "availability": unavailable_entities,
        }

    def parse_register_data(
        self,
        buffer: Any,
        registerInfo: dict[str, RegisterInfo],
        unit: int | str,
    ) -> dict[str, Any]:
        first_reg = self.api.get_first_register_id(registerInfo)
        decoder = VictronPayloadDecoder(buffer.registers, start_register=first_reg)
        decoded_data = OrderedDict()

        for key, value in registerInfo.items():
            full_key = f"{unit}.{key}"
            if value.dataType == UINT16:
                unscaled = decoder.decode_16bit_uint(value.register)
                decoded_data[full_key] = None if unscaled == 65535 else self.decode_scaling(unscaled, value.scale, value.unit)
            elif value.dataType == INT16:
                unscaled = decoder.decode_16bit_int(value.register)
                decoded_data[full_key] = None if unscaled == 32767 else self.decode_scaling(unscaled, value.scale, value.unit)
            elif value.dataType == UINT32:
                unscaled = decoder.decode_32bit_uint(value.register)
                decoded_data[full_key] = None if unscaled == 4294967295 else self.decode_scaling(unscaled, value.scale, value.unit)
            elif value.dataType == INT32:
                unscaled = decoder.decode_32bit_int(value.register)
                decoded_data[full_key] = None if unscaled == 2147483647 else self.decode_scaling(unscaled, value.scale, value.unit)
            elif isinstance(value.dataType, STRING):
                decoded_data[full_key] = decoder.decode_string(
                    value.register, value.dataType.readLength
                )
            else:
                raise DecodeDataTypeUnsupported(
                    f"Not supported dataType: {value.dataType}"
                )
        return decoded_data

    def decode_scaling(self, number: float | int, scale: float | int, unit: str) -> float | int:
        if unit == "" and scale == 1:
            return round(number)
        else:
            return number / scale if scale != 0 else number

    def encode_scaling(self, value: float | int, unit: str, scale: float | int) -> int:
        if scale == 0:
            return int(value)
        else:
            if unit == "" and scale == 1:
                return int(round(value))
            else:
                return int(round(value * scale))

    def get_data(self) -> dict:
        return self.data

    async def async_update_local_entry(self, key: str, value: Any) -> None:
        if self.data is not None and "data" in self.data:
            self.data["data"][key] = value
            self.async_set_updated_data(self.data)

    def processed_data(self) -> dict:
        return self.data if self.data is not None else {"data": {}, "availability": {}, "register_set": {}}

    async def fetch_registers(self, unit: int | str, registerData: dict) -> Any:
        try:
            return await self.hass.async_add_executor_job(
                self.api_update, unit, registerData
            )
        except Exception as err:
            _LOGGER.error("Fetching registers failed for unit %s: %s", unit, err, exc_info=True)
            return None

    def write_register(self, unit: int | str, address: int, value: int) -> Any:
        return self.api_write(unit, address, value)

    def api_write(self, unit: int | str, address: int, value: int) -> Any:
        return self.api.write_register(unit=int(unit), address=address, value=value)

    def api_update(self, unit: int | str, registerInfo: dict) -> Any:
        return self.api.read_holding_registers(
            unit=int(unit),
            address=self.api.get_first_register_id(registerInfo),
            count=self.api.calculate_register_count(registerInfo),
        )


class DecodeDataTypeUnsupported(Exception):
    pass


class DataEntry:
    def __init__(self, unit: int, value: Any) -> None:
        self.unit = unit
        self.value = value

