"""Config, reconfigure and options flow tests."""

import asyncio

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.modbus_slave.const import DOMAIN


async def test_user_creates_entry(hass, free_port):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"slave_id": 3, "port": free_port}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"Modbus Slave (port {free_port}, ID 3)"
    assert result["data"] == {"slave_id": 3, "port": free_port, "host": "", "allowed_ips": []}


async def test_user_defaults(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    defaults = {str(k): k.default() for k in result["data_schema"].schema}
    assert defaults == {"slave_id": 1, "port": 502, "host": "", "allowed_ips": ""}


@pytest.mark.parametrize(
    "data",
    [
        {"slave_id": 0, "port": 5020},
        {"slave_id": 248, "port": 5020},
        {"slave_id": 1, "port": 0},
        {"slave_id": 1, "port": 65536},
    ],
)
async def test_user_rejects_out_of_range(hass, data):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(result["flow_id"], data)


async def test_user_port_in_use(hass, free_port):
    blocker = await asyncio.start_server(lambda _r, _w: None, port=free_port)
    try:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"slave_id": 1, "port": free_port}
        )
    finally:
        blocker.close()
        await blocker.wait_closed()
    assert result["errors"] == {"base": "port_in_use"}


async def test_user_duplicate_port(hass, free_port):
    MockConfigEntry(domain=DOMAIN, unique_id=str(free_port)).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"slave_id": 1, "port": free_port}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def setup_entry(hass, port, mappings=()):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=str(port),
        data={"slave_id": 1, "port": port},
        options={"mappings": list(mappings)},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_reconfigure_changes_port(hass, free_port):
    entry = await setup_entry(hass, free_port)
    new_port = free_port + 1 if free_port < 65535 else free_port - 1
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"slave_id": 9, "port": new_port}
    )
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {"slave_id": 9, "port": new_port, "host": "", "allowed_ips": []}
    assert entry.unique_id == str(new_port)
    # old port is free again, new port is held by the reloaded server
    blocker = await asyncio.start_server(lambda _r, _w: None, port=free_port)
    blocker.close()
    await blocker.wait_closed()
    with pytest.raises(OSError):
        await asyncio.start_server(lambda _r, _w: None, port=new_port)


async def test_reconfigure_same_port_keeps_working(hass, free_port):
    entry = await setup_entry(hass, free_port)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"slave_id": 2, "port": free_port}
    )
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["slave_id"] == 2


async def add_mapping(hass, entry, entity, address, **confirm):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_mapping"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"entity": entity, "address": address}
    )
    if result["step_id"] != "confirm":
        return result
    defaults = {str(k): k.default() for k in result["data_schema"].schema}
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {**defaults, **confirm}
    ), defaults


async def test_add_mapping_detects_type(hass, free_port):
    hass.states.async_set("sensor.t", "12.34")
    entry = await setup_entry(hass, free_port)
    result, defaults = await add_mapping(hass, entry, "sensor.t", 100)
    assert defaults["data_type"] == "float32"
    assert defaults["scale"] == "100"
    assert defaults["writable"] is False
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["mappings"] == [
        {
            "entity_id": "sensor.t",
            "address": 100,
            "data_type": "float32",
            "scale": 100,
            "signed": False,
            "writable": False,
            "fallback": 0,
        }
    ]


async def test_add_mapping_unsupported(hass, free_port):
    hass.states.async_set("sensor.text", "hello")
    entry = await setup_entry(hass, free_port)
    result = await add_mapping(hass, entry, "sensor.text", 0)
    assert result["errors"] == {"base": "unsupported_entity"}


async def test_add_mapping_overlap(hass, free_port):
    hass.states.async_set("sensor.a", "1")
    hass.states.async_set("sensor.b", "1")
    entry = await setup_entry(
        hass, free_port, [{"entity_id": "sensor.a", "address": 100, "data_type": "float32"}]
    )
    result, _ = await add_mapping(hass, entry, "sensor.b", 101)
    assert result["errors"] == {"base": "address_overlap"}
    assert result["description_placeholders"]["conflict"] == "sensor.a"


async def test_add_mapping_past_end(hass, free_port):
    hass.states.async_set("sensor.a", "1")
    entry = await setup_entry(hass, free_port)
    result, _ = await add_mapping(hass, entry, "sensor.a", 65535)
    assert result["errors"] == {"base": "address_out_of_range"}


@pytest.mark.parametrize(
    ("entity", "state", "data_type", "error"),
    [
        ("sensor.s", "1", "float32", "not_writable"),
        ("binary_sensor.b", "on", "bit", "not_writable"),
        ("input_number.n", "1", "bit", "type_mismatch"),
        ("switch.s", "on", "uint16", "type_mismatch"),
        ("switch.s", "on", "bit", None),
        ("light.l", "on", "bit", None),
        ("input_number.n", "1", "float32", None),
    ],
)
async def test_writable_validation(hass, free_port, entity, state, data_type, error):
    hass.states.async_set(entity, state, {"min": 0, "max": 10, "step": 1})
    entry = await setup_entry(hass, free_port)
    result, _ = await add_mapping(hass, entry, entity, 0, data_type=data_type, writable=True)
    if error:
        assert result["errors"] == {"base": error}
    else:
        assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_edit_and_remove(hass, free_port):
    hass.states.async_set("sensor.a", "1")
    entry = await setup_entry(
        hass,
        free_port,
        [
            {"entity_id": "sensor.a", "address": 100, "data_type": "float32"},
            {"entity_id": "sensor.gone", "address": 200, "data_type": "uint16"},
        ],
    )
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["menu_options"] == ["add_mapping", "edit_mapping", "remove_mapping"]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "edit_mapping"}
    )
    options = result["data_schema"].schema["mapping"].config["options"]
    assert [o["label"] for o in options] == [
        "sensor.a → REG 100–101 float32",
        "sensor.gone → REG 200–200 uint16 (missing)",
    ]
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"mapping": "0"})
    defaults = {str(k): k.default() for k in result["data_schema"].schema}
    # moving within its own range must not count as overlap with itself
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**defaults, "address": 101}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["mappings"][0]["address"] == 101

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "remove_mapping"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"mappings": ["1"]}
    )
    await hass.async_block_till_done()
    assert [m["entity_id"] for m in entry.options["mappings"]] == ["sensor.a"]


async def test_user_host_and_allowlist(hass, free_port):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "slave_id": 1,
            "port": free_port,
            "host": "127.0.0.1",
            "allowed_ips": "10.0.0.5, 10.1.0.0/16",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["host"] == "127.0.0.1"
    assert result["data"]["allowed_ips"] == ["10.0.0.5/32", "10.1.0.0/16"]


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("host", "not-an-ip", "invalid_host"),
        ("allowed_ips", "10.0.0.5, nope", "invalid_allowed_ips"),
        ("host", "203.0.113.7", "port_in_use"),  # not an address of this machine
    ],
)
async def test_user_invalid_server_settings(hass, free_port, field, value, error):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"slave_id": 1, "port": free_port, field: value}
    )
    assert result["errors"] == {"base": error}


async def test_reconfigure_shows_current_allowlist(hass, free_port):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=str(free_port),
        data={"slave_id": 1, "port": free_port, "host": "", "allowed_ips": ["10.0.0.5/32"]},
        options={"mappings": []},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    result = await entry.start_reconfigure_flow(hass)
    defaults = {str(k): k.default() for k in result["data_schema"].schema}
    assert defaults["allowed_ips"] == "10.0.0.5/32"
