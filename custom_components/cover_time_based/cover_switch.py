"""Abstract base for covers controlled via switch entities."""

from .cover_base import CoverTimeBased


class SwitchCoverTimeBased(CoverTimeBased):
    """Abstract base for covers controlled via switch entities."""

    def __init__(
        self,
        open_switch_entity_id,
        close_switch_entity_id,
        stop_switch_entity_id=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._open_switch_entity_id = open_switch_entity_id
        self._close_switch_entity_id = close_switch_entity_id
        self._stop_switch_entity_id = stop_switch_entity_id

    def _are_entities_configured(self) -> bool:
        """Return True if open and close switch entities are configured."""
        return bool(self._open_switch_entity_id and self._close_switch_entity_id)
