"""Diagnostics download for Modbus Slave."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_ALLOWED_IPS, CONF_HOST

TO_REDACT = {CONF_HOST, CONF_ALLOWED_IPS}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    runtime = entry.runtime_data
    table = runtime.table
    mappings = []
    for mapping in table.mappings:
        state = hass.states.get(mapping.entity_id)
        read = table.read_bits if mapping.space == "bits" else table.read_registers
        mappings.append(
            {
                **mapping.as_dict(),
                "state": state.state if state else None,
                "values": read(mapping.address, mapping.size),
            }
        )
    return {
        "config": async_redact_data(dict(entry.data), TO_REDACT),
        "connected_masters": runtime.server.connected_masters,
        "mappings": mappings,
    }
