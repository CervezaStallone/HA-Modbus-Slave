"""Evidence from the recorder: history and statistics."""

import asyncio
import time

import pytest
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.modbus_slave import suggest
from custom_components.modbus_slave.registers import Evidence


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock, enable_custom_integrations):
    """The recorder must start before hass, so it joins the autouse fixture here."""
    yield


async def test_evidence_from_history(hass):
    for state in ("-4.25", "12.3", "unavailable", "31.7"):
        hass.states.async_set("sensor.t", state, {"state_class": "measurement"})
        await hass.async_block_till_done()
    await async_wait_recording_done(hass)
    evidence = await suggest.async_gather_evidence(hass, "sensor.t")
    assert evidence.lo == -4.25
    assert evidence.hi == 31.7
    assert evidence.current == 31.7
    assert evidence.decimals == 2
    assert evidence.state_class == "measurement"
    assert evidence.history_days >= 1


async def test_evidence_unavailable_now_uses_history(hass):
    for state in ("7.5", "unavailable"):
        hass.states.async_set("sensor.t", state)
        await hass.async_block_till_done()
    await async_wait_recording_done(hass)
    evidence = await suggest.async_gather_evidence(hass, "sensor.t")
    assert evidence.current is None
    assert evidence.hi == 7.5
    assert evidence.decimals == 1


async def test_evidence_timeout(hass, monkeypatch):
    async def slow(*_args):
        await asyncio.sleep(10)

    monkeypatch.setattr(suggest, "_history_minmax", slow)
    monkeypatch.setattr(suggest, "HISTORY_TIMEOUT", 0.05)
    hass.states.async_set("sensor.t", "2")
    start = time.monotonic()
    evidence = await suggest.async_gather_evidence(hass, "sensor.t")
    assert time.monotonic() - start < 1
    assert evidence == Evidence(current=2, lo=2, hi=2, decimals=0, history_days=0)
