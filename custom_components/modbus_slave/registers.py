"""Register mapping, type detection and encoding. No Home Assistant imports."""

from __future__ import annotations

import math
import struct
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from .const import BIT_DOMAINS


class DataType(StrEnum):
    """Supported Modbus data types."""

    BIT = "bit"
    UINT16 = "uint16"
    INT16 = "int16"
    UINT32 = "uint32"
    INT32 = "int32"
    FLOAT32 = "float32"
    SCALED16 = "scaled16"


# struct format and (min, max) per integer type; big-endian, high word first
_INT_FORMATS = {
    DataType.UINT16: (">H", 0, 0xFFFF),
    DataType.INT16: (">h", -0x8000, 0x7FFF),
    DataType.UINT32: (">I", 0, 0xFFFFFFFF),
    DataType.INT32: (">i", -0x80000000, 0x7FFFFFFF),
}
_FLOAT32_MAX = 3.4028234663852886e38


@dataclass
class Mapping:
    """One entity mapped to a register range."""

    entity_id: str
    address: int
    data_type: DataType
    scale: int = 1
    signed: bool = False
    writable: bool = False
    fallback: float = 0

    def __post_init__(self) -> None:
        self.data_type = DataType(self.data_type)

    @property
    def size(self) -> int:
        return 2 if self.data_type in (DataType.UINT32, DataType.INT32, DataType.FLOAT32) else 1

    @property
    def space(self) -> str:
        return "bits" if self.data_type == DataType.BIT else "registers"

    @property
    def end(self) -> int:
        return self.address + self.size - 1

    @classmethod
    def from_dict(cls, data: dict) -> Mapping:
        return cls(**data)

    def as_dict(self) -> dict:
        return {**asdict(self), "data_type": str(self.data_type)}


def _decimals(value: str) -> int:
    try:
        exponent = Decimal(str(value)).normalize().as_tuple().exponent
    except InvalidOperation:
        return 0
    return max(0, -exponent) if isinstance(exponent, int) else 0


def _suggested_scale(value: str) -> int:
    return min(10 ** _decimals(value), 1000)


def _to_float(state: str) -> float | None:
    try:
        value = float(state)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def detect(domain: str, state: str, attributes: dict) -> dict | None:
    """Pick data type, scale suggestion and sign for an entity."""
    if domain in BIT_DOMAINS:
        return {"data_type": DataType.BIT, "scale": 1, "signed": False}

    if domain in ("number", "input_number") and {"min", "max", "step"} <= attributes.keys():
        lo, hi, step = attributes["min"], attributes["max"], attributes["step"]
        signed = lo < 0
        data_type = DataType.FLOAT32
        if float(step).is_integer():
            if 0 <= lo and hi <= 0xFFFF:
                data_type = DataType.UINT16
            elif -0x8000 <= lo and hi <= 0x7FFF:
                data_type = DataType.INT16
        return {"data_type": data_type, "scale": _suggested_scale(step), "signed": signed}

    value = _to_float(state)
    if value is None:
        return None
    return {"data_type": DataType.FLOAT32, "scale": _suggested_scale(state), "signed": value < 0}


def encode(mapping: Mapping, state: str) -> tuple[list, bool]:
    """Encode an entity state to register words (or one bit). Returns (values, clamped)."""
    if mapping.data_type == DataType.BIT:
        return [state == "on"], False

    value = _to_float(state)
    if value is None:
        value = float(mapping.fallback)

    if mapping.data_type == DataType.FLOAT32:
        clamped = abs(value) > _FLOAT32_MAX
        value = max(-_FLOAT32_MAX, min(_FLOAT32_MAX, value))
        return list(struct.unpack(">HH", struct.pack(">f", value))), clamped

    data_type = mapping.data_type
    if data_type == DataType.SCALED16:
        value *= mapping.scale
        data_type = DataType.INT16 if mapping.signed else DataType.UINT16

    fmt, lo, hi = _INT_FORMATS[data_type]
    number = round(value)
    clamped = not lo <= number <= hi
    number = max(lo, min(hi, number))
    packed = struct.pack(fmt, number)
    return list(struct.unpack(f">{len(packed) // 2}H", packed)), clamped


def decode(mapping: Mapping, words: list) -> float | int | bool:
    """Decode register words (or bits) written by the master."""
    if mapping.data_type == DataType.BIT:
        return bool(words[0])

    raw = struct.pack(f">{len(words)}H", *words)
    if mapping.data_type == DataType.FLOAT32:
        return struct.unpack(">f", raw)[0]
    if mapping.data_type == DataType.SCALED16:
        fmt = ">h" if mapping.signed else ">H"
        return struct.unpack(fmt, raw)[0] / mapping.scale
    return struct.unpack(_INT_FORMATS[mapping.data_type][0], raw)[0]


def find_overlap(
    mappings: list[Mapping], candidate: Mapping, ignore_index: int | None = None
) -> Mapping | None:
    """Return the first mapping in the same space whose range overlaps the candidate."""
    for index, other in enumerate(mappings):
        if index == ignore_index or other.space != candidate.space:
            continue
        if other.address <= candidate.end and candidate.address <= other.end:
            return other
    return None


class RegisterTable:
    """In-memory bit and register spaces served to the Modbus master."""

    def __init__(self, mappings: list[Mapping]) -> None:
        self.mappings = mappings
        self.bits: dict[int, bool] = {}
        self.registers: dict[int, int] = {}

    def apply(self, mapping: Mapping, values: list) -> None:
        target = self.bits if mapping.space == "bits" else self.registers
        for offset, value in enumerate(values):
            target[mapping.address + offset] = value

    def read_bits(self, address: int, count: int) -> list[bool]:
        return [self.bits.get(a, False) for a in range(address, address + count)]

    def read_registers(self, address: int, count: int) -> list[int]:
        return [self.registers.get(a, 0) for a in range(address, address + count)]

    def writable_mapping_at(self, space: str, address: int, count: int) -> Mapping | None:
        """Return the writable mapping exactly covered by a write, else None."""
        for mapping in self.mappings:
            if (
                mapping.writable
                and mapping.space == space
                and mapping.address == address
                and mapping.size == count
            ):
                return mapping
        return None
