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
