"""Config, reconfigure and options flow tests."""

import asyncio

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType, InvalidData, section
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
    assert result["data"] == {
        "slave_id": 3,
        "port": free_port,
        "host": "",
        "allowed_ips": [],
        "float_support": False,
        "share_usage": False,
    }


async def test_user_defaults(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    defaults = {str(k): k.default() for k in result["data_schema"].schema}
    assert defaults == {
        "slave_id": 1,
        "port": 502,
        "host": "",
        "allowed_ips": "",
        "float_support": False,
        "share_usage": False,
    }


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


async def test_user_duplicate_port_and_slave_id(hass, free_port):
    MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"{free_port}-1",
        data={"slave_id": 1, "port": free_port},
        minor_version=2,
    ).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"slave_id": 1, "port": free_port}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_second_slave_on_a_used_port(hass, free_port):
    await setup_entry(hass, free_port, allowed_ips=["10.0.0.0/24"])
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"slave_id": 2, "port": free_port, "allowed_ips": "10.0.0.0/24"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == f"{free_port}-2"


async def test_user_shared_port_needs_same_settings(hass, free_port):
    await setup_entry(hass, free_port)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"slave_id": 2, "port": free_port, "allowed_ips": "10.0.0.5"}
    )
    assert result["errors"] == {"base": "port_settings_differ"}


async def test_reconfigure_rejects_slave_id_taken_on_port(hass, free_port):
    await setup_entry(hass, free_port)
    other = await setup_entry(hass, free_port, slave_id=2)
    result = await other.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"slave_id": 1, "port": free_port}
    )
    assert result["errors"] == {"base": "slave_id_in_use"}


async def test_migration_sets_port_and_slave_id_unique_id(hass, free_port):
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=str(free_port), data={"slave_id": 3, "port": free_port}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.unique_id == f"{free_port}-3"
    assert entry.minor_version == 2


async def setup_entry(hass, port, mappings=(), **data):
    data = {"slave_id": 1, "port": port, **data}
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"{port}-{data['slave_id']}",
        data=data,
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
    assert entry.data == {
        "slave_id": 9,
        "port": new_port,
        "host": "",
        "allowed_ips": [],
        "float_support": False,
        "share_usage": False,  # opt-in: an entry without the key counts as off
    }
    assert entry.unique_id == f"{new_port}-9"
    # old port is free again, new port is held by the reloaded server
    blocker = await asyncio.start_server(lambda _r, _w: None, port=free_port)
    blocker.close()
    await blocker.wait_closed()
    with pytest.raises(OSError):
        await asyncio.start_server(lambda _r, _w: None, port=new_port)


async def test_reconfigure_rejects_foreign_host_on_same_port(hass, free_port):
    entry = await setup_entry(hass, free_port)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"slave_id": 1, "port": free_port, "host": "203.0.113.1"}
    )
    assert result.get("errors") == {"base": "invalid_host"}
    assert entry.data.get("host", "") == ""

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"slave_id": 1, "port": free_port, "host": "127.0.0.1"}
    )
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["host"] == "127.0.0.1"


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
    defaults = form_defaults(result)
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {**defaults, **confirm}
    ), defaults


def form_defaults(result):
    """Default form values, including those inside a collapsed section."""
    out = {}
    for key, value in result["data_schema"].schema.items():
        if isinstance(value, section):
            out[str(key)] = {str(k): k.default() for k in value.schema.schema}
        else:
            out[str(key)] = key.default()
    return out


async def test_confirm_prefills_from_evidence(hass, free_port):
    hass.states.async_set("sensor.t", "21.34", {"device_class": "temperature"})
    entry = await setup_entry(hass, free_port)
    result, defaults = await add_mapping(hass, entry, "sensor.t", 100)
    assert defaults.get("negative") is True
    assert defaults.get("decimals") == "2"
    assert defaults.get("max_value") == 50
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["mappings"] == [
        {
            "entity_id": "sensor.t",
            "address": 100,
            "data_type": "scaled16",
            "scale": 100,
            "signed": True,
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
    advanced = {"data_type": "float32", "scale": "1", "signed": False}
    result, _ = await add_mapping(hass, entry, "sensor.a", 65535, advanced=advanced)
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
    advanced = {"data_type": data_type, "scale": "1", "signed": False}
    result, _ = await add_mapping(hass, entry, entity, 0, advanced=advanced, writable=True)
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
    defaults = form_defaults(result)
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


async def test_float_support_set_and_reconfigured(hass, free_port):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"slave_id": 1, "port": free_port, "float_support": True}
    )
    await hass.async_block_till_done()
    entry = hass.config_entries.async_get_entry(result["result"].entry_id)
    assert entry.data["float_support"] is True
    mappings = [{"entity_id": "sensor.a", "address": 0, "data_type": "float32"}]
    hass.config_entries.async_update_entry(entry, options={"mappings": mappings})
    await hass.async_block_till_done()

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"slave_id": 1, "port": free_port, "float_support": False}
    )
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["float_support"] is False
    assert entry.options["mappings"] == mappings


async def test_edit_unchanged_keeps_type(hass, free_port):
    hass.states.async_set("sensor.a", "1.5")
    stored = {
        "entity_id": "sensor.a",
        "address": 100,
        "data_type": "float32",
        "scale": 1,
        "signed": False,
        "writable": False,
        "fallback": 0,
    }
    entry = await setup_entry(hass, free_port, [stored])  # float_support is off
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "edit_mapping"}
    )
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"mapping": "0"})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], form_defaults(result)
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["mappings"] == [stored]


