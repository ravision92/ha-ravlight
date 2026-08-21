"""Config flow for RavLight."""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RavLightApiClient, RavLightApiError
from .const import CONF_HOST, CONF_PORT, DEFAULT_PORT, DOMAIN


class RavLightConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RavLight."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        super().__init__()
        self._discovered_devices: dict[str, dict[str, Any]] = {}
        self._port = DEFAULT_PORT

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            client = RavLightApiClient(
                async_get_clientsession(self.hass),
                user_input[CONF_HOST], user_input[CONF_PORT]
            )
            try:
                status = await client.async_get_status()
            except RavLightApiError:
                errors["base"] = "cannot_connect"
            else:
                device_id = status.get("id")
                if not device_id:
                    errors["base"] = "invalid_device"
                else:
                    self._port = user_input[CONF_PORT]
                    self._discovered_devices = {
                        str(status.get("ip") or user_input[CONF_HOST]): status
                    }
                    try:
                        scan = await client.async_start_discovery()
                        await asyncio.sleep((scan.get("duration", 4500) / 1000) + 1)
                        for device in await client.async_get_discovered_devices():
                            host = device.get("ip")
                            if host:
                                self._discovered_devices[str(host)] = device
                    except RavLightApiError:
                        # The known device remains usable when discovery is unavailable.
                        pass
                    return await self.async_step_discovery()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
            }),
            errors=errors,
        )

    async def async_step_discovery(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Let the user select a device found by a RavLight discovery relay."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            client = RavLightApiClient(
                async_get_clientsession(self.hass), host, self._port
            )
            try:
                status = await client.async_get_status()
            except RavLightApiError:
                errors["base"] = "cannot_connect"
            else:
                device_id = status.get("id")
                if not device_id:
                    errors["base"] = "invalid_device"
                else:
                    await self.async_set_unique_id(str(device_id))
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=f"RavLight {device_id}",
                        data={CONF_HOST: host, CONF_PORT: self._port},
                    )

        choices = {
            host: f"{device.get('id', 'RavLight')} ({host})"
            for host, device in self._discovered_devices.items()
        }
        return self.async_show_form(
            step_id="discovery",
            data_schema=vol.Schema({vol.Required(CONF_HOST): vol.In(choices)}),
            errors=errors,
        )
