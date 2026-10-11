"""A wrapped cover can show on the device page of the cover it wraps (#304)."""

from __future__ import annotations

import logging
from datetime import timedelta

import homeassistant.util.dt as dt_util
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.cover_time_based.device_link import (
    LINK_BY_DEVICE_ENTRY,
    ONE_OWNER_DEVICES,
)

DOMAIN = "cover_time_based"
# Loggers that warn on every test run for reasons unrelated to this feature.
_UNRELATED_LOGGERS = {"homeassistant.loader", "aiohttp_fast_zlib"}


def _hardware_cover(
    hass: HomeAssistant,
    name: str,
    *,
    device_name: str = "Lounge blind motor",
    with_device: bool = True,
):
    """A cover from another integration, like a Zigbee blind, on its own device."""
    owner = MockConfigEntry(domain="hardware")
    owner.add_to_hass(hass)
    device = None
    if with_device:
        device = dr.async_get(hass).async_get_or_create(
            config_entry_id=owner.entry_id,
            identifiers={("hardware", name)},
            name=device_name,
        )
    entity = er.async_get(hass).async_get_or_create(
        "cover",
        "hardware",
        name,
        suggested_object_id=name,
        config_entry=owner,
        device_id=device.id if device else None,
    )
    hass.states.async_set(entity.entity_id, "open", {"current_position": 100})
    return device, entity.entity_id


def _wrapped_entry(
    hass: HomeAssistant,
    inner_entity_id: str,
    *,
    title: str = "Lounge Timed",
    link_to_device: bool | None = True,
):
    """A wrapped cover's config entry; `link_to_device=None` leaves the key out."""
    options = {
        "control_mode": "wrapped",
        "cover_entity_id": inner_entity_id,
        "travel_time_open": 30.0,
        "travel_time_close": 30.0,
    }
    if link_to_device is not None:
        options["link_to_device"] = link_to_device
    entry = MockConfigEntry(domain=DOMAIN, version=4, title=title, options=options)
    entry.add_to_hass(hass)
    return entry


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _change_options(
    hass: HomeAssistant, entry: MockConfigEntry, **changes
) -> None:
    """Save new options the way the card does; the update listener reloads."""
    hass.config_entries.async_update_entry(entry, options={**entry.options, **changes})
    await hass.async_block_till_done()


async def _pass_hass_reload_delay(hass: HomeAssistant) -> None:
    """Run the reload HA schedules ~30 s after an entity is re-enabled."""
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()


def _disable_device(hass: HomeAssistant, device) -> None:
    dr.async_get(hass).async_update_device(
        device.id, disabled_by=dr.DeviceEntryDisabler.USER
    )


def _our_entity(hass: HomeAssistant, entry: MockConfigEntry) -> er.RegistryEntry:
    entries = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert len(entries) == 1
    return entries[0]


def _devices_listing(hass: HomeAssistant, entry: MockConfigEntry) -> list[str]:
    """Ids of the devices that name our config entry (owner or co-owner)."""
    return [
        d.id
        for d in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    ]


def _expected_listing(device) -> list[str]:
    # Before 2025.8 the only link method also adds our config entry to the device.
    return [] if LINK_BY_DEVICE_ENTRY else [device.id]


@pytest.fixture(autouse=True)
async def unload_our_entries(hass: HomeAssistant):
    """Unload every cover this test loaded, to cancel its timers and listeners."""
    yield
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.fixture
def entity_removals(hass: HomeAssistant) -> list[dict]:
    """Every entity-registry removal. A relink must never delete our entry."""
    removals: list[dict] = []

    def _record(event) -> None:
        if event.data["action"] == "remove":
            removals.append(dict(event.data))

    hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, _record)
    return removals


@pytest.fixture
def no_warnings(caplog):
    """Fail if the test body logs anything at warning or above (deprecations too)."""
    yield
    noisy = [
        f"{r.name}: {r.getMessage()}"
        for r in caplog.get_records("call")
        if r.levelno >= logging.WARNING and r.name not in _UNRELATED_LOGGERS
    ]
    assert noisy == []


