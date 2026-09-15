"""Read-only client for the private E.ON Polska web API."""

import json
import re
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

    async def request(self, path, params=None):
        if not path.startswith("/mojeon/"):
            raise ApiError("Unexpected endpoint")
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
                if response.status in (301, 302, 303, 307, 308, 401, 403):
                    raise AuthError("E.ON requires a new browser session")
                if response.status != 200:
                    raise ApiError(f"E.ON returned HTTP {response.status}")
                for name, morsel in response.cookies.items():
                    if morsel["max-age"] == "0" or not morsel.value:
                        self.cookies.pop(name, None)
                    else:
                        self.cookies[name] = morsel.value
                text = await response.text(encoding="utf-8-sig")
                return text
        except (aiohttp.ClientError, TimeoutError) as err:
            # Never include request headers, cookie values or full URLs in errors.
            raise ApiError("Unable to reach E.ON") from err

    async def accounts(self):
        try:
            data = json.loads(await self.request("/mojeon/api/GetPHList"))
        except (ValueError, TypeError) as err:
            raise AuthError("Invalid account response") from err
        if not data.get("Partners"):
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
            raise ApiError("Invalid session-service response") from err
        if not isinstance(data, dict):
            raise ApiError("Invalid session-service response")
        status = data.get("Status")
        if status in (401, 403, 404):
            raise AuthError("E.ON session expired")
        if status != 200:
            raise ApiError("Session service temporarily unavailable")
        return data

    async def renew(self):
        data = await self._session_status(
            "/mojeon/api/resetauthorizationcookie", {"path": REFERER}
        )
        # Reset alone does not exercise the website's inactivity keepalive path.
        await self._session_status("/mojeon/api/keepalive")
        await self._session_status("/mojeon/api/getuserstatus")
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