async def test_confirm_float_support_picks_float32(hass, free_port):
    hass.states.async_set("sensor.t", "21.34", {"device_class": "temperature"})
    entry = await setup_entry(hass, free_port, float_support=True)
    result, _ = await add_mapping(hass, entry, "sensor.t", 100)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["mappings"][0]["data_type"] == "float32"


async def test_confirm_changed_answer_reshows_then_saves(hass, free_port):
    hass.states.async_set("sensor.t", "21.34", {"device_class": "temperature"})
    entry = await setup_entry(hass, free_port)
    result, _ = await add_mapping(hass, entry, "sensor.t", 100, decimals="0")
    assert result.get("errors") == {"base": "result_changed"}
    assert "int16" in result["description_placeholders"]["result_type"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], form_defaults(result)
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["mappings"][0]["data_type"] == "int16"


async def test_confirm_value_too_large(hass, free_port):
    hass.states.async_set("sensor.t", "21.34")
    entry = await setup_entry(hass, free_port)
    result, _ = await add_mapping(hass, entry, "sensor.t", 100, decimals="3", max_value=1e7)
    assert result.get("errors") == {"base": "value_too_large"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], form_defaults(result)
    )
    assert result.get("errors") == {"base": "value_too_large"}


async def test_confirm_warns_when_unticking_negative(hass, free_port):
    hass.states.async_set("sensor.t", "-3")
    entry = await setup_entry(hass, free_port)
    result, defaults = await add_mapping(hass, entry, "sensor.t", 100, negative=False)
    assert defaults["negative"] is True
    assert result.get("errors") == {"base": "warn_negative"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], form_defaults(result)
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["mappings"][0]["data_type"] == "uint16"


async def test_confirm_warns_when_max_below_seen(hass, free_port):
    hass.states.async_set("sensor.t", "500")
    entry = await setup_entry(hass, free_port)
    result, _ = await add_mapping(hass, entry, "sensor.t", 100, max_value=100)
    assert result.get("errors") == {"base": "warn_max"}


async def test_confirm_bit_entity_has_no_questions(hass, free_port):
    hass.states.async_set("switch.s", "on")
    entry = await setup_entry(hass, free_port)
    result, defaults = await add_mapping(hass, entry, "switch.s", 5)
    assert not {"negative", "decimals", "max_value"} & defaults.keys()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["mappings"][0]["data_type"] == "bit"


async def test_add_mapping_unavailable_sensor_with_device_class(hass, free_port):
    hass.states.async_set("sensor.x", "unavailable", {"device_class": "power"})
    hass.states.async_set("sensor.ts", "unavailable", {"device_class": "timestamp"})
    entry = await setup_entry(hass, free_port)
    result, defaults = await add_mapping(hass, entry, "sensor.x", 0)
    assert defaults["negative"] is True  # power can be fed back
    assert result["type"] is FlowResultType.CREATE_ENTRY
    result = await add_mapping(hass, entry, "sensor.ts", 10)
    assert result["errors"] == {"base": "unsupported_entity"}


async def test_add_mapping_rejects_non_numeric_domain_with_device_class(hass, free_port):
    hass.states.async_set("cover.garage", "closed", {"device_class": "garage"})
    entry = await setup_entry(hass, free_port)
    result = await add_mapping(hass, entry, "cover.garage", 0)
    assert isinstance(result, dict)
    assert result.get("errors") == {"base": "unsupported_entity"}


async def edit_first(hass, entry):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "edit_mapping"}
    )
    return await hass.config_entries.options.async_configure(result["flow_id"], {"mapping": "0"})


LEGACY_FLOAT = {"entity_id": "sensor.a", "address": 100, "data_type": "float32", "scale": 10}


async def test_edit_legacy_mapping_changed_answer_applies(hass, free_port):
    hass.states.async_set("sensor.a", "12.3")
    entry = await setup_entry(hass, free_port, [LEGACY_FLOAT])
    result = await edit_first(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**form_defaults(result), "decimals": "0"}
    )
    assert result.get("errors") == {"base": "result_changed"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], form_defaults(result)
    )
    await hass.async_block_till_done()
    assert entry.options["mappings"][0]["data_type"] == "uint16"


async def test_edit_legacy_mapping_shows_override_expanded(hass, free_port):
    hass.states.async_set("sensor.a", "12.3")
    entry = await setup_entry(hass, free_port, [LEGACY_FLOAT])
    result = await edit_first(hass, entry)
    advanced = result["data_schema"].schema["advanced"]
    assert advanced.options["collapsed"] is False


async def test_confirm_warns_negative_from_bounds(hass, free_port):
    hass.states.async_set("input_number.sp", "5", {"min": -10, "max": 40, "step": 0.5})
    entry = await setup_entry(hass, free_port)
    result, _ = await add_mapping(hass, entry, "input_number.sp", 0, negative=False)
    assert result.get("errors") == {"base": "warn_negative"}


async def test_confirm_bounds_suggestion_saves_without_max_warning(hass, free_port):
    hass.states.async_set("number.n", "150", {"min": 0, "max": 100, "step": 1})
    entry = await setup_entry(hass, free_port)
    result, defaults = await add_mapping(hass, entry, "number.n", 0)
    assert defaults["max_value"] == 100
    assert result.get("errors") is None
    assert result["type"] is FlowResultType.CREATE_ENTRY
