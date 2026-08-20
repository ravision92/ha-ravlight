"""Config flow for RavLight."""

from __future__ import annotations

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
                    await self.async_set_unique_id(str(device_id))
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=f"RavLight {device_id}", data=user_input
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
            }),
            errors=errors,
        )
