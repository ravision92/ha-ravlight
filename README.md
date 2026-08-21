# RavLight Home Assistant integration

HACS custom integration for RavLight firmware devices, including Orion motorized winch fixtures.

## Install

1. In HACS, add this repository as an **Integration** custom repository.
2. Download **RavLight** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration**, select **RavLight**, and enter the IP address or `.local` hostname of any one RavLight device.
4. The entered device performs RavLight's UDP network scan; select the desired fixture from the results.

## What it provides

- Device temperature, uptime, lifetime hours, and DMX-active status.
- Orion diagnostics: homed state, motor state, position, driver temperature, and fault flags.
- Safe device controls: identify fixture, release DMX override, clear motor fault, and emergency stop.

The integration never invokes factory reset, reboot, OTA firmware update, limit capture, StallGuard calibration, or continuous jog commands. Those remain deliberately manual operations.

## Compatibility

Requires RavLight firmware exposing `GET /api/status`. The first fixture must be entered manually because the documented discovery API is a scan performed by an existing RavLight device. Orion-specific entities appear only when the firmware reports the Orion fixture and provides `/motorstatus`.
