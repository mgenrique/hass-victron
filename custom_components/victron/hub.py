import logging
import threading
from typing import Any

from pymodbus.client import ModbusTcpClient

from .const import INT32, STRING, UINT32, register_info_dict, valid_unit_ids

_LOGGER = logging.getLogger(__name__)


class VictronHub:
    def __init__(self, host: str, port: int) -> None:
        """Initialize Victron Modbus TCP Hub."""
        self.host = host
        self.port = int(port)
        self._client = ModbusTcpClient(host=self.host, port=self.port, timeout=5)
        self._lock = threading.Lock()

    def is_still_connected(self) -> bool:
        try:
            if getattr(self._client, "socket", None) is None:
                return False
            if hasattr(self._client, "is_socket_open") and callable(self._client.is_socket_open):
                return bool(self._client.is_socket_open())
            if hasattr(self._client, "connected"):
                conn = getattr(self._client, "connected")
                return bool(conn() if callable(conn) else conn)
            return True
        except Exception:
            return False

    def connect(self) -> bool:
        with self._lock:
            try:
                res = self._client.connect()
                _LOGGER.info("VictronHub connecting to %s:%s -> %s", self.host, self.port, res)
                return bool(res)
            except Exception as err:
                _LOGGER.error("Failed to connect to Victron hub at %s:%s: %s", self.host, self.port, err, exc_info=True)
                return False

    def disconnect(self) -> None:
        with self._lock:
            try:
                if hasattr(self._client, "close"):
                    self._client.close()
            except Exception as err:
                _LOGGER.debug("Error closing connection to Victron hub: %s", err)

    def _call_pymodbus(self, method_name: str, address: int, value_or_count: int, slave: int) -> Any:
        method = getattr(self._client, method_name)
        kw_name = "value" if method_name == "write_register" else "count"
        
        try:
            return method(address=address, **{kw_name: value_or_count}, slave=slave)
        except TypeError as e1:
            if "unexpected keyword argument" not in str(e1):
                raise
            try:
                return method(address=address, **{kw_name: value_or_count}, unit=slave)
            except TypeError as e2:
                if "unexpected keyword argument" not in str(e2):
                    raise
                try:
                    return method(address=address, **{kw_name: value_or_count}, slave_id=slave)
                except TypeError as e3:
                    if "unexpected keyword argument" not in str(e3):
                        raise
                    try:
                        return method(address=address, **{kw_name: value_or_count}, device_id=slave)
                    except TypeError as e4:
                        if "unexpected keyword argument" not in str(e4):
                            raise
                        # Final fallback: pure positional
                        return method(address, value_or_count, slave)

    def write_register(self, unit: int, address: int, value: int) -> Any:
        with self._lock:
            if not self.is_still_connected():
                if not self._client.connect():
                    _LOGGER.error("Cannot write register: not connected to %s:%s", self.host, self.port)
                    return None
            slave = int(unit) if unit is not None and str(unit) != "" else 1
            addr_int = int(address)
            val_int = int(value)
            try:
                return self._call_pymodbus("write_register", addr_int, val_int, slave)
            except Exception as err:
                _LOGGER.error("Failed writing register %s on slave %s: %s", addr_int, slave, err, exc_info=True)
                return None

    def read_holding_registers(self, unit: int, address: int, count: int) -> Any:
        """Read holding registers."""
        with self._lock:
            if not self.is_still_connected():
                conn_res = self._client.connect()
                if not conn_res:
                    _LOGGER.error("Cannot read registers: connection to %s:%s failed", self.host, self.port)
                    return None

            slave = int(unit) if unit is not None and str(unit) != "" else 1
            addr_int = int(address)
            cnt_int = int(count)
            try:
                resp = self._call_pymodbus("read_holding_registers", addr_int, cnt_int, slave)
            except Exception as err:
                _LOGGER.error("Error reading registers from address %s, count %s on slave %s: %s", addr_int, cnt_int, slave, err, exc_info=True)
                return None

            if resp is None:
                _LOGGER.warning("read_holding_registers returned None for slave %s, address %s, count %s", slave, addr_int, cnt_int)
            elif hasattr(resp, "isError") and resp.isError():
                _LOGGER.debug("Modbus error response for slave %s, address %s, count %s: %s", slave, addr_int, cnt_int, resp)

            return resp

    def calculate_register_count(self, registerInfoDict: dict) -> int:
        if not registerInfoDict:
            return 1
        items = list(registerInfoDict.values())
        min_reg = min(item.register for item in items)
        max_item = max(items, key=lambda item: item.register)
        end_correction = 1
        if max_item.dataType in (INT32, UINT32):
            end_correction = 2
        elif isinstance(max_item.dataType, STRING):
            end_correction = max_item.dataType.length

        return (max_item.register - min_reg) + end_correction

    def get_first_register_id(self, registerInfoDict: dict) -> int:
        if not registerInfoDict:
            return 0
        return min(item.register for item in registerInfoDict.values())

    def determine_present_devices(self) -> dict[int, list[str]]:
        valid_devices: dict[int, list[str]] = {}

        if not self.is_still_connected():
            self.connect()

        for unit in valid_unit_ids:
            working_registers: list[str] = []
            for key, register_definition in register_info_dict.items():
                try:
                    address = self.get_first_register_id(register_definition)
                    count = self.calculate_register_count(register_definition)
                    result = self.read_holding_registers(unit, address, count)
                    is_error = (
                        result is None
                        or (hasattr(result, "isError") and result.isError())
                        or not hasattr(result, "registers")
                        or result.registers is None
                    )
                    if is_error:
                        _LOGGER.debug(
                            "Result is error for unit: %s address: %s count: %s -> %s",
                            unit,
                            address,
                            count,
                            result,
                        )
                    else:
                        working_registers.append(key)
                except Exception as e:  # pylint: disable=broad-except
                    _LOGGER.error("Error checking register %s on unit %s: %s", key, unit, e)

            if len(working_registers) > 0:
                valid_devices[unit] = working_registers
            else:
                _LOGGER.debug("No registers found for unit: %s", unit)

        return valid_devices




