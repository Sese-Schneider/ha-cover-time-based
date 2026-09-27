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
