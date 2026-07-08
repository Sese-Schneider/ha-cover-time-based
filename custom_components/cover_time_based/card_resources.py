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

from homeassistant.components import frontend, persistent_notification
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
# Key under hass.data[DOMAIN] holding the registered resource's id.
_RESOURCE_ID_KEY = "card_resource_id"
# Stable id so repeated (re)registrations replace the notice rather than stack.
_REFRESH_NOTIFICATION_ID = f"{DOMAIN}_card_refresh"


def _get_lovelace_resources(hass: HomeAssistant):
    """The Lovelace resource collection, or None if unavailable (YAML mode)."""
    return getattr(hass.data.get("lovelace"), "resources", None)


def _record_resource_id(hass: HomeAssistant, resource_id: str) -> None:
    """Remember the resource's id (hass.data is empty after a restart) so a
    later full uninstall can delete it."""
    hass.data.setdefault(DOMAIN, {})[_RESOURCE_ID_KEY] = resource_id


def _notify_card_refresh(hass: HomeAssistant) -> None:
    """Tell the user to hard-refresh so the browser loads the newly added card.

    HA loads its Lovelace resource list once, at page load, and does not
    hot-inject a newly registered resource into already-open browser sessions.
    So a fresh install leaves the card missing (or showing a "custom element
    doesn't exist" error) until the page is reloaded — and, because HA's service
    worker serves the app through a cache, often only a *hard* refresh picks it
    up. Since the card is registered from Python rather than installed as a
    standalone HACS plugin, the user otherwise gets no prompt to reload at all.

    Fired only when the resource is newly created — a first install (or a
    re-create after a full uninstall / upgrade from a pre-resource version),
    all cases where open sessions lack the card. A version update instead leaves
    the card already present (running the previous code) with the new JS at a
    fresh, uncached URL, so a normal reload picks it up — nagging on every
    release would be spam.
    """
    persistent_notification.async_create(
        hass,
        (
            "The Cover Time Based dashboard card was installed. "
            "Do a hard refresh of your browser (Ctrl+Shift+R, or ⌘+Shift+R "
            "on Mac) to load it. If the card still shows a configuration error, "
            "clear your browser cache and reload."
        ),
        title="Cover Time Based card installed",
        notification_id=_REFRESH_NOTIFICATION_ID,
    )


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
    # Set only when the resource is created for the first time — the sole case
    # that warrants a refresh prompt (see _notify_card_refresh for why).
    installed = False
    try:
        resources = _get_lovelace_resources(hass)
        if resources is None or not hasattr(resources, "async_create_item"):
            frontend.add_extra_js_url(hass, card_url)
            return

        if not resources.loaded:
            await resources.async_load()
            resources.loaded = True

        stale = None
        for item in resources.async_items():
            url = item.get("url", "")
            if url == card_url:
                # Already current — record the id so a later uninstall can
                # delete it. No change, so no refresh notification.
                _record_resource_id(hass, item["id"])
                return
            if url.startswith(base_url):
                stale = item
                break

        if stale is not None:
            # Old version → cache-bust in place. The card is already present in
            # open sessions (running the old code) and the new JS is at a fresh,
            # uncached URL, so a normal reload picks it up — done silently.
            await resources.async_update_item(stale["id"], {"url": card_url})
            _record_resource_id(hass, stale["id"])
        else:
            item = await resources.async_create_item(
                {"res_type": "module", "url": card_url}
            )
            _record_resource_id(hass, item["id"])
            installed = True
    except Exception:  # pylint: disable=broad-exception-caught
        _LOGGER.debug(
            "Could not register card as a Lovelace resource; "
            "falling back to add_extra_js_url",
            exc_info=True,
        )
        frontend.add_extra_js_url(hass, card_url)
        return

    # Notify outside the try so a notification failure can't trigger the
    # fallback path and double-register the card; guard it separately so that
    # failure also can't abort integration setup.
    if installed:
        try:
            _notify_card_refresh(hass)
        except Exception:  # pylint: disable=broad-exception-caught
            _LOGGER.debug("Could not create card refresh notification", exc_info=True)


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
