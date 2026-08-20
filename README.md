# RavLight Home Assistant integration

HACS custom integration for RavLight firmware devices, including Orion motorized winch fixtures.

## Install

1. In HACS, add this repository as an **Integration** custom repository.
2. Download **RavLight** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration**, select **RavLight**, and enter the device IP address or `.local` hostname.

## What it provides

- Device temperature, uptime, lifetime hours, and DMX-active status.
- Orion diagnostics: homed state, motor state, position, driver temperature, and fault flags.
- Safe device controls: identify fixture, release DMX override, clear motor fault, and emergency stop.

The integration never invokes factory reset, reboot, OTA firmware update, limit capture, StallGuard calibration, or continuous jog commands. Those remain deliberately manual operations.

## Compatibility

Requires RavLight firmware exposing `GET /api/status`. Orion-specific entities appear only when the firmware reports the Orion fixture and provides `/motorstatus`.
