"""Base class for time-based cover entities."""

import asyncio
import logging
from abc import abstractmethod
from asyncio import sleep
from contextvars import ContextVar
from datetime import timedelta

from homeassistant.components.cover import (
    ATTR_CURRENT_POSITION,
    ATTR_CURRENT_TILT_POSITION,
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.const import (
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_STOP_COVER,
    STATE_UNAVAILABLE,
)
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.restore_state import RestoreEntity
from .travel_calculator import TravelCalculator, TravelStatus

from .calibration import CalibrationState
from .cover_calibration import CalibrationMixin
from .position_storage import async_get_position_store
from .const import (
    CONF_DIRECTION_CHANGE_DELAY,
    CONF_ENDPOINT_RUNON_TIME,
    CONF_FORCE_ENDPOINT_REDRIVE,
    CONF_MIN_MOVEMENT_TIME,
    CONF_TILT_MODE,
    CONF_TILT_STARTUP_DELAY,
    CONF_TILT_TIME_CLOSE,
    CONF_TILT_TIME_OPEN,
    CONF_TRAVEL_STARTUP_DELAY,
    CONF_TRAVEL_TIME_CLOSE,
    CONF_TRAVEL_TIME_OPEN,
    DEFAULT_DIRECTION_CHANGE_DELAY,
)
from .tilt_strategies import InlineTilt, SequentialTilt
from .tilt_strategies.planning import (
    calculate_pre_step_delay,
    extract_coupled_tilt,
    extract_coupled_travel,
    has_travel_pre_step,
)

_LOGGER = logging.getLogger(__name__)

# The covers whose external-state handler is running in the current context.
# One module-level var holding a set, rather than one var per entity: context
# variables are never reclaimed, so creating them per instance would leak on
# every integration reload. See CoverTimeBased._triggered_externally.
_EXTERNAL_TRIGGER: ContextVar[frozenset] = ContextVar(
    "cover_time_based_external_trigger", default=frozenset()
)


class CoverTimeBased(CalibrationMixin, CoverEntity, RestoreEntity):
    """Time-based cover with position tracking."""

    def __init__(
        self,
        device_id,
        name,
        tilt_strategy,
        travel_time_close,
        travel_time_open,
        tilt_time_close,
        tilt_time_open,
        travel_startup_delay,
        tilt_startup_delay,
        endpoint_runon_time,
        min_movement_time,
        direction_change_delay=None,
        tilt_open_switch=None,
        tilt_close_switch=None,
        tilt_stop_switch=None,
        tilt_mode_str="none",
        close_includes_tilt=True,
        assumed_state=True,
        force_endpoint_redrive=False,
    ):
        """Initialize the cover."""
        self._unique_id = device_id
        self._assumed_state = assumed_state
        self._force_endpoint_redrive = force_endpoint_redrive

        self._tilt_strategy = tilt_strategy
        # Keep the raw configured mode so calibration can still pick the right
        # relay before tilt times are set (when _tilt_strategy is None).
        self._tilt_mode_str = tilt_mode_str
        self._travel_time_close = travel_time_close
        self._travel_time_open = travel_time_open
        self._tilting_time_close = tilt_time_close
        self._tilting_time_open = tilt_time_open
        self._travel_startup_delay = travel_startup_delay
        self._tilt_startup_delay = tilt_startup_delay
        self._endpoint_runon_time = endpoint_runon_time
        self._min_movement_time = min_movement_time
        # Resolved here, not just at the config boundary. An explicit None does
        # reach this constructor: the YAML `defaults:` block accepts it
        # (DEFAULTS_SCHEMA allows `vol.Any(cv.positive_float, None)`) and
        # `_get_value` returns that None verbatim, which `options.get(key,
        # default)` then hands straight through — `.get` only substitutes the
        # default for a *missing* key, not a present-but-None one. Without this
        # sleep(None) would raise on every reversal for those users. (The card
        # cannot produce it: ws_update_config pops the key on null.) Kept
        # non-None so the reversal path can sleep it directly, and compared
        # against None rather than falsiness because 0 is a legitimate
        # "no settle gap".
        self._direction_change_delay_time = (
            DEFAULT_DIRECTION_CHANGE_DELAY
            if direction_change_delay is None
            else direction_change_delay
        )
        self._tilt_open_switch_id = tilt_open_switch
        self._tilt_close_switch_id = tilt_close_switch
        self._tilt_stop_switch_id = tilt_stop_switch
        self._close_includes_tilt = close_includes_tilt

        if name:
            self._name = name
        else:
            self._name = device_id

        self._config_entry_id: str | None = None
        self._calibration: CalibrationState | None = None
        self._unsubscribe_auto_updater = None
        self._delay_task = None
        self._startup_delay_task = None
        self._last_command = None
        # Claimed by every command that supersedes an in-flight movement; read
        # across the settle gap by _settle_before_reversing.
        self._movement_epoch = 0
        # Drives the post-travel tilt phase via _start_tilt_restore (consumed
        # by the auto-updater when travel reaches endpoint). Set by:
        #   - _plan_tilt_for_travel (mid-position moves: restore prior tilt;
        #     dual-motor endpoint moves: snap tilt to endpoint).
        #   - _start_tilt_pre_step (after pre-step + travel completes).
        #   - async_close_cover when close_includes_tilt is on and the tilt
        #     strategy doesn't already drive tilt to 0 during close travel
        #     (sequential_close, dual_motor — not inline or sequential_open).
        self._tilt_restore_target: int | None = None
        self._tilt_restore_active: bool = False
        # Identity for the active restore, bumped on every claim. The bool says
        # only that *a* restore is live, which a restore resuming from an await
        # cannot distinguish from its own — see _tilt_restore_superseded.
        self._tilt_restore_epoch: int = 0
        self._pending_travel_target: int | None = None
        self._pending_travel_command: str | None = None
        self._pending_tilt_target: int | None = None
        self._pending_tilt_command: str | None = None
        self._self_initiated_movement = True
        # True while the active movement drives a dedicated tilt motor (dual
        # motor), so auto-stop settles the tilt motor instead of travel.
        self._moving_tilt_motor = False
        # True while the active movement is a tilt move (any tilt mode). The
        # endpoint run-on is a *travel* concept — it keeps a latched relay
        # energized so the shutter seats against its physical limit. A tilt
        # move that finishes while the cover is parked at a travel endpoint is
        # not at a limit, so it must not run on (issue #125).
        self._moving_tilt = False
        self._state = True
        self._pending_switch = {}
        self._pending_switch_timers = {}
        self._state_listener_unsubs = []

        self.travel_calc = TravelCalculator(
            self._travel_time_close,
            self._travel_time_open,
        )
        if self._tilting_time_close is not None and self._tilting_time_open is not None:
            self.tilt_calc = TravelCalculator(
                self._tilting_time_close,
                self._tilting_time_open,
            )

    def _log(self, msg, *args):
        """Log a debug message prefixed with the entity ID."""
        _LOGGER.debug("(%s) " + msg, self.entity_id, *args)

    async def _async_load_restored_positions(self) -> tuple[int | None, int | None]:
        """Return (position, tilt_position) for restore.

        PositionStore is authoritative; RestoreEntity state is only used
        when the Store has no record for this entry (pre-Store installs
        or fresh entries).
        """
        if self._config_entry_id is not None:
            store = await async_get_position_store(self.hass)
            stored = await store.async_get(self._config_entry_id)
            if stored is not None:
                return stored.get("position"), stored.get("tilt_position")

        old_state = await self.async_get_last_state()
        self._log("async_added_to_hass :: oldState %s", old_state)
        if old_state is None:
            return None, None
        return (
            old_state.attributes.get(ATTR_CURRENT_POSITION),
            old_state.attributes.get(ATTR_CURRENT_TILT_POSITION),
        )

    async def _async_persist_position(self) -> None:
        """Write the current travel/tilt position to the position store."""
        if self._config_entry_id is None:
            return
        data: dict[str, int] = {}
        position = self.travel_calc.current_position()
        if position is not None:
            data["position"] = int(position)
        if self._has_tilt_support():
            tilt_position = self.tilt_calc.current_position()
            if tilt_position is not None:
                data["tilt_position"] = int(tilt_position)
        store = await async_get_position_store(self.hass)
        await store.async_save(self._config_entry_id, data)

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    # Single source of truth for the switch-target attribute names. Used both
    # to register state-change listeners and to enumerate configured targets.
    _SWITCH_TARGET_ATTRS = (
        "_open_switch_entity_id",
        "_close_switch_entity_id",
        "_stop_switch_entity_id",
        "_tilt_open_switch_id",
        "_tilt_close_switch_id",
        "_tilt_stop_switch_id",
    )

    async def async_added_to_hass(self):
        """Only cover's position and tilt matters."""
        pos, tilt_pos = await self._async_load_restored_positions()
        if self.travel_calc is not None and pos is not None:
            self.travel_calc.set_position(int(pos))
            if self._has_tilt_support() and tilt_pos is not None:
                self.tilt_calc.set_position(int(tilt_pos))

        # Register state change listeners for switch entities
        for attr in self._SWITCH_TARGET_ATTRS:
            entity_id = getattr(self, attr, None)
            if entity_id:
                self._state_listener_unsubs.append(
                    async_track_state_change_event(
                        self.hass,
                        [entity_id],
                        self._async_switch_state_changed,
                    )
                )

    async def async_will_remove_from_hass(self):
        """Clean up when entity is removed."""
        self.stop_auto_updater()
        for unsub in self._state_listener_unsubs:
            unsub()
        self._state_listener_unsubs.clear()
        for timer in self._pending_switch_timers.values():
            timer()
        self._pending_switch_timers.clear()
        if self._calibration is not None:
            if (
                self._calibration.timeout_task
                and not self._calibration.timeout_task.done()
            ):
                self._calibration.timeout_task.cancel()
            if (
                self._calibration.automation_task
                and not self._calibration.automation_task.done()
            ):
                self._calibration.automation_task.cancel()
            self._calibration = None

    # -----------------------------------------------------------------------
    # Properties
    # -----------------------------------------------------------------------

    @property
    def name(self):
        """Return the name of the cover."""
        return self._name

    @property
    def unique_id(self):
        """Return the unique id."""
        return "cover_timebased_uuid_" + self._unique_id

    @property
    def device_class(self):
        """Return the device class of the cover."""
        return None

    @property
    def available(self) -> bool:
        """Return True if the cover is configured and its targets are available."""
        return (
            not self._get_missing_configuration() and not self._any_target_unavailable()
        )

    @property
    def assumed_state(self):
        """Return whether Home Assistant should treat the position as assumed.

        Defaults to True because a time-based cover's position is calculated
        from travel time with no feedback. Users who trust the calculation can
        set this False so the UI greys out unavailable actions (e.g. close when
        already closed).
        """
        return self._assumed_state

    @property
    def supported_features(self) -> CoverEntityFeature:
        """Flag supported features."""
        supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
            | CoverEntityFeature.SET_POSITION
        )

        if self._has_tilt_support():
            supported_features |= (
                CoverEntityFeature.OPEN_TILT
                | CoverEntityFeature.CLOSE_TILT
                | CoverEntityFeature.STOP_TILT
                | CoverEntityFeature.SET_TILT_POSITION
            )

        return supported_features

    @property
    def current_cover_position(self) -> int | None:
        """Return the current position of the cover."""
        return self.travel_calc.current_position()

    @property
    def current_cover_tilt_position(self) -> int | None:
        """Return the current tilt of the cover."""
        if self._has_tilt_support():
            return self.tilt_calc.current_position()
        return None

    @property
    def is_opening(self):
        """Return if the cover is opening or not."""
        return (
            self.travel_calc.is_traveling()
            and self.travel_calc.travel_direction == TravelStatus.DIRECTION_UP
        ) or (
            self._has_tilt_support()
            and self.tilt_calc.is_traveling()
            and self.tilt_calc.travel_direction == TravelStatus.DIRECTION_UP
        )

    @property
    def is_closing(self):
        """Return if the cover is closing or not."""
        return (
            self.travel_calc.is_traveling()
            and self.travel_calc.travel_direction == TravelStatus.DIRECTION_DOWN
        ) or (
            self._has_tilt_support()
            and self.tilt_calc.is_traveling()
            and self.tilt_calc.travel_direction == TravelStatus.DIRECTION_DOWN
        )

    def _travel_axis_opening(self) -> bool:
        """Whether the *travel* axis is opening, for reversal decisions.

        On dual_motor a dedicated tilt motor moves independently of travel, so
        a moving tilt motor must not read as the cover opening (that would make
        a travel command stop-and-settle the running tilt motor). A travel
        operation still counts while its tilt-to-safe pre-step runs — travel is
        pending though ``travel_calc`` hasn't started — so the pending travel
        command's direction is honoured (the queued travel direction, not the
        tilt pre-step's own motion, which may be the opposite way). Shared-motor
        tilt (inline/sequential) has no separate motor — its tilt phase IS the
        travel motor running — so the cover-level property is retained there to
        keep settle-before-reverse.
        """
        if not self._has_tilt_motor():
            return self.is_opening
        if self.travel_calc.is_opening():
            return True
        if self._pending_travel_target is not None:
            return self._pending_travel_command == SERVICE_OPEN_COVER
        return False

    def _travel_axis_closing(self) -> bool:
        """Travel-axis counterpart of :meth:`_travel_axis_opening`."""
        if not self._has_tilt_motor():
            return self.is_closing
        if self.travel_calc.is_closing():
            return True
        if self._pending_travel_target is not None:
            return self._pending_travel_command == SERVICE_CLOSE_COVER
        return False

    @property
    def is_closed(self):
        """Return if the cover is closed.

        Tracks travel position only — tilt is reported independently via
        current_cover_tilt_position. This matches HA's general cover
        semantics and is what drives the built-in toggle action.
        """
        return self.travel_calc.is_closed()

    @property
    def extra_state_attributes(self):
        """Return the device state attributes."""
        attr = {}
        if self._tilt_strategy is not None:
            attr[CONF_TILT_MODE] = self._tilt_strategy.name
        if self._travel_time_close is not None:
            attr[CONF_TRAVEL_TIME_CLOSE] = self._travel_time_close
        if self._travel_time_open is not None:
            attr[CONF_TRAVEL_TIME_OPEN] = self._travel_time_open
        if self._tilting_time_close is not None:
            attr[CONF_TILT_TIME_CLOSE] = self._tilting_time_close
        if self._tilting_time_open is not None:
            attr[CONF_TILT_TIME_OPEN] = self._tilting_time_open
        if self._travel_startup_delay is not None:
            attr[CONF_TRAVEL_STARTUP_DELAY] = self._travel_startup_delay
        if self._tilt_startup_delay is not None:
            attr[CONF_TILT_STARTUP_DELAY] = self._tilt_startup_delay
        if self._endpoint_runon_time is not None:
            attr[CONF_ENDPOINT_RUNON_TIME] = self._endpoint_runon_time
        if self._min_movement_time is not None:
            attr[CONF_MIN_MOVEMENT_TIME] = self._min_movement_time
        attr[CONF_FORCE_ENDPOINT_REDRIVE] = self._force_endpoint_redrive
        attr[CONF_DIRECTION_CHANGE_DELAY] = self._direction_change_delay_time
        if self._calibration is not None:
            attr["calibration_active"] = True
            attr["calibration_attribute"] = self._calibration.attribute
            if self._calibration.final_step:
                attr["calibration_final_step"] = True
            elif self._calibration.step_count > 0:
                attr["calibration_step"] = self._calibration.step_count
        return attr

    # -----------------------------------------------------------------------
    # Public HA service handlers
    # -----------------------------------------------------------------------

    async def async_close_cover(self, **kwargs):
        """Close the cover fully.

        Travel is moved to 0 unless already settled there (no resync motor
        pulse — matches HA convention that close_cover re-applied is a no-op).

        When close_includes_tilt is True and the cover has tilt support and
        tilt is not already at 0, the slats are closed afterward. This makes
        close_cover land at (0, 0) on strategies that would otherwise park
        tilt at an implicit-open or safe position (sequential_close, dual_motor).
        """
        self._require_configured()
        self._log("async_close_cover")
        if not self._triggered_externally and (
            self._travel_axis_opening() or self._travel_axis_closing()
        ):
            # In-motion UI click stops the cover. Reversing direction requires
            # a second click after the stop, or use set_cover_position which
            # keeps its existing stop-then-reverse behavior. External triggers
            # (wall switches) keep the legacy "stop and reverse if needed"
            # behavior to honor the physical user intent. Decisions key off the
            # travel axis so a moving independent tilt motor (dual_motor) isn't
            # stopped by a travel command.
            self._log("async_close_cover :: cover is in motion, stopping")
            await self.async_stop_cover()
            return
        if self._triggered_externally and self._travel_axis_opening():
            # External trigger: stop the opposite-direction motion, settle,
            # then proceed with close (legacy reverse behavior).
            self._log("async_close_cover :: external close while opening, reversing")
            # This stop is the reversal's own prelude, not a command to halt —
            # superseding here would cancel the movement it is starting.
            await self.async_stop_cover(supersede=False)
            if not await self._settle_before_reversing():
                return

        # Skip the re-drive when already settled at 0 (HA convention: a
        # re-applied close is a no-op). _settled_at_endpoint keeps the
        # carve-outs that must still reach _async_move_to_endpoint — a pending
        # opposite-direction startup delay to cancel, or an external sequential
        # close that articulates the slats.
        settled = self._settled_at_endpoint(0)
        force_redrive = settled and self._force_endpoint_redrive
        if force_redrive:
            # issue #167: don't trust "already closed" — re-drive the full close
            # so a remote-opened, no-feedback cover actually closes.
            await self._force_full_redrive(target=0)
        elif not settled:
            await self._async_move_to_endpoint(target=0)
        # Travel was skipped only when settled at 0 without a forced re-drive.
        skip_travel = settled and not force_redrive

        # Skip inline: its close already drives tilt to 0 via a TiltTo pre-step,
        # so the trailing restore would be a no-op AND would short-circuit the
        # endpoint_runon_time block in auto_stop_if_necessary.
        if (
            self._close_includes_tilt
            and self._has_tilt_support()
            and not isinstance(self._tilt_strategy, InlineTilt)
            and self.tilt_calc.current_position() not in (None, 0)
        ):
            if skip_travel:
                # Already settled at travel=0. The auto-updater isn't running
                # to consume _tilt_restore_target, so drive tilt directly.
                self._log(
                    "async_close_cover :: travel already at 0, closing tilt directly"
                )
                await self._async_move_tilt_to_endpoint(target=0)
            elif self._tilt_restore_target is None:
                # Travel is in flight via the auto-updater. Set the restore
                # target so the auto-updater chains _start_tilt_restore after
                # travel completes. This avoids _abandon_active_lifecycle
                # cancelling the in-flight travel.
                #
                # Guarded on `is None` so we don't overwrite a value that
                # _plan_tilt_for_travel may already have set (e.g. dual_motor
                # pre-step path sets _tilt_restore_target = target).
                self._log("async_close_cover :: scheduling tilt-close after travel")
                self._tilt_restore_target = 0

    async def async_open_cover(self, **kwargs):
        """Open the cover fully.

        In-motion UI click stops the cover. Reversing direction requires a
        second click, or use set_cover_position which keeps its existing
        stop-then-reverse behavior. External triggers (wall switches) keep
        the legacy "stop and reverse if needed" behavior.
        """
        self._require_configured()
        self._log("async_open_cover")
        if not self._triggered_externally and (
            self._travel_axis_opening() or self._travel_axis_closing()
        ):
            self._log("async_open_cover :: cover is in motion, stopping")
            await self.async_stop_cover()
            return
        if self._triggered_externally and self._travel_axis_closing():
            self._log("async_open_cover :: external open while closing, reversing")
            # Reversal prelude, not a halt command — see async_close_cover.
            await self.async_stop_cover(supersede=False)
            if not await self._settle_before_reversing():
                return
        # Mirror async_close_cover's skip-at-0 for covers that treat an endpoint
        # re-command as a pointless re-energize rather than a resync (command-
        # echo wrapped, issue #152). Relay modes keep the resync re-drive.
        settled_open = self._settled_at_endpoint(100)
        if settled_open and self._force_endpoint_redrive:
            # issue #167: don't trust "already open" — re-drive the full open,
            # overriding both the command-echo skip and the short resync.
            await self._force_full_redrive(target=100)
            return
        if self._skip_open_resync_at_endpoint() and settled_open:
            self._log("async_open_cover :: already settled at 100, skipping resync")
            return
        await self._async_move_to_endpoint(target=100)

    def _settled_at_endpoint(self, endpoint: int) -> bool:
        """Return True when the tracker is stopped exactly at ``endpoint`` (0 or
        100) and a re-drive there would be a pure resync — nothing to cancel or
        articulate.

        Excludes two cases that must still reach ``_async_move_to_endpoint``: a
        pending opposite-direction startup delay (which that method cancels),
        and an external close on sequential-tilt hardware (which drives past 0
        to articulate the slats). The sequential carve-out is an endpoint-0
        concern only — the drive-past redirect in ``_async_move_to_endpoint`` is
        gated on ``target == 0`` — so it is not applied at 100, where it would
        needlessly defeat the open-at-100 no-op.
        """
        opposite = SERVICE_OPEN_COVER if endpoint == 0 else SERVICE_CLOSE_COVER
        pending_opposite_startup = (
            self._startup_delay_task is not None
            and not self._startup_delay_task.done()
            and self._last_command == opposite
        )
        external_sequential = (
            endpoint == 0
            and self._triggered_externally
            and isinstance(self._tilt_strategy, SequentialTilt)
        )
        return (
            not (pending_opposite_startup or external_sequential)
            and self.travel_calc.current_position() == endpoint
            and self.travel_calc.travel_direction == TravelStatus.STOPPED
        )

    def _skip_open_resync_at_endpoint(self) -> bool:
        """Whether ``open_cover`` at the open endpoint (100%) is a no-op rather
        than a resync re-drive.

        Relay-driven modes return False: re-driving to the endpoint physically
        resyncs a drifted cover, and the pulse (#129) and toggle (#105) resync
        paths depend on it. A command-echo wrapped cover overrides this to True
        — it has no feedback to resync and drives an endstop-less motor, so
        re-commanding open there only re-energizes (and stalls) it (issue #152).
        ``async_close_cover`` already treats 0% as a universal no-op; this
        brings open into line for the covers that need it.
        """
        return False

    async def _force_full_redrive(self, target: int) -> None:
        """Re-drive fully to ``target`` (0 or 100) even though the tracker
        believes it is already settled there (issue #167).

        For a cover with no position feedback that an external remote may have
        moved, the believed endpoint is untrustworthy. Model the start as the
        opposite endpoint so the normal endpoint move runs the motor for the
        full travel time (and each mode's tilt phases) instead of skipping or
        firing only a short resync pulse.

        Correctness relies on callers only invoking this from a settled
        endpoint: _settled_at_endpoint already excludes the states where
        _async_move_to_endpoint would early-return without starting travel (a
        pending opposite-direction startup delay, an external sequential close),
        so seeding the opposite endpoint always reaches the full-travel branch.
        Keep that exclusion in sync if those guards ever change.
        """
        opposite = 100 if target == 0 else 0
        self._log(
            "_force_full_redrive :: target=%d modeled from opposite=%d",
            target,
            opposite,
        )
        self.travel_calc.set_position(opposite)
        await self._async_move_to_endpoint(target=target)

    async def _direction_change_delay(self):
        """Pause between stop and direction change to let the motor settle.

        Configurable per cover — see DEFAULT_DIRECTION_CHANGE_DELAY in const.py
        for why a fixed gap is not good enough.
        """
        await sleep(self._direction_change_delay_time)

    @property
    def _triggered_externally(self) -> bool:
        """Whether *this* call is handling something the hardware did.

        Set by the external-state dispatcher around its handler, and read all
        over to suppress relay writes (never echo a command back at hardware
        that is already doing it) and to pick external-trigger behaviour.

        Task-scoped, not instance-scoped. An external handler holds this across
        every await it makes — including a reversal's whole settle gap — so as
        plain instance state it leaked onto anything that ran meanwhile. A UI
        stop landing in that window inherited the suppression and sent no relay
        command at all, halting the tracker while the motor ran on. HA
        dispatches each service call as its own task, and a task gets a copy of
        the context at creation, so scoping it here means the dispatcher's
        handler still sees it across its awaits while a concurrent caller
        correctly does not.
        """
        return self in _EXTERNAL_TRIGGER.get()

    @_triggered_externally.setter
    def _triggered_externally(self, value: bool) -> None:
        current = _EXTERNAL_TRIGGER.get()
        _EXTERNAL_TRIGGER.set(current | {self} if value else current - {self})

    def _supersede_movement(self) -> None:
        """Claim the movement, cancelling any reversal waiting out its settle."""
        self._movement_epoch += 1

    def _claim_tilt_restore(self) -> int:
        """Mark a tilt restore active and return its identity."""
        self._tilt_restore_active = True
        self._tilt_restore_epoch += 1
        return self._tilt_restore_epoch

    def _release_tilt_restore(self) -> None:
        """Mark no restore active, cancelling any still parked on an await.

        Deliberately leaves the epoch alone: releasing does not hand identity
        to anyone, and the next claim bumps it anyway. That is why
        _tilt_restore_superseded has to test the flag as well as the epoch.
        """
        self._tilt_restore_active = False

    def _clear_multiphase_tilt_state(self) -> None:
        """Drop every in-flight tilt phase — restore and pre-step alike."""
        self._tilt_restore_target = None
        self._release_tilt_restore()
        self._pending_travel_target = None
        self._pending_travel_command = None
        self._pending_tilt_target = None
        self._pending_tilt_command = None

    def _tilt_restore_superseded(self, epoch: int) -> bool:
        """Whether the restore holding ``epoch`` has been cancelled or replaced.

        The active flag alone answers "is a restore live", not "is mine". A
        restore cancelled while parked on an await, then replaced by a newer one
        before it resumed, read its own True back and carried on — driving the
        motor a second time and retargeting the tilt tracker at the goal it had
        already been told to abandon.
        """
        return not self._tilt_restore_active or epoch != self._tilt_restore_epoch

    async def _settle_before_reversing(self) -> bool:
        """Await the settle gap; False if this movement was superseded.

        A reversal stops the motor, waits for it to come to rest, then drives
        the other way — but the caller is a plain service-call coroutine, not a
        task anything can cancel. Without this check a stop (or a newer target)
        arriving inside the gap is overridden the moment the reversal resumes,
        moving the cover after the user stopped it up to
        direction_change_delay seconds later — a window that widens with the
        gap, which slow motors are meant to widen.
        """
        epoch = self._movement_epoch
        await self._direction_change_delay()
        if epoch != self._movement_epoch:
            self._log("_settle_before_reversing :: superseded during settle, aborting")
            return False
        return True

    async def async_stop_cover(self, *, supersede: bool = True, **kwargs):
        """Turn the device stop.

        ``supersede`` defaults True so a stop arriving from HA (service call,
        UI, automation) always claims the movement; the internal and
        external-trigger callers that are echoes or reversal preludes pass
        False. See _handle_stop.
        """
        self._require_configured()
        self._log("async_stop_cover")
        tilt_restore_was_active = self._tilt_restore_active
        tilt_pre_step_was_active = (
            self._pending_travel_target is not None
            or self._pending_tilt_target is not None
        )
        self._cancel_startup_delay_task()
        self._cancel_delay_task()
        self._handle_stop(supersede=supersede)
        if self._has_tilt_support():
            self._tilt_strategy.snap_trackers_to_physical(
                self.travel_calc, self.tilt_calc
            )
        if not self._triggered_externally:
            await self._send_stop()
            if (
                tilt_restore_was_active or tilt_pre_step_was_active
            ) and self._has_tilt_motor():
                await self._send_tilt_stop()
        self.async_write_ha_state()
        self._last_command = None
        await self._async_persist_position()

    async def async_close_cover_tilt(self, **kwargs):
        """Tilt the cover fully closed."""
        self._log("async_close_cover_tilt")
        await self._async_move_tilt_to_endpoint(target=0)

    async def async_open_cover_tilt(self, **kwargs):
        """Tilt the cover fully open."""
        self._log("async_open_cover_tilt")
        await self._async_move_tilt_to_endpoint(target=100)

    async def async_set_cover_position(self, **kwargs):
        """Move the cover to a specific position."""
        self._require_configured()
        if ATTR_POSITION in kwargs:
            position = kwargs[ATTR_POSITION]
            self._log("async_set_cover_position: %d", position)
            await self.set_position(position)

    async def async_set_cover_tilt_position(self, **kwargs):
        """Move the cover tilt to a specific position."""
        if ATTR_TILT_POSITION in kwargs:
            position = kwargs[ATTR_TILT_POSITION]
            self._log("async_set_cover_tilt_position: %d", position)
            await self.set_tilt_position(position)

    async def set_known_position(self, *, supersede: bool = True, **kwargs):
        """Set the cover to a known position (0=closed, 100=open).

        Exposed as a service (a user resyncing the tracker is a real command,
        hence the default) and used internally by wrapped covers to snap to a
        position the device just reported, which is not — see _handle_stop.
        """
        position = kwargs[ATTR_POSITION]
        self._handle_stop(supersede=supersede)
        self.travel_calc.set_position(position)
        if self._has_tilt_support():
            self._tilt_strategy.snap_trackers_to_physical(
                self.travel_calc, self.tilt_calc
            )
        self.async_write_ha_state()
        await self._async_persist_position()

    async def set_known_tilt_position(self, **kwargs):
        """Set the tilt to a known position (0=closed, 100=open)."""
        if not self._has_tilt_support():
            return
        position = kwargs[ATTR_TILT_POSITION]
        self.tilt_calc.set_position(position)
        self.async_write_ha_state()
        await self._async_persist_position()

    # -----------------------------------------------------------------------
    # Movement orchestration
    # -----------------------------------------------------------------------

    async def _async_move_to_endpoint(self, target):
        """Move cover to an endpoint (0=fully closed, 100=fully open)."""
        self._self_initiated_movement = not self._triggered_externally

        # External close on sequential hardware runs the full journey:
        # the motor drives all the way past cover-closed to the articulated
        # extreme (tilt=100 on sequential_open, tilt=0 on sequential_close).
        # Redirect to set_tilt_position so tracking plans both phases as
        # [TravelTo(0), TiltTo(articulated)].
        #
        # Open externally is already handled correctly by the default plan
        # (plan_move_position restores tilt to implicit before travel when
        # starting from the articulated state).
        if (
            target == 0
            and self._triggered_externally
            and isinstance(self._tilt_strategy, SequentialTilt)
        ):
            articulated = 100 - self._tilt_strategy.implicit_tilt_during_travel
            self._log(
                "_async_move_to_endpoint :: external close on sequential → "
                "set_tilt_position(%d) for full-journey tracking",
                articulated,
            )
            await self.set_tilt_position(articulated)
            return

        await self._abandon_active_lifecycle()

        closing = target == 0
        command = SERVICE_CLOSE_COVER if closing else SERVICE_OPEN_COVER
        opposite_command = SERVICE_OPEN_COVER if closing else SERVICE_CLOSE_COVER

        # Check startup delay conflicts BEFORE position check, since during
        # startup delay the position hasn't started changing yet.
        if self._startup_delay_task and not self._startup_delay_task.done():
            if self._last_command == opposite_command:
                self._log(
                    "_async_move_to_endpoint :: direction change, cancelling startup delay"
                )
                self._cancel_startup_delay_task()
                await self._async_handle_command(SERVICE_STOP_COVER)
                self._last_command = None
                return
            else:
                self._log(
                    "_async_move_to_endpoint :: startup delay already active, not restarting"
                )
                return

        current = self.travel_calc.current_position()
        if current is not None and current == target:
            # Resync: send command + endpoint run-on even though tracker
            # says we're already there. Physical cover may need resyncing.
            self._cancel_delay_task()
            self._last_command = command
            await self._async_handle_command(command)
            if self._self_stops_at_endpoints() and self._at_endpoint(target):
                # The re-drive above resyncs the cover physically; the motor
                # self-stops at its limit. A stop here is redundant (and for
                # toggle re-pulses → restart), so skip it and any run-on.
                self._log(
                    "_async_move_to_endpoint :: motor self-stops at endpoint,"
                    " no relay stop"
                )
            elif (
                self._endpoint_runon_time is not None and self._endpoint_runon_time > 0
            ):
                self._delay_task = self.hass.async_create_task(
                    self._delayed_stop(self._endpoint_runon_time)
                )
            else:
                await self._async_handle_command(SERVICE_STOP_COVER)
            return

        relay_was_on = self._cancel_delay_task()
        if relay_was_on:
            await self._async_handle_command(SERVICE_STOP_COVER)

        if current is None:
            # Position unknown — assume opposite endpoint so full travel occurs
            current = 100 if closing else 0
            self.travel_calc.update_position(current)

        travel_distance = abs(target - current)
        travel_time = self._require_travel_time(closing)
        movement_time = (travel_distance / 100.0) * travel_time

        self._log(
            "_async_move_to_endpoint :: target=%d, travel_distance=%f%%, movement_time=%fs",
            target,
            travel_distance,
            movement_time,
        )

        self._last_command = command

        tilt_target = None
        pre_step_delay = 0.0
        # Plan tilt for every trigger including external. Even when the cover
        # motor is externally controlled, the hardware itself is expected to
        # move tilt to safe before travel (interlock behavior); tracking the
        # pre-step keeps the integration's tilt_calc in sync with reality
        # without needing snap_trackers_to_physical to "correct" the tracker
        # at stop time. _start_tilt_pre_step and _start_pending_travel already
        # skip relay firing when _triggered_externally is True, so the
        # integration only mirrors the physical motion in its calculators.
        current_tilt = (
            self.tilt_calc.current_position() if self._tilt_strategy else None
        )
        self._require_movement_target_available(self._movement_target(closing))
        tilt_target, pre_step_delay, started = await self._plan_tilt_for_travel(
            target, command, current, current_tilt
        )
        if started:
            return

        await self._async_handle_command(command)
        coupled_calc = self.tilt_calc if tilt_target is not None else None
        self._begin_movement(
            target,
            tilt_target,
            self.travel_calc,
            coupled_calc,
            self._travel_startup_delay,
            pre_step_delay,
        )

    async def _async_move_tilt_to_endpoint(self, target):
        """Move tilt to an endpoint (0=fully closed, 100=fully open)."""
        self._self_initiated_movement = not self._triggered_externally
        await self._abandon_active_lifecycle()

        closing = target == 0
        if self._tilt_strategy is not None:
            command = self._tilt_strategy.tilt_command_for(closing)
            opposite_command = self._tilt_strategy.tilt_command_for(not closing)
        else:
            command = SERVICE_CLOSE_COVER if closing else SERVICE_OPEN_COVER
            opposite_command = SERVICE_OPEN_COVER if closing else SERVICE_CLOSE_COVER

        if self._startup_delay_task and not self._startup_delay_task.done():
            if self._last_command == opposite_command:
                self._log(
                    "_async_move_tilt_to_endpoint :: direction change, cancelling startup delay"
                )
                self._cancel_startup_delay_task()
                await self._async_handle_command(SERVICE_STOP_COVER)
                if (
                    self._tilt_strategy is not None
                    and self._tilt_strategy.uses_tilt_motor
                ):
                    await self._send_tilt_stop()
            else:
                self._log(
                    "_async_move_tilt_to_endpoint :: startup delay already active, not restarting"
                )
                return

        relay_was_on = self._cancel_delay_task()
        if relay_was_on:
            await self._async_handle_command(SERVICE_STOP_COVER)
            if self._tilt_strategy is not None and self._tilt_strategy.uses_tilt_motor:
                await self._send_tilt_stop()

        self._stop_travel_if_traveling()

        current_tilt = self.tilt_calc.current_position()
        if current_tilt is not None and current_tilt == target:
            return

        if current_tilt is None:
            current_tilt = 100 if closing else 0
            self.tilt_calc.update_position(current_tilt)

        tilt_distance = abs(target - current_tilt)
        tilt_time = self._tilting_time_close if closing else self._tilting_time_open
        movement_time = (tilt_distance / 100.0) * tilt_time

        travel_target = None
        pre_step_delay = 0.0
        needs_travel_pre_step = False
        if self._tilt_strategy is not None:
            current_pos = self.travel_calc.current_position()
            if current_pos is not None:
                steps = self._tilt_strategy.plan_move_tilt(
                    target, current_pos, current_tilt
                )
                travel_target = extract_coupled_travel(steps)
                pre_step_delay = calculate_pre_step_delay(
                    steps, self._tilt_strategy, self.tilt_calc, self.travel_calc
                )
                if self._tilt_strategy.uses_tilt_motor and has_travel_pre_step(steps):
                    needs_travel_pre_step = True

        self._log(
            "_async_move_tilt_to_endpoint :: target=%d, tilt_distance=%f%%,"
            " movement_time=%fs, travel_pos=%s, travel_pre_step=%s",
            target,
            tilt_distance,
            movement_time,
            travel_target if travel_target is not None else "N/A",
            needs_travel_pre_step,
        )

        self._require_movement_target_available(self._tilt_movement_target(command))
        # The travel pre-step below isn't covered by the tilt gate above — see
        # _require_movement_target_available.
        if needs_travel_pre_step and travel_target is not None:
            await self._start_travel_pre_step(travel_target, target, command)
            return

        self._last_command = command
        # Committed past the no-op return above — mark this as a tilt move so it
        # doesn't run on at a travel endpoint (#125); see set_tilt_position.
        self._moving_tilt = True
        if self._tilt_strategy is not None and self._tilt_strategy.uses_tilt_motor:
            self._moving_tilt_motor = True
            # Externally triggered moves only track — the relay is already
            # driven from outside HA, and re-firing it here would turn the
            # opposite relay off a second time (the observe-path interlock in
            # _handle_external_tilt_state_change already did), double-marking
            # its pending echo and swallowing the user's next press. Mirrors
            # the _async_handle_command guard the non-tilt-motor branch uses.
            if not self._triggered_externally:
                if closing:
                    await self._send_tilt_close()
                else:
                    await self._send_tilt_open()
        else:
            await self._async_handle_command(command)
        self._begin_movement(
            target,
            travel_target,
            self.tilt_calc,
            self.travel_calc,
            self._tilt_startup_delay,
            pre_step_delay,
        )

    async def set_position(self, position):
        """Move cover to a designated position."""
        self._self_initiated_movement = not self._triggered_externally
        await self._abandon_active_lifecycle()
        current = self.travel_calc.current_position()
        target = position
        self._log(
            "set_position :: current: %s, target: %d",
            current if current is not None else "None",
            target,
        )

        if current is None:
            # Position unknown — assume opposite endpoint so full travel occurs
            closing = target <= 50
            command = SERVICE_CLOSE_COVER if closing else SERVICE_OPEN_COVER
            current = 100 if closing else 0
            self.travel_calc.update_position(current)
        elif target < current:
            command = SERVICE_CLOSE_COVER
        elif target > current:
            command = SERVICE_OPEN_COVER
        else:
            return

        closing = command == SERVICE_CLOSE_COVER

        should_proceed, is_direction_change = await self._handle_pre_movement_checks(
            command
        )
        if not should_proceed:
            return

        if is_direction_change and self.travel_calc.is_traveling():
            self._log("set_position :: stopping active travel movement")
            self.travel_calc.stop()
            self.stop_auto_updater()
            if self._has_tilt_support() and self.tilt_calc.is_traveling():
                self.tilt_calc.stop()
            await self._async_handle_command(SERVICE_STOP_COVER)
            if not await self._settle_before_reversing():
                return
            current = self.travel_calc.current_position()
            if target == current:
                return

        relay_was_on = self._cancel_delay_task()
        if relay_was_on:
            await self._async_handle_command(SERVICE_STOP_COVER)

        travel_time = self._require_travel_time(closing)
        movement_time = (abs(target - current) / 100.0) * travel_time

        if self._is_movement_too_short(movement_time, target, current, "set_position"):
            return

        self._last_command = command

        # If the cover is already travelling the right way, the motor is
        # running and only the stop target needs to change. Re-issuing the
        # start command would, in toggle mode, pulse the direction switch a
        # second time and stop the motor — desyncing it from the position
        # tracker (a later auto-stop pulse then restarts it and runs the cover
        # to the endpoint). Tilt coupling is still recomputed below for the new
        # target before we retarget.
        already_moving_same_dir = (
            not is_direction_change and self.travel_calc.is_traveling()
        )

        current_tilt = (
            self.tilt_calc.current_position() if self._tilt_strategy else None
        )
        # A tilt pre-step started here returns before the gate below — see
        # _require_movement_target_available.
        tilt_target, pre_step_delay, started = await self._plan_tilt_for_travel(
            target, command, current, current_tilt
        )
        if started:
            return

        coupled_calc = self.tilt_calc if tilt_target is not None else None

        # Drive the motor toward the target, then begin tracking. When already
        # moving the right way the motor is left running and only the tracker is
        # retargeted (no startup delay re-applied). _command_position_move is the
        # seam subclasses override when the device has native position control.
        if already_moving_same_dir:
            self._log("set_position :: retargeting active movement to %d", target)
        await self._command_position_move(target, command, already_moving_same_dir)
        startup_delay = None if already_moving_same_dir else self._travel_startup_delay
        self._begin_movement(
            target,
            tilt_target,
            self.travel_calc,
            coupled_calc,
            startup_delay,
            pre_step_delay,
        )

    async def _command_position_move(self, target, command, already_moving_same_dir):
        """Drive the travel motor for a mid-position ``set_position`` move.

        Base behavior: when already travelling the right way, leave the motor
        running (the caller only retargets the tracker); otherwise check target
        availability and latch the directional relay, relying on the tracker to
        stop it on arrival. Subclasses whose device has native position control
        (e.g. a wrapped cover exposing ``set_cover_position``) override this to
        forward the target straight to the device instead.
        """
        if already_moving_same_dir:
            return
        self._require_movement_target_available(
            self._movement_target(command == SERVICE_CLOSE_COVER)
        )
        await self._async_handle_command(command)

    async def set_tilt_position(self, position):
        """Move cover tilt to a designated position."""
        self._self_initiated_movement = not self._triggered_externally
        await self._abandon_active_lifecycle()
        current = self.tilt_calc.current_position()
        target = position
        self._log(
            "set_tilt_position :: current: %s, target: %d",
            current if current is not None else "None",
            target,
        )

        if current is None:
            closing = target <= 50
            current = 100 if closing else 0
            self.tilt_calc.update_position(current)
        elif target < current:
            closing = True
        elif target > current:
            closing = False
        else:
            return

        if self._tilt_strategy is not None:
            command = self._tilt_strategy.tilt_command_for(closing)
        else:
            command = SERVICE_CLOSE_COVER if closing else SERVICE_OPEN_COVER

        should_proceed, is_direction_change = await self._handle_pre_movement_checks(
            command
        )
        if not should_proceed:
            return

        if is_direction_change:
            if self.tilt_calc.is_traveling():
                self.tilt_calc.stop()
            if self.travel_calc.is_traveling():
                self.travel_calc.stop()
            self.stop_auto_updater()
            await self._async_handle_command(SERVICE_STOP_COVER)
            if self._tilt_strategy is not None and self._tilt_strategy.uses_tilt_motor:
                await self._send_tilt_stop()
            current = self.tilt_calc.current_position()
            if target == current:
                return

        relay_was_on = self._cancel_delay_task()
        if relay_was_on:
            await self._async_handle_command(SERVICE_STOP_COVER)
            if self._tilt_strategy is not None and self._tilt_strategy.uses_tilt_motor:
                await self._send_tilt_stop()

        if not is_direction_change:
            self._stop_travel_if_traveling()

        tilt_time = self._tilting_time_close if closing else self._tilting_time_open
        movement_time = (abs(target - current) / 100.0) * tilt_time

        travel_target = None
        pre_step_delay = 0.0
        needs_travel_pre_step = False
        if self._tilt_strategy is not None:
            current_pos = self.travel_calc.current_position()
            if current is not None and current_pos is not None:
                steps = self._tilt_strategy.plan_move_tilt(target, current_pos, current)
                travel_target = extract_coupled_travel(steps)
                pre_step_delay = calculate_pre_step_delay(
                    steps, self._tilt_strategy, self.tilt_calc, self.travel_calc
                )
                if self._tilt_strategy.uses_tilt_motor and has_travel_pre_step(steps):
                    needs_travel_pre_step = True

        if self._is_movement_too_short(
            movement_time, target, current, "set_tilt_position"
        ):
            return

        self._require_movement_target_available(self._tilt_movement_target(command))
        # The travel pre-step below isn't covered by the tilt gate above — see
        # _require_movement_target_available.
        if needs_travel_pre_step and travel_target is not None:
            await self._start_travel_pre_step(travel_target, target, command)
            return

        self._last_command = command
        # Set only now that the move is committed (past every no-op/too-short
        # early return) — a tilt move must not run on at a travel endpoint, but
        # leaking this onto a bailed-out call would wrongly suppress an
        # in-flight travel move's run-on (issue #125).
        self._moving_tilt = True

        if self._tilt_strategy is not None and self._tilt_strategy.uses_tilt_motor:
            self._moving_tilt_motor = True
            if closing:
                await self._send_tilt_close()
            else:
                await self._send_tilt_open()
        else:
            await self._async_handle_command(command)
        self._begin_movement(
            target,
            travel_target,
            self.tilt_calc,
            self.travel_calc,
            self._tilt_startup_delay,
            pre_step_delay,
        )

    async def _plan_tilt_for_travel(
        self, target: int, command: str, current_pos, current_tilt
    ) -> tuple[int | None, float, bool]:
        """Plan tilt coupling for a travel movement.

        Returns (tilt_target, pre_step_delay, started_pre_step).
        If started_pre_step is True, the caller should return immediately
        because _start_tilt_pre_step has taken over the movement lifecycle.
        """
        tilt_target = None
        pre_step_delay = 0.0
        self._tilt_restore_target = None

        if self._tilt_strategy is None:
            return tilt_target, pre_step_delay, False

        if current_pos is None or current_tilt is None:
            return tilt_target, pre_step_delay, False

        steps = self._tilt_strategy.plan_move_position(
            target, current_pos, current_tilt
        )
        tilt_target = extract_coupled_tilt(steps)
        pre_step_delay = calculate_pre_step_delay(
            steps, self._tilt_strategy, self.tilt_calc, self.travel_calc
        )

        # Dual motor: tilt to safe position first, then travel
        if (
            tilt_target is not None
            and self._tilt_strategy.uses_tilt_motor
            and current_tilt != tilt_target
        ):
            if target in (0, 100):
                restore = target
            elif self._tilt_strategy.allows_tilt_at_position(target):
                restore = current_tilt
            else:
                restore = tilt_target  # stay at safe position
            await self._start_tilt_pre_step(tilt_target, target, command, restore)
            return tilt_target, pre_step_delay, True

        # Dual motor: pre-step skipped, but still snap tilt to endpoint
        if (
            tilt_target is not None
            and self._tilt_strategy.uses_tilt_motor
            and target in (0, 100)
            and current_tilt != target
        ):
            self._tilt_restore_target = target

        # Shared motor with restore: save tilt for post-travel restore
        if (
            tilt_target is not None
            and self._tilt_strategy.restores_tilt
            and not self._tilt_strategy.uses_tilt_motor
            and target not in (0, 100)
        ):
            self._tilt_restore_target = current_tilt

        return tilt_target, pre_step_delay, False

    async def _handle_pre_movement_checks(self, command):
        """Handle startup delay conflicts and relay delay before a movement.

        Returns (should_proceed, is_direction_change).
        """
        is_direction_change = (
            self._last_command is not None and self._last_command != command
        )

        # If startup delay active for same direction, don't restart
        if self._startup_delay_task and not self._startup_delay_task.done():
            if not is_direction_change:
                self._log(
                    "_handle_pre_movement_checks :: startup delay active, skipping"
                )
                return False, is_direction_change
            self._log(
                "_handle_pre_movement_checks :: direction change, cancelling startup delay"
            )
            self._cancel_startup_delay_task()
            await self._async_handle_command(SERVICE_STOP_COVER)

        return True, is_direction_change

    def _is_movement_too_short(self, movement_time, target, current, label):
        """Check if movement time is below minimum. Returns True if movement should be skipped."""
        is_to_endpoint = target in (0, 100)
        if (
            self._min_movement_time is not None
            and self._min_movement_time > 0
            and not is_to_endpoint
            and movement_time < self._min_movement_time
        ):
            _LOGGER.info(
                "%s :: movement too short (%fs < %fs), ignoring - from %d%% to %d%%",
                label,
                movement_time,
                self._min_movement_time,
                current,
                target,
            )
            self.async_write_ha_state()
            return True
        return False

    def _require_configured(self) -> None:
        """Raise if the cover is not properly configured."""
        missing = self._get_missing_configuration()
        if missing:
            raise HomeAssistantError(
                f"Cover not configured: missing {', '.join(missing)}. "
                "Please configure using the Cover Time Based card."
            )

    def _require_travel_time(self, closing: bool) -> float:
        """Return travel time for the given direction, or raise if not configured."""
        travel_time = self._travel_time_close if closing else self._travel_time_open
        if travel_time is None:
            raise HomeAssistantError(
                "Travel time not configured. Please configure travel times "
                "using the Cover Time Based card."
            )
        return travel_time

    def _are_entities_configured(self) -> bool:
        """Return True if the required input entities are configured.

        Subclasses override this to check their specific entity IDs.
        """
        return True

    def _get_missing_configuration(self) -> list[str]:
        """Return list of missing configuration items."""
        missing = []
        if not self._are_entities_configured():
            missing.append("input entities")
        if self._travel_time_close is None and self._travel_time_open is None:
            missing.append("travel times")
        return missing

    def _target_entity_ids(self) -> list[str]:
        """Return the configured target entity IDs this cover drives.

        These are the switch/button/script entities that actually move the
        device. Subclasses (e.g. wrapped mode) extend this with their own
        targets.
        """
        return [
            entity_id
            for attr in self._SWITCH_TARGET_ATTRS
            if (entity_id := getattr(self, attr, None))
        ]

    @staticmethod
    def _entity_unavailable(state) -> bool:
        """Return True if a target entity is unavailable.

        Unavailable means the entity is missing (state is None) or its state is
        STATE_UNAVAILABLE. STATE_UNKNOWN is treated as available (a connected
        entity whose value isn't known yet, e.g. a button after a restart).
        """
        return state is None or state.state == STATE_UNAVAILABLE

    def _any_target_unavailable(self) -> bool:
        """Short-circuiting check used by the hot-path `available` property."""
        if self.hass is None:
            return False
        return any(
            self._entity_unavailable(self.hass.states.get(entity_id))
            for entity_id in self._target_entity_ids()
        )

    def _movement_target(self, closing: bool) -> str | None:
        """Entity driven to move the cover in the given travel direction."""
        return self._close_switch_entity_id if closing else self._open_switch_entity_id

    def _tilt_movement_target(self, command: str) -> str | None:
        """Entity driven for a resolved tilt command.

        ``command`` is what the funnel already computed via ``tilt_command_for``
        (which some strategies, e.g. sequential_open, invert). Dual-motor tilt
        uses dedicated tilt switches; shared-motor tilt drives the main travel
        switch.
        """
        closing = command == SERVICE_CLOSE_COVER
        if self._tilt_strategy is not None and self._tilt_strategy.uses_tilt_motor:
            return self._tilt_close_switch_id if closing else self._tilt_open_switch_id
        return self._movement_target(closing)

    def _require_movement_target_available(self, target: str | None) -> None:
        """Reject a fresh, self-initiated movement whose target is unavailable.

        Only fresh user/automation movement is gated (`_self_initiated_movement`).
        Stops, reverses, external reactions, retargets, and internal
        continuations never reach here (or have `_self_initiated_movement` False),
        so the cover can always be halted regardless of target availability.

        Movement that runs via a pre-step (dual-motor / sequential) returns from
        the funnel before reaching the funnel's own per-direction gate, so each
        pre-step phase calls this directly for its target (in
        `_start_tilt_pre_step` / `_start_travel_pre_step`). The all-targets
        `available` flag (the cover reports unavailable whenever any target is
        down) is the backstop covering both paths.
        """
        if not self._self_initiated_movement or self.hass is None:
            return
        if target and self._entity_unavailable(self.hass.states.get(target)):
            raise HomeAssistantError(
                f"Cover target '{target}' is unavailable; cannot start movement."
            )

    def _has_tilt_support(self):
        """Return if cover has tilt support."""
        return self._tilt_strategy is not None and hasattr(self, "tilt_calc")

    # -----------------------------------------------------------------------
    # Movement tracking
    # -----------------------------------------------------------------------

    def _begin_movement(
        self,
        target,
        coupled_target,
        primary_calc,
        coupled_calc,
        startup_delay,
        pre_step_delay: float = 0.0,
    ):
        """Start position tracking on primary and optionally coupled calculator.

        Begins travel on the primary calculator toward `target`, and if a
        coupled_target is provided, also starts the coupled calculator.
        Then starts the auto updater. Honors motor startup delay if configured.

        If pre_step_delay > 0, the coupled calculator is a pre-step that must
        complete before the primary starts (e.g. tilt-before-travel in
        sequential mode). The primary calculator's start is offset by this
        delay so its position stays put until the pre-step finishes.
        """

        def start():
            primary_calc.start_travel(target, delay=pre_step_delay)
            if coupled_target is not None:
                coupled_calc.start_travel(int(coupled_target))
            self.start_auto_updater()

        self._start_movement(startup_delay, start)

    def _start_movement(self, startup_delay, start_callback):
        """Start position tracking, optionally after a motor startup delay.

        If startup_delay is set, the relay is already ON but the motor hasn't
        started moving yet. We wait for the delay, then begin tracking.
        Otherwise we start tracking immediately.
        """
        if startup_delay and startup_delay > 0:
            self._startup_delay_task = self.hass.async_create_task(
                self._execute_with_startup_delay(startup_delay, start_callback)
            )
        else:
            start_callback()

    async def _execute_with_startup_delay(self, startup_delay, start_callback):
        """Wait for motor startup delay, then start position tracking."""
        self._log(
            "_execute_with_startup_delay :: waiting %fs before starting position tracking",
            startup_delay,
        )
        try:
            await sleep(startup_delay)
            self._log(
                "_execute_with_startup_delay :: startup delay complete, starting position tracking"
            )
            start_callback()
            self._startup_delay_task = None
        except asyncio.CancelledError:
            self._log("_execute_with_startup_delay :: startup delay cancelled")
            self._startup_delay_task = None
            raise

    def _cancel_delay_task(self):
        """Cancel any active delay task."""
        if self._delay_task is not None and not self._delay_task.done():
            self._log("_cancel_delay_task :: cancelling active delay task")
            self._delay_task.cancel()
            self._delay_task = None
            return True
        return False

    def _cancel_startup_delay_task(self):
        """Cancel any active startup delay task."""
        if self._startup_delay_task is not None and not self._startup_delay_task.done():
            self._log(
                "_cancel_startup_delay_task :: cancelling active startup delay task"
            )
            self._startup_delay_task.cancel()
            self._startup_delay_task = None

    def start_auto_updater(self):
        """Start the autoupdater to update HASS while cover is moving."""
        self._log("start_auto_updater")
        if self._unsubscribe_auto_updater is None:
            self._log("init _unsubscribe_auto_updater")
            interval = timedelta(seconds=0.1)
            self._unsubscribe_auto_updater = async_track_time_interval(
                self.hass, self.auto_updater_hook, interval
            )

    @callback
    def auto_updater_hook(self, _now):
        """Call for the autoupdater."""
        self.async_schedule_update_ha_state()
        if self.position_reached():
            self._log("auto_updater_hook :: position_reached")
            self.stop_auto_updater()
        self.hass.async_create_task(self.auto_stop_if_necessary())

    def stop_auto_updater(self):
        """Stop the autoupdater."""
        self._log("stop_auto_updater")
        if self._unsubscribe_auto_updater is not None:
            self._unsubscribe_auto_updater()
            self._unsubscribe_auto_updater = None

    def position_reached(self):
        """Return if cover has reached its final position."""
        return self.travel_calc.position_reached() and (
            not self._has_tilt_support() or self.tilt_calc.position_reached()
        )

    # -----------------------------------------------------------------------
    # Movement lifecycle (auto-stop, pre-step, restore)
    # -----------------------------------------------------------------------

    async def auto_stop_if_necessary(self):
        """Do auto stop if necessary."""
        if self.position_reached():
            self._log(
                "auto_stop_if_necessary :: position reached (self_initiated=%s)",
                self._self_initiated_movement,
            )
            self.travel_calc.stop()
            if self._has_tilt_support():
                self.tilt_calc.stop()

            if not self._self_initiated_movement:
                # Movement was triggered externally. A multi-phase move still
                # has to chain its phases (dual-motor tilt pre-step → travel, or
                # travel pre-step → tilt); only the final endpoint relay handling
                # is special-cased below. Without continuing here the cover would
                # tilt-to-safe and then stall, needing a second press to travel.
                self._log("auto_stop_if_necessary :: external movement")
                if self._pending_travel_target is not None:
                    self._log(
                        "auto_stop_if_necessary :: external tilt pre-step complete"
                    )
                    await self._start_pending_travel()
                    return
                if self._pending_tilt_target is not None:
                    self._log(
                        "auto_stop_if_necessary :: external travel pre-step complete"
                    )
                    await self._start_pending_tilt()
                    return
                # Move complete: don't re-drive the relay, but a latched relay
                # (switch mode) must still be de-energized; momentary modes
                # self-released and no-op in _settle_external_endpoint.
                await self._settle_external_endpoint()
                if self._tilt_strategy is not None:
                    self._tilt_strategy.snap_trackers_to_physical(
                        self.travel_calc, self.tilt_calc
                    )
                self._last_command = None
                self._moving_tilt_motor = False
                self._moving_tilt = False
                await self._async_persist_position()
                return

            if self._tilt_restore_active:
                self._log("auto_stop_if_necessary :: tilt restore complete")
                self._release_tilt_restore()
                if self._has_tilt_motor():
                    await self._tilt_settle()
                else:
                    await self._async_handle_command(SERVICE_STOP_COVER)
                if self._tilt_strategy is not None:
                    self._tilt_strategy.snap_trackers_to_physical(
                        self.travel_calc, self.tilt_calc
                    )
                self._last_command = None
                self._moving_tilt_motor = False
                self._moving_tilt = False
                await self._async_persist_position()
                return

            if self._pending_travel_target is not None:
                # Tilt pre-step complete — start travel phase
                self._log("auto_stop_if_necessary :: tilt pre-step complete")
                await self._start_pending_travel()
                return

            if self._pending_tilt_target is not None:
                # Travel pre-step complete — start tilt phase
                self._log("auto_stop_if_necessary :: travel pre-step complete")
                await self._start_pending_tilt()
                return

            if self._tilt_strategy is not None:
                self._tilt_strategy.snap_trackers_to_physical(
                    self.travel_calc, self.tilt_calc
                )

            if self._tilt_restore_target is not None:
                # Travel just completed — start tilt restore phase
                await self._start_tilt_restore()
                return

            current_travel = self.travel_calc.current_position()
            # Endpoint handling (the self-stop skip and the run-on below) is a
            # *travel* concept: it only applies when a travel move reaches a
            # physical limit. A tilt move that merely finishes while the cover is
            # parked at a travel endpoint has driven the motor *off* that limit
            # to articulate the slats, so the motor will NOT self-stop there and
            # must always be stopped explicitly — never given the self-stop skip
            # (issue #142) or the run-on (issue #125).
            endpoint_applies = (
                self._at_endpoint(current_travel) and not self._moving_tilt
            )
            if self._motor_stops_itself():
                # The device drives to the target and holds there on its own
                # (e.g. a wrapped cover commanded via set_cover_position). Any
                # stop we issue here is at best redundant and at worst nudges it
                # off the exact target (a freeze re-commands the calculated, not
                # requested, position). Just settle the tracker.
                self._log("auto_stop_if_necessary :: device self-stops, no relay stop")
            elif self._has_tilt_motor() and self._moving_tilt_motor:
                # The completed movement drove the dedicated tilt motor — settle
                # that motor (skipping the stop at the tilt endpoints), not
                # travel. Without this a tilt move would fall through to the
                # travel stop below and re-pulse the travel relay off a stale
                # _last_command.
                await self._tilt_settle()
            elif endpoint_applies and self._self_stops_at_endpoints():
                # The motor self-stops at its physical limit switch. Sending a
                # stop here is redundant (and for toggle re-pulses → restart),
                # so skip the relay stop and any run-on; just settle the
                # tracker. Run-on (below) is therefore switch-mode only.
                self._log(
                    "auto_stop_if_necessary :: motor self-stops at endpoint"
                    " (position=%d), no relay stop",
                    current_travel,
                )
            elif (
                endpoint_applies
                and self._endpoint_runon_time is not None
                and self._endpoint_runon_time > 0
            ):
                self._log(
                    "auto_stop_if_necessary :: at endpoint (position=%d),"
                    " delaying relay stop by %fs",
                    current_travel,
                    self._endpoint_runon_time,
                )
                self._delay_task = self.hass.async_create_task(
                    self._delayed_stop(self._endpoint_runon_time)
                )
            else:
                await self._async_handle_command(SERVICE_STOP_COVER)
            self._last_command = None
            self._moving_tilt_motor = False
            self._moving_tilt = False
            await self._async_persist_position()

    def _motor_stops_itself(self) -> bool:
        """Return True if the device halts at the target without a stop command.

        Relay-driven covers (the default) must be told to stop when the tracker
        reaches the target, so this is False. Subclasses whose device has native
        position control and stops itself at the commanded position override this
        to True so auto-stop skips the redundant (and potentially target-nudging)
        relay stop.
        """
        return False

    def _self_stops_at_endpoints(self) -> bool:
        """Return True if the motor self-stops at the physical endpoints.

        Roller-shutter motors have internal limit switches that halt the motor
        at fully-open/closed on their own. For modes whose relays are momentary
        or delegated (toggle, pulse, wrapped), the stop we would otherwise send
        at 0%/100% is therefore redundant — and for toggle actively harmful, as
        re-pulsing the direction relay restarts the already-stopped motor. Such
        modes return True so auto-stop skips the relay stop (and run-on) at an
        endpoint while still stopping mid-travel, where nothing self-stops.

        Switch mode overrides this to False: its direction relay is latched ON
        for the whole travel, so reaching an endpoint must still de-energize it.
        """
        return True

    def _at_endpoint(self, position) -> bool:
        """Return True at a travel endpoint (0/100) where endpoint handling
        (self-stop skip or run-on) applies.

        Sequential tilt drives the motor past cover-closed to articulate the
        slats, so it disallows endpoint handling at 0 (``allows_endpoint_runon``).
        """
        return (
            position is not None
            and position in (0, 100)
            and (
                self._tilt_strategy is None
                or self._tilt_strategy.allows_endpoint_runon(position)
            )
        )

    async def _tilt_settle(self) -> None:
        """Stop the dedicated tilt motor at the end of a tilt-motor movement.

        Mirrors the travel endpoint logic: at the tilt endpoints (0%/100%) the
        tilt motor self-stops on its own limit, so the stop is skipped (and for
        toggle a re-pulse would restart it) — except in switch mode, whose
        latched tilt relay must still be de-energized. Mid-tilt always stops.
        """
        current_tilt = (
            self.tilt_calc.current_position() if self._has_tilt_support() else None
        )
        if (
            current_tilt is not None
            and current_tilt in (0, 100)
            and self._self_stops_at_endpoints()
        ):
            self._log(
                "_tilt_settle :: tilt motor self-stops at endpoint (%d), no relay stop",
                current_tilt,
            )
        else:
            await self._send_tilt_stop()

    async def _settle_external_endpoint(self) -> None:
        """De-energize any latched relay after an externally-triggered move
        reaches its endpoint.

        Auto-stop skips the relay stop for externally-triggered movements
        (``_self_initiated_movement`` False): the trigger came from outside HA,
        and for momentary modes (pulse/toggle/wrapped) the relay was a brief
        pulse that has already self-released — there is nothing to de-energize,
        so they keep this no-op. Switch mode latches its direction relay ON for
        the whole travel, so it overrides this to turn the relay off (only if
        still on); otherwise the relay stays energized at the endpoint forever.
        """
        return

    async def _delayed_stop(self, delay):
        """Stop the relay after a delay."""
        self._log("_delayed_stop :: waiting %fs before stopping relay", delay)
        try:
            await sleep(delay)
            self._log("_delayed_stop :: delay complete, stopping relay")
            await self._async_handle_command(SERVICE_STOP_COVER)
            self._last_command = None
            self._delay_task = None
        except asyncio.CancelledError:
            self._log("_delayed_stop :: delay cancelled")
            self._delay_task = None
            raise

    async def _abandon_active_lifecycle(self):
        """Abandon any active multi-phase tilt lifecycle (pre-step, restore).

        Called at the start of every movement method. If a tilt restore or
        tilt pre-step is in progress, stops all hardware and calculators.
        Always clears the pending restore target so it won't fire after
        the next travel completes.

        Being the one hook every movement entry point funnels through, this is
        also where a new movement claims the epoch — see
        _settle_before_reversing. Tilt counts: on shared-motor strategies tilt
        is driven by the travel motor, so a tilt command must invalidate a
        travel reversal parked in its settle gap just as a travel command does.
        """
        self._supersede_movement()
        was_restoring = self._tilt_restore_active
        was_pre_stepping = (
            self._pending_travel_target is not None
            or self._pending_tilt_target is not None
        )

        # Always clear multi-phase state
        self._clear_multiphase_tilt_state()
        # Each movement entry point funnels through here; default to a travel
        # move and let the tilt paths below opt in.
        self._moving_tilt_motor = False
        self._moving_tilt = False

        if not was_restoring and not was_pre_stepping:
            return

        self._log(
            "_abandon_active_lifecycle :: abandoning %s",
            "tilt restore" if was_restoring else "pre-step",
        )

        self._cancel_startup_delay_task()

        if self.travel_calc.is_traveling():
            self.travel_calc.stop()
        if self._has_tilt_support() and self.tilt_calc.is_traveling():
            self.tilt_calc.stop()
        self.stop_auto_updater()

        await self._async_handle_command(SERVICE_STOP_COVER)
        if self._has_tilt_motor() and not self._triggered_externally:
            await self._send_tilt_stop()

    def _stop_travel_if_traveling(self):
        """Stop cover movement if it's currently traveling."""
        if self.travel_calc.is_traveling():
            self._log("_stop_travel_if_traveling :: stopping cover movement")
            self.travel_calc.stop()
            if self._has_tilt_support() and self.tilt_calc.is_traveling():
                self._log("_stop_travel_if_traveling :: also stopping tilt")
                self.tilt_calc.stop()

    def _handle_stop(self, *, supersede: bool = True):
        """Handle stop.

        ``supersede`` says whether this is a fresh command to halt the cover,
        which claims the movement and so keeps a reversal parked in its settle
        gap from driving afterwards. Every route that halts the cover lands
        here — both async_stop_cover implementations (the toggle override does
        not call super), plus the known-position resets.

        Passive routes must pass ``supersede=False``: a wrapped cover reporting
        its settled position snaps via set_known_position, and a switch-mode
        relay's unmarked off (a hardware interlock clearing the opposite relay)
        calls async_stop_cover. Both can arrive inside the settle window — the
        wrapped self-echo suppressors are keyed on is_traveling(), which the
        reversal has already cleared — and treating them as supersessions would
        silently drop the user's move, or freeze the tracker while the motor
        runs. So must the stop a reversal issues as its own prelude, which would
        otherwise cancel the very movement it is starting.

        The caller has to say so because _triggered_externally cannot: it is
        ambient instance state held for the whole external call, settle gap
        included, so inferring from it read a genuine stop landing in that gap
        as a device echo and dropped it.
        """
        if supersede:
            self._supersede_movement()
        self._clear_multiphase_tilt_state()

        if self.travel_calc.is_traveling():
            self._log("_handle_stop :: button stops cover movement")
            self.travel_calc.stop()
            self.stop_auto_updater()

        if self._has_tilt_support() and self.tilt_calc.is_traveling():
            self._log("_handle_stop :: button stops tilt movement")
            self.tilt_calc.stop()
            self.stop_auto_updater()

    async def _start_tilt_pre_step(
        self, tilt_target, travel_target, travel_command, restore_target
    ):
        """Move tilt to safe position before travel (dual_motor).

        Sends the tilt motor command and starts tilt_calc. When tilt reaches
        target, auto_stop_if_necessary will call _start_pending_travel to
        begin the actual cover travel.
        """
        current_tilt = self.tilt_calc.current_position()
        self._log(
            "_start_tilt_pre_step :: tilt %s→%d, pending travel→%d (%s)",
            current_tilt,
            tilt_target,
            travel_target,
            travel_command,
        )
        closing_tilt = tilt_target < current_tilt
        self._require_movement_target_available(
            self._tilt_movement_target(
                SERVICE_CLOSE_COVER if closing_tilt else SERVICE_OPEN_COVER
            )
        )
        self._pending_travel_target = travel_target
        self._pending_travel_command = travel_command
        self._tilt_restore_target = restore_target

        if not self._triggered_externally:
            if closing_tilt:
                await self._send_tilt_close()
            else:
                await self._send_tilt_open()

        self.tilt_calc.start_travel(tilt_target)
        self.start_auto_updater()

    async def _start_pending_travel(self):
        """Start travel after tilt pre-step completes (dual_motor).

        Called by auto_stop_if_necessary when tilt_calc reaches the safe
        position. For self-initiated moves: stops the tilt motor and sends
        the travel command. For external triggers (where hardware is doing
        the multi-phase motion itself), only updates the integration's
        trackers — the relays are left to the hardware.
        """
        target = self._pending_travel_target
        command = self._pending_travel_command
        assert target is not None and command is not None
        self._pending_travel_target = None
        self._pending_travel_command = None

        self._log(
            "_start_pending_travel :: starting travel to %d (%s)",
            target,
            command,
        )

        self._moving_tilt_motor = False
        if not self._triggered_externally:
            # Stop tilt motor and send travel command.
            await self._send_tilt_stop()
            await self._async_handle_command(command)
        self._last_command = command
        self._begin_movement(
            target,
            None,
            self.travel_calc,
            None,
            self._travel_startup_delay,
        )

    async def _start_travel_pre_step(self, travel_target, tilt_target, tilt_command):
        """Move cover to allowed position before tilt (dual_motor).

        Sends the travel motor command and starts travel_calc. When travel
        reaches target, auto_stop_if_necessary will call _start_pending_tilt
        to begin the actual tilt movement.
        """
        current_pos = self.travel_calc.current_position()
        self._log(
            "_start_travel_pre_step :: travel %s→%d, pending tilt→%d (%s)",
            current_pos,
            travel_target,
            tilt_target,
            tilt_command,
        )
        closing = travel_target < current_pos
        command = SERVICE_CLOSE_COVER if closing else SERVICE_OPEN_COVER
        self._require_movement_target_available(self._movement_target(closing))
        self._pending_tilt_target = tilt_target
        self._pending_tilt_command = tilt_command
        self._last_command = command
        await self._async_handle_command(command)

        self._begin_movement(
            travel_target,
            None,
            self.travel_calc,
            None,
            self._travel_startup_delay,
        )

    async def _start_pending_tilt(self):
        """Start tilt after travel pre-step completes (dual_motor).

        Called by auto_stop_if_necessary when travel_calc reaches the
        allowed position. Stops the travel motor, sends the tilt command,
        and starts tracking with tilt_calc.
        """
        target = self._pending_tilt_target
        command = self._pending_tilt_command
        assert target is not None and command is not None
        self._pending_tilt_target = None
        self._pending_tilt_command = None

        self._log(
            "_start_pending_tilt :: starting tilt to %d (%s)",
            target,
            command,
        )

        # Stop travel motor
        await self._async_handle_command(SERVICE_STOP_COVER)

        # Send tilt command and start tracking
        self._moving_tilt_motor = True
        closing_tilt = command == SERVICE_CLOSE_COVER
        if closing_tilt:
            await self._send_tilt_close()
        else:
            await self._send_tilt_open()
        self._last_command = command
        self._begin_movement(
            target,
            None,
            self.tilt_calc,
            None,
            self._tilt_startup_delay,
        )

    async def _start_tilt_restore(self):
        """Restore tilt to its pre-movement position.

        For dual_motor: stops travel motor, starts tilt motor.
        For shared motor (inline): reverses main motor direction.
        """
        restore_target = self._tilt_restore_target
        self._tilt_restore_target = None
        if restore_target is None:
            return

        current_tilt = self.tilt_calc.current_position()
        if current_tilt is None or current_tilt == restore_target:
            self._log(
                "_start_tilt_restore :: no restore needed (current=%s, target=%s)",
                current_tilt,
                restore_target,
            )
            await self._async_handle_command(SERVICE_STOP_COVER)
            self._last_command = None
            return

        self._log(
            "_start_tilt_restore :: restoring tilt from %d%% to %d%%",
            current_tilt,
            restore_target,
        )

        closing = restore_target < current_tilt

        # Everything below runs on the auto-updater's background task, so every
        # await yields the event loop and a user STOP or a new movement command
        # can interleave. Mark the restore active *before* the first await so
        # those paths (async_stop_cover -> _handle_stop, other moves ->
        # _abandon_active_lifecycle) recognise it, stop the motor, and clear the
        # flag; we then re-check the flag after each await and bail so we never
        # (re)start or keep tracking a motor the user just stopped. The
        # auto-updater stays unsubscribed for this whole window (stopped when
        # travel reached its target, re-armed only at the tail below), so no
        # re-entrant auto_stop_if_necessary can take the restore-complete branch
        # mid-startup — keep it that way if this ever moves.
        epoch = self._claim_tilt_restore()

        if self._tilt_strategy.uses_tilt_motor:
            # Dual motor: stop travel, then start the separate tilt motor.
            await self._async_handle_command(SERVICE_STOP_COVER)
            if self._tilt_restore_superseded(epoch):
                self._log("_start_tilt_restore :: cancelled before tilt motor start")
                return
            if closing:
                await self._send_tilt_close()
            else:
                await self._send_tilt_open()
        else:
            # Shared motor (inline tilt — the only strategy that both restores
            # tilt and drives it via the travel motor): the travel motor is
            # still running from the travel phase and the restore reverses it.
            # Stop and let the motor settle before commanding the opposite
            # direction (issue #147) — an instant reversal leaves a short
            # restore pulse's stop command dropped by the relay, so the cover
            # overruns to its physical endpoint.
            await self._async_handle_command(SERVICE_STOP_COVER)
            if self._tilt_restore_superseded(epoch):
                # Cancelled while stopping — bail before the settle delay so we
                # don't block the background task for a dead restore. The gap is
                # the per-cover direction_change_delay, so it can be several
                # seconds, not the ~1s this once assumed.
                self._log("_start_tilt_restore :: cancelled before settle delay")
                return
            await self._direction_change_delay()
            if self._tilt_restore_superseded(epoch):
                self._log("_start_tilt_restore :: cancelled during settle delay")
                return
            command = self._tilt_strategy.tilt_command_for(closing)
            await self._async_handle_command(command)

        if self._tilt_restore_superseded(epoch):
            # The motor is already energized: whoever cancelled us sent their
            # stop while we were awaiting this turn-on, so theirs went out
            # first and ours landed after it. Nothing else will take it down —
            # we are the only one that knows it went up — and on a latching
            # relay that means a cover driving to its endpoint untracked.
            self._log("_start_tilt_restore :: cancelled during motor start, stopping")
            await self._stop_restore_motor()
            return
        self.tilt_calc.start_travel(restore_target)
        self.start_auto_updater()

    async def _stop_restore_motor(self) -> None:
        """Take down whichever motor the restore energized."""
        if self._tilt_strategy.uses_tilt_motor:
            await self._send_tilt_stop()
        else:
            await self._async_handle_command(SERVICE_STOP_COVER)

    # -----------------------------------------------------------------------
    # Relay command dispatch
    # -----------------------------------------------------------------------

    async def _async_handle_command(self, command, *_args):
        cmd = command
        if command == SERVICE_CLOSE_COVER:
            cmd = "CLOSE"
            self._state = False
            self._last_command = command
            if not self._triggered_externally:
                await self._send_close()
        elif command == SERVICE_OPEN_COVER:
            cmd = "OPEN"
            self._state = True
            self._last_command = command
            if not self._triggered_externally:
                await self._send_open()
        elif command == SERVICE_STOP_COVER:
            cmd = "STOP"
            self._state = True
            if not self._triggered_externally:
                await self._send_stop()

        self._log("_async_handle_command :: %s", cmd)
        self.async_write_ha_state()

    @abstractmethod
    async def _send_open(self) -> None:
        """Send the open command to the underlying device."""

    @abstractmethod
    async def _send_close(self) -> None:
        """Send the close command to the underlying device."""

    @abstractmethod
    async def _send_stop(self) -> None:
        """Send the stop command to the underlying device."""

    async def _raw_direction_command(self, command: str) -> None:
        """Execute a raw direction command (for calibration screen buttons).

        Sets _last_command / _last_tilt_direction and sends relay commands.
        Override in subclasses that need stop-before-direction-change
        (e.g. toggle mode where opposite-direction = stop, not reverse).
        """
        if command == "open":
            self._last_command = SERVICE_OPEN_COVER
            await self._send_open()
        elif command == "close":
            self._last_command = SERVICE_CLOSE_COVER
            await self._send_close()
        elif command == "stop":
            await self._send_stop()
            self._last_command = None
        elif command == "tilt_open":
            await self._send_tilt_open()
        elif command == "tilt_close":
            await self._send_tilt_close()
        elif command == "tilt_stop":
            await self._send_tilt_stop()

    # -----------------------------------------------------------------------
    # Tilt motor relay commands (dual_motor only)
    # -----------------------------------------------------------------------

    def _has_tilt_motor(self) -> bool:
        """Return True if a dedicated tilt motor is configured (dual_motor mode)."""
        return (
            self._tilt_strategy is not None
            and self._tilt_strategy.uses_tilt_motor
            and bool(self._tilt_open_switch_id and self._tilt_close_switch_id)
        )

    async def _send_tilt_open(self) -> None:
        """Send open to the tilt motor (bypasses position tracker).

        Switch-mode (latching) semantics: each turn_on/turn_off produces
        at most one state-change event, and only when the switch isn't
        already in the target state. Mark pending=1 per expected echo,
        and only when the relay call will actually flip state. Otherwise
        the orphan pending count consumes the next real state change.
        """
        if self._switch_is_on(self._tilt_close_switch_id):
            self._mark_switch_pending(self._tilt_close_switch_id, 1)
        if not self._switch_is_on(self._tilt_open_switch_id):
            self._mark_switch_pending(self._tilt_open_switch_id, 1)
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._tilt_close_switch_id},
            False,
        )
        await self.hass.services.async_call(
            "homeassistant",
            "turn_on",
            {"entity_id": self._tilt_open_switch_id},
            False,
        )

    async def _send_tilt_close(self) -> None:
        """Send close to the tilt motor (bypasses position tracker).

        See _send_tilt_open for the pending-count rationale.
        """
        if self._switch_is_on(self._tilt_open_switch_id):
            self._mark_switch_pending(self._tilt_open_switch_id, 1)
        if not self._switch_is_on(self._tilt_close_switch_id):
            self._mark_switch_pending(self._tilt_close_switch_id, 1)
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._tilt_open_switch_id},
            False,
        )
        await self.hass.services.async_call(
            "homeassistant",
            "turn_on",
            {"entity_id": self._tilt_close_switch_id},
            False,
        )

    async def _send_tilt_stop(self) -> None:
        """Send stop to the tilt motor (bypasses position tracker)."""
        if self._switch_is_on(self._tilt_open_switch_id):
            self._mark_switch_pending(self._tilt_open_switch_id, 1)
        if self._switch_is_on(self._tilt_close_switch_id):
            self._mark_switch_pending(self._tilt_close_switch_id, 1)
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._tilt_open_switch_id},
            False,
        )
        await self.hass.services.async_call(
            "homeassistant",
            "turn_off",
            {"entity_id": self._tilt_close_switch_id},
            False,
        )
        if self._tilt_stop_switch_id:
            self._mark_switch_pending(self._tilt_stop_switch_id, 2)
            await self.hass.services.async_call(
                "homeassistant",
                "turn_on",
                {"entity_id": self._tilt_stop_switch_id},
                False,
            )

    # -----------------------------------------------------------------------
    # Switch echo filtering
    # -----------------------------------------------------------------------

    def _switch_is_on(self, entity_id) -> bool:
        """Check if a switch entity is currently on."""
        state = self.hass.states.get(entity_id)
        return state is not None and state.state == "on"

    def _mark_switch_pending(self, entity_id, expected_transitions):
        """Mark a switch as having pending echo transitions to ignore."""
        self._pending_switch[entity_id] = (
            self._pending_switch.get(entity_id, 0) + expected_transitions
        )
        self._log(
            "_mark_switch_pending :: %s pending=%d",
            entity_id,
            self._pending_switch[entity_id],
        )

        # Cancel any existing timeout for this switch
        if entity_id in self._pending_switch_timers:
            self._pending_switch_timers[entity_id]()

        # Safety timeout: clear pending after 5 seconds
        @callback
        def _clear_pending(_now):
            if entity_id in self._pending_switch:
                self._log("_mark_switch_pending :: timeout clearing %s", entity_id)
                del self._pending_switch[entity_id]
            self._pending_switch_timers.pop(entity_id, None)

        self._pending_switch_timers[entity_id] = async_call_later(
            self.hass, 5, _clear_pending
        )

    async def _async_switch_state_changed(self, event):
        """Handle state changes on monitored switch entities."""
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")

        # Availability transition: push a state write so `available` updates
        # live in the UI. Done before the None-guard below so entity
        # removal/re-appearance is also reflected. An "unavailable" transition
        # drives no movement (it matches no opening/closing/stopped branch).
        was_unavailable = self._entity_unavailable(old_state)
        now_unavailable = self._entity_unavailable(new_state)
        if was_unavailable != now_unavailable:
            self.async_write_ha_state()

        if new_state is None or old_state is None:
            return

        new_val = new_state.state
        old_val = old_state.state

        self._log(
            "_async_switch_state_changed :: %s: %s -> %s (pending=%s)",
            entity_id,
            old_val,
            new_val,
            self._pending_switch.get(entity_id, 0),
        )

        # Attribute-only updates (same state string, only attributes changed)
        # must not consume pending echo counts, but may carry useful info
        # (e.g. a wrapped cover updating its current_position attribute).
        # Dispatch to a subclass hook, then return without touching the echo
        # filter or external-state handler. _triggered_externally is set so
        # downstream helpers (async_stop_cover etc.) don't echo a service
        # call back to the wrapped entity in response to its own update.
        if old_val == new_val:
            self._triggered_externally = True
            try:
                await self._handle_external_attribute_change(event)
            finally:
                self._triggered_externally = False
            return

        # Echo filtering: if this switch has pending echoes, decrement and skip
        if self._pending_switch.get(entity_id, 0) > 0:
            self._pending_switch[entity_id] -= 1
            if self._pending_switch[entity_id] <= 0:
                del self._pending_switch[entity_id]
                # Cancel the safety timeout
                timer = self._pending_switch_timers.pop(entity_id, None)
                if timer:
                    timer()
            self._log(
                "_async_switch_state_changed :: echo filtered, remaining=%s",
                self._pending_switch.get(entity_id, 0),
            )
            return

        # Skip external state handling during calibration — calibration drives
        # the motors directly and must not be interfered with.
        if self._calibration is not None:
            self._log("_async_switch_state_changed :: calibration active, skipping")
            return

        # A relay that does not report its own OFF stays stuck reporting 'on'
        # across a restart/reconnect (it pulsed and physically released but
        # never told HA). The entity (re)appearing — unavailable/unknown -> on —
        # is then that stale retained state resurfacing, NOT a fresh button
        # press; replaying it as one would start a phantom movement (tracked,
        # but with no relay fired since _triggered_externally) and desync the
        # tracker from the physical cover. Modes that know their relay is
        # unreliable this way opt in via _is_stale_reappearance.
        if self._is_stale_reappearance(old_val, new_val):
            self._log(
                "_async_switch_state_changed :: %s came online (%s -> %s),"
                " not treating as a command",
                entity_id,
                old_val,
                new_val,
            )
            return

        # External state change (physical button / remote / HA button).
        # Delegate to mode-specific handlers which start/stop position
        # tracking normally via async_open_cover / async_close_cover etc.
        is_tilt = entity_id in (
            self._tilt_open_switch_id,
            self._tilt_close_switch_id,
            self._tilt_stop_switch_id,
        )
        self._triggered_externally = True
        try:
            if is_tilt:
                await self._handle_external_tilt_state_change(
                    entity_id, old_val, new_val
                )
            else:
                await self._handle_external_state_change(entity_id, old_val, new_val)
        finally:
            self._triggered_externally = False

    # -----------------------------------------------------------------------
    # External state change handlers
    # -----------------------------------------------------------------------

    def _is_stale_reappearance(self, old_val, new_val) -> bool:
        """Whether this transition is an unreliable relay (re)appearing.

        Default ``False`` — most relays report their own OFF, so they come back
        ``off`` after a restart and a real ``off->on`` press is unambiguous.
        Overridden by modes whose relay's reported state can't be trusted
        across a restart/reconnect (see ToggleModeCover with
        ``relay_reports_off`` disabled), so the dispatcher skips treating the
        reappearance as a command.
        """
        return False

    async def _handle_external_tilt_state_change(self, entity_id, old_val, new_val):
        """Handle external state change on tilt switches (dual_motor).

        Tilt switches use pulse-mode behavior. The ON signal (rising edge)
        is the button press. The OFF transition is just button release.
        """
        if new_val != "on":
            return

        if entity_id == self._tilt_open_switch_id:
            self._log(
                "_handle_external_tilt_state_change :: external tilt open pulse detected"
            )
            await self.async_open_cover_tilt()
        elif entity_id == self._tilt_close_switch_id:
            self._log(
                "_handle_external_tilt_state_change :: external tilt close pulse detected"
            )
            await self.async_close_cover_tilt()
        elif entity_id == self._tilt_stop_switch_id:
            self._log(
                "_handle_external_tilt_state_change :: external tilt stop pulse detected"
            )
            # A dedicated stop relay is a press, not a report — see
            # SwitchCoverTimeBased._handle_external_state_change.
            await self.async_stop_cover()

    async def _handle_external_state_change(self, entity_id, old_val, new_val):
        """Handle external state change. Override in subclasses for mode-specific behavior."""

    async def _handle_external_attribute_change(self, event):
        """Handle attribute-only updates on monitored entities. Default no-op.

        Override in subclasses that need to react to attribute changes
        (e.g. a wrapped cover updating its current_position attribute).
        """
