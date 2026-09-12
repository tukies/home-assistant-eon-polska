from unittest.mock import AsyncMock

import pytest

from custom_components.eon_polska.browser_session import (
    InvalidSessionCode,
    decode_session,
    encode_session,
)


def test_session_roundtrip_filters_tracking_and_preserves_required_values():
    code = encode_session(
        [
            {"name": ".AspNet.Cookies", "value": "test-cookie"},
            {"name": "LoginContext", "value": '{"value":1}'},
            {"name": "_ga", "value": "tracking"},
        ],
        "Test browser",
    )
    auth = decode_session(code)
    assert auth["user_agent"] == "Test browser"
    assert ".AspNet.Cookies=test-cookie" in auth["cookie"]
    assert "_ga" not in auth["cookie"]


@pytest.mark.parametrize(
    "code", ["", "random", "EON_SESSION_V1.%%", "EON_SESSION_V1.e30=", "X" * 65537]
)
def test_invalid_codes_are_rejected_without_echo(code):
    with pytest.raises(InvalidSessionCode) as err:
        decode_session(code)
    assert str(err.value) == "Invalid sign-in code"


def test_code_rejects_header_injection():
    with pytest.raises(InvalidSessionCode):
        encode_session(
            [{"name": ".AspNet.Cookies", "value": "x\r\nInjected: secret"}], "browser"
        )


@pytest.mark.asyncio
async def test_config_flow_offers_helper_first():
    from custom_components.eon_polska.config_flow import ConfigFlow

    result = await ConfigFlow().async_step_user()
    assert result["menu_options"] == ["browser", "cookie"]


@pytest.mark.asyncio
async def test_browser_flow_passes_only_decoded_session(monkeypatch):
    from custom_components.eon_polska.config_flow import ConfigFlow

    flow = ConfigFlow()
    authenticate = AsyncMock(return_value={"step_id": "select"})
    monkeypatch.setattr(flow, "_authenticate", authenticate)
    code = encode_session(
        [{"name": ".AspNet.Cookies", "value": "synthetic"}], "browser"
    )
    assert await flow.async_step_browser({"session_code": code}) == {
        "step_id": "select"
    }
    authenticate.assert_awaited_once_with(
        {"cookie": ".AspNet.Cookies=synthetic", "user_agent": "browser"}
    )


@pytest.mark.asyncio
async def test_reauthentication_rejects_a_different_account(monkeypatch):
    from types import SimpleNamespace

    from custom_components.eon_polska import config_flow

    flow = config_flow.ConfigFlow()
    monkeypatch.setattr(
        flow, "_get_reauth_entry", lambda: SimpleNamespace(data={"ppes": ["expected"]})
    )
    client = AsyncMock()
    client.accounts.return_value = [{"ppe": "different"}]
    monkeypatch.setattr(config_flow, "EonClient", lambda *a: client)
    with pytest.raises(config_flow.AuthError, match="wrong_account"):
        await flow._reauthenticate({"cookie": "synthetic", "user_agent": "browser"})
    client.renew.assert_not_awaited()


def test_most_specific_cookie_wins():
    code = encode_session(
        [
            {"name": ".AspNet.Cookies", "value": "specific"},
            {"name": ".AspNet.Cookies", "value": "general"},
        ],
        "Browser",
    )
    assert decode_session(code)["cookie"] == ".AspNet.Cookies=specific"
