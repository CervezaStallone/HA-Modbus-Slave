"""Modbus TCP server backed by the register table. Only module that imports pymodbus."""

from __future__ import annotations

import logging
import math

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pymodbus.constants import ExcCodes
from pymodbus.datastore import ModbusServerContext
from pymodbus.exceptions import NoSuchIdException
from pymodbus.server import ModbusTcpServer

from .registers import RegisterTable, decode

_LOGGER = logging.getLogger(__name__)

_READ_SPACES = {1: "bits", 2: "bits", 3: "registers", 4: "registers", 23: "registers"}
_WRITE_SPACES = {5: "bits", 15: "bits", 6: "registers", 16: "registers", 23: "registers"}
_ECHO_CODES = (5, 6)  # single writes echo the request back


class HAContext(ModbusServerContext):
    """Serves one slave ID from the register table and forwards writes to HA.

    Subclassed only because ModbusTcpServer type-checks the context; the
    deprecated base __init__ is deliberately not called.
    """

    def __init__(self, hass: HomeAssistant, slave_id: int, table: RegisterTable) -> None:
        self.hass = hass
        self.slave_id = slave_id
        self.table = table
        self.simdevices = []
        self._echo: list = []

    def device_ids(self) -> list[int]:
        return [self.slave_id]

    def _check_device(self, device_id: int) -> None:
        if device_id != self.slave_id:
            raise NoSuchIdException(f"device_id {device_id} is not served")

    async def async_getValues(  # noqa: N802 - pymodbus API name
        self, device_id: int, func_code: int, address: int, count: int = 1
    ) -> list[int] | list[bool] | ExcCodes:
        self._check_device(device_id)
        if func_code in _ECHO_CODES:
            return self._echo
        space = _READ_SPACES.get(func_code)
        if space == "bits":
            return self.table.read_bits(address, count)
        if space == "registers":
            return self.table.read_registers(address, count)
        return ExcCodes.ILLEGAL_FUNCTION

    async def async_setValues(  # noqa: N802 - pymodbus API name
        self, device_id: int, func_code: int, address: int, values: list[int] | list[bool]
    ) -> ExcCodes | None:
        self._check_device(device_id)
        space = _WRITE_SPACES.get(func_code)
        if space is None:
            return ExcCodes.ILLEGAL_FUNCTION
        mapping = self.table.writable_mapping_at(space, address, len(values))
        if mapping is None:
            return ExcCodes.ILLEGAL_ADDRESS

        value = decode(mapping, list(values))
        domain = mapping.entity_id.split(".", 1)[0]
        try:
            if space == "bits":
                service = "turn_on" if value else "turn_off"
                await self.hass.services.async_call(
                    "homeassistant", service, {"entity_id": mapping.entity_id}, blocking=True
                )
            else:
                state = self.hass.states.get(mapping.entity_id)
                attrs = state.attributes if state else {}
                if math.isnan(value) or not (
                    attrs.get("min", -math.inf) <= value <= attrs.get("max", math.inf)
                ):
                    return ExcCodes.ILLEGAL_VALUE
                await self.hass.services.async_call(
                    domain,
                    "set_value",
                    {"entity_id": mapping.entity_id, "value": value},
                    blocking=True,
                )
        except (HomeAssistantError, ValueError) as err:
            _LOGGER.warning("Modbus write to %s failed: %s", mapping.entity_id, err)
            return ExcCodes.DEVICE_FAILURE
        # register itself is updated by the state listener, not optimistically
        self._echo = list(values)
        return None


async def start_server(context: HAContext, port: int) -> ModbusTcpServer:
    """Start listening; raises RuntimeError if the port cannot be bound."""
    server = ModbusTcpServer(context, address=("", port), ignore_missing_devices=True)
    await server.serve_forever(background=True)
    return server


async def stop_server(server: ModbusTcpServer) -> None:
    await server.shutdown()
