"""Usage report: only a random installation ID, opt-out."""

import uuid
from datetime import timedelta

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.modbus_slave.const import DOMAIN, TELEMETRY_URL
from custom_components.modbus_slave.telemetry import TelemetryReporter, build_report


def test_report_has_only_schema_and_install_id():
    install_id = str(uuid.uuid4()).upper()
    assert build_report(install_id) == {"schema": 1, "install_id": install_id.lower()}


def add_entry(hass, port, share_usage):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=str(port),
        data={"slave_id": 1, "port": port, "share_usage": share_usage},
        options={"mappings": []},
    )
    entry.add_to_hass(hass)
    return entry


async def test_sends_when_opted_in(hass, aioclient_mock):
    aioclient_mock.post(TELEMETRY_URL, status=204)
    add_entry(hass, 5020, share_usage=True)
    reporter = TelemetryReporter(hass)

    await reporter.async_send()
    await reporter.async_send()

    assert aioclient_mock.call_count == 2
    first, second = (call[2] for call in aioclient_mock.mock_calls)
    assert set(first) == {"schema", "install_id"}
    assert uuid.UUID(first["install_id"])
    assert first == second  # the installation ID is stable


async def test_entry_without_the_option_counts_as_on(hass, aioclient_mock):
    aioclient_mock.post(TELEMETRY_URL, status=204)
    MockConfigEntry(
        domain=DOMAIN, unique_id="5020", data={"slave_id": 1, "port": 5020}, options={}
    ).add_to_hass(hass)

    await TelemetryReporter(hass).async_send()

    assert aioclient_mock.call_count == 1


async def test_sends_nothing_when_opted_out(hass, aioclient_mock):
    aioclient_mock.post(TELEMETRY_URL, status=204)
    add_entry(hass, 5020, share_usage=False)
    add_entry(hass, 5021, share_usage=False)

    await TelemetryReporter(hass).async_send()

    assert aioclient_mock.call_count == 0


async def test_server_error_is_silent(hass, aioclient_mock, caplog):
    aioclient_mock.post(TELEMETRY_URL, status=500)
    add_entry(hass, 5020, share_usage=True)

    await TelemetryReporter(hass).async_send()

    assert aioclient_mock.call_count == 1
    assert "WARNING" not in caplog.text and "ERROR" not in caplog.text


async def test_schedule(hass, aioclient_mock):
    aioclient_mock.post(TELEMETRY_URL, status=204)
    add_entry(hass, 5020, share_usage=True)
    reporter = TelemetryReporter(hass)
    reporter.async_start()

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=599))
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == 0

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=601))
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == 1

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=6, seconds=1))
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == 2

    reporter.async_stop()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=13))
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == 2
