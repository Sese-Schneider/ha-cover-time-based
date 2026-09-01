from custom_components.cover_time_based.cover_base import CoverTimeBased


def test_supports_tilt_defaults_true():
    assert CoverTimeBased.supports_tilt is True


def test_has_tilt_support_false_when_flag_off():
    class _Dummy(CoverTimeBased):
        supports_tilt = False

        async def _send_open(self) -> None:
            pass

        async def _send_close(self) -> None:
            pass

        async def _send_stop(self) -> None:
            pass

    obj = _Dummy.__new__(_Dummy)  # skip __init__; exercise the gate only
    obj._tilt_strategy = object()  # non-None strategy present
    obj.tilt_calc = object()  # tilt_calc attribute present
    assert obj._has_tilt_support() is False


def test_has_tilt_support_true_when_flag_on_and_configured():
    class _Dummy(CoverTimeBased):
        supports_tilt = True

        async def _send_open(self) -> None:
            pass

        async def _send_close(self) -> None:
            pass

        async def _send_stop(self) -> None:
            pass

    obj = _Dummy.__new__(_Dummy)
    obj._tilt_strategy = object()
    obj.tilt_calc = object()
    assert obj._has_tilt_support() is True
