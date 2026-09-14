# RavLight Home Assistant integration

HACS custom integration for [RavLight](https://ravlight.com) firmware devices — Veyron pixel bars, Elyon LED controllers, Orion motorized winches and Axon nodes.

> The integration started as [@gmint](https://github.com/gmint)'s work at [Q-Squared-Systems/ha-ravlight](https://github.com/ravlight-ha/ha-ravlight), and is maintained by [@gmint](https://github.com/gmint) and [@ravision92](https://github.com/ravision92). See [What changed](#what-changed) for the second round of work.

## Install

1. In HACS, add this repository as an **Integration** custom repository.
2. Download **RavLight** and restart Home Assistant.
3. Devices running firmware newer than 2.23.15 announce themselves — accept the discovery notification and you are done. Otherwise go to **Settings → Devices & services → Add integration**, select **RavLight**, and either scan the network or enter one device's address.

The RavLight icon ships with the integration (`custom_components/ravlight/brand/`) and needs no brands-repository submission — Home Assistant 2026.3 and newer serve brand images bundled in a custom integration, and prefer them over the CDN. On older versions the integration simply shows the default icon.

## Finding devices

Three ways, all built in:

| Path | Needs | Finds |
|---|---|---|
| **mDNS (zeroconf)** | firmware after 2.23.15 | devices already running, automatically, and follows them across address changes |
| **DHCP hostname** | any firmware (hostname is `Ravlight-<ID>`) | devices as they take or renew a lease, automatically |
| **UDP scan** | Home Assistant on host networking | anything that answers a broadcast probe, on demand from the setup dialog |

The setup dialog also offers a fourth route: enter one reachable device and it will scan on your behalf, which reaches fixtures on subnets Home Assistant sees no broadcast from.

The UDP scan implements the RavLight discovery protocol directly — probe `R_DISCOVER` to udp/4210, replies arrive on the **fixed** port udp/4211. That fixed reply port is why the scan needs host networking (a NAT has no mapping for a port nothing sent from) and why only one process per host can run it: if Polaris is running on the same machine, the scan will report that it cannot start rather than silently finding nothing. Use one of the automatic paths, or enter an address, in that case.

## What it provides

Entities are created from what the device reports about itself (`/api/features`, `/api/config`), so a fixture only ever gets the entities it actually has.

**Every fixture** — temperature (where the board has a sensor), WiFi signal (where the link is wireless), connection type, IP address, uptime, lifetime hours, DMX frame rate, DMX source, universe, free memory, configuration revision, reachability, DMX-active, firmware version and update availability, identify, restart, check for update.

**Veyron** — active personality (by name) with its channel footprint, and the DMX start addresses of the pixel, accent and function blocks.

**Elyon / Axon** — number of active outputs, total pixel count, a per-output breakdown (protocol, pixels, universe, start channel) as attributes, and an identify button per configured output that wipes that run white. Outputs wired as a clock line for a clocked chipset are not counted as outputs of their own. Elyon serves no fixture-wide identify route, so its "Identify fixture" button wipes each output in turn.

**Orion** — motor state, position in cm with its travel limits, driver temperature, fault flags, StallGuard result, homed, moving, manual override, plus run homing, emergency stop, clear fault and release DMX override. Orion boards that also drive LED outputs get the Elyon entities as well.

Factory reset, OTA upload, limit capture, StallGuard calibration and continuous jog are deliberately not exposed: they are destructive, or they need an operator watching the fixture.

## What changed

- **Devices are identified by their hardware MAC**, not by the device name. The name is editable from the web UI, and renaming a fixture previously created a second device and orphaned every entity of the first. Existing installations are migrated in place — same device row, same entity rows, re-keyed — the first time each device is reachable after the update. Entities you had customised keep their history and settings.
- **Discovery**: mDNS and DHCP entries in the manifest, plus a direct UDP scan in the setup dialog. The first device no longer has to be typed in by hand, and a device that changes address is followed instead of going unavailable.
- **Every fixture family is covered**, driven by what the device reports rather than by hardcoded assumptions. Notably Elyon has no `/highlight` route at all: identify goes through `/ledhighlight`, which is per-output and wants the index in the POST **body** (a query string is answered 400). Verified against a QuinLED Octa on the bench.
- **The additional-devices selection now works.** It hung off `async_on_create_entry`, which is not a config-flow hook, so the extra fixtures a scan found were silently never added.
- **One request per cycle instead of two.** The configuration is only re-read when the device says it changed, using the `cfg_rev`/`cfg_hash` fields that already ride along in every status reply.
- **The WiFi password is dropped on arrival.** `/api/config` serves it in clear text; it is stripped in the API client so it cannot reach an entity attribute or a diagnostics download.
- **Firmware update entity** from the device's own update check (report-only — flashing stays a deliberate operation in the web UI).
- **Tests** for the flows, the migration and the per-fixture entity tables, run in CI alongside hassfest and the HACS validation.

## Compatibility

Requires firmware exposing `GET /api/status` and `GET /api/features`. Everything degrades rather than failing: older firmware without `/api/personalities`, `cfg_rev`/`cfg_hash` or an mDNS service record simply gets fewer entities and one of the other discovery paths.

## Development

```bash
pip install pytest-homeassistant-custom-component
pytest
```

On Windows the socket blocking in Home Assistant's test plugin refuses the socket pair asyncio's proactor loop needs for its own self-pipe; `tests/conftest.py` neutralises it there, and nothing in the tests reaches the network.