async def test_wrapped_cover_joins_the_inner_covers_device(
    hass: HomeAssistant, entity_removals, no_warnings
):
    device, inner = _hardware_cover(hass, "lounge_blind")
    entry = _wrapped_entry(hass, inner)

    await _setup(hass, entry)

    assert _our_entity(hass, entry).device_id == device.id
    assert _devices_listing(hass, entry) == _expected_listing(device)
    assert entity_removals == []


async def test_switch_off_by_default_leaves_the_cover_on_its_own(
    hass: HomeAssistant, no_warnings
):
    _, inner = _hardware_cover(hass, "lounge_blind")
    entry = _wrapped_entry(hass, inner, link_to_device=None)

    await _setup(hass, entry)

    assert _our_entity(hass, entry).device_id is None
    assert _devices_listing(hass, entry) == []


async def test_a_plain_reload_leaves_the_device_registry_alone(
    hass: HomeAssistant, entity_removals, no_warnings
):
    """Re-linking to the same device must not churn the device registry."""
    device, inner = _hardware_cover(hass, "lounge_blind")
    entry = _wrapped_entry(hass, inner)
    await _setup(hass, entry)
    device_events: list[dict] = []
    hass.bus.async_listen(
        dr.EVENT_DEVICE_REGISTRY_UPDATED,
        lambda event: device_events.append(dict(event.data)),
    )

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert device_events == []
    assert _our_entity(hass, entry).device_id == device.id
    assert entity_removals == []


async def test_inner_cover_without_a_device_leaves_the_cover_on_its_own(
    hass: HomeAssistant, no_warnings
):
    _, inner = _hardware_cover(hass, "template_blind", with_device=False)
    entry = _wrapped_entry(hass, inner)

    await _setup(hass, entry)

    assert _our_entity(hass, entry).device_id is None
    assert _devices_listing(hass, entry) == []


@pytest.mark.parametrize(
    "inner",
    ["cover.not_there", "not an entity id", ""],
    ids=["missing", "garbage", "empty"],
)
async def test_unusable_inner_cover_id_loads_the_cover_without_a_device(
    hass: HomeAssistant, no_warnings, inner
):
    entry = _wrapped_entry(hass, inner)

    await _setup(hass, entry)

    assert _our_entity(hass, entry).device_id is None
    assert _devices_listing(hass, entry) == []


async def test_changing_the_inner_cover_moves_the_link(
    hass: HomeAssistant, entity_removals, no_warnings
):
    first_device, first = _hardware_cover(hass, "lounge_blind")
    second_device, second = _hardware_cover(
        hass, "kitchen_blind", device_name="Kitchen blind motor"
    )
    entry = _wrapped_entry(hass, first)
    await _setup(hass, entry)
    registry_id = _our_entity(hass, entry).id

    await _change_options(hass, entry, cover_entity_id=second)

    ours = _our_entity(hass, entry)
    assert ours.id == registry_id
    assert ours.device_id == second_device.id
    assert _devices_listing(hass, entry) == _expected_listing(second_device)
    assert dr.async_get(hass).async_get(first_device.id) is not None
    assert entity_removals == []


async def test_turning_the_switch_off_removes_the_link(
    hass: HomeAssistant, entity_removals, no_warnings
):
    device, inner = _hardware_cover(hass, "lounge_blind")
    entry = _wrapped_entry(hass, inner)
    await _setup(hass, entry)

    await _change_options(hass, entry, link_to_device=False)

    assert _our_entity(hass, entry).device_id is None
    assert _devices_listing(hass, entry) == []
    assert dr.async_get(hass).async_get(device.id) is not None
    assert entity_removals == []


async def test_leaving_wrapped_mode_removes_the_link(
    hass: HomeAssistant, setup_input_booleans, entity_removals, no_warnings
):
    device, inner = _hardware_cover(hass, "lounge_blind")
    entry = _wrapped_entry(hass, inner)
    await _setup(hass, entry)

    # cover_entity_id and link_to_device stay stored: the link follows the mode.
    await _change_options(
        hass,
        entry,
        control_mode="switch",
        open_switch_entity_id="input_boolean.open_switch",
        close_switch_entity_id="input_boolean.close_switch",
    )

    assert entry.options["cover_entity_id"] == inner
    assert entry.options["link_to_device"] is True
    assert _our_entity(hass, entry).device_id is None
    assert _devices_listing(hass, entry) == []
    assert dr.async_get(hass).async_get(device.id) is not None
    assert entity_removals == []


