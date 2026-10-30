"""Modbus TCP server backed by the register table. Only module that imports pymodbus."""

from __future__ import annotations

import ipaddress
import logging
import math

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pymodbus.constants import ExcCodes
from pymodbus.datastore import ModbusServerContext
from pymodbus.exceptions import NoSuchIdException
from pymodbus.server import ModbusTcpServer
from pymodbus.server.requesthandler import ServerRequestHandler

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


def parse_networks(text: str) -> list[str]:
    """Parse comma or space separated IPs / CIDR ranges. Raises ValueError."""
    return [
        str(ipaddress.ip_network(part, strict=False)) for part in text.replace(",", " ").split()
    ]


class _FilteredHandler(ServerRequestHandler):
    """Closes connections from masters that are not on the allowlist."""

    def connection_made(self, transport) -> None:
        super().connection_made(transport)
        peer = transport.get_extra_info("peername")
        if peer and not self.server.peer_allowed(peer[0]):
            transport.abort()


class HAModbusServer(ModbusTcpServer):
    """Modbus TCP server with an optional IP allowlist."""

    def __init__(self, context: HAContext, host: str, port: int, allowed: list[str]) -> None:
        super().__init__(context, address=(host, port), ignore_missing_devices=True)
        self._allowed = [ipaddress.ip_network(net) for net in allowed]
        self._rejected: set[str] = set()

    def peer_allowed(self, host: str) -> bool:
        if not self._allowed:
            return True
        ip = ipaddress.ip_address(host.split("%", 1)[0])
        ip = getattr(ip, "ipv4_mapped", None) or ip  # dual-stack socket reports ::ffff:a.b.c.d
        if any(ip in net for net in self._allowed):
            return True
        if host not in self._rejected:  # warn once per address, a scanner must not flood the log
            self._rejected.add(host)
            _LOGGER.warning("Rejected Modbus connection from %s: not in the allowed list", host)
        return False

    def callback_new_connection(self) -> ServerRequestHandler:
        return _FilteredHandler(self, self.trace_packet, self.trace_pdu, self.trace_connect)

    @property
    def connected_masters(self) -> int:
        return len(self.active_connections)


async def start_server(
    context: HAContext, host: str, port: int, allowed: list[str]
) -> HAModbusServer:
    """Start listening; raises RuntimeError if the address cannot be bound."""
    server = HAModbusServer(context, host, port, allowed)
    await server.serve_forever(background=True)
    return server


async def stop_server(server: HAModbusServer) -> None:
    await server.shutdown()
