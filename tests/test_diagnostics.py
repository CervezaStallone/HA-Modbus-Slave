"""Diagnostics download."""

from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)

from custom_components.modbus_slave.const import DOMAIN


async def test_diagnostics(hass, hass_client, free_port):
    assert await async_setup_component(hass, "diagnostics", {})
    hass.states.async_set("sensor.t", "12.3")
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=str(free_port),
        data={
            "slave_id": 1,
            "port": free_port,
            "host": "127.0.0.1",
            "allowed_ips": ["10.0.0.5/32"],
        },
        options={
            "mappings": [
                {"entity_id": "sensor.t", "address": 100, "data_type": "float32"},
                {"entity_id": "sensor.gone", "address": 0, "data_type": "uint16"},
            ]
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)

    result = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    assert result["config"] == {
        "slave_id": 1,
        "port": free_port,
        "host": "**REDACTED**",
        "allowed_ips": "**REDACTED**",
    }
    assert result["connected_masters"] == 0
    assert result["mappings"][0]["state"] == "12.3"
    assert result["mappings"][0]["values"] == [0x4144, 0xCCCD]
    assert result["mappings"][1]["state"] is None
    assert result["mappings"][1]["values"] == [0]
