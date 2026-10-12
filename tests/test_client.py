import json
from http.cookies import SimpleCookie
from unittest.mock import Mock

import pytest

from custom_components.eon_polska.client import ApiError, AuthError, EonClient


class Response:
    def __init__(self, body, status=200, cookies=None):
        self.body, self.status, self.cookies = body, status, cookies or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def text(self, **kwargs):
        return self.body


class Session:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def test_cookie_parser_handles_browser_analytics_syntax():
    client = EonClient(Session(), '.AspNet.Cookies=secret; vuex={"x":1}; other=value')
    assert client.cookies[".AspNet.Cookies"] == "secret"
    assert client.cookies["vuex"] == '{"x":1}'


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [302, 401, 403])
async def test_expired_session_no_redirect_following(code):
    session = Session(Response("", code))
    with pytest.raises(AuthError):
        await EonClient(session, ".AspNet.Cookies=secret").accounts()
    assert session.calls[0][1]["allow_redirects"] is False


@pytest.mark.asyncio
async def test_anonymous_200_is_not_authenticated():
    client = EonClient(Session(Response('{"Partners":[]}')), ".AspNet.Cookies=secret")
    with pytest.raises(AuthError):
        await client.accounts()


@pytest.mark.asyncio
async def test_oze_only_and_renew_failure():
    payload = {
        "Partners": [
            {
                "Id": "ph",
                "ContractAccounts": [
                    {
                        "Id": "ku",
                        "PPEList": [
                            {"Id": "solar", "ProductType": 300, "IsActive": True},
                            {"Id": "normal", "ProductType": 100, "IsActive": True},
                        ],
                    }
                ],
            }
        ]
    }
    client = EonClient(
        Session(Response(json.dumps(payload)), Response('{"Status":404}')),
        ".AspNet.Cookies=secret",
    )
    assert [p["ppe"] for p in await client.accounts()] == ["solar"]
    with pytest.raises(AuthError):
        await client.renew()


@pytest.mark.asyncio
async def test_rotated_cookie_used_on_next_call():
    from http.cookies import SimpleCookie

    c = SimpleCookie()
    c[".AspNet.Cookies"] = "rotated"
    session = Session(
        Response('{"Status":200}', cookies=c),
        *[Response('{"Status":200}') for _ in range(5)],
    )
    client = EonClient(session, ".AspNet.Cookies=old")
    await client.renew()
    await client.renew()
    assert session.calls[1][1]["headers"]["Cookie"] == ".AspNet.Cookies=rotated"


@pytest.mark.asyncio
async def test_error_does_not_expose_session():
    client = EonClient(Session(Response("secret", 500)), ".AspNet.Cookies=secret")
    with pytest.raises(ApiError) as err:
        await client.renew()
    assert "secret" not in str(err.value)


def test_first_cookie_has_browser_path_priority():
    client = EonClient(Session(), ".AspNet.Cookies=specific; .AspNet.Cookies=general")
    assert client.cookies[".AspNet.Cookies"] == "specific"


@pytest.mark.asyncio
async def test_renew_exercises_keepalive_and_checks_auth_status():
    session = Session(*[Response('{"Status":200}') for _ in range(3)])
    await EonClient(session, ".AspNet.Cookies=synthetic").renew()
    assert [call[0].rsplit("/", 1)[-1] for call in session.calls] == [
        "resetauthorizationcookie",
        "keepalive",
        "getuserstatus",
    ]


@pytest.mark.asyncio
async def test_keepalive_expiry_is_not_reported_as_success():
    session = Session(Response('{"Status":200}'), Response('{"Status":401}'))
    with pytest.raises(AuthError):
        await EonClient(session, ".AspNet.Cookies=synthetic").renew()
    assert len(session.calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body", ["<html>service unavailable</html>", '{"Status":500}', "null", "{}"]
)
async def test_bad_renewal_service_response_is_not_invalid_credentials(body):
    with pytest.raises(ApiError):
        await EonClient(Session(Response(body)), ".AspNet.Cookies=synthetic").renew()


@pytest.mark.asyncio
async def test_server_intervals_are_available_even_when_later_renewal_fails():
    session = Session(
        Response('{"Status":200,"Interval":45,"ResetInterval":120}'),
        Response("unavailable", status=503),
    )
    client = EonClient(session, ".AspNet.Cookies=old")
    with pytest.raises(ApiError):
        await client.renew()
    assert client.status_interval == 45
    assert client.keepalive_interval == 120
    assert client.diagnostic_data()["last_failure"] == {
        "at": client.diagnostics["last_failure"]["at"],
        "endpoint": "/mojeon/api/keepalive",
        "reason": "http_error",
        "http_status": 503,
        "application_status": None,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, 0, -1, True, "45", 1.5, 86401, {}])
