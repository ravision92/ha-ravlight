"""Tests for the RavLight config flow."""

from __future__ import annotations

from ipaddress import ip_address
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ravlight.const import DOMAIN

MAC = "aa:bb:cc:dd:ee:ff"


def _zeroconf_info():
    """Build the mDNS announcement the firmware publishes."""
    try:
        from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
    except ImportError:
        from homeassistant.components.zeroconf import ZeroconfServiceInfo
    return ZeroconfServiceInfo(
        ip_address=ip_address("192.168.1.50"),
        ip_addresses=[ip_address("192.168.1.50")],
        port=80,
        hostname="ravRVD008.local.",
        type="_ravlight._tcp.local.",
        name="ravRVD008._ravlight._tcp.local.",
        properties={
            "id": "RVD008",
            "mac": "AA:BB:CC:DD:EE:FF",
            "fixture": "Elyon",
            "board": "QuinLED Dig-Octa",
            "fw": "2.23.15",
            "fw_base": "elyon_quinled_octa",
        },
    )


def _dhcp_info():
    """Build the DHCP lease event for a device on older firmware."""
    try:
        from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
    except ImportError:
        from homeassistant.components.dhcp import DhcpServiceInfo
    return DhcpServiceInfo(
        ip="192.168.1.50", hostname="ravlight-rvd008", macaddress="aabbccddeeff"
    )


async def test_manual_entry_is_keyed_on_the_mac(
    hass: HomeAssistant, patched_client
) -> None:
    """A device typed in by address is identified by its MAC, not its name."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    assert result["step_id"] == "manual"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.168.1.50", "port": 80}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Elyon RVD008"
    assert result["data"] == {"host": "192.168.1.50", "port": 80}
    assert result["result"].unique_id == MAC


async def test_unreachable_host_is_reported(hass: HomeAssistant, patched_client) -> None:
    """A host that does not answer keeps the form open with an error."""
    from custom_components.ravlight.api import RavLightConnectionError

    patched_client.async_get_status.side_effect = RavLightConnectionError("timeout")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.168.1.50", "port": 80}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_zeroconf_discovery(hass: HomeAssistant, patched_client) -> None:
    """A device announcing itself over mDNS is offered for confirmation."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_zeroconf_info(),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"
    assert result["description_placeholders"] == {
        "name": "RVD008",
        "fixture": "Elyon",
        "host": "192.168.1.50",
    }

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == MAC
    assert result["data"]["host"] == "192.168.1.50"


async def test_dhcp_discovery(hass: HomeAssistant, patched_client) -> None:
    """A DHCP lease is enough to find a device on firmware without mDNS."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=_dhcp_info()
    )
    assert result["step_id"] == "discovery_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == MAC


@pytest.mark.parametrize(
    ("source", "data"),
    [
        (config_entries.SOURCE_ZEROCONF, _zeroconf_info),
        (config_entries.SOURCE_DHCP, _dhcp_info),
    ],
)
async def test_discovery_updates_a_changed_address(
    hass: HomeAssistant, patched_client, source, data
) -> None:
    """Rediscovering a configured device moves it to its new address."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=MAC, data={"host": "192.168.1.7", "port": 80}
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": source}, data=data()
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data["host"] == "192.168.1.50"


async def test_scan_lists_devices_and_adds_each_one(
    hass: HomeAssistant, patched_client
) -> None:
    """The UDP scan offers what answered, and every pick becomes its own device."""
    replies = [
        {"id": "RVD008", "mac": "AA:BB:CC:DD:EE:FF", "fixture": "Elyon",
         "ip": "192.168.1.50", "source_ip": "192.168.1.50"},
        {"id": "RVL001", "mac": "AA:BB:CC:DD:EE:01", "fixture": "Orion",
         "ip": "192.168.1.51", "source_ip": "192.168.1.51"},
    ]
    with (
        patch(
            "custom_components.ravlight.config_flow.async_get_ipv4_broadcast_addresses",
            return_value=[ip_address("192.168.1.255")],
        ),
        patch(
            "custom_components.ravlight.config_flow.async_scan", return_value=replies
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "scan"}
        )
        assert result["step_id"] == "scan"
        assert result["description_placeholders"] == {"count": "2"}

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"devices": ["192.168.1.50", "192.168.1.51"]}
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()

    # The first pick is this flow's entry; the second is queued as its own.
    hosts = {entry.data["host"] for entry in hass.config_entries.async_entries(DOMAIN)}
    assert hosts == {"192.168.1.50", "192.168.1.51"}


async def test_scan_without_the_reply_port_falls_back_to_manual(
    hass: HomeAssistant, patched_client
) -> None:
    """A scan that cannot bind udp/4211 says so instead of reporting nothing."""
    from custom_components.ravlight.discovery import RavLightScanUnavailableError

    with (
        patch(
            "custom_components.ravlight.config_flow.async_get_ipv4_broadcast_addresses",
            return_value=[ip_address("192.168.1.255")],
        ),
        patch(
            "custom_components.ravlight.config_flow.async_scan",
            side_effect=RavLightScanUnavailableError("address already in use"),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "scan"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"
    assert result["errors"] == {"base": "scan_unavailable"}


async def test_relay_scan_offers_what_the_seed_device_found(
    hass: HomeAssistant, patched_client
) -> None:
    """A reachable device can find fixtures Home Assistant cannot broadcast to."""
    patched_client.async_get_discovered_devices.return_value = [
        {"id": "RVL001", "mac": "AA:BB:CC:DD:EE:01", "fixture": "Orion",
         "ip": "192.168.1.51"}
    ]
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.168.1.50", "port": 80}
    )
    assert result["step_id"] == "relay"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"devices": ["192.168.1.51"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    hosts = {entry.data["host"] for entry in hass.config_entries.async_entries(DOMAIN)}
    assert hosts == {"192.168.1.50", "192.168.1.51"}
