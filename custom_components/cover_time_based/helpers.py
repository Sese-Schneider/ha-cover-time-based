"""Shared helper functions for the cover_time_based integration."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError


def resolve_entity(hass: HomeAssistant, entity_id: str):
    """Resolve an entity_id to a CoverTimeBased entity instance.

    Returns the entity or raises HomeAssistantError.
    """
    from .cover_base import CoverTimeBased

    component = hass.data.get("entity_components", {}).get("cover")
    if component is None:
        raise HomeAssistantError("Cover platform not loaded")
    entity = component.get_entity(entity_id)
    if entity is None or not isinstance(entity, CoverTimeBased):
        raise HomeAssistantError(f"{entity_id} is not a cover_time_based entity")
    return entity


def resolve_entity_or_none(hass: HomeAssistant, entity_id: str):
    """Resolve an entity_id to a CoverTimeBased entity, or None."""
    try:
        return resolve_entity(hass, entity_id)
    except HomeAssistantError:
        return None
