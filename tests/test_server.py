"""End-to-end tests: real Modbus TCP client against the integration."""

import asyncio
import struct
import time

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.modbus_slave.const import DOMAIN

ILLEGAL_ADDRESS, ILLEGAL_VALUE, DEVICE_FAILURE = 2, 3, 4


def f32(value: float) -> list[int]:
    return list(struct.unpack(">HH", struct.pack(">f", value)))


async def setup(hass, port, mappings=(), slave_id=1, **data):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=str(port),
        data={"slave_id": slave_id, "port": port, **data},
        options={"mappings": list(mappings)},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture
async def client(free_port):
    clients = []

    async def connect(port=free_port):
        c = AsyncModbusTcpClient("127.0.0.1", port=port, timeout=0.5, retries=0)
        clients.append(c)
        await c.connect()
        return c

    yield connect
    for c in clients:
        c.close()


async def test_reads_zero_and_ignores_other_slave(hass, free_port, client):
    await setup(hass, free_port)
    c = await client()
    assert c.connected
    assert (await c.read_holding_registers(0, count=1, device_id=1)).registers == [0]
    assert (await c.read_coils(0, count=1, device_id=1)).bits[0] is False
    with pytest.raises(ModbusException):
        await c.read_holding_registers(0, count=1, device_id=2)


async def test_unload_closes_port(hass, free_port, client):
    entry = await setup(hass, free_port)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    c = await client()
    assert not c.connected


async def test_values_follow_state(hass, free_port, client):
    hass.states.async_set("sensor.t", "12.3")
    hass.states.async_set("input_boolean.x", "on")
    await setup(
        hass,
        free_port,
        [
            {"entity_id": "sensor.t", "address": 100, "data_type": "float32"},
            {"entity_id": "input_boolean.x", "address": 0, "data_type": "bit"},
            {"entity_id": "sensor.gone", "address": 10, "data_type": "uint16", "fallback": 5},
        ],
    )
    c = await client()
    assert (await c.read_holding_registers(100, count=2, device_id=1)).registers == [0x4144, 0xCCCD]
    assert (await c.read_input_registers(100, count=2, device_id=1)).registers == [0x4144, 0xCCCD]
    assert (await c.read_coils(0, count=1, device_id=1)).bits[0] is True
    assert (await c.read_discrete_inputs(0, count=1, device_id=1)).bits[0] is True
    assert (await c.read_holding_registers(10, count=1, device_id=1)).registers == [5]

    start = time.monotonic()
    hass.states.async_set("sensor.t", "15")
    await hass.async_block_till_done()
    assert (await c.read_holding_registers(100, count=2, device_id=1)).registers == f32(15)
    assert time.monotonic() - start < 1

    hass.states.async_set("sensor.t", "unavailable")
    await hass.async_block_till_done()
    assert (await c.read_holding_registers(100, count=2, device_id=1)).registers == [0, 0]


@pytest.fixture
async def writable(hass, free_port):
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, "input_boolean", {"input_boolean": {"x": {}}})
    assert await async_setup_component(
        hass, "input_number", {"input_number": {"sp": {"min": 0, "max": 30, "step": 0.5}}}
    )
    hass.states.async_set("sensor.ro", "1")
    return await setup(
        hass,
        free_port,
        [
            {"entity_id": "input_boolean.x", "address": 0, "data_type": "bit", "writable": True},
            {
                "entity_id": "input_number.sp",
                "address": 200,
                "data_type": "float32",
                "writable": True,
            },
            {"entity_id": "sensor.ro", "address": 300, "data_type": "uint16"},
        ],
    )


async def test_bit_write(hass, writable, client):
    c = await client()
    assert not (await c.write_coil(0, True, device_id=1)).isError()
    await hass.async_block_till_done()
    assert hass.states.get("input_boolean.x").state == "on"
    assert (await c.read_coils(0, count=1, device_id=1)).bits[0] is True

    assert not (await c.write_coils(0, [False], device_id=1)).isError()
    await hass.async_block_till_done()
    assert hass.states.get("input_boolean.x").state == "off"


