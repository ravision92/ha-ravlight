"""Tests for setting a RavLight device up."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ravlight.const import DOMAIN

from .conftest import PRIMARY_HOST

MAC = "aa:bb:cc:dd:ee:ff"


async def _setup(hass: HomeAssistant, **kwargs) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, data={"host": PRIMARY_HOST, "port": 80}, **kwargs
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_entities_follow_the_fixture(hass: HomeAssistant, patched_client) -> None:
    """An Elyon gets its LED entities and none of Orion's motor entities."""
    entry = await _setup(hass, unique_id=MAC)
    assert entry.state is ConfigEntryState.LOADED

    keys = {
        registry_entry.unique_id.removeprefix(f"{MAC}_")
        for registry_entry in er.async_entries_for_config_entry(
            er.async_get(hass), entry.entry_id
        )
    }
    # Every entity is keyed on the MAC, so a rename cannot orphan them.
    assert all(
        registry_entry.unique_id.startswith(MAC)
        for registry_entry in er.async_entries_for_config_entry(
            er.async_get(hass), entry.entry_id
        )
    )
    assert {"active_outputs", "total_pixels", "dmx_source", "online", "firmware"} <= keys
    # No temperature module on this board, and no motor on this fixture.
    assert "temperature" not in keys
    assert not {"motor_state", "position", "homed", "home", "release_dmx"} & keys
    # Elyon has no /highlight route: its fixture-wide identify is built from
    # the per-output wipes, and every configured output gets its own button.
    assert "highlight" in keys
    assert "identify_output_1" in keys


async def test_device_registry_entry(hass: HomeAssistant, patched_client) -> None:
    """The device carries the fixture, board and firmware it reported."""
    entry = await _setup(hass, unique_id=MAC)
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, MAC)})
    assert device is not None
    assert device.name == "RVD008"
    assert device.model == "Elyon (QuinLED Dig-Octa)"
    assert device.sw_version == "2.23.15"
    assert device.configuration_url == f"http://{PRIMARY_HOST}"
    assert (dr.CONNECTION_NETWORK_MAC, MAC) in device.connections


