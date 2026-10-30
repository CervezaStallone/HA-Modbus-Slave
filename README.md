# Modbus Slave for Home Assistant

Makes Home Assistant act as a **Modbus TCP slave (server)**. Pick entities, give them a register address, and any Modbus master (PLC, SCADA, energy manager) can read them, and optionally write them back.

## Install

**HACS**: add this repository as a custom repository (category *Integration*), install *Modbus Slave*, restart Home Assistant.

**Manual**: copy `custom_components/modbus_slave` into `config/custom_components/` and restart.

## Setup

*Settings → Devices & services → Add integration → Modbus Slave*

| Field | Default | Range |
|---|---|---|
| Slave ID | 1 | 1–247 |
| Port | 502 | 1–65535 |

Requests for any other slave ID get no reply. You can change the slave ID and port later with *Reconfigure*.

> **Port 502** is a privileged port. It works on Home Assistant OS / Supervised. On Container/Core installs running as non-root, pick a port ≥ 1024 (e.g. 5020) or grant `CAP_NET_BIND_SERVICE`.

## Mappings

*Configure → Add mapping*: pick an entity and a start address. The integration picks the data type:

| Entity | Type |
|---|---|
| binary_sensor, switch, light, input_boolean, fan | `bit` |
| number / input_number with whole-number step and range inside 16 bits | `uint16` / `int16` |
| other number / input_number, all numeric sensors | `float32` (2 registers) |

You can override it with `uint16`, `int16`, `uint32`, `int32`, `float32` or `scaled16`. `scaled16` stores `round(value × scale)` in one register, with the scale suggested from the number of decimals.

### Address spaces

There are two address spaces, each 0–65535:

- **Bits**: readable with FC1 (coils) **and** FC2 (discrete inputs), which return the same values. Writable with FC5/FC15.
- **Registers**: readable with FC3 (holding) **and** FC4 (input), which return the same values. Writable with FC6/FC16.

So a master that only supports one read function still sees everything.

### Encoding

- 32-bit values are big-endian, **high word first** (ABCD). Floats are IEEE-754.
- Values outside the type's range are clamped, and a warning is logged.
- `unavailable` / `unknown` / non-numeric states read as the mapping's fallback value (default 0).
- Unmapped addresses read as 0.

Example: `sensor.outdoor_temperature` = 12.3 as `float32` at address 100 reads `[0x4144, 0xCCCD]`.

### Writing (optional)

Tick **Writable** on a mapping to let the master control the entity:

- bit → `switch`, `light`, `input_boolean`, `fan` (1 = on, 0 = off)
- numeric → `number`, `input_number` (`set_value`; values outside min/max are rejected)

| Error | When |
|---|---|
| `ILLEGAL_ADDRESS` (02) | address not mapped, mapping read-only, or write covers only part of a 32-bit value |
| `ILLEGAL_VALUE` (03) | value outside the entity's min/max |
| `DEVICE_FAILURE` (04) | the Home Assistant service call failed |

## ⚠️ Security

Modbus TCP has **no authentication and no encryption**. Anyone who can reach the port can read every mapping and write every writable one. Keep the port on a trusted network or VLAN, and do not forward it to the internet.

## Development

```bash
uv venv -p 3.14 .venv && uv pip install -p .venv -r requirements_test.txt
.venv/bin/pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

CI runs ruff, hassfest, HACS validation and pytest on every push and pull request. Pushing a tag `vX.Y.Z` (matching `version` in `manifest.json`) creates a GitHub release with `modbus_slave.zip`.
