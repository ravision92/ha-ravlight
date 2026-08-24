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
    # Elyon has no /highlight route, so identify is the only LED button.
    assert "highlight" in keys
    assert "led_highlight" not in keys


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
    assert {"highlight", "led_highlight", "active_outputs"} <= keys

    state = hass.states.get("sensor.rvd008_position")
    assert state is not None and state.state == "128.4"
