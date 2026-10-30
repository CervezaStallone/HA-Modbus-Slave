<p align="center">
  <img src="img/logo.png" alt="Modbus Slave" width="256">

<h1 align="center">Modbus Slave for Home Assistant</h1>

<p align="center">
  <a href="https://github.com/CervezaStallone/HA-Modbus-Slave/releases/latest"><img src="https://img.shields.io/github/v/release/CervezaStallone/HA-Modbus-Slave?label=Version&color=gold" alt="Version"></a>
  <img src="https://img.shields.io/badge/Home%20Assistant-2026.7.0%2B-41BDF5" alt="Home Assistant 2026.7.0+">
  <a href="https://hacs.xyz"><img src="https://img.shields.io/badge/HACS-Custom-orange" alt="HACS Custom"></a>
  <a href="https://github.com/CervezaStallone/HA-Modbus-Slave/actions/workflows/tests.yml"><img src="https://img.shields.io/github/actions/workflow/status/CervezaStallone/HA-Modbus-Slave/tests.yml?branch=main&label=Tests" alt="Tests"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/CervezaStallone/HA-Modbus-Slave?label=License" alt="License"></a>
</p>

<p align="center">
  Turn Home Assistant into a Modbus TCP device — no YAML, no hassle.<br>
  Pick an entity, give it a register address, and any PLC, SCADA or energy manager can read it.
</p>

<p align="center">
  <strong>HACS Compatible</strong> · GUI-only setup · Automatic data types · Optional write-back
</p>

---

