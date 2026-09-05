"""Integration tests for administrator gating of the card's commands.

Everything that writes a cover's configuration or drives a relay is
admin-only: the websocket commands and the two calibration services.
The websocket tests go through a real connection so the decorator chain
is exercised; tests/test_websocket_api.py unwraps the decorators and
cannot see an auth gate.
"""

from __future__ import annotations

import pytest
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError, Unauthorized

from .conftest import DOMAIN

ENTITY_ID = "cover.test_cover"

COMMANDS = [
    {"type": "cover_time_based/get_config", "entity_id": ENTITY_ID},
    {
        "type": "cover_time_based/update_config",
        "entity_id": ENTITY_ID,
        "travel_time_open": 45.0,
    },
    {
        "type": "cover_time_based/start_calibration",
        "entity_id": ENTITY_ID,
        "attribute": "travel_time_open",
        # The schema minimum: a regressed gate runs a one-second calibration,
        # not a minute-long one.
        "timeout": 1,
    },
    {"type": "cover_time_based/stop_calibration", "entity_id": ENTITY_ID},
    {"type": "cover_time_based/raw_command", "entity_id": ENTITY_ID, "command": "open"},
]


@pytest.mark.parametrize("command", COMMANDS, ids=[c["type"] for c in COMMANDS])
async def test_non_admin_is_rejected(
    hass: HomeAssistant,
    setup_cover,
    hass_ws_client,
    hass_read_only_access_token,
    base_options,
    command,
):
    """A read-only user's websocket command is refused with no side effect."""
    client = await hass_ws_client(hass, hass_read_only_access_token)
    await client.send_json({"id": 1, **command})
    msg = await client.receive_json()

    assert msg["success"] is False
    assert msg["error"]["code"] == "unauthorized"
    # No side effect: update_config would have rewritten the option,
    # start_calibration and raw_command would have driven the relay.
    # get_config and stop_calibration have no side effect to check.
    assert setup_cover.options["travel_time_open"] == base_options["travel_time_open"]
    assert hass.states.get("input_boolean.open_switch").state == "off"


@pytest.mark.parametrize("command", COMMANDS, ids=[c["type"] for c in COMMANDS])
async def test_admin_is_accepted(
    hass: HomeAssistant, setup_cover, hass_ws_client, base_options, command
):
    """An admin passes the gate on every command."""
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, **command})
    msg = await client.receive_json()

    if command["type"] == "cover_time_based/stop_calibration":
        # Nothing is calibrating, so the handler's own error is what proves the
        # gate let the admin reach it — "unauthorized" would have come instead.
        assert msg["success"] is False
        assert msg["error"]["code"] == "failed"
    else:
        assert msg["success"] is True

    if command["type"] == "cover_time_based/get_config":
        assert msg["result"]["travel_time_open"] == base_options["travel_time_open"]

    if command["type"] == "cover_time_based/start_calibration":
        # The command really ran, so cancel the session it opened rather than
        # leaving its timers to outlive the test.
        await client.send_json(
            {
                "id": 2,
                "type": "cover_time_based/stop_calibration",
                "entity_id": ENTITY_ID,
                "cancel": True,
            }
        )
        await client.receive_json()


CALIBRATION_SERVICES = [
    ("start_calibration", {"attribute": "travel_time_open", "timeout": 1}),
    ("stop_calibration", {}),
]


@pytest.mark.parametrize(
    ("service", "data"),
    CALIBRATION_SERVICES,
    ids=[s for s, _ in CALIBRATION_SERVICES],
)
async def test_non_admin_cannot_call_calibration_services(
    hass: HomeAssistant, setup_cover, hass_read_only_user, service, data
):
    """A read-only user's calibration service call is refused with no side effect."""
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            service,
            {"entity_id": ENTITY_ID, **data},
            blocking=True,
            context=Context(user_id=hass_read_only_user.id),
        )
    await hass.async_block_till_done()
    assert hass.states.get("input_boolean.open_switch").state == "off"


async def test_admin_reaches_calibration_service(
    hass: HomeAssistant, setup_cover, hass_admin_user
):
    """An admin passes the gate: the handler itself reports no calibration running."""
    with pytest.raises(HomeAssistantError, match="No calibration in progress"):
        await hass.services.async_call(
            DOMAIN,
            "stop_calibration",
            {"entity_id": ENTITY_ID},
            blocking=True,
            context=Context(user_id=hass_admin_user.id),
        )
