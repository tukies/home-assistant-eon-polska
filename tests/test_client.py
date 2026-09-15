import json

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
