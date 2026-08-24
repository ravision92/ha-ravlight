"""Constants for the RavLight integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "ravlight"
MANUFACTURER = "RavLight"

CONF_HOST = "host"
CONF_PORT = "port"
DEFAULT_PORT = 80

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.UPDATE,
]

UPDATE_INTERVAL_SECONDS = 15
# /api/ota only reports the result of the last manifest check the device made,
# so polling it as often as the live status would be pure traffic.
OTA_INTERVAL_SECONDS = 300

# Fixture families, as reported by /api/features["fixture"] (PROJECT_NAME in
# the firmware). Which entities a device gets is decided from this.
FIXTURE_VEYRON = "Veyron"
FIXTURE_ELYON = "Elyon"
FIXTURE_ORION = "Orion"
FIXTURE_AXON = "Axon"

# Elyon is the exception: it has no /highlight route at all, only the LED one.
HIGHLIGHT_PATH = "/highlight"
LED_HIGHLIGHT_PATH = "/ledhighlight"

# DmxInputType in the firmware's config.h, as enum sensor options. Slugs
# rather than display names: these are translation keys, and the display text
# lives in strings.json.
DMX_SOURCE_SLUGS = {
    1: "physical_dmx",
    2: "artnet",
    3: "sacn",
    4: "recorded_scene",
    5: "effects",
}

# getConnectionMode() in the firmware's network_manager.cpp.
CONNECTION_MODE_SLUGS = {
    "ETH": "ethernet",
    "WiFi": "wifi",
    "AP-WiFi": "access_point",
    "not connected": "not_connected",
}

# led_protocol_t in the firmware's core/output_config.h. Only used to label
# outputs in the diagnostic attributes.
LED_PROTOCOL_NAMES = {
    0: "WS2811",
    1: "WS2812B",
    2: "SK6812",
    3: "WS2814",
    4: "WS2815",
    5: "TM1814",
    6: "TM1914",
    7: "APA102",
    8: "SK9822",
    9: "P9813",
    50: "PWM",
    51: "Relay",
    60: "Clock follower",
}

# Outputs with this protocol are wired as the clock line of another output:
# they drive nothing themselves and must not be counted as active.
LED_PROTOCOL_CLOCK_FOLLOWER = 60
