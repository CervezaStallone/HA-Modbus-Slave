"""Tests for the pure register logic (no Home Assistant)."""

import struct

import pytest

from custom_components.modbus_slave.registers import (
    DataType,
    Mapping,
    RegisterTable,
    decode,
    detect,
    encode,
    find_overlap,
)


@pytest.mark.parametrize("domain", ["binary_sensor", "switch", "light", "input_boolean", "fan"])
def test_detect_bits(domain):
    assert detect(domain, "on", {})["data_type"] == DataType.BIT


@pytest.mark.parametrize(
    ("attrs", "expected", "scale"),
    [
        ({"min": 0, "max": 100, "step": 1}, DataType.UINT16, 1),
        ({"min": -10, "max": 100, "step": 1}, DataType.INT16, 1),
        ({"min": 0, "max": 30, "step": 0.5}, DataType.FLOAT32, 10),
        ({"min": 0, "max": 70000, "step": 1}, DataType.FLOAT32, 1),
        ({"min": -40000, "max": 0, "step": 1}, DataType.FLOAT32, 1),
    ],
)
def test_detect_number(attrs, expected, scale):
    result = detect("input_number", "5", attrs)
    assert result["data_type"] == expected
    assert result["scale"] == scale


def test_detect_sensor_is_float32_with_scale_suggestion():
    assert detect("sensor", "20", {}) == {
        "data_type": DataType.FLOAT32,
        "scale": 1,
        "signed": False,
    }
    assert detect("sensor", "-1.25", {}) == {
        "data_type": DataType.FLOAT32,
        "scale": 100,
        "signed": True,
    }
    assert detect("sensor", "0.123456", {})["scale"] == 1000


def test_detect_unsupported():
    assert detect("sensor", "abc", {}) is None
    assert detect("sensor", "unavailable", {}) is None


def m(data_type, address=0, **kw):
    return Mapping(
        entity_id=kw.pop("entity_id", "sensor.x"), address=address, data_type=data_type, **kw
    )


@pytest.mark.parametrize(
    ("mapping", "state", "words", "clamped"),
    [
        (m(DataType.FLOAT32), "12.3", [0x4144, 0xCCCD], False),
        (m(DataType.INT16), "-1", [0xFFFF], False),
        (m(DataType.UINT32), "70000", [0x0001, 0x1170], False),
        (m(DataType.INT32), "-2", [0xFFFF, 0xFFFE], False),
        (m(DataType.SCALED16, scale=10), "12.34", [123], False),
        (m(DataType.SCALED16, scale=10, signed=True), "-1.5", [0xFFF1], False),
        (m(DataType.UINT16), "70000", [65535], True),
        (m(DataType.UINT16), "-5", [0], True),
        (m(DataType.INT16), "-40000", [0x8000], True),
        (m(DataType.UINT16), "unavailable", [0], False),
        (m(DataType.UINT16, fallback=7), "abc", [7], False),
        (m(DataType.FLOAT32), "nan", [0, 0], False),
        (m(DataType.BIT), "on", [True], False),
        (m(DataType.BIT), "off", [False], False),
        (m(DataType.BIT), "unavailable", [False], False),
    ],
)
def test_encode(mapping, state, words, clamped):
    assert encode(mapping, state) == (words, clamped)


@pytest.mark.parametrize(
    ("mapping", "words", "value"),
    [
        (m(DataType.FLOAT32), list(struct.unpack(">HH", struct.pack(">f", 21.5))), 21.5),
        (m(DataType.INT16), [0xFFFF], -1),
        (m(DataType.UINT32), [0x0001, 0x1170], 70000),
        (m(DataType.SCALED16, scale=10), [123], 12.3),
        (m(DataType.SCALED16, scale=10, signed=True), [0xFFF1], -1.5),
        (m(DataType.BIT), [True], True),
    ],
)
def test_decode(mapping, words, value):
    assert decode(mapping, words) == pytest.approx(value)


def test_find_overlap():
    existing = [
        m(DataType.FLOAT32, 100, entity_id="sensor.a"),
        m(DataType.BIT, 100, entity_id="switch.b"),
    ]
    assert find_overlap(existing, m(DataType.UINT16, 101)).entity_id == "sensor.a"
    assert find_overlap(existing, m(DataType.UINT16, 102)) is None
    assert find_overlap(existing, m(DataType.FLOAT32, 99)).entity_id == "sensor.a"
    assert find_overlap(existing, m(DataType.BIT, 101)) is None
    # editing a mapping does not conflict with itself
    assert find_overlap(existing, m(DataType.FLOAT32, 101), ignore_index=0) is None


def test_table_read_and_writable_lookup():
    ro = m(DataType.FLOAT32, 100, entity_id="sensor.a")
    rw = m(DataType.FLOAT32, 200, entity_id="input_number.b", writable=True)
    sw = m(DataType.BIT, 0, entity_id="switch.c", writable=True)
    table = RegisterTable([ro, rw, sw])
    table.apply(ro, [1, 2])
    table.apply(sw, [True])
    assert table.read_registers(99, 4) == [0, 1, 2, 0]
    assert table.read_bits(0, 2) == [True, False]
    assert table.writable_mapping_at("registers", 200, 2) is rw
    assert table.writable_mapping_at("registers", 200, 1) is None  # partial
    assert table.writable_mapping_at("registers", 100, 2) is None  # read-only
    assert table.writable_mapping_at("registers", 300, 1) is None  # unmapped
    assert table.writable_mapping_at("bits", 0, 1) is sw
    assert table.writable_mapping_at("registers", 0, 1) is None  # other space
