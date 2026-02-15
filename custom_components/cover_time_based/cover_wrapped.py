"""Cover that wraps an existing cover entity."""

from .cover_base import CoverTimeBased


class WrappedCoverTimeBased(CoverTimeBased):
    """A cover that delegates open/close/stop to an underlying cover entity."""

    def __init__(
        self,
        cover_entity_id,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._cover_entity_id = cover_entity_id

    async def _send_open(self) -> None:
        await self.hass.services.async_call(
            "cover", "open_cover", {"entity_id": self._cover_entity_id}, False
        )

    async def _send_close(self) -> None:
        await self.hass.services.async_call(
            "cover", "close_cover", {"entity_id": self._cover_entity_id}, False
        )

    async def _send_stop(self) -> None:
        await self.hass.services.async_call(
            "cover", "stop_cover", {"entity_id": self._cover_entity_id}, False
        )