async def test_leftover_link_from_an_older_home_assistant_is_cleaned_up(
    hass: HomeAssistant, entity_removals, no_warnings
):
    """The state a user is in after linking with the old method, then upgrading HA.

    Before 2026.8 the old method added our config entry to the hardware device.
    From 2026.8 HA splits such a shared device into one device per config entry,
    each keeping the hardware's identifiers, with our cover on our own one.
    """
    device, inner = _hardware_cover(hass, "lounge_blind")
    entry = _wrapped_entry(hass, inner)
    dev_reg = dr.async_get(hass)
    leftover = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("hardware", "lounge_blind")},
        name="Lounge blind motor",
    )
    if ONE_OWNER_DEVICES:
        assert leftover.id != device.id
    else:
        assert leftover.id == device.id
    registered = er.async_get(hass).async_get_or_create(
        "cover",
        DOMAIN,
        "cover_timebased_uuid_" + entry.entry_id,
        suggested_object_id="lounge_timed",
        config_entry=entry,
        device_id=leftover.id,
    )

    await _setup(hass, entry)

    ours = _our_entity(hass, entry)
    assert ours.id == registered.id
    assert ours.entity_id == registered.entity_id
    assert ours.device_id == device.id
    assert _devices_listing(hass, entry) == _expected_listing(device)
    assert dev_reg.async_get(device.id) is not None
    if ONE_OWNER_DEVICES:
        assert dev_reg.async_get(leftover.id) is None
    assert entity_removals == []


async def test_disabling_the_inner_covers_device_disables_the_cover(
    hass: HomeAssistant,
):
    device, inner = _hardware_cover(hass, "lounge_blind")
    entry = _wrapped_entry(hass, inner)
    await _setup(hass, entry)

    _disable_device(hass, device)
    await hass.async_block_till_done()

    assert _our_entity(hass, entry).disabled_by is er.RegistryEntryDisabler.DEVICE


async def _link_then_disable_the_device(hass: HomeAssistant):
    device, inner = _hardware_cover(hass, "lounge_blind")
    entry = _wrapped_entry(hass, inner)
    await _setup(hass, entry)
    _disable_device(hass, device)
    await hass.async_block_till_done()
    ours = _our_entity(hass, entry)
    assert ours.disabled_by is er.RegistryEntryDisabler.DEVICE
    assert hass.states.get(ours.entity_id) is None
    return entry, ours.entity_id


async def test_unlinking_from_a_disabled_device_brings_the_cover_back(
    hass: HomeAssistant, entity_removals, no_warnings
):
    entry, entity_id = await _link_then_disable_the_device(hass)

    await _change_options(hass, entry, link_to_device=False)

    ours = _our_entity(hass, entry)
    assert ours.device_id is None
    assert ours.disabled_by is None
    assert hass.states.get(entity_id) is not None
    await _pass_hass_reload_delay(hass)
    assert _our_entity(hass, entry).disabled_by is None
    assert hass.states.get(entity_id) is not None
    assert entity_removals == []


async def test_moving_from_a_disabled_device_to_an_enabled_one_brings_the_cover_back(
    hass: HomeAssistant, entity_removals, no_warnings
):
    entry, entity_id = await _link_then_disable_the_device(hass)
    kitchen_device, kitchen = _hardware_cover(
        hass, "kitchen_blind", device_name="Kitchen blind motor"
    )

    await _change_options(hass, entry, cover_entity_id=kitchen)

    ours = _our_entity(hass, entry)
    assert ours.device_id == kitchen_device.id
    assert ours.disabled_by is None
    assert hass.states.get(entity_id) is not None
    await _pass_hass_reload_delay(hass)
    assert _our_entity(hass, entry).disabled_by is None
    assert hass.states.get(entity_id) is not None
    assert entity_removals == []


