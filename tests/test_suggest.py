"""Evidence about an entity's value, gathered from Home Assistant."""

from homeassistant.helpers import entity_registry as er

from custom_components.modbus_slave import suggest
from custom_components.modbus_slave.registers import Evidence


async def test_evidence_from_state_and_attributes(hass):
    hass.states.async_set("number.n", "5", {"min": -10, "max": 40, "step": 0.5})
    assert await suggest.async_gather_evidence(hass, "number.n") == Evidence(
        current=5, lo=5, hi=5, bounds=(-10, 40), decimals=1
    )


async def test_evidence_display_precision(hass):
    registry = er.async_get(hass)
    entry = registry.async_get_or_create("sensor", "test", "p", suggested_object_id="p")
    registry.async_update_entity_options(
        entry.entity_id, "sensor", {"suggested_display_precision": 2}
    )
    hass.states.async_set(entry.entity_id, "3", {"device_class": "power"})
    evidence = await suggest.async_gather_evidence(hass, entry.entity_id)
    assert evidence.decimals == 2
    assert evidence.device_class == "power"


async def test_evidence_without_recorder(hass):
    hass.states.async_set("sensor.t", "3.5")
    assert await suggest.async_gather_evidence(hass, "sensor.t") == Evidence(
        current=3.5, lo=3.5, hi=3.5, decimals=1, history_days=0
    )
