"""Home Assistant as a Modbus TCP slave."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_ALLOWED_IPS, CONF_HOST, CONF_MAPPINGS, CONF_PORT, CONF_SLAVE_ID, DOMAIN
from .registers import Mapping, RegisterTable, encode
from .server import HAContext, HAModbusServer, start_server, stop_server
from .telemetry import TelemetryReporter

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class RuntimeData:
    server: HAModbusServer
    table: RegisterTable


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

    context = HAContext(hass, entry.data[CONF_SLAVE_ID], table)
    try:
        server = await start_server(
            context,
            entry.data.get(CONF_HOST, ""),
            entry.data[CONF_PORT],
            entry.data.get(CONF_ALLOWED_IPS, []),
        )
    except (OSError, RuntimeError) as err:
        raise ConfigEntryNotReady(f"Cannot listen on port {entry.data[CONF_PORT]}") from err
    entry.runtime_data = RuntimeData(server, table)

    @callback
    def on_state_change(event: Event[EventStateChangedData]) -> None:
        update(event.data["entity_id"])

    entry.async_on_unload(async_track_state_change_event(hass, entity_ids, on_state_change))
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await stop_server(entry.runtime_data.server)
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
