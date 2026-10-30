"""Constants for the Modbus Slave integration."""

DOMAIN = "modbus_slave"

CONF_SLAVE_ID = "slave_id"
CONF_PORT = "port"
CONF_MAPPINGS = "mappings"

DEFAULT_SLAVE_ID = 1
DEFAULT_PORT = 502

BIT_DOMAINS = {"binary_sensor", "switch", "light", "input_boolean", "fan"}
BIT_WRITABLE_DOMAINS = {"switch", "light", "input_boolean", "fan"}
REG_WRITABLE_DOMAINS = {"number", "input_number"}
