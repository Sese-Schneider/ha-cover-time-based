"""The known-position services through HA's service layer.

Both are target-based, so an area target must resolve to the cover, and the
percent range must be enforced before the entity method runs.
"""

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from .conftest import DOMAIN

ENTITY_ID = "cover.test_cover"


async def test_set_known_position_by_area(hass: HomeAssistant, setup_cover):
    area = ar.async_get(hass).async_get_or_create("Kitchen")
    er.async_get(hass).async_update_entity(ENTITY_ID, area_id=area.id)

    await hass.services.async_call(
        DOMAIN,
        "set_known_position",
        {"area_id": area.id, "position": 42},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).attributes["current_position"] == 42


async def test_set_known_position_above_100_rejected(hass: HomeAssistant, setup_cover):
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "set_known_position",
            {"entity_id": ENTITY_ID, "position": 150},
            blocking=True,
        )
