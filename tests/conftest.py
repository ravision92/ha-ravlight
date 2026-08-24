"""Fixtures for the RavLight tests."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_socket

pytest_plugins = "pytest_homeassistant_custom_component"

# Windows only: asyncio's ProactorEventLoop builds its self-pipe from an AF_INET
# socket pair, and the socket blocking Home Assistant's test plugin installs
# refuses that — every test errors in setup before it runs. (On Linux the pair
# is AF_UNIX, which the plugin allows, so this is a no-op there in practice.)
# Nothing in these tests reaches the network: the API client is mocked and the
# UDP scan is patched out.
if sys.platform == "win32":
    pytest_socket.disable_socket = lambda *args, **kwargs: None

PRIMARY_HOST = "192.168.1.50"

STATUS = {
    "fw": "2.23.15",
    "board": "QuinLED Dig-Octa",
    "fw_base": "elyon_quinled_octa",
    "cfg_rev": 12,
    "cfg_hash": 2748291043,
    "project": "Elyon",
    "id": "RVD008",
    "mode": "ETH",
    "ip": "192.168.1.50",
    "mac": "AA:BB:CC:DD:EE:FF",
    "mdns": "ravRVD008.local",
    "rssi": 0,
    "uptime_sec": 3612,
    "total_hours": 42,
    "heap_free": 145000,
    "heap_min": 120000,
    "dmx_active": True,
    "fps": 40,
}

FEATURES = {
    "dmx": 1,
    "ethernet": 1,
    "discovery": 1,
    "fixture": "Elyon",
    "hw_outputs": 8,
    "hw_pins": [0, 1, 2, 3, 4, 5, 12, 13],
}

CONFIG = {
    "version": 2,
    "project": "Elyon",
    "network": {"id": "RVD008", "ssid": "rig", "dhcp": True},
    "dmx": {"input": 2, "universe": 1},
    "fixture": {"outputs": [{"proto": 1, "count": 100, "univ": 1, "ch": 1}]},
}

OTA = {
    "current": "2.23.15",
    "latest": "2.23.15",
    "notes": "",
    "url": "",
    "checked": False,
    "checking": False,
    "available": False,
    "error": "",
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make the custom integration loadable in every test."""
    yield


def build_client(host: str) -> MagicMock:
    """Return a client that answers like a reachable device at this address.

    Identity is derived from the address so that a flow adding several devices
    sees several MACs — one client for every host, not one shared mock.
    """
    status = dict(STATUS)
    if host != PRIMARY_HOST:
        octet = int(host.rsplit(".", 1)[-1])
        status |= {
            "ip": host,
            "mac": f"AA:BB:CC:DD:EE:{octet:02X}",
            "id": f"RVD{octet:03d}",
        }
    client = MagicMock()
    client.host = host
    client.async_get_status = AsyncMock(return_value=status)
    client.async_get_features = AsyncMock(return_value=dict(FEATURES))
    client.async_get_config = AsyncMock(return_value=dict(CONFIG))
    client.async_get_personalities = AsyncMock(
        return_value={"fixture": "Elyon", "count": 0, "personalities": []}
    )
    client.async_get_ota = AsyncMock(return_value=dict(OTA))
    client.async_get_motor_status = AsyncMock(return_value=None)
    client.async_start_discovery = AsyncMock(return_value={"duration": 0})
    client.async_get_discovered_devices = AsyncMock(return_value=[])
    client.async_post = AsyncMock()
    return client


@pytest.fixture
def mock_client() -> MagicMock:
    """Return the client for the device the tests type in by hand."""
    return build_client(PRIMARY_HOST)


@pytest.fixture
def patched_client(mock_client: MagicMock):
    """Patch the API client everywhere the integration constructs one."""
    clients = {mock_client.host: mock_client}

    def factory(session, host, port=80):
        return clients.setdefault(host, build_client(host))

    with (
        patch(
            "custom_components.ravlight.config_flow.RavLightApiClient",
            side_effect=factory,
        ),
        patch("custom_components.ravlight.RavLightApiClient", side_effect=factory),
        # The real session is never used, but building one pulls in aiodns,
        # which refuses to run on Windows' proactor event loop.
        patch(
            "custom_components.ravlight.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.ravlight.async_get_clientsession",
            return_value=MagicMock(),
        ),
    ):
        yield mock_client
