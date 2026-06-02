"""Lovelace card resource registration for the Cover Time Based card.

The card JS must be registered as a Lovelace *resource* rather than loaded via
``frontend.add_extra_js_url``. ``add_extra_js_url`` injects the module into the
index page's ``<script type="module">``, which runs at page load — *before* HA
lazily installs ``@webcomponents/scoped-custom-element-registry`` on first
Lovelace render. Installing that polyfill swaps ``window.customElements`` for a
fresh registry, silently dropping any element defined beforehand, so HA then
reports "custom element doesn't exist" until the user refreshes. Lovelace
resources are loaded during Lovelace init (after the swap), so the card
survives a cold load.

Falls back to ``add_extra_js_url`` when the Lovelace resource store is
unavailable (e.g. YAML-mode dashboards), where the timing issue doesn't apply.
"""

from __future__ import annotations

import logging

from homeassistant.components import frontend
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
# Key under hass.data[DOMAIN] holding the registered resource's id.
_RESOURCE_ID_KEY = "card_resource_id"


def _get_lovelace_resources(hass: HomeAssistant):
    """The Lovelace resource collection, or None if unavailable (YAML mode)."""
    return getattr(hass.data.get("lovelace"), "resources", None)


async def async_register_card_resource(
    hass: HomeAssistant,
    base_url: str,
    card_url: str,
) -> None:
    """Register the card JS as a Lovelace resource (preferred).

    ``base_url`` is the stable, hash-independent prefix used to recognise a
    resource left over from a previous version so it can be cache-busted in
    place; ``card_url`` is the current, content-hashed URL. Falls back to
    ``add_extra_js_url`` if the Lovelace resource store isn't available.
    """
    try:
        resources = _get_lovelace_resources(hass)
        if resources is not None and hasattr(resources, "async_create_item"):
            if not resources.loaded:
                await resources.async_load()
                resources.loaded = True
            for item in resources.async_items():
                url = item.get("url", "")
                if url == card_url:
                    return  # Already the current version.
                if url.startswith(base_url):
                    # Old version → cache-bust in place.
                    await resources.async_update_item(item["id"], {"url": card_url})
                    hass.data.setdefault(DOMAIN, {})[_RESOURCE_ID_KEY] = item["id"]
                    return
            item = await resources.async_create_item(
                {"res_type": "module", "url": card_url}
            )
            hass.data.setdefault(DOMAIN, {})[_RESOURCE_ID_KEY] = item["id"]
            return
    except Exception:  # pylint: disable=broad-exception-caught
        _LOGGER.debug(
            "Could not register card as a Lovelace resource; "
            "falling back to add_extra_js_url",
            exc_info=True,
        )

    frontend.add_extra_js_url(hass, card_url)


async def async_unregister_card_resource(
    hass: HomeAssistant,
    card_url: str,
) -> None:
    """Remove the card's Lovelace resource (on full uninstall).

    Mirrors :func:`async_register_card_resource`: deletes the resource by the id
    stored at registration time, or — if the card was added via the
    ``add_extra_js_url`` fallback (no stored id) — removes that instead.
    """
    resource_id = hass.data.get(DOMAIN, {}).get(_RESOURCE_ID_KEY)
    if resource_id is None:
        try:
            frontend.remove_extra_js_url(hass, card_url)
        except Exception:  # pylint: disable=broad-exception-caught
            _LOGGER.debug(
                "Could not remove card via remove_extra_js_url", exc_info=True
            )
        return

    try:
        resources = _get_lovelace_resources(hass)
        if resources is not None and hasattr(resources, "async_delete_item"):
            await resources.async_delete_item(resource_id)
            hass.data.get(DOMAIN, {}).pop(_RESOURCE_ID_KEY, None)
    except Exception:  # pylint: disable=broad-exception-caught
        _LOGGER.debug(
            "Could not remove Lovelace resource %s", resource_id, exc_info=True
        )
