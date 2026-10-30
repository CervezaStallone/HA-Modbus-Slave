# Security Policy

## Supported Versions

Only the latest release of the Modbus Slave integration is actively maintained and will receive security fixes.

| Version | Supported          |
| ------- | ------------------ |
| Latest  | ✅ Yes             |
| Older   | ❌ No              |

## Reporting a Vulnerability

We take security seriously — especially given that this integration opens a Modbus TCP server inside Home Assistant, and writable mappings let a Modbus master control Home Assistant entities, which may in turn control physical equipment (pumps, heating, lighting, etc.).

**Please do NOT open a public GitHub issue to report a security vulnerability.**

Instead, report vulnerabilities privately using one of the following methods:

- **GitHub Private Security Advisory** (preferred):
  Go to [Security → Advisories](https://github.com/CervezaStallone/HA-Modbus-Slave/security/advisories/new) and open a draft advisory. This keeps the report confidential until a fix is available.
- **Email**: Contact the maintainer directly via their [GitHub profile](https://github.com/CervezaStallone).

### What to include in your report

To help us triage and reproduce the issue quickly, please include:

- A clear description of the vulnerability and its potential impact
- The version(s) of the integration affected
- Steps to reproduce the issue or a proof-of-concept (if applicable)
- Any relevant logs, screenshots, or configuration snippets (with sensitive data redacted)
- Your suggested severity (Critical / High / Medium / Low)

## Response Timeline

| Stage                          | Target timeframe |
| ------------------------------ | ---------------- |
| Acknowledgement of report      | Within 48 hours  |
| Initial assessment & triage    | Within 7 days    |
| Fix developed & tested         | Within 30 days   |
| Public disclosure (coordinated)| After fix is released |

We follow **coordinated disclosure**: we will work with you to agree on a disclosure timeline before publishing details of the vulnerability.

## Scope

The following are considered **in scope** for security reports:

- **Unauthorized write access**: Logic flaws that let a Modbus master write to a mapping that is not marked writable, to an entity outside the writable domains, or with a value outside the entity's min/max
- **Wrong slave ID handling**: Requests for another unit ID being answered or acted upon
- **Injection vulnerabilities**: Crafted Modbus frames that cause unsafe behaviour in Home Assistant (e.g. calling services other than the intended ones)
- **Denial of service**: Issues that cause Home Assistant to crash, block the event loop or become unresponsive via malformed or excessive Modbus traffic
- **Information exposure**: Entity data being served that the user did not map
- **Dependency vulnerabilities**: Critical CVEs in `pymodbus`, `voluptuous`, or `homeassistant` that directly affect this integration's security posture

The following are **out of scope**:

- The lack of authentication and encryption in Modbus TCP itself — this is a property of the protocol and documented in the README
- Vulnerabilities in Home Assistant Core itself — report those to the [Home Assistant security team](https://www.home-assistant.io/security/)
- Vulnerabilities in third-party Modbus masters or devices
- Issues that require physical access to the network
- Social engineering

## Security Best Practices for Users

When deploying this integration, we recommend the following:

- **Network isolation**: Keep the Modbus port on a dedicated VLAN with only the Modbus master(s), isolated from the general network and the internet.
- **Firewall rules**: Restrict the configured TCP port (default 502) to the IP addresses of your Modbus master(s). Never forward it to the internet.
- **Least privilege**: Leave mappings read-only unless the master really needs to control the entity. Writable is off by default.
- **Map only what's needed**: Every mapped entity is readable by anyone who can reach the port.
- **Home Assistant security**: Keep Home Assistant updated and enable two-factor authentication on your account.
- **Logging**: Monitor the Home Assistant logbook and logs for unexpected state changes on writable entities.

## Disclosure Policy

Once a fix has been released, we will publish a security advisory on the [GitHub Security Advisories](https://github.com/CervezaStallone/HA-Modbus-Slave/security/advisories) page, crediting the reporter (unless they prefer to remain anonymous).

## Acknowledgements

We thank all security researchers who responsibly disclose vulnerabilities and help make this integration safer for everyone.
