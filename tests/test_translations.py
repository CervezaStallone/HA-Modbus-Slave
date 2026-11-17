"""UI strings stay in sync across languages."""

import json
from pathlib import Path

COMPONENT = Path(__file__).parent.parent / "custom_components" / "modbus_slave"


def load(name: str) -> dict:
    return json.loads((COMPONENT / name).read_text(encoding="utf-8"))


def keys(data: dict, prefix: str = "") -> set[str]:
    result = set()
    for key, value in data.items():
        path = f"{prefix}.{key}"
        result |= keys(value, path) if isinstance(value, dict) else {path}
    return result


def test_english_equals_strings():
    assert load("translations/en.json") == load("strings.json")


def test_dutch_has_same_keys():
    assert keys(load("translations/nl.json")) == keys(load("strings.json"))


def test_guided_confirm_step_is_translated():
    strings = load("strings.json")["options"]
    confirm = strings["step"]["confirm"]
    assert {"address", "negative", "decimals", "max_value", "writable", "fallback"} <= set(
        confirm["data"]
    )
    assert set(confirm["sections"]["advanced"]["data"]) == {"data_type", "scale", "signed"}
    for placeholder in ("{current}", "{result_type}", "{example_words}"):
        assert placeholder in confirm["description"]
    assert {"value_too_large", "warn_negative", "warn_max", "result_changed"} <= set(
        strings["error"]
    )
    types = load("strings.json")["selector"]["data_type"]["options"]
    assert set(types) == {
        "auto",
        "bit",
        "uint16",
        "int16",
        "uint32",
        "int32",
        "float32",
        "scaled16",
        "scaled32",
    }
