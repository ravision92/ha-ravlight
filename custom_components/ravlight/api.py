"""HTTP client for RavLight firmware."""

from __future__ import annotations

from collections.abc import Mapping
import asyncio
from typing import Any

import aiohttp

from .const import DEFAULT_PORT


class RavLightApiError(Exception):
    """Base error for RavLight API communication."""


class RavLightConnectionError(RavLightApiError):
    """Connection to a RavLight device failed."""


class RavLightInvalidResponseError(RavLightApiError):
    """RavLight device returned an unexpected response."""


class RavLightNotFoundError(RavLightApiError):
    """The device does not serve this route.

    Routes only exist when the module or fixture behind them was compiled into
    the running firmware, so a 404 is a normal answer meaning "not this device"
    rather than a failure.
    """


class RavLightApiClient:
    """Minimal asynchronous client for the documented RavLight HTTP API."""

    def __init__(
        self, session: aiohttp.ClientSession, host: str, port: int = DEFAULT_PORT
    ) -> None:
        self._session = session
        self._host = host
        self._port = port
        self._base_url = f"http://{host}:{port}"

    @property
    def host(self) -> str:
        """Return the address this client talks to."""
        return self._host

    async def _request(
        self,
        method: str,
        path: str,
        *,
        expect_json: bool = True,
        params: Mapping[str, str | int] | None = None,
    ) -> Any:
        try:
            async with asyncio.timeout(10):
                async with self._session.request(
                    method, f"{self._base_url}{path}", params=params
                ) as response:
                    if response.status == 404:
                        raise RavLightNotFoundError(path)
                    response.raise_for_status()
                    if not expect_json:
                        return None
                    return await response.json(content_type=None)
        except (TimeoutError, aiohttp.ClientError) as err:
            raise RavLightConnectionError(str(err)) from err
        except ValueError as err:
            raise RavLightInvalidResponseError(str(err)) from err

    async def _request_json_object(self, path: str) -> dict[str, Any]:
        payload = await self._request("GET", path)
        if not isinstance(payload, dict):
            raise RavLightInvalidResponseError(f"{path}: expected a JSON object")
        return payload

    async def async_get_status(self) -> dict[str, Any]:
        """Return the live device status."""
        return await self._request_json_object("/api/status")

    async def async_get_features(self) -> dict[str, Any]:
        """Return the compile-time feature flags of the running firmware."""
        return await self._request_json_object("/api/features")

    async def async_get_config(self) -> dict[str, Any]:
        """Return the device configuration, without its WiFi password.

        The firmware serves the stored password in clear text. It is dropped
        here so it never reaches the coordinator, an entity attribute or a
        diagnostics download.
        """
        config = await self._request_json_object("/api/config")
        network = config.get("network")
        if isinstance(network, dict):
            network.pop("password", None)
        return config

    async def async_get_personalities(self) -> dict[str, Any]:
        """Return the personality catalog of the running firmware."""
        return await self._request_json_object("/api/personalities")

    async def async_get_ota(self) -> dict[str, Any]:
        """Return the result of the device's last firmware update check."""
        return await self._request_json_object("/api/ota")

    async def async_get_motor_status(self) -> dict[str, Any] | None:
        """Return Orion motor status, or None on a fixture without a motor."""
        try:
            return await self._request_json_object("/motorstatus")
        except RavLightNotFoundError:
            return None

    async def async_start_discovery(self, *, espnow: bool = False) -> dict[str, Any]:
        """Ask this device to scan the network for other RavLight devices."""
        return await self._request_json_object(
            f"/discover?espnow={1 if espnow else 0}"
        )

    async def async_get_discovered_devices(self) -> list[dict[str, Any]]:
        """Return the devices found by this device's most recent scan."""
        payload = await self._request("GET", "/devices")
        if not isinstance(payload, list) or not all(
            isinstance(device, dict) for device in payload
        ):
            raise RavLightInvalidResponseError("/devices: expected a JSON array")
        return payload

    async def async_post(
        self, path: str, params: Mapping[str, str | int] | None = None
    ) -> None:
        """Call an action endpoint."""
        await self._request("POST", path, expect_json=False, params=params)
