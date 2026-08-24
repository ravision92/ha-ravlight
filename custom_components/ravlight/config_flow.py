"""Config flow for RavLight."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.network import async_get_ipv4_broadcast_addresses
from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY, ConfigFlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac

if TYPE_CHECKING:
    # Type-only: these classes moved from homeassistant.components.<x> to
    # homeassistant.helpers.service_info.<x> in 2025.2, and importing either
    # path at runtime would both pin a Home Assistant version and drag in the
    # discovery components' own requirements.
    from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
    from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import RavLightApiClient, RavLightApiError
from .const import CONF_HOST, CONF_PORT, DEFAULT_PORT, DOMAIN
from .discovery import RavLightScanUnavailableError, async_scan

_LOGGER = logging.getLogger(__name__)

CONF_DEVICES = "devices"


class RavLightConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RavLight."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        super().__init__()
        self._host: str | None = None
        self._port = DEFAULT_PORT
        self._device_id: str | None = None
        self._fixture: str | None = None
        self._candidates: dict[str, dict[str, Any]] = {}

    # ── Manual entry ────────────────────────────────────────────────────────

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick between typing an address and scanning."""
        return self.async_show_menu(step_id="user", menu_options=["manual", "scan"])

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add one device by address."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            status = await self._async_read_status(host, port)
            if status is None:
                errors["base"] = "cannot_connect"
            elif not status.get("id"):
                errors["base"] = "invalid_device"
            else:
                await self._async_set_identity(status, host)
                # A device that can scan finds the rest of the rig for us, which
                # is the one thing this flow can offer that discovery cannot:
                # it reaches subnets Home Assistant sees no broadcast from.
                await self._async_collect_from_relay(host, port)
                self._host, self._port = host, port
                return await self._async_step_after_seed()

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=65535)
                    ),
                }
            ),
            errors=errors,
        )

    # ── Direct UDP scan ─────────────────────────────────────────────────────

    async def async_step_scan(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Find devices by probing the network directly over UDP."""
        if user_input is not None:
            hosts = list(user_input[CONF_DEVICES])
            if not hosts:
                return self.async_abort(reason="no_devices_selected")
            return await self._async_create_first_and_queue_rest(hosts, DEFAULT_PORT)

        broadcasts = [str(address) for address in await async_get_ipv4_broadcast_addresses(self.hass)]
        try:
            replies = await async_scan(broadcasts)
        except RavLightScanUnavailableError as err:
            # Port 4211 is exclusive and the reply arrives there or nowhere, so
            # there is nothing to retry — say so and let the user type an
            # address instead.
            _LOGGER.debug("UDP scan unavailable: %s", err)
            return self.async_show_form(
                step_id="manual",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_HOST): str,
                        vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.All(
                            vol.Coerce(int), vol.Range(min=1, max=65535)
                        ),
                    }
                ),
                errors={"base": "scan_unavailable"},
            )

        configured = {entry.unique_id for entry in self._async_current_entries()}
        choices: dict[str, str] = {}
        for reply in replies:
            host = str(reply.get("source_ip") or reply.get("ip") or "")
            mac = reply.get("mac")
            if not host or (mac and format_mac(str(mac)) in configured):
                continue
            choices[host] = _describe(reply, host)

        if not choices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="scan",
            data_schema=vol.Schema(
                {vol.Required(CONF_DEVICES, default=list(choices)): cv.multi_select(choices)}
            ),
            description_placeholders={"count": str(len(choices))},
        )

    # ── Zeroconf / DHCP ─────────────────────────────────────────────────────

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle a device announcing itself over mDNS."""
        properties = discovery_info.properties or {}
        host = str(discovery_info.host)
        mac = properties.get("mac")
        if mac:
            await self.async_set_unique_id(format_mac(str(mac)))
            self._abort_if_unique_id_configured(updates={CONF_HOST: host})

        self._host = host
        self._port = discovery_info.port or DEFAULT_PORT
        self._device_id = properties.get("id")
        self._fixture = properties.get("fixture")

        status = await self._async_read_status(self._host, self._port)
        if status is None:
            return self.async_abort(reason="cannot_connect")
        await self._async_set_identity(status, self._host)
        return await self.async_step_discovery_confirm()

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """Handle a device taking a DHCP lease.

        Covers firmware that predates the mDNS service record: the hostname
        (Ravlight-<ID>) has always been set.
        """
        await self.async_set_unique_id(format_mac(discovery_info.macaddress))
        self._abort_if_unique_id_configured(updates={CONF_HOST: discovery_info.ip})

        self._host = discovery_info.ip
        self._port = DEFAULT_PORT
        status = await self._async_read_status(self._host, self._port)
        if status is None:
            return self.async_abort(reason="cannot_connect")
        await self._async_set_identity(status, self._host)
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm adding a device that announced itself."""
        if user_input is not None:
            return self._async_create()

        self.context["title_placeholders"] = {"name": self._title()}
        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={
                "name": self._device_id or "RavLight",
                "fixture": self._fixture or "RavLight",
                "host": self._host or "",
            },
        )

    async def async_step_integration_discovery(
        self, discovery_info: dict[str, Any]
    ) -> ConfigFlowResult:
        """Add a device the user already selected in a scan."""
        self._host = discovery_info[CONF_HOST]
        self._port = discovery_info.get(CONF_PORT, DEFAULT_PORT)
        status = await self._async_read_status(self._host, self._port)
        if status is None:
            return self.async_abort(reason="cannot_connect")
        await self._async_set_identity(status, self._host)
        return self._async_create()

    # ── Helpers ─────────────────────────────────────────────────────────────

    async def _async_read_status(self, host: str, port: int) -> dict[str, Any] | None:
        """Return /api/status, or None when the device cannot be reached."""
        client = RavLightApiClient(async_get_clientsession(self.hass), host, port)
        try:
            return await client.async_get_status()
        except RavLightApiError as err:
            _LOGGER.debug("Cannot read status from %s:%s: %s", host, port, err)
            return None

    async def _async_set_identity(self, status: dict[str, Any], host: str) -> None:
        """Key this flow on the device's MAC and remember its labels."""
        self._device_id = str(status.get("id") or self._device_id or "")
        self._fixture = str(status.get("project") or self._fixture or "")
        if mac := status.get("mac"):
            await self.async_set_unique_id(format_mac(str(mac)))
            self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        elif self._device_id:
            # Firmware too old to report a MAC over HTTP — fall back to the
            # editable id rather than refusing to set the device up.
            await self.async_set_unique_id(self._device_id)
            self._abort_if_unique_id_configured(updates={CONF_HOST: host})

    async def _async_collect_from_relay(self, host: str, port: int) -> None:
        """Ask a reachable device to scan, and remember what it found."""
        client = RavLightApiClient(async_get_clientsession(self.hass), host, port)
        try:
            scan = await client.async_start_discovery()
            await asyncio.sleep(float(scan.get("duration", 4500)) / 1000 + 1)
            replies = await client.async_get_discovered_devices()
        except RavLightApiError as err:
            # The device the user typed in is still perfectly usable.
            _LOGGER.debug("Relay scan on %s failed: %s", host, err)
            return

        configured = {entry.unique_id for entry in self._async_current_entries()}
        for reply in replies:
            found_host = str(reply.get("ip") or "")
            mac = reply.get("mac")
            if not found_host or found_host == host:
                continue
            if mac and format_mac(str(mac)) in configured:
                continue
            self._candidates[found_host] = reply

    async def _async_step_after_seed(self) -> ConfigFlowResult:
        """Offer the other devices the seed found, if it found any."""
        if not self._candidates:
            return self._async_create()
        return await self.async_step_relay()

    async def async_step_relay(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select additional devices found by the seed device's own scan."""
        if user_input is not None:
            for host in user_input[CONF_DEVICES]:
                self._async_queue_discovery(str(host), self._port)
            return self._async_create()

        choices = {
            host: _describe(reply, host) for host, reply in self._candidates.items()
        }
        return self.async_show_form(
            step_id="relay",
            data_schema=vol.Schema(
                {vol.Optional(CONF_DEVICES, default=[]): cv.multi_select(choices)}
            ),
        )

    async def _async_create_first_and_queue_rest(
        self, hosts: list[str], port: int
    ) -> ConfigFlowResult:
        """Create an entry for the first host and a flow for each other one."""
        first, rest = hosts[0], hosts[1:]
        status = await self._async_read_status(first, port)
        if status is None:
            return self.async_abort(reason="cannot_connect")
        await self._async_set_identity(status, first)
        self._host, self._port = first, port
        for host in rest:
            self._async_queue_discovery(host, port)
        return self._async_create()

    def _async_queue_discovery(self, host: str, port: int) -> None:
        """Start a separate flow for another device.

        One config entry per device, so each keeps its own identity, entities
        and reachability. Duplicates abort on their own unique id.
        """
        self.hass.async_create_task(
            self.hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_INTEGRATION_DISCOVERY},
                data={CONF_HOST: host, CONF_PORT: port},
            )
        )

    def _title(self) -> str:
        """Return the entry title."""
        name = self._device_id or "device"
        return f"{self._fixture} {name}" if self._fixture else f"RavLight {name}"

    def _async_create(self) -> ConfigFlowResult:
        """Create the config entry for the device this flow is about."""
        if not self._host:
            return self.async_abort(reason="invalid_device")
        return self.async_create_entry(
            title=self._title(),
            data={CONF_HOST: self._host, CONF_PORT: self._port},
        )


def _describe(reply: dict[str, Any], host: str) -> str:
    """Return a one-line label for a device found by a scan."""
    name = reply.get("id") or "RavLight"
    fixture = reply.get("fixture") or reply.get("project")
    return f"{name} — {fixture} ({host})" if fixture else f"{name} ({host})"