async def test_register_write(hass, writable, client):
    c = await client()
    assert not (await c.write_registers(200, f32(21.5), device_id=1)).isError()
    await hass.async_block_till_done()
    assert float(hass.states.get("input_number.sp").state) == 21.5
    assert (await c.read_holding_registers(200, count=2, device_id=1)).registers == f32(21.5)

    async def code(coro):
        return (await coro).exception_code

    assert await code(c.write_register(200, 0x41AC, device_id=1)) == ILLEGAL_ADDRESS  # half float
    assert await code(c.write_registers(200, f32(40), device_id=1)) == ILLEGAL_VALUE
    assert await code(c.write_register(300, 1, device_id=1)) == ILLEGAL_ADDRESS  # read-only
    assert await code(c.write_register(999, 1, device_id=1)) == ILLEGAL_ADDRESS  # unmapped
    assert await code(c.write_coil(5, True, device_id=1)) == ILLEGAL_ADDRESS
    assert float(hass.states.get("input_number.sp").state) == 21.5


async def test_service_failure(hass, free_port, client):
    async def fail(call):
        raise HomeAssistantError("boom")

    hass.services.async_register("number", "set_value", fail)
    hass.states.async_set("number.bad", "1", {"min": 0, "max": 10})
    await setup(
        hass,
        free_port,
        [{"entity_id": "number.bad", "address": 0, "data_type": "uint16", "writable": True}],
    )
    c = await client()
    assert (await c.write_register(0, 2, device_id=1)).exception_code == DEVICE_FAILURE
    assert (await c.read_holding_registers(0, count=1, device_id=1)).registers == [1]


async def test_options_change_applies_without_restart(hass, free_port, client):
    hass.states.async_set("sensor.t", "7")
    entry = await setup(
        hass, free_port, [{"entity_id": "sensor.t", "address": 0, "data_type": "float32"}]
    )
    c = await client()
    assert (await c.read_holding_registers(0, count=2, device_id=1)).registers == f32(7)
    c.close()

    hass.config_entries.async_update_entry(entry, options={"mappings": []})
    await hass.async_block_till_done()
    c = await client()
    assert (await c.read_holding_registers(0, count=2, device_id=1)).registers == [0, 0]


async def test_many_mappings_and_clients(hass, free_port, client):
    mappings = []
    for i in range(500):
        hass.states.async_set(f"sensor.s{i}", str(i))
        mappings.append({"entity_id": f"sensor.s{i}", "address": i * 2, "data_type": "float32"})
    await setup(hass, free_port, mappings)
    clients = [await client() for _ in range(10)]

    start = time.monotonic()
    results = await asyncio.gather(
        *(c.read_holding_registers(0, count=100, device_id=1) for c in clients)
    )
    assert time.monotonic() - start < 1
    assert all(r.registers[2:4] == f32(1) for r in results)


async def test_allowlist_rejects_other_masters(hass, free_port, client, caplog):
    await setup(hass, free_port, allowed_ips=["10.0.0.5/32"])
    c = await client()
    with pytest.raises(ModbusException):
        await c.read_holding_registers(0, count=1, device_id=1)
    assert "Rejected Modbus connection from 127.0.0.1" in caplog.text


async def test_allowlist_accepts_listed_master(hass, free_port, client):
    await setup(hass, free_port, allowed_ips=["10.0.0.5/32", "127.0.0.0/8"])
    c = await client()
    assert (await c.read_holding_registers(0, count=1, device_id=1)).registers == [0]


async def test_listen_address(hass, free_port, client):
    entry = await setup(hass, free_port, host="127.0.0.1")
    c = await client()
    assert (await c.read_holding_registers(0, count=1, device_id=1)).registers == [0]
    assert entry.runtime_data.server.connected_masters == 1
