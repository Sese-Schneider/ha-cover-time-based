from custom_components.cover_time_based.single_button_cycle import Phase
from tests.test_cover_single_button_mode import _make_sb_cover


def test_extra_persist_data_carries_phase():
    cover = _make_sb_cover()
    cover._phase = Phase.STOPPED_AFTER_DOWN
    assert cover._extra_persist_data() == {"phase": "stopped_after_down"}


def test_apply_restored_extra_sets_phase():
    cover = _make_sb_cover()
    cover._phase = Phase.AT_CLOSED
    cover._apply_restored_extra({"position": 50, "phase": "moving_up"})
    assert cover._phase is Phase.MOVING_UP


def test_apply_restored_extra_ignores_missing_phase():
    cover = _make_sb_cover()
    cover._phase = Phase.AT_OPEN
    cover._apply_restored_extra({"position": 50})
    assert cover._phase is Phase.AT_OPEN


def test_apply_restored_extra_ignores_invalid_phase():
    # A corrupted store or a renamed/removed Phase value must not raise --
    # it should leave the current/default phase untouched instead of
    # breaking entity restore.
    cover = _make_sb_cover()
    cover._phase = Phase.AT_OPEN
    cover._apply_restored_extra({"position": 50, "phase": "not_a_real_phase"})
    assert cover._phase is Phase.AT_OPEN
