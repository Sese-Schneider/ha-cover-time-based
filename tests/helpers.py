"""Plain helper functions shared by the cover_time_based tests."""

from unittest.mock import AsyncMock, MagicMock, patch


def stub_switches(cover, *, on=(), optimistic=()):
    """Make ``hass.states.get`` deterministic for the feedback guards.

    Without this the conftest MagicMock hass returns a truthy MagicMock for
    ``attributes.get("assumed_state")``, which would read every relay as
    optimistic. Listed entities are ON and/or optimistic; everything else is a
    plain OFF, non-optimistic switch.
    """

    def _get(entity_id):
        st = MagicMock()
        st.state = "on" if entity_id in on else "off"
        st.attributes = {"assumed_state": True} if entity_id in optimistic else {}
        return st

    cover.hass.states.get = _get


def single_button_sleep_patch(**kwargs):
    """Patch the single-button mode's ``sleep``; defaults to an AsyncMock."""
    return patch(
        "custom_components.cover_time_based.cover_single_button_mode.sleep",
        **(kwargs or {"new_callable": AsyncMock}),
    )


def relay_calls(cover, start=0) -> list[tuple[str, str]]:
    """Return service names and entity IDs in call order after the watermark."""
    return [
        (c.args[1], c.args[2].get("entity_id"))
        for c in cover.hass.services.async_call.call_args_list[start:]
    ]
