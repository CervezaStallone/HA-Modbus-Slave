"""Diagnostics download for Modbus Slave."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_ALLOWED_IPS, CONF_HOST, CONF_MAPPINGS
from .registers import Mapping

TO_REDACT = {CONF_HOST, CONF_ALLOWED_IPS}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    # not set when setup failed (e.g. port in use), which is when diagnostics matter most
    runtime = getattr(entry, "runtime_data", None)
    if runtime:
        table = runtime.table
        mapping_list = table.mappings
    else:
        table = None
        mapping_list = [Mapping.from_dict(d) for d in entry.options.get(CONF_MAPPINGS, [])]

    mappings = []
    for mapping in mapping_list:
        state = hass.states.get(mapping.entity_id)
        values = None
        if table:
            read = table.read_bits if mapping.space == "bits" else table.read_registers
            values = read(mapping.address, mapping.size)
        mappings.append(
            {
                **mapping.as_dict(),
                "state": state.state if state else None,
                "values": values,
            }
        )
    return {
        "config": async_redact_data(dict(entry.data), TO_REDACT),
        "state": entry.state.value,
        "connected_masters": runtime.server.connected_masters if runtime else None,
        "mappings": mappings,
    }
