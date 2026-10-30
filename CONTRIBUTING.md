# Contributing to Modbus Slave for Home Assistant

Thank you for your interest in contributing! This project is a custom Home Assistant integration that turns Home Assistant into a Modbus TCP slave, built in Python on top of [pymodbus](https://github.com/pymodbus-dev/pymodbus). Contributions of all kinds are welcome — bug reports, feature requests, documentation improvements, and code changes.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Making Changes](#making-changes)
- [Coding Standards](#coding-standards)
- [Submitting a Pull Request](#submitting-a-pull-request)
- [Reporting Bugs](#reporting-bugs)
- [Requesting Features](#requesting-features)
- [Security Issues](#security-issues)

---

## Code of Conduct

Please be respectful and constructive in all interactions. This project follows the [Contributor Covenant](https://www.contributor-covenant.org/) code of conduct. Harassment, discrimination, or disruptive behaviour will not be tolerated.

---

## Getting Started

1. **Fork** the repository on GitHub.
2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/your-username/HA-Modbus-Slave.git
   cd HA-Modbus-Slave
   ```
3. Add the upstream remote so you can stay up to date:
   ```bash
   git remote add upstream https://github.com/CervezaStallone/HA-Modbus-Slave.git
   ```

---

## Development Setup

### Requirements

- **Python 3.14** (the version current Home Assistant runs on)
- **Home Assistant** 2026.7.0 or newer (for local testing)
- A Modbus client to test against, e.g. [mbpoll](https://github.com/epsilonrt/mbpoll), [Modbus Poll](https://www.modbustools.com/modbus_poll.html), Node-RED or `pymodbus.console`

### Install dependencies

It is recommended to work inside a virtual environment:

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements_test.txt
```

`requirements_test.txt` pins `pymodbus` to the version Home Assistant core ships, so tests run against what users actually get.

### Linking the integration to a local Home Assistant instance

Copy (or symlink) the `custom_components/modbus_slave` folder into your Home Assistant `config/custom_components/` directory:

```bash
cp -r custom_components/modbus_slave /path/to/your/ha-config/custom_components/modbus_slave
```

Restart Home Assistant to pick up the changes.

### Enable debug logging

Add the following to your `configuration.yaml` while developing:

```yaml
logger:
  logs:
    custom_components.modbus_slave: debug
    pymodbus: debug
```

---

## Project Structure

```
custom_components/modbus_slave/
├── __init__.py           # Entry setup/unload, register table, state listener, reload on change
├── manifest.json         # Integration metadata (version, dependencies)
├── config_flow.py        # Setup + reconfigure (slave ID, port) and options (mappings)
├── const.py              # Constants, defaults, bit/writable domain sets
├── diagnostics.py        # Diagnostics download (listen address and allowlist redacted)
├── registers.py          # Pure logic, no HA imports: type detection, encode/decode, overlap
├── server.py             # The only pymodbus module: context adapter, write-back, allowlist, server start/stop
├── strings.json          # Translatable UI strings (source)
└── translations/
    ├── en.json           # English — must equal strings.json
    └── nl.json           # Dutch — must have the same keys

tests/
├── test_registers.py     # Detection, encoding, overlap — milliseconds, no HA
├── test_config_flow.py   # Config, reconfigure and options flows
├── test_server.py        # End-to-end: real HA + real Modbus TCP client
├── test_diagnostics.py   # Diagnostics content and redaction
└── test_translations.py  # en.json equals strings.json, nl.json has the same keys
```

Keep `registers.py` free of Home Assistant imports and keep `server.py` the only module that imports `pymodbus`. pymodbus changes its server API between minor versions; this limits what a bump can break to one file.

---

## Making Changes

1. **Sync** with upstream before starting:
   ```bash
   git fetch upstream
   git checkout main
   git merge upstream/main
   ```

2. **Create a feature branch** — use a descriptive name:
   ```bash
   git checkout -b feature/word-order-option
   # or
   git checkout -b fix/scaled16-negative-rounding
   ```

3. **Make your changes** following the [coding standards](#coding-standards) below.

4. **Test your changes** with a real Modbus client against a local Home Assistant, and run the automated suite:
   ```bash
   pytest
   ruff check . && ruff format --check .
   ```
   CI runs the tests against both the minimum supported Home Assistant (2026.7.0, from `hacs.json`) and the latest release.

5. **Commit** with a clear, concise message:
   ```bash
   git commit -m "feat: add little-endian word order option"
   ```
   Preferred commit message prefixes:
   | Prefix | When to use |
   |--------|-------------|
   | `feat:` | New functionality |
   | `fix:` | Bug fixes |
   | `docs:` | Documentation only |
   | `refactor:` | Code restructuring without behaviour change |
   | `test:` | Adding or updating tests |
   | `chore:` | Dependency bumps, CI, tooling |

6. **Push** to your fork:
   ```bash
   git push origin feature/word-order-option
   ```

---

## Coding Standards

This project follows the [Home Assistant developer guidelines](https://developers.home-assistant.io/docs/development_guidelines) and general Python best practices.

### Style

- Follow **[PEP 8](https://peps.python.org/pep-0008/)**.
- Use **type hints** for all function signatures.
- Lint and format with **[Ruff](https://docs.astral.sh/ruff/)** (settings in `pyproject.toml`):
  ```bash
  ruff check --fix .
  ruff format .
  ```

### Home Assistant conventions

- No blocking I/O on the event loop — the Modbus server runs on Home Assistant's loop.
- Configuration lives in the config entry (`data` for the server, `options` for mappings); changes apply through a reload, never a Home Assistant restart.
- Every user-facing string goes in `strings.json` and both translation files.

### Modbus / pymodbus

- Never update a register optimistically on a write; the state listener updates it once Home Assistant reports the new state.
- Reject writes with a proper Modbus exception code (`ILLEGAL_ADDRESS`, `ILLEGAL_VALUE`, `DEVICE_FAILURE`) instead of failing silently.
- Keep the encoding documented in the README (big-endian, high word first) — changing it breaks every master already configured.
- Log unexpected errors at `WARNING`; log expected conditions (e.g. a master reading an unmapped address) at `DEBUG` or not at all.

---

## Submitting a Pull Request

1. Open a Pull Request from your feature branch to `main` on this repository.
2. Fill in the PR description:
   - **What** was changed and **why**.
   - Steps to **reproduce** the issue being fixed (if applicable).
   - Screenshots or log output if relevant.
3. Ensure your branch is up to date with `main` before requesting a review.
4. A maintainer will review your PR. Please be responsive to feedback — small requested changes keep the review cycle short.
5. Once approved, your PR will be merged using **squash merge** to keep the history clean.

PRs that change `.github/workflows/` or `.github/rulesets/` from someone without write access are closed automatically, to prevent supply-chain attacks through CI. A maintainer will apply such a change if it's legitimate.

---

## Reporting Bugs

Please [open an issue](https://github.com/CervezaStallone/HA-Modbus-Slave/issues/new/choose) and include:

- **Home Assistant version**
- **Integration version** (from HACS or `manifest.json`)
- The **Modbus master** you use (PLC, SCADA, tool)
- The **mapping** and the **request** (function code, address, count)
- A clear **description** of the problem
- **Steps to reproduce**
- **Debug logs** (see [debug logging](#enable-debug-logging) above)

---

## Requesting Features

[Open an issue](https://github.com/CervezaStallone/HA-Modbus-Slave/issues/new/choose) with:

- A description of the **use case** and **problem** it solves.
- The function codes, data types or entity domains involved, if applicable.

---

## Security Issues

Please **do not** open a public issue for security vulnerabilities. Instead, follow the process described in [SECURITY.md](SECURITY.md).

---

## License

By contributing to this project you agree that your contributions will be licensed under the [GNU General Public License v3.0](LICENSE).

---

<p align="center">
  Developed by <strong><a href="https://brdc.nl">BRDC</a></strong><br>
  Powered by <a href="https://github.com/pymodbus-dev/pymodbus">pymodbus</a> · Built for <a href="https://www.home-assistant.io/">Home Assistant</a>
</p>
