"""Exceptions raised by time-based cover entities.

A leaf module, importing only Home Assistant, so every mixin module can import
it at load time without importing another mixin module.
"""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError


class CoverNotConfiguredError(HomeAssistantError):
    """A command refused because the cover is missing required configuration."""

    def __init__(self, missing: list[str]) -> None:
        super().__init__(
            f"Cover not configured: missing {', '.join(missing)}. "
            "Please configure using the Cover Time Based card."
        )
        self.missing = missing


class CoverBlockedByExternalSwitchError(HomeAssistantError):
    """A command refused because a wall switch holds a direction relay ON.

    Raised only with the block_while_external option, so the physical switch
    stays authoritative while it is latched.
    """

    def __init__(self, entity_id: str, service: str, switch_entity_id: str) -> None:
        super().__init__(
            f"{entity_id}: {service} refused — {switch_entity_id} is held on by "
            "a wall switch. Release the switch first."
        )
        self.entity_id = entity_id
        self.service = service
        self.switch_entity_id = switch_entity_id