> **This integration is free and stays free.** It is built and maintained in spare time: new features, answering issues and testing against real Modbus masters. How much time goes into it depends on support from the people who use it. If it saves you time or money, please consider sponsoring or buying me a coffee.
>
> **No budget? A star helps too.** It costs nothing, takes one click on the ★ Star button of the [GitHub repository](https://github.com/CervezaStallone/HA-Modbus-Slave) and helps other Home Assistant users find the integration.
>
> <a href="https://github.com/CervezaStallone/HA-Modbus-Slave"><img src="https://img.shields.io/github/stars/CervezaStallone/HA-Modbus-Slave?style=for-the-badge&logo=github&label=Star&color=f5c518" alt="Star on GitHub" height="32"></a>
> <a href="https://github.com/sponsors/CervezaStallone"><img src="https://img.shields.io/badge/Sponsor-GitHub-ea4aaa?style=for-the-badge&logo=githubsponsors&logoColor=white" alt="Sponsor on GitHub" height="32"></a>
> <a href="https://buymeacoffee.com/cervezastallone"><img src="https://img.shields.io/badge/Buy_me_a-Coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=black" alt="Buy Me A Coffee" height="32"></a>

**Contents:** [What it does](#what-does-this-integration-do) · [Features](#features-at-a-glance) · [Safety](#safety-on-a-live-site) · [Installation](#installation) · [Getting started](#getting-started) · [Configuration](#configuration-options) · [Data types](#data-types) · [Address spaces](#address-spaces) · [How writes work](#how-writes-work) · [Examples](#examples) · [Troubleshooting](#troubleshooting) · [Requirements](#requirements) · [Contributing](#contributing) · [License](#license)

## What does this integration do?

This custom integration makes Home Assistant act as a **Modbus TCP slave (server)** — the protocol almost every PLC, SCADA system, building management system and energy manager speaks.

In plain terms: everything Home Assistant knows — sensors, switches, setpoints from any integration — becomes available as Modbus registers. Your PLC reads the outdoor temperature from a Zigbee sensor, your energy manager reads the car charger's power, and if you allow it, the PLC switches a Home Assistant light or sets a thermostat.

**No YAML configuration required.** Everything is set up through the Home Assistant GUI.

---

## Features at a glance

- **Two-field setup** — slave ID and port (default `502`), and Home Assistant answers Modbus TCP requests
- **Map any entity** — pick an entity and a start address; the register follows the entity's state
- **Automatic data types** — on/off entities become a bit, numbers with a whole-number range become `uint16`/`int16`, everything else `float32`
- **Override when needed** — `uint16`, `int16`, `uint32`, `int32`, `float32` or `scaled16` (value × 10/100/1000 in one register)
- **Works with every master** — coils and discrete inputs return the same bits, holding and input registers the same registers, so masters that only support FC3 still see everything
- **Optional write-back** — tick *Writable* to let the master switch entities or set numbers, with proper Modbus exception codes on invalid writes
- **Real-time** — state changes are in the registers immediately, no polling
- **Only answers its own slave ID** — requests for other unit IDs get no reply, like a real device behind a gateway
- **Overlap protection** — a mapping can't overlap another one, including the second register of a 32-bit value
- **Reconfigure** — change slave ID or port without re-adding the integration; mapping changes apply without restarting Home Assistant
- **English and Dutch** user interface

---

## Safety on a live site

What this integration lets a Modbus master do, so you know before connecting it to a running installation:

- **Read-only by default** — a new mapping is read-only. A master can only change an entity when you tick **Writable** on that mapping.
- **Limited to controllable domains** — *Writable* is only accepted on `switch`, `light`, `input_boolean` and `fan` (as a bit) and `number` and `input_number` (as a value). Sensors can never be written.
- **Min/max are enforced** — a written value outside the entity's `min`/`max` is rejected with `ILLEGAL_VALUE`; nothing is sent to Home Assistant.
- **No partial writes** — a write that covers only one word of a 32-bit value is rejected, so a master can't set half a float.
- **No authentication** — Modbus TCP has none. Anyone who can reach the port can read every mapping and write every writable one. Keep the port on a trusted network or VLAN, firewall it to your master's IP, and never forward it to the internet. See [SECURITY.md](SECURITY.md).

---

## Installation

### Via HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=CervezaStallone&repository=HA-Modbus-Slave&category=integration)

1. Click the button above, or:
   - Open **HACS** → **Integrations** → **⋮** → **Custom repositories**
   - Paste this repository URL and select category **Integration**
2. Click **Download**
3. **Restart** Home Assistant

### Manual installation

Copy the `custom_components/modbus_slave` folder into your Home Assistant `config/custom_components/` directory and restart.

---

## Getting started

### 1. Add the integration

Go to **Settings → Devices & Services → Add Integration** and search for **Modbus Slave**.

### 2. Set slave ID and port

| Setting | What it does | Default |
|---|---|---|
| **Slave ID** | The unit ID Home Assistant answers to (1–247) | `1` |
| **TCP port** | The port the Modbus server listens on (1–65535) | `502` |

> **Port 502** is a privileged port. It works on Home Assistant OS and Supervised. On Container or Core installs running as non-root, pick a port ≥ 1024 (e.g. `5020`) or grant `CAP_NET_BIND_SERVICE`. Setup tells you when the port can't be opened.

### 3. Add your first mapping

Click **Configure** → **Add mapping**, pick an entity and a start address. The next screen shows what the integration detected, e.g. `REG 100–101 float32`. Change anything you like and click **Submit** — the master can read it right away.

---

## Configuration options

After setup, click **Configure** on the integration card. A menu opens with:

| Entry | What it does |
|---|---|
| **Add mapping** | Pick an entity and start address; confirm or change the detected type |
| **Edit mapping** | Change the address, type, scale, writable flag or fallback of a mapping. Mappings whose entity no longer exists are marked *(missing)* |
| **Remove mappings** | Select one or more mappings to remove |

Every mapping has these settings:

| Setting | What it does | Default |
|---|---|---|
| **Start address** | First address of the mapping (0–65535) | — |
| **Data type** | See [Data types](#data-types) | Detected |
| **Scale factor** | Multiplier for `scaled16` (1, 10, 100, 1000) | From the number of decimals |
| **Signed** | `scaled16` as signed instead of unsigned | From the entity's range |
| **Writable** | Let the master control this entity. See [How writes work](#how-writes-work) | Off |
| **Value when unavailable** | What the master reads while the entity is `unavailable` or `unknown` | `0` |

Changes apply immediately — the integration reloads itself; Home Assistant doesn't restart.

### Reconfigure

To change the slave ID or port: **Settings → Devices & Services → Modbus Slave → ⋮ → Reconfigure**. Mappings are kept.

---

## Data types

The integration picks the type when you add a mapping:

| Entity | Detected type | Registers |
|---|---|---|
| `binary_sensor`, `switch`, `light`, `input_boolean`, `fan` | `bit` | 1 bit |
| `number` / `input_number` with a whole-number step and a range inside 0–65535 | `uint16` | 1 |
| `number` / `input_number` with a whole-number step and a range inside −32768–32767 | `int16` | 1 |
| Other `number` / `input_number`, and every numeric `sensor` | `float32` | 2 |

Sensors are always `float32`: their current value doesn't tell what they'll report later (20 °C now, 20.5 or −3 °C tomorrow), and `float32` is exact for every whole number up to 16,777,216.

### Encoding

| Type | Registers | Encoding |
|---|---|---|
| `bit` | 1 bit | `on` = 1, anything else = 0 |
| `uint16` / `int16` | 1 | Two's complement for signed |
| `scaled16` | 1 | `round(value × scale)` as `uint16` or `int16` |
| `uint32` / `int32` / `float32` | 2 | Big-endian, **high word first** (ABCD); IEEE-754 for floats |

- Values outside the type's range are **clamped** to its min/max, and a warning is logged once.
- `unavailable`, `unknown` and non-numeric states read as the mapping's **fallback** value.
- Unmapped addresses read as `0`.

Example: `sensor.outdoor_temperature` = `12.3` as `float32` at address 100 reads `[0x4144, 0xCCCD]`.

---

## Address spaces

There are two address spaces, each 0–65535:

| Space | Read with | Write with |
|---|---|---|
| **Bits** | FC1 (Read Coils) **and** FC2 (Read Discrete Inputs) — same values | FC5, FC15 |
| **Registers** | FC3 (Read Holding Registers) **and** FC4 (Read Input Registers) — same values | FC6, FC16 |

A bit at address 100 and a register at address 100 are different things; two registers at address 100 are not possible. Any other function code is answered with `ILLEGAL_FUNCTION`.

> Addresses are 0-based, as on the wire. Some tools (mbpoll, Modbus Poll in "PLC addresses" mode) count from 1 — address 100 here is register 101 there.

---

## How writes work

A write is only accepted on a mapping with **Writable** ticked:

| Mapping | Master writes | Home Assistant does |
|---|---|---|
| `bit` on `switch`, `light`, `input_boolean`, `fan` | `1` / `0` | `homeassistant.turn_on` / `turn_off` |
| Numeric on `number`, `input_number` | A value in the mapping's type | `set_value` with the decoded value (scale applied) |

The master gets an answer once Home Assistant has handled the call. The register itself changes when Home Assistant reports the new state — never optimistically — so reading back shows what the entity really did.

| Exception | When |
|---|---|
| `ILLEGAL_ADDRESS` (02) | Address not mapped, mapping read-only, or the write covers only part of a 32-bit value |
| `ILLEGAL_VALUE` (03) | Value outside the entity's `min`/`max` |
| `DEVICE_FAILURE` (04) | The Home Assistant service call failed |

---

## Examples

### Read a temperature with mbpoll

Mapping: `sensor.outdoor_temperature` → address `100`, `float32`.

```bash
mbpoll -m tcp -a 1 -t 4:float -B -r 101 -c 1 192.168.1.10 -p 502
```

`-t 4:float` reads holding registers as float (`-t 3:float` gives the same value from the input registers), `-B` sets high word first, `-r 101` is address 100 in mbpoll's 1-based counting.

### Switch a light from a PLC

Mapping: `light.hallway` → address `0`, `bit`, **Writable**.

The PLC writes coil 0 (FC5) `ON` → the hallway light turns on. Reading coil 0 (FC1) afterwards returns the light's real state, also when someone switched it from the dashboard.

### Send a setpoint as a scaled integer

Mapping: `input_number.boiler_setpoint` (min 30, max 80, step 0.5) → address `200`, `scaled16`, scale `10`, **Writable**.

The PLC writes `655` to holding register 200 (FC6) → the setpoint becomes `65.5`. Writing `900` (90.0) is rejected with `ILLEGAL_VALUE`.

---

## Troubleshooting

| Problem | Likely cause | Solution |
|---|---|---|
| "Port is in use or cannot be opened" | Another program uses the port, or the port is below 1024 on a non-root install | Stop the other program, or use a port ≥ 1024 (e.g. `5020`) |
| Master gets a timeout | Wrong slave ID, firewall, or wrong port | Check the slave ID on the integration card; the integration doesn't answer other unit IDs |
| Value reads as `0` | Entity is `unavailable`, address not mapped, or off-by-one addressing | Check the entity state, and whether your tool counts addresses from 1 |
| Float value looks like garbage | Master uses low word first | Set the master to big-endian / high word first (ABCD) |
| Value is stuck at a maximum | Value is clamped to the type's range | Use a larger type (`float32`, `int32`) or a smaller `scaled16` scale |
| Write returns `ILLEGAL_ADDRESS` | Mapping not writable, wrong address, or only one word of a 32-bit value written | Tick *Writable*, and write both registers with FC16 |
| Write returns `ILLEGAL_VALUE` | Value outside the entity's min/max | Check the entity's range and the scale factor |
| Mapping shows *(missing)* | The entity was removed or renamed | Edit the mapping or remove it; meanwhile the master reads the fallback |

### Debug logging

Add this to your `configuration.yaml` for detailed logs:

```yaml
logger:
  logs:
    custom_components.modbus_slave: debug
    pymodbus: debug
```

---

## Requirements

- **Home Assistant** 2026.7.0 or newer
- **Network** TCP port (default `502`) reachable from the Modbus master
- **Port below 1024** HA OS / Supervised, or `CAP_NET_BIND_SERVICE` on Container / Core

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-improvement`)
3. Submit a Pull Request

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup and coding standards.

---

## License

GPL-3.0 — see [LICENSE](LICENSE) for details.

---

<p align="center">
  Developed by <strong><a href="https://brdc.nl">BRDC</a></strong><br>
  Powered by <a href="https://github.com/pymodbus-dev/pymodbus">pymodbus</a> · Built for <a href="https://www.home-assistant.io/">Home Assistant</a>
</p>
