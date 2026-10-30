"""Constants for the Modbus Slave integration."""

from datetime import timedelta

DOMAIN = "modbus_slave"

CONF_SLAVE_ID = "slave_id"
CONF_PORT = "port"
CONF_HOST = "host"
CONF_ALLOWED_IPS = "allowed_ips"
CONF_MAPPINGS = "mappings"

DEFAULT_SLAVE_ID = 1
DEFAULT_PORT = 502

BIT_DOMAINS = {"binary_sensor", "switch", "light", "input_boolean", "fan"}
BIT_WRITABLE_DOMAINS = {"switch", "light", "input_boolean", "fan"}
REG_WRITABLE_DOMAINS = {"number", "input_number"}

# Usage report (telemetry.py)
TELEMETRY_SCHEMA = 2  # payload contract version, shared with the server
CONF_SHARE_USAGE = "share_usage"  # entry data; ticked by default in setup
TELEMETRY_URL = "https://ha-modbus.telemetry.brdc.nl/v1/report"
PRIVACY_URL = "https://github.com/CervezaStallone/HA-Modbus-Slave/blob/main/PRIVACY.md"
TELEMETRY_TIMEOUT = 10  # seconds; fire-and-forget, no retries
TELEMETRY_FIRST_DELAY = 600  # seconds after start
TELEMETRY_INTERVAL = timedelta(hours=6)
