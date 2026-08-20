"""Constants for the RavLight integration."""

from homeassistant.const import Platform

DOMAIN = "ravlight"
CONF_HOST = "host"
CONF_PORT = "port"
DEFAULT_PORT = 80
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]
UPDATE_INTERVAL_SECONDS = 15
