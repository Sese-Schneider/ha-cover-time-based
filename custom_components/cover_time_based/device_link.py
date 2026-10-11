"""Show a wrapped cover on the device page of the cover it wraps."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, callback, valid_entity_id
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device import (
    async_device_info_to_link_from_entity,
    async_entity_id_to_device_id,
)
from homeassistant.helpers.entity import Entity

# HA 2025.8 lets an entity name another integration's device through
# `device_entry`, leaving that device untouched. Before it the only way was a
# `device_info` carrying the device's identifiers, which also adds our config
# entry to the device. Drop the fallback once the minimum HA is 2025.8.
try:
    from homeassistant.helpers.device import async_entity_id_to_device
except ImportError:  # HA < 2025.8
    async_entity_id_to_device = None

LINK_BY_DEVICE_ENTRY = async_entity_id_to_device is not None


@callback
def async_link_to_source_device(
    hass: HomeAssistant,
    entity: Entity,
    config_entry_id: str,
    source_entity_id: str | None,
) -> None:
    """Attach `entity` to the device of `source_entity_id`, before it is added.

    No source, or a source with no device, leaves the entity on no device and
    removes any link an earlier setup made.
    """
    # HA's helpers raise on a string that is not an entity id (the exception
    # type changed in 2026.10), so screen it out rather than catch it.
    if not source_entity_id or not valid_entity_id(source_entity_id):
        source_entity_id = None
    keep_device_id = None
    if async_entity_id_to_device is not None:
        if source_entity_id:
            entity.device_entry = async_entity_id_to_device(hass, source_entity_id)
        # This method never adds our config entry to a device, so any device
        # naming it is left over from the old method.
    elif source_entity_id:
        entity._attr_device_info = async_device_info_to_link_from_entity(
            hass, source_entity_id
        )
        keep_device_id = async_entity_id_to_device_id(hass, source_entity_id)
    _remove_stale_links(hass, config_entry_id, keep_device_id)


def _remove_stale_links(
    hass: HomeAssistant, config_entry_id: str, keep_device_id: str | None
) -> None:
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    for device in list(dr.async_entries_for_config_entry(dev_reg, config_entry_id)):
        if device.id == keep_device_id:
            continue
        # HA deletes an entity whose config entry leaves the device it sits on,
        # so move ours off first; adding the entity sets the right device again.
        for entry in er.async_entries_for_device(
            ent_reg, device.id, include_disabled_entities=True
        ):
            if entry.config_entry_id == config_entry_id:
                ent_reg.async_update_entity(entry.entity_id, device_id=None)
        if hasattr(device, "config_entry_id"):
            # HA 2026.8+: a device has one owner, so a device we own is ours alone.
            dev_reg.async_remove_device(device.id)
        else:
            dev_reg.async_update_device(
                device.id, remove_config_entry_id=config_entry_id
            )
