"""Read-only client for the private E.ON Polska web API."""

import json
import re
from copy import deepcopy
from datetime import UTC, datetime
from html.parser import HTMLParser

import aiohttp

from .parser import ReportError, parse_report

BASE = "https://eon.pl"
REFERER = BASE + "/mojeon/Historia-zuzycia"
DEFAULT_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"


class AuthError(Exception):
    """The browser session has expired or is invalid."""


class ApiError(Exception):
    """The API response was not usable."""


class ReportForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and attrs.get("name", "").startswith("FormData."):
            self.values[attrs["name"]] = attrs.get("value", "")
            if attrs.get("name") == "FormData.DateFrom":
                self.values["maxdate"] = attrs.get("data-maxdate")


class EonClient:
    def __init__(self, session, cookie, user_agent=DEFAULT_AGENT):
        self.session = session
        self.user_agent = user_agent
        self.on_cookie_change = None
        self.on_timing_change = None
        self.status_interval = 600
        self.keepalive_interval = 600
        self.diagnostics = {
            "started_at": datetime.now(UTC).isoformat(),
            "requests": 0,
            "cookie_updates": 0,
            "auth_cookie_rotations": 0,
            "auth_cookie_deletions": 0,
            "last_cookie_update_at": None,
            "last_auth_cookie_rotation_at": None,
            "last_auth_cookie_deletion_at": None,
            "last_http_success_at": None,
            "last_failure": None,
            "failure_counts": {},
            "recent_failures": [],
            "timing_fallbacks": 0,
        }
        # SimpleCookie.load rejects the complete browser string when an unrelated
        # analytics cookie contains unsupported syntax. Parse each pair ourselves.
        self.cookies = {}
        for pair in cookie.split(";"):
            if "=" not in pair:
                continue
            name, value = pair.strip().split("=", 1)
            if re.fullmatch(r"[!#$%&\'*+.^_`|~0-9a-zA-Z-]+", name) and not any(
                c in value for c in "\r\n"
            ):
                self.cookies.setdefault(name, value)
        if not self.cookies.get(".AspNet.Cookies"):
            raise AuthError("Missing E.ON authentication cookie")

    @property
    def cookie(self):
        return "; ".join(k + "=" + v for k, v in self.cookies.items())

    def diagnostic_data(self):
        """Return only explicitly selected metadata, never credentials or bodies."""
        return {
            **deepcopy(self.diagnostics),
            "status_interval_seconds": self.status_interval,
            "keepalive_interval_seconds": self.keepalive_interval,
        }

    def _failure(self, path, reason, *, http_status=None, application_status=None):
        failure = {
            "at": datetime.now(UTC).isoformat(),
            "endpoint": path,
            "reason": reason,
            "http_status": http_status,
            "application_status": application_status,
        }
        self.diagnostics["last_failure"] = failure
        counts = self.diagnostics["failure_counts"]
        counts[reason] = counts.get(reason, 0) + 1
        self.diagnostics["recent_failures"].append(failure)
        del self.diagnostics["recent_failures"][:-20]

    def _update_cookies(self, cookies):
        previous = self.cookies.copy()
        for name, morsel in cookies.items():
            if morsel["max-age"] == "0" or not morsel.value:
                self.cookies.pop(name, None)
            else:
                self.cookies[name] = morsel.value
        if previous == self.cookies:
            return
        now = datetime.now(UTC).isoformat()
        self.diagnostics["cookie_updates"] += 1
        self.diagnostics["last_cookie_update_at"] = now
        if previous.get(".AspNet.Cookies") != self.cookies.get(".AspNet.Cookies"):
            if self.cookies.get(".AspNet.Cookies"):
                self.diagnostics["auth_cookie_rotations"] += 1
                self.diagnostics["last_auth_cookie_rotation_at"] = now
            else:
                self.diagnostics["auth_cookie_deletions"] += 1
                self.diagnostics["last_auth_cookie_deletion_at"] = now
        # Persist before reading the body or issuing another request. Even an
        # error response can rotate/delete cookies.
        if self.on_cookie_change is not None:
            self.on_cookie_change()

    def _interval(self, value):
        # bool is an int in Python; reject it along with malformed/unbounded
        # values instead of scheduling a tight loop or an effectively dead timer.
        if type(value) is int and 1 <= value <= 86400:
            return value
        self.diagnostics["timing_fallbacks"] += 1
        return 600

    async def request(self, path, params=None):
        if not path.startswith("/mojeon/"):
            raise ApiError("Unexpected endpoint")
        self.diagnostics["requests"] += 1
        headers = {
            "Cookie": self.cookie,
            "User-Agent": self.user_agent,
            "Referer": REFERER,
        }
        try:
            async with self.session.get(
                BASE + path,
                params=params,
                headers=headers,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                self._update_cookies(response.cookies)
                if response.status in (301, 302, 303, 307, 308, 401, 403):
                    self._failure(
                        path, "http_auth_rejected", http_status=response.status
                    )
                    raise AuthError("E.ON requires a new browser session")
                if response.status != 200:
                    self._failure(path, "http_error", http_status=response.status)
                    raise ApiError(f"E.ON returned HTTP {response.status}")
                text = await response.text(encoding="utf-8-sig")
                self.diagnostics["last_http_success_at"] = datetime.now(UTC).isoformat()
                return text
        except (aiohttp.ClientError, TimeoutError) as err:
            self._failure(path, "network_or_timeout")
            # Never include request headers, cookie values or full URLs in errors.
            raise ApiError("Unable to reach E.ON") from err

    async def accounts(self):
        try:
            data = json.loads(await self.request("/mojeon/api/GetPHList"))
        except (ValueError, TypeError) as err:
            self._failure("/mojeon/api/GetPHList", "invalid_account_response")
            raise AuthError("Invalid account response") from err
        if not data.get("Partners"):
            self._failure("/mojeon/api/GetPHList", "no_authenticated_accounts")
            raise AuthError("Session has no authenticated accounts")
        points = []
        for partner in data["Partners"]:
            for account in partner.get("ContractAccounts", []):
                for point in account.get("PPEList", []):
                    if point.get("IsActive") and point.get("ProductType") == 300:
                        points.append(
                            {
                                "ph": partner["Id"],
                                "ku": account["Id"],
                                "ppe": point["Id"],
                                "name": point.get("PPEDisplayName") or point["Id"],
                            }
                        )
        return points

    async def _session_status(self, endpoint, params=None):
        try:
            data = json.loads(await self.request(endpoint, params))
        except ValueError as err:
            self._failure(endpoint, "invalid_session_response")
            raise ApiError("Invalid session-service response") from err
        if not isinstance(data, dict):
            self._failure(endpoint, "invalid_session_response")
            raise ApiError("Invalid session-service response")
        status = data.get("Status")
        if status in (401, 403, 404):
            self._failure(endpoint, "session_expired", application_status=status)
            raise AuthError("E.ON session expired")
        if status != 200:
            self._failure(
                endpoint,
                "session_service_error",
                application_status=status if type(status) is int else None,
            )
            raise ApiError("Session service temporarily unavailable")
        if endpoint.endswith("/resetauthorizationcookie"):
            previous = (self.status_interval, self.keepalive_interval)
            self.status_interval = self._interval(data.get("Interval"))
            self.keepalive_interval = self._interval(data.get("ResetInterval"))
            if (
                previous != (self.status_interval, self.keepalive_interval)
                and self.on_timing_change is not None
            ):
                self.on_timing_change()
        return data

    async def keepalive(self):
        return await self._session_status("/mojeon/api/keepalive")

    async def session_status(self):
        return await self._session_status("/mojeon/api/getuserstatus")

    async def renew(self):
        data = await self._session_status(
            "/mojeon/api/resetauthorizationcookie", {"path": REFERER}
        )
        # Reset alone does not exercise the website's inactivity keepalive path.
        await self.keepalive()
        await self.session_status()
        return data

    async def report_form(self):
        parser = ReportForm()
        parser.feed(await self.request("/mojeon/Historia-zuzycia"))
        if not parser.values.get("FormData.ItemId"):
            raise ApiError("E.ON report form not found")
        return parser.values

    async def report(self, point, start, end, item_id):
        text = await self.request(
            "/mojeon/api/sitecore/OzeReport/GenerateOzeReport",
            {
                "FormData.ItemId": item_id,
                "FormData.Ku": point["ku"],
                "FormData.SelectedPpe": point["ppe"],
                "FormData.DateFrom": start.strftime("%d.%m.%Y"),
                "FormData.DateTo": end.strftime("%d.%m.%Y"),
                "FormData.ReportType": "CSV",
            },
        )
        readings = parse_report(text)
        from .parser import WARSAW

        if any(not start <= r.start.astimezone(WARSAW).date() <= end for r in readings):
            raise ReportError("Report includes unexpected dates")
        return readings

    async def monthly(self, point, year):
        text = await self.request(
            "/mojeon/api/oze/GetOzeAgrData",
            {
                "ku": point["ku"],
                "ppe": point["ppe"],
                "yearFrom": max(2022, year - 1),
                "yearTo": year,
            },
        )
        try:
            return json.loads(text)
        except ValueError as err:
            raise ApiError("Invalid monthly response") from err

    async def billing(self, point, year):
        text = await self.request(
            "/mojeon/api/oze/GetBillingData",
            {
                "ku": point["ku"],
                "ppe": point["ppe"],
                "yearFrom": 2022,
                "yearTo": year,
                "cycle": 6,
            },
        )
        try:
            return json.loads(text)
        except ValueError as err:
            raise ApiError("Invalid billing response") from err
