"""The known-position services through HA's service layer.

Both are target-based, so an area target must resolve to the cover.
"""

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

    assert hass.states.get(ENTITY_ID).attributes["current_position"] == 42
