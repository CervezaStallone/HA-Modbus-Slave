"""Register mapping, type detection and encoding. No Home Assistant imports."""

from __future__ import annotations

import math
import struct
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from .const import (
    BIT_DOMAINS,
    FLOAT32_EXACT,
    HEADROOM,
    HEADROOM_TOTAL,
    SIGNED_DEVICE_CLASSES,
)


class DataType(StrEnum):
    """Supported Modbus data types."""

    BIT = "bit"
    UINT16 = "uint16"
    INT16 = "int16"
    UINT32 = "uint32"
    INT32 = "int32"
    FLOAT32 = "float32"
    SCALED16 = "scaled16"
    SCALED32 = "scaled32"


_WIDE = (DataType.UINT32, DataType.INT32, DataType.FLOAT32, DataType.SCALED32)
_SCALED = (DataType.SCALED16, DataType.SCALED32)


def _scaled_base(mapping: Mapping) -> DataType:
    """The integer type a scaled value is stored as."""
    if mapping.data_type == DataType.SCALED32:
        return DataType.INT32 if mapping.signed else DataType.UINT32
    return DataType.INT16 if mapping.signed else DataType.UINT16


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
        return 2 if self.data_type in _WIDE else 1

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


def decimals_of(value: str) -> int:
    try:
        exponent = Decimal(str(value)).normalize().as_tuple().exponent
    except InvalidOperation:
        return 0
    return max(0, -exponent) if isinstance(exponent, int) else 0


def to_float(state: str) -> float | None:
    try:
        value = float(state)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def encode(mapping: Mapping, state: str) -> tuple[list, bool]:
    """Encode an entity state to register words (or one bit). Returns (values, clamped)."""
    if mapping.data_type == DataType.BIT:
        return [state == "on"], False

    value = to_float(state)
    if value is None:
        value = float(mapping.fallback)

    if mapping.data_type == DataType.FLOAT32:
        clamped = abs(value) > _FLOAT32_MAX
        value = max(-_FLOAT32_MAX, min(_FLOAT32_MAX, value))
        return list(struct.unpack(">HH", struct.pack(">f", value))), clamped

    data_type = mapping.data_type
    if data_type in _SCALED:
        value *= mapping.scale
        data_type = _scaled_base(mapping)

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
    if mapping.data_type in _SCALED:
        return struct.unpack(_INT_FORMATS[_scaled_base(mapping)][0], raw)[0] / mapping.scale
    return struct.unpack(_INT_FORMATS[mapping.data_type][0], raw)[0]


# --- guided type choice: plain answers about the value -> data type -----------


@dataclass(frozen=True)
class Evidence:
    """What Home Assistant knows about an entity's value."""

    current: float | None = None
    lo: float | None = None  # lowest numeric value seen (history, statistics, current)
    hi: float | None = None
    bounds: tuple[float, float] | None = None  # number/input_number (min, max)
    decimals: int | None = None
    device_class: str | None = None
    state_class: str | None = None
    history_days: int = 0


@dataclass(frozen=True)
class Answers:
    """The user's answers: can it be negative, decimals to keep, highest value."""

    negative: bool
    decimals: int
    max_value: float


@dataclass(frozen=True)
class TypeChoice:
    data_type: DataType
    scale: int = 1
    signed: bool = False


def has_numbers(evidence: Evidence) -> bool:
    return any(v is not None for v in (evidence.current, evidence.lo, evidence.hi, evidence.bounds))


def nice_ceil(value: float) -> float:
    """Round up to 1, 2 or 5 × 10^n, at least 10."""
    if value <= 10:
        return 10
    power = 10 ** math.floor(math.log10(value))
    return next(step * power for step in (1, 2, 5, 10) if step * power >= value)


def suggest_answers(domain: str, evidence: Evidence) -> Answers:
    """Pre-fill the questions from the evidence."""
    if domain in BIT_DOMAINS:
        return Answers(False, 0, 1)
    if evidence.decimals is not None:
        decimals = min(evidence.decimals, 3)
    else:
        decimals = 0 if evidence.bounds else 1
    if evidence.bounds:  # a number's own range is exact: no guessing, no headroom
        lo, hi = evidence.bounds
        return Answers(lo < 0, decimals, max(abs(lo), abs(hi)))

    seen = [v for v in (evidence.lo, evidence.hi, evidence.current) if v is not None]
    negative = any(v < 0 for v in seen) or evidence.device_class in SIGNED_DEVICE_CLASSES
    if not seen:
        return Answers(negative, decimals, 1000)
    rising = evidence.state_class in ("total", "total_increasing")
    headroom = HEADROOM_TOTAL if rising else HEADROOM
    return Answers(negative, decimals, nice_ceil(max(abs(v) for v in seen) * headroom))


def answers_from_mapping(mapping: Mapping, evidence: Evidence) -> Answers:
    """The answers that lead to an existing mapping's type, for editing it."""
    suggested = suggest_answers(mapping.entity_id.split(".", 1)[0], evidence)
    data_type = mapping.data_type
    if data_type in _SCALED:
        negative, decimals = mapping.signed, round(math.log10(mapping.scale))
    elif data_type in (DataType.INT16, DataType.INT32):
        negative, decimals = True, 0
    elif data_type in (DataType.UINT16, DataType.UINT32):
        negative, decimals = False, 0
    else:
        return suggested
    return Answers(negative, decimals, suggested.max_value)


def choose_type(answers: Answers, float_support: bool) -> TypeChoice | None:
    """The smallest type that holds the answers exactly; None if nothing fits."""

    def fits(value: float, bits: int) -> bool:
        limit = 2 ** (bits - 1) - 1 if answers.negative else 2**bits - 1
        return value <= limit

    if answers.decimals == 0:
        if fits(answers.max_value, 16):
            return TypeChoice(DataType.INT16 if answers.negative else DataType.UINT16)
        if fits(answers.max_value, 32):
            return TypeChoice(DataType.INT32 if answers.negative else DataType.UINT32)
        return None

    scale = 10**answers.decimals
    raw = round(answers.max_value * scale, 6)  # 6553.5 × 10 must be 65535, not 65535.000001
    if float_support and raw <= FLOAT32_EXACT:
        return TypeChoice(DataType.FLOAT32)
    if fits(raw, 16):
        return TypeChoice(DataType.SCALED16, scale, answers.negative)
    if fits(raw, 32):
        return TypeChoice(DataType.SCALED32, scale, answers.negative)
    return None


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


def first_free(mappings: list[Mapping], candidate: Mapping) -> int:
    """Lowest start address in the candidate's space where it fits without overlap."""
    address = 0
    for other in sorted(
        (m for m in mappings if m.space == candidate.space), key=lambda m: m.address
    ):
        if address + candidate.size <= other.address:
            break
        address = max(address, other.end + 1)
    return address


def master_view(mapping: Mapping) -> str:
    """What the master reads, in its own terms: base type, divisor and range."""
    if mapping.data_type in (DataType.BIT, DataType.FLOAT32):
        return str(mapping.data_type)
    base = _scaled_base(mapping) if mapping.data_type in _SCALED else mapping.data_type
    _, lo, hi = _INT_FORMATS[base]
    scale = mapping.scale
    digits = len(str(scale)) - 1
    divisor = f" ÷ {scale}" if scale > 1 else ""
    return f"{base}{divisor} · {lo / scale:.{digits}f} … {hi / scale:.{digits}f}"


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
