"""Home Assistant as a Modbus TCP slave."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_ALLOWED_IPS, CONF_HOST, CONF_MAPPINGS, CONF_PORT, CONF_SLAVE_ID, DOMAIN
from .registers import Mapping, RegisterTable, encode
from .server import HAContext, HAModbusServer, start_server, stop_server
from .telemetry import TelemetryReporter

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
DATA_SERVERS = f"{DOMAIN}_servers"  # port -> SharedServer: one listener per port
DATA_LOCK = f"{DOMAIN}_servers_lock"  # entries on one port start together at boot


@dataclass
class SharedServer:
    """One TCP listener; every entry on its port adds a slave ID to the context."""

    server: HAModbusServer
    context: HAContext
    host: str
    allowed: list[str]


@dataclass
class RuntimeData:
    server: HAModbusServer
    table: RegisterTable
    port: int  # as served: entry.data already holds the new values when a reload unloads
    slave_id: int


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Start the usage reporter once; it sends nothing when every entry opted out."""
    reporter = TelemetryReporter(hass)
    reporter.async_start()
    hass.data[DOMAIN] = reporter
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    mappings = [Mapping.from_dict(d) for d in entry.options.get(CONF_MAPPINGS, [])]
    table = RegisterTable(mappings)
    warned: set[int] = set()

    @callback
    def update(entity_id: str) -> None:
        state = hass.states.get(entity_id)
        for index, mapping in enumerate(mappings):
            if mapping.entity_id != entity_id:
                continue
            text = state.state if state else "unavailable"
            values, clamped = encode(mapping, text)
            if clamped and index not in warned:
                warned.add(index)
                _LOGGER.warning(
                    "%s value %s does not fit %s at address %s, clamped",
                    entity_id,
                    text,
                    mapping.data_type,
                    mapping.address,
                )
            table.apply(mapping, values)

    entity_ids = {mapping.entity_id for mapping in mappings}
    for entity_id in entity_ids:
        update(entity_id)

    async with hass.data.setdefault(DATA_LOCK, asyncio.Lock()):
        shared = await _async_join_server(hass, entry, table)
    entry.runtime_data = RuntimeData(
        shared.server, table, entry.data[CONF_PORT], entry.data[CONF_SLAVE_ID]
    )

    @callback
    def on_state_change(event: Event[EventStateChangedData]) -> None:
        update(event.data["entity_id"])

    entry.async_on_unload(async_track_state_change_event(hass, entity_ids, on_state_change))
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_join_server(
    hass: HomeAssistant, entry: ConfigEntry, table: RegisterTable
) -> SharedServer:
    """Serve this entry's slave ID on its port, starting the listener if it is the first."""
    servers: dict[int, SharedServer] = hass.data.setdefault(DATA_SERVERS, {})
    port, slave_id = entry.data[CONF_PORT], entry.data[CONF_SLAVE_ID]
    host, allowed = entry.data.get(CONF_HOST, ""), entry.data.get(CONF_ALLOWED_IPS, [])
    shared = servers.get(port)
    if shared is None:
        context = HAContext(hass)
        try:
            server = await start_server(context, host, port, allowed)
        except (OSError, RuntimeError) as err:
            raise ConfigEntryNotReady(f"Cannot listen on port {port}") from err
        shared = servers[port] = SharedServer(server, context, host, allowed)
    elif (shared.host, sorted(shared.allowed)) != (host, sorted(allowed)):
        # the config flow prevents this; a listener has one address and one allowlist
        raise ConfigEntryError(f"Port {port} is shared with a different host or allowed IPs")
    if slave_id in shared.context.tables:
        raise ConfigEntryError(f"Slave ID {slave_id} is already served on port {port}")
    shared.context.tables[slave_id] = table
    return shared


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    runtime: RuntimeData = entry.runtime_data
    servers: dict[int, SharedServer] = hass.data[DATA_SERVERS]
    async with hass.data[DATA_LOCK]:
        shared = servers[runtime.port]
        shared.context.tables.pop(runtime.slave_id, None)
        if not shared.context.tables:  # last slave on this port: stop listening
            del servers[runtime.port]
            await stop_server(shared.server)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """1.1 → 1.2: unique ID is port and slave ID, so slaves can share a port."""
    if entry.version == 1 and entry.minor_version < 2:
        hass.config_entries.async_update_entry(
            entry,
            unique_id=f"{entry.data[CONF_PORT]}-{entry.data[CONF_SLAVE_ID]}",
            minor_version=2,
        )
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
