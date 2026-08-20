"""HTTP client for RavLight firmware."""

from __future__ import annotations

from collections.abc import Mapping
import asyncio
from typing import Any

import aiohttp


class RavLightApiError(Exception):
    """Base error for RavLight API communication."""


class RavLightConnectionError(RavLightApiError):
    """Connection to a RavLight device failed."""


class RavLightInvalidResponseError(RavLightApiError):
    """RavLight device returned an unexpected response."""


class RavLightApiClient:
    """Minimal asynchronous client for the documented RavLight HTTP API."""

    def __init__(self, session: aiohttp.ClientSession, host: str, port: int) -> None:
        self._session = session
        self._base_url = f"http://{host}:{port}"

    async def _request_json(self, method: str, path: str) -> dict[str, Any]:
        try:
            async with asyncio.timeout(10):
                async with self._session.request(method, f"{self._base_url}{path}") as response:
                    response.raise_for_status()
                    payload = await response.json(content_type=None)
        except (TimeoutError, aiohttp.ClientError) as err:
            raise RavLightConnectionError(str(err)) from err
        except (ValueError, aiohttp.ContentTypeError) as err:
            raise RavLightInvalidResponseError(str(err)) from err

        if not isinstance(payload, dict):
            raise RavLightInvalidResponseError("Expected a JSON object")
        return payload

    async def async_get_status(self) -> dict[str, Any]:
        """Return the core device status."""
        return await self._request_json("GET", "/api/status")

    async def async_get_features(self) -> dict[str, Any]:
        """Return compiled firmware features."""
        return await self._request_json("GET", "/api/features")

    async def async_get_motor_status(self) -> dict[str, Any] | None:
        """Return Orion motor status, or None if the fixture does not expose it."""
        try:
            return await self._request_json("GET", "/motorstatus")
        except RavLightConnectionError as err:
            if "404" in str(err):
                return None
            raise

    async def async_post(self, path: str, params: Mapping[str, str | int] | None = None) -> None:
        """Call a documented action endpoint."""
        try:
            async with asyncio.timeout(10):
                async with self._session.post(
                    f"{self._base_url}{path}", params=params
                ) as response:
                    response.raise_for_status()
        except (TimeoutError, aiohttp.ClientError) as err:
            raise RavLightConnectionError(str(err)) from err
