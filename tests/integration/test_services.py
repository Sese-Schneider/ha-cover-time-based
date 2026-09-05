"""The known-position services through HA's service layer.

Both are target-based, so an area target must resolve to the cover.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import DOMAIN

ENTITY_ID = "cover.test_cover"


@pytest.fixture
async def setup_tilt_cover(hass: HomeAssistant, setup_input_booleans, base_options):
    """Load the standard switch-mode cover with tilt added."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        title="Test Cover",
        data={},
        options={
            **base_options,
            "tilt_mode": "sequential_close",
            "tilt_time_open": 2.0,
            "tilt_time_close": 2.0,
        },
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID) is not None, "Cover entity was not created"

    yield entry

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_set_known_position_by_area(hass: HomeAssistant, setup_cover):
    """An area target resolves to the cover and sets its tracked position."""
    area = ar.async_get(hass).async_get_or_create("Kitchen")
    er.async_get(hass).async_update_entity(ENTITY_ID, area_id=area.id)

    await hass.services.async_call(
        DOMAIN,
        "set_known_position",
        {"area_id": area.id, "position": 42},
        blocking=True,
    )

    assert hass.states.get(ENTITY_ID).attributes["current_position"] == 42


async def test_set_known_tilt_position_by_area(hass: HomeAssistant, setup_tilt_cover):
    """The tilt service is target-based too."""
    area = ar.async_get(hass).async_get_or_create("Kitchen")
    er.async_get(hass).async_update_entity(ENTITY_ID, area_id=area.id)

    await hass.services.async_call(
        DOMAIN,
        "set_known_tilt_position",
        {"area_id": area.id, "tilt_position": 37},
        blocking=True,
    )

    assert hass.states.get(ENTITY_ID).attributes["current_tilt_position"] == 37
