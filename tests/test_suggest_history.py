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


async def test_no_history_query_when_it_cannot_change_the_answers(hass, monkeypatch):
    calls = []

    async def spy(_hass, entity_id):
        calls.append(entity_id)
        return None, None, None, 0

    monkeypatch.setattr(suggest, "_history_minmax", spy)
    hass.states.async_set("number.n", "5", {"min": 0, "max": 10, "step": 1})
    hass.states.async_set("switch.s", "on")
    await suggest.async_gather_evidence(hass, "number.n")
    await suggest.async_gather_evidence(hass, "switch.s")
    assert calls == []


async def test_raw_history_query_is_small(hass, monkeypatch):
    from homeassistant.components.recorder import history
    from homeassistant.util import dt as dt_util

    seen = {}

    def spy(_hass, start_time, *args, **kwargs):
        seen["days"] = (dt_util.utcnow() - start_time).total_seconds() / 86400
        seen.update(kwargs)
        return {}

    monkeypatch.setattr(history, "get_significant_states", spy)
    hass.states.async_set("sensor.p1", "1234")
    await suggest.async_gather_evidence(hass, "sensor.p1")
    assert seen["days"] <= 2.01  # a 1 Hz meter: ~170k rows, not millions
    assert seen["minimal_response"] is True


async def test_statistics_rows_without_min_max_do_not_count_as_days(hass, monkeypatch):
    from homeassistant.components.recorder import statistics
    from homeassistant.util import dt as dt_util

    old = dt_util.utcnow().timestamp() - 300 * 86400
    monkeypatch.setattr(
        statistics,
        "statistics_during_period",
        lambda *a, **k: {"sensor.e": [{"start": old, "min": None, "max": None}]},
    )
    hass.states.async_set("sensor.e", "139.56")
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)
    evidence = await suggest.async_gather_evidence(hass, "sensor.e")
    assert evidence.history_days == 1


async def test_statistics_extend_range_and_days_are_capped(hass, monkeypatch):
    from homeassistant.components.recorder import statistics
    from homeassistant.util import dt as dt_util

    now = dt_util.utcnow().timestamp()
    rows = [
        {"start": now - 390 * 86400, "min": -5.5, "max": 12.0},  # month bucket before window
        {"start": now - 100 * 86400, "min": 2.0, "max": 30.25},
    ]
    monkeypatch.setattr(
        statistics, "statistics_during_period", lambda *a, **k: {"sensor.out": rows}
    )
    hass.states.async_set("sensor.out", "8.1")
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)
    evidence = await suggest.async_gather_evidence(hass, "sensor.out")
    assert (evidence.lo, evidence.hi) == (-5.5, 30.25)
    assert evidence.history_days == 365
