"""Show a wrapped cover on the device page of the cover it wraps."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import attr
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback, valid_entity_id
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device import (
    async_device_info_to_link_from_entity,
    async_entity_id_to_device_id,
)
from homeassistant.helpers.entity import Entity

from .const import (
    CONF_CONTROL_MODE,
    CONF_COVER_ENTITY_ID,
    CONF_LINK_TO_DEVICE,
    CONTROL_MODE_WRAPPED,
    DEFAULT_LINK_TO_DEVICE,
)

# HA 2025.8 lets an entity name another integration's device through
# `device_entry`, leaving that device untouched. Before it the only way was a
# `device_info` carrying the device's identifiers, which also adds our config
# entry to the device. Drop the fallback once the minimum HA is 2025.8.
try:
    from homeassistant.helpers.device import async_entity_id_to_device
except ImportError:  # HA < 2025.8
    async_entity_id_to_device = None

LINK_BY_DEVICE_ENTRY = async_entity_id_to_device is not None
# HA 2026.8+: a device has a single owning `config_entry_id`, not a set.
ONE_OWNER_DEVICES = "config_entry_id" in attr.fields_dict(dr.DeviceEntry)


@callback
def async_link_to_source_device(
    hass: HomeAssistant, entity: Entity, config_entry: ConfigEntry
) -> None:
    """Attach `entity` to the device of the cover it wraps, before it is added.

    Only a wrapped cover with the option on is linked. Any other cover, or one
    whose wrapped cover has no device, sits on no device, and any link an
    earlier setup made is removed. It also re-enables a cover that a device it
    no longer sits on had disabled.
    """
    source_entity_id = _source_entity_id(config_entry.options)
    device_id = keep_device_id = None
    if async_entity_id_to_device is not None:
        if source_entity_id:
            entity.device_entry = async_entity_id_to_device(hass, source_entity_id)
        if entity.device_entry:
            device_id = entity.device_entry.id
    elif source_entity_id:
        entity._attr_device_info = async_device_info_to_link_from_entity(
            hass, source_entity_id
        )
        device_id = keep_device_id = async_entity_id_to_device_id(
            hass, source_entity_id
        )
    # Linking through `device_entry` never adds our config entry to a device, so
    # with it every device naming our entry is left over from the old method.
    _remove_stale_links(hass, config_entry.entry_id, keep_device_id)
    _undo_stale_device_disabling(hass, config_entry.entry_id, device_id)


def _source_entity_id(options: Mapping[str, Any]) -> str | None:
    if options.get(CONF_CONTROL_MODE) != CONTROL_MODE_WRAPPED or not options.get(
        CONF_LINK_TO_DEVICE, DEFAULT_LINK_TO_DEVICE
    ):
        return None
    source_entity_id = options.get(CONF_COVER_ENTITY_ID)
    # HA's helpers raise on a string that is not an entity id (the exception
    # type changed in 2026.10), so screen it out rather than catch it.
    if not source_entity_id or not valid_entity_id(source_entity_id):
        return None
    return source_entity_id


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
        if ONE_OWNER_DEVICES:
            dev_reg.async_remove_device(device.id)
        else:
            dev_reg.async_update_device(
                device.id, remove_config_entry_id=config_entry_id
            )


def _undo_stale_device_disabling(
    hass: HomeAssistant, config_entry_id: str, device_id: str | None
) -> None:
    """Re-enable a cover disabled by a device it no longer sits on.

    HA clears a device's disabling from its entities only when that device is
    re-enabled, so a cover moved off a disabled device would never be added.
    Disabling by the user or the integration is left alone.
    """
    device = dr.async_get(hass).async_get(device_id) if device_id else None
    if device is not None and device.disabled:
        return
    ent_reg = er.async_get(hass)
    for entry in er.async_entries_for_config_entry(ent_reg, config_entry_id):
        if entry.disabled_by is er.RegistryEntryDisabler.DEVICE:
            # HA reloads the config entry once, about 30 s later, as it does
            # whenever an entity is re-enabled.
            ent_reg.async_update_entity(entry.entity_id, disabled_by=None)
