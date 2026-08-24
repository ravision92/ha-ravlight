"""Direct UDP discovery of RavLight devices.

Implements the RavLight UDP discovery protocol so Home Assistant can find
fixtures on its own, without a configured device to relay a scan:

    probe    the literal ASCII string "R_DISCOVER" to udp/4210
    reply    one JSON datagram per device, sent to the probe's source IP but
             always to the FIXED port 4211 — never to the port that probed

That fixed reply port is why this needs two sockets and why it cannot work
from a NAT-ed container: the reply carries a destination port no outbound
mapping exists for. Home Assistant must be on host networking for a scan to
return anything, and only one process per host can hold 4211.

The responder is compiled into every RavLight firmware unconditionally, so any
device answers regardless of board, fixture or build flags.
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
from typing import Any

_LOGGER = logging.getLogger(__name__)

PROBE_PORT = 4210
REPLY_PORT = 4211
COMMAND_PORT = 4212
PROBE = b"R_DISCOVER"

# Three waves, because nothing in the protocol retransmits a lost datagram.
PROBE_WAVES = 3
WAVE_GAP = 1.5
SETTLE = 1.0


class RavLightScanUnavailableError(Exception):
    """Port 4211 could not be opened, so no reply could ever be received."""


class _ReplyCollector(asyncio.DatagramProtocol):
    """Collects one JSON reply per device, keyed by MAC."""

    def __init__(self) -> None:
        self.found: dict[str, dict[str, Any]] = {}

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            reply = json.loads(data)
        except (ValueError, UnicodeDecodeError):
            return
        if not isinstance(reply, dict):
            return
        mac = reply.get("mac")
        if not mac:
            return
        # The device reports the address it believes it has; the datagram
        # source is the address that actually reached us, which is the one to
        # talk to on a multi-homed device.
        reply["source_ip"] = addr[0]
        self.found[str(mac)] = reply


async def async_scan(
    targets: list[str],
    *,
    waves: int = PROBE_WAVES,
    gap: float = WAVE_GAP,
    settle: float = SETTLE,
) -> list[dict[str, Any]]:
    """Probe the given broadcast (or unicast) addresses and return the replies."""
    loop = asyncio.get_running_loop()

    # Bind the reply port before any probe leaves, or the answers are lost.
    try:
        rx_transport, collector = await loop.create_datagram_endpoint(
            _ReplyCollector, local_addr=("0.0.0.0", REPLY_PORT)
        )
    except OSError as err:
        raise RavLightScanUnavailableError(str(err)) from err

    tx_transport, _ = await loop.create_datagram_endpoint(
        asyncio.DatagramProtocol, family=socket.AF_INET, allow_broadcast=True
    )
    try:
        for wave in range(waves):
            for target in targets:
                try:
                    tx_transport.sendto(PROBE, (target, PROBE_PORT))
                except OSError as err:
                    _LOGGER.debug("Probe to %s failed: %s", target, err)
            await asyncio.sleep(gap if wave < waves - 1 else settle)
    finally:
        tx_transport.close()
        rx_transport.close()
        # close() only schedules the socket teardown. Returning before the loop
        # has run it leaves 4211 held, so a second scan — the user pressing
        # "scan" again — would fail to bind a port nothing is really using.
        await asyncio.sleep(0.05)

    _LOGGER.debug("UDP scan of %s found %d device(s)", targets, len(collector.found))
    return list(collector.found.values())


async def async_send_command(host: str, command: str, **payload: Any) -> None:
    """Send a fire-and-forget command datagram to one device.

    HIGHLIGHT | APMODE | CONNECT | RESET. Never acknowledged, so there is
    nothing to await. Only used as a fallback: the HTTP routes report failure.
    """
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        asyncio.DatagramProtocol, family=socket.AF_INET, remote_addr=(host, COMMAND_PORT)
    )
    try:
        transport.sendto(json.dumps({"cmd": command, **payload}).encode())
    finally:
        transport.close()