async def test_invalid_server_timings_use_safe_fallback(value):
    body = json.dumps({"Status": 200, "Interval": value, "ResetInterval": value})
    client = EonClient(Session(Response(body)), ".AspNet.Cookies=old")
    await client._session_status("/mojeon/api/resetauthorizationcookie")
    assert client.status_interval == client.keepalive_interval == 600
    assert client.diagnostics["timing_fallbacks"] == 2


@pytest.mark.asyncio
async def test_rotated_cookie_persisted_before_later_failure():
    cookies = SimpleCookie()
    cookies[".AspNet.Cookies"] = "replacement-secret"
    session = Session(
        Response('{"Status":200}', cookies=cookies), Response("", status=503)
    )
    client = EonClient(session, ".AspNet.Cookies=original-secret")
    saved = []
    client.on_cookie_change = lambda: saved.append(client.cookie)
    with pytest.raises(ApiError):
        await client.renew()
    assert saved == [".AspNet.Cookies=replacement-secret"]
    diagnostic = json.dumps(client.diagnostic_data())
    assert "original-secret" not in diagnostic
    assert "replacement-secret" not in diagnostic
    assert client.diagnostics["auth_cookie_rotations"] == 1


@pytest.mark.asyncio
async def test_cookie_persisted_even_when_response_body_read_fails():
    import aiohttp

    cookies = SimpleCookie()
    cookies[".AspNet.Cookies"] = "replacement"
    response = Response("", cookies=cookies)

    async def fail(**kwargs):
        raise aiohttp.ClientPayloadError("sensitive response content")

    response.text = fail
    client = EonClient(Session(response), ".AspNet.Cookies=original")
    saved = []
    client.on_cookie_change = lambda: saved.append(client.cookie)
    with pytest.raises(ApiError):
        await client.renew()
    assert saved == [".AspNet.Cookies=replacement"]
    assert "sensitive" not in json.dumps(client.diagnostic_data())


@pytest.mark.asyncio
async def test_cookie_deletion_persisted_before_auth_error():
    cookies = SimpleCookie()
    cookies[".AspNet.Cookies"] = ""
    cookies[".AspNet.Cookies"]["max-age"] = "0"
    client = EonClient(
        Session(Response("", status=401, cookies=cookies)), ".AspNet.Cookies=secret"
    )
    saved = []
    client.on_cookie_change = lambda: saved.append(client.cookie)
    with pytest.raises(AuthError):
        await client.renew()
    assert saved == [""]
    assert client.diagnostics["auth_cookie_deletions"] == 1
    assert client.diagnostics["auth_cookie_rotations"] == 0


@pytest.mark.asyncio
async def test_unchanged_cookies_do_not_write_config():
    cookies = SimpleCookie()
    cookies[".AspNet.Cookies"] = "same"
    client = EonClient(
        Session(Response('{"Status":200}', cookies=cookies)), ".AspNet.Cookies=same"
    )
    client.on_cookie_change = Mock()
    await client.session_status()
    client.on_cookie_change.assert_not_called()


@pytest.mark.asyncio
async def test_application_auth_status_recorded_without_response_content():
    client = EonClient(
        Session(Response('{"Status":401,"RedirectUrl":"private-secret"}')),
        ".AspNet.Cookies=secret",
    )
    with pytest.raises(AuthError):
        await client.session_status()
    diagnostic = client.diagnostic_data()
    assert diagnostic["last_failure"]["application_status"] == 401
    assert "secret" not in json.dumps(diagnostic)


@pytest.mark.asyncio
async def test_failure_history_is_bounded_and_survives_success():
    client = EonClient(
        Session(
            *[Response("private body", status=503) for _ in range(25)],
            Response('{"Status":200}'),
        ),
        ".AspNet.Cookies=secret",
    )
    for _ in range(25):
        with pytest.raises(ApiError):
            await client.keepalive()
    await client.keepalive()
    data = client.diagnostic_data()
    assert len(data["recent_failures"]) == 20
    assert data["failure_counts"] == {"http_error": 25}
    assert data["last_failure"]["http_status"] == 503
    assert "private body" not in json.dumps(data)


@pytest.mark.asyncio
async def test_timing_changes_notify_scheduler_once():
    body = '{"Status":200,"Interval":45,"ResetInterval":90}'
    client = EonClient(Session(Response(body), Response(body)), ".AspNet.Cookies=old")
    client.on_timing_change = Mock()
    await client._session_status("/mojeon/api/resetauthorizationcookie")
    await client._session_status("/mojeon/api/resetauthorizationcookie")
    client.on_timing_change.assert_called_once()