async def test_moving_to_another_disabled_device_keeps_the_cover_disabled(
    hass: HomeAssistant, entity_removals, no_warnings
):
    entry, entity_id = await _link_then_disable_the_device(hass)
    kitchen_device, kitchen = _hardware_cover(
        hass, "kitchen_blind", device_name="Kitchen blind motor"
    )
    _disable_device(hass, kitchen_device)
    await hass.async_block_till_done()
    # Re-enabling the cover, even briefly, would make HA reload it 30 s later.
    flips: list[dict] = []
    hass.bus.async_listen(
        er.EVENT_ENTITY_REGISTRY_UPDATED,
        lambda event: (
            flips.append(dict(event.data))
            if "disabled_by" in event.data.get("changes", {})
            else None
        ),
    )

    await _change_options(hass, entry, cover_entity_id=kitchen)

    ours = _our_entity(hass, entry)
    assert ours.device_id == kitchen_device.id
    assert ours.disabled_by is er.RegistryEntryDisabler.DEVICE
    assert hass.states.get(entity_id) is None
    assert flips == []
    assert entity_removals == []


@pytest.mark.parametrize("change", ["off", "move"])
async def test_a_cover_the_user_disabled_stays_disabled(
    hass: HomeAssistant, entity_removals, no_warnings, change
):
    device, inner = _hardware_cover(hass, "lounge_blind")
    _, kitchen = _hardware_cover(
        hass, "kitchen_blind", device_name="Kitchen blind motor"
    )
    entry = _wrapped_entry(hass, inner)
    await _setup(hass, entry)
    entity_id = _our_entity(hass, entry).entity_id
    er.async_get(hass).async_update_entity(
        entity_id, disabled_by=er.RegistryEntryDisabler.USER
    )
    _disable_device(hass, device)
    await hass.async_block_till_done()

    if change == "off":
        await _change_options(hass, entry, link_to_device=False)
    else:
        await _change_options(hass, entry, cover_entity_id=kitchen)

    assert _our_entity(hass, entry).disabled_by is er.RegistryEntryDisabler.USER
    assert hass.states.get(entity_id) is None
    assert entity_removals == []


async def test_leftover_link_to_a_disabled_device_is_cleaned_up_and_the_cover_returns(
    hass: HomeAssistant, entity_removals, no_warnings
):
    """Our cover sits on a disabled device left over from an earlier link."""
    device, inner = _hardware_cover(hass, "lounge_blind")
    entry = _wrapped_entry(hass, inner)
    dev_reg = dr.async_get(hass)
    leftover = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("hardware", "old_blind")},
        name="Old blind motor",
    )
    _disable_device(hass, leftover)
    registered = er.async_get(hass).async_get_or_create(
        "cover",
        DOMAIN,
        "cover_timebased_uuid_" + entry.entry_id,
        suggested_object_id="lounge_timed",
        config_entry=entry,
        device_id=leftover.id,
        disabled_by=er.RegistryEntryDisabler.DEVICE,
    )

    await _setup(hass, entry)

    ours = _our_entity(hass, entry)
    assert ours.id == registered.id
    assert ours.device_id == device.id
    assert ours.disabled_by is None
    assert hass.states.get(ours.entity_id) is not None
    assert _devices_listing(hass, entry) == _expected_listing(device)
    await _pass_hass_reload_delay(hass)
    assert _our_entity(hass, entry).disabled_by is None
    assert entity_removals == []


async def test_newer_home_assistant_puts_the_device_name_in_front(
    hass: HomeAssistant,
):
    """Why the switch is opt-in, and what its help text and the README warn about."""
    _, inner = _hardware_cover(hass, "lounge_blind", device_name="Lounge blind motor")
    entry = _wrapped_entry(hass, inner, title="Lounge Timed")
    await _setup(hass, entry)
    ours = _our_entity(hass, entry)

    expected = (
        "Lounge blind motor Lounge Timed" if LINK_BY_DEVICE_ENTRY else "Lounge Timed"
    )
    assert hass.states.get(ours.entity_id).attributes["friendly_name"] == expected

    er.async_get(hass).async_update_entity(ours.entity_id, name="Lounge shade")
    await hass.async_block_till_done()
    assert hass.states.get(ours.entity_id).attributes["friendly_name"] == "Lounge shade"