async def test_legacy_entry_moves_from_the_name_to_the_mac(
    hass: HomeAssistant, patched_client
) -> None:
    """An entry created before identity moved to the MAC is migrated in place."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={"host": PRIMARY_HOST, "port": 80}, unique_id="RVD008"
    )
    entry.add_to_hass(hass)

    device_registry = dr.async_get(hass)
    legacy_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "RVD008")}
    )
    entity_registry = er.async_get(hass)
    legacy_entity = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "RVD008_uptime",
        config_entry=entry,
        device_id=legacy_device.id,
    )

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.unique_id == MAC
    # Same device row, same entity row — re-keyed rather than duplicated.
    assert device_registry.async_get(legacy_device.id).identifiers == {(DOMAIN, MAC)}
    assert device_registry.async_get_device(identifiers={(DOMAIN, "RVD008")}) is None
    assert entity_registry.async_get(legacy_entity.entity_id).unique_id == (
        f"{MAC}_uptime"
    )


async def test_configuration_is_only_reread_when_it_changes(
    hass: HomeAssistant, patched_client
) -> None:
    """cfg_rev/cfg_hash in the status reply save a request per cycle."""
    entry = await _setup(hass, unique_id=MAC)
    coordinator = entry.runtime_data
    assert patched_client.async_get_config.call_count == 1

    await coordinator.async_refresh()
    assert patched_client.async_get_config.call_count == 1

    # Somebody edits the device from its web UI.
    patched_client.async_get_status.return_value = (
        patched_client.async_get_status.return_value | {"cfg_rev": 13, "cfg_hash": 42}
    )
    await coordinator.async_refresh()
    assert patched_client.async_get_config.call_count == 2


async def test_wifi_password_never_reaches_home_assistant(
    hass: HomeAssistant, patched_client
) -> None:
    """The client strips it, so no entity attribute or diagnostic can leak it."""
    from custom_components.ravlight.api import RavLightApiClient

    class _Response:
        status = 200

        async def json(self, content_type=None):
            return {"network": {"ssid": "rig", "password": "hunter2"}}

        def raise_for_status(self):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class _Session:
        def request(self, *args, **kwargs):
            return _Response()

    config = await RavLightApiClient(_Session(), PRIMARY_HOST).async_get_config()
    assert config["network"]["ssid"] == "rig"
    assert "password" not in config["network"]


async def test_orion_gets_motor_entities(hass: HomeAssistant, patched_client) -> None:
    """A winch reports its own hardware, and keeps the LED entities too."""
    patched_client.async_get_features.return_value = {
        "dmx": 1, "ethernet": 1, "discovery": 1, "fixture": "Orion",
        "hw_outputs": 4, "hw_pins": [4, 5, 15, 16],
    }
    patched_client.async_get_status.return_value = (
        patched_client.async_get_status.return_value
        | {"project": "Orion", "board": "LED Lifter v5"}
    )
    patched_client.async_get_motor_status.return_value = {
        "available": True, "state": "IDLE", "faultFlags": 0, "sgResult": 231,
        "driverTemp": 0, "homed": True, "busy": False, "positionCm": 128.4,
        "downCm": 0.0, "upCm": 250.0, "override": False,
    }
    entry = await _setup(hass, unique_id=MAC)

    keys = {
        registry_entry.unique_id.removeprefix(f"{MAC}_")
        for registry_entry in er.async_entries_for_config_entry(
            er.async_get(hass), entry.entry_id
        )
    }
    assert {"motor_state", "position", "homed", "motor_fault", "motor_busy"} <= keys
    assert {"home", "stop", "clear_fault", "release_dmx"} <= keys
    # Orion has both its own identify sequence and LED outputs to identify.
    assert {"highlight", "identify_output_1", "active_outputs"} <= keys

    state = hass.states.get("sensor.rvd008_position")
    assert state is not None and state.state == "128.4"


async def test_identify_sends_the_output_index_in_the_body(
    hass: HomeAssistant, patched_client
) -> None:
    """The firmware reads `out` as a body param and 400s on a query string."""
    patched_client.async_get_config.return_value = {
        "version": 2,
        "project": "Elyon",
        "network": {"id": "RVD008"},
        "dmx": {"input": 2, "universe": 0},
        "fixture": {"outputs": [
            {"proto": 3, "count": 300, "univ": 0, "ch": 1},
            {"proto": 3, "count": 300, "univ": 2, "ch": 177},
            {"proto": 0, "count": 0},
        ]},
    }
    entry = await _setup(hass, unique_id=MAC)

    keys = {
        registry_entry.unique_id.removeprefix(f"{MAC}_")
        for registry_entry in er.async_entries_for_config_entry(
            er.async_get(hass), entry.entry_id
        )
    }
    # Two configured outputs, so two per-output buttons — not one per socket.
    assert {"identify_output_1", "identify_output_2"} <= keys
    assert "identify_output_3" not in keys

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.rvd008_identify_output_2"},
        blocking=True,
    )
    # Index is 0-based on the wire, and goes in the body.
    patched_client.async_post.assert_called_with("/ledhighlight", {"out": 1})


async def test_an_older_manifest_is_not_offered_as_an_update(
    hass: HomeAssistant, patched_client
) -> None:
    """A hand-flashed build is newer than the feed — that is not an update."""
    patched_client.async_get_ota.return_value = {
        "current": "2.23.15", "latest": "2.23.14", "notes": "older release",
        "url": "", "checked": True, "checking": False, "available": False,
        "error": "",
    }
    await _setup(hass, unique_id=MAC)

    state = hass.states.get("update.rvd008_firmware")
    assert state is not None
    assert state.state == "off"
    assert state.attributes["installed_version"] == "2.23.15"
    assert state.attributes["latest_version"] == "2.23.15"


async def test_an_available_update_is_offered(hass: HomeAssistant, patched_client) -> None:
    """When the device says there is one, it shows up with its notes."""
    patched_client.async_get_ota.return_value = {
        "current": "2.23.15", "latest": "2.24.1", "notes": "Zeroconf discovery",
        "url": "https://ravlight.com/firmware/elyon_quinled_octa_fw.bin",
        "checked": True, "checking": False, "available": True, "error": "",
    }
    await _setup(hass, unique_id=MAC)

    state = hass.states.get("update.rvd008_firmware")
    assert state.state == "on"
    assert state.attributes["latest_version"] == "2.24.1"
    assert state.attributes["release_summary"] == "Zeroconf discovery"
