"""Portable session-code format shared by the browser extension and HA config flow."""

import base64
import json

PREFIX = "EON_SESSION_V1."
MAX_CODE_LENGTH = 65536
COOKIE_NAMES = {
    "ASP.NET_SessionId",
    ".ASPXAUTH",
    "LoginContext",
    "SessionInfo",
    "clientToken",
    "SERO",
    "SEROW",
    "dws01-level",
    "eon#lang",
    "website#sc_mode",
    "eon#sc_mode",
    "shell#lang",
}


class InvalidSessionCode(ValueError):
    """A helper code is malformed. Never include its value in errors."""


def encode_session(cookies, user_agent):
    selected = {}
    for item in cookies:
        if item["name"] in COOKIE_NAMES or item["name"].startswith(".AspNet."):
            # Browser cookies are ordered most-specific path first.
            selected.setdefault(item["name"], item["value"])
    payload = {
        "cookie": "; ".join(name + "=" + value for name, value in selected.items()),
        "user_agent": user_agent,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    code = PREFIX + base64.urlsafe_b64encode(raw).decode()
    decode_session(code)  # Validate before handing a credential to the user.
    return code


def decode_session(code):
    if not isinstance(code, str) or len(code) > MAX_CODE_LENGTH:
        raise InvalidSessionCode("Invalid sign-in code")
    code = code.strip()
    if not code.startswith(PREFIX):
        raise InvalidSessionCode("Invalid sign-in code")
    try:
        raw = base64.b64decode(code[len(PREFIX) :], altchars=b"-_", validate=True)
        data = json.loads(raw)
        if not isinstance(data, dict) or set(data) != {"cookie", "user_agent"}:
            raise ValueError
        if any(
            not isinstance(v, str) or not v or "\r" in v or "\n" in v
            for v in data.values()
        ):
            raise ValueError
        cookies = dict(part.strip().split("=", 1) for part in data["cookie"].split(";"))
        if not cookies.get(".AspNet.Cookies"):
            raise ValueError
        if len(data["user_agent"]) > 1024:
            raise ValueError
    except (ValueError, TypeError, UnicodeError) as err:
        raise InvalidSessionCode("Invalid sign-in code") from err
    return data
