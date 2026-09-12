"""Browser-session setup and account-bound reauthentication."""

from datetime import date, datetime, timedelta

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .browser_session import InvalidSessionCode, decode_session
from .client import DEFAULT_AGENT, ApiError, AuthError, EonClient
from .const import DOMAIN
from .parser import WARSAW


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        return self.async_show_menu(step_id="user", menu_options=["browser", "cookie"])

    async def async_step_browser(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                auth = decode_session(user_input["session_code"])
                result = await self._authenticate(auth)
                if result is not None:
                    return result
            except InvalidSessionCode:
                errors["base"] = "invalid_session_code"
            except AuthError:
                errors["base"] = "invalid_auth"
            except ApiError:
                errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="browser",
            data_schema=vol.Schema(
                {
                    vol.Required("session_code"): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def _authenticate(self, auth):
        async with aiohttp.ClientSession(
            cookie_jar=aiohttp.DummyCookieJar()
        ) as session:
            client = EonClient(session, auth["cookie"], auth["user_agent"])
            points = await client.accounts()
            if not points:
                return self.async_abort(reason="no_oze_accounts")
            await client.renew()
            self._auth = {"cookie": client.cookie, "user_agent": auth["user_agent"]}
            self._points = points
        return await self.async_step_select()

    async def async_step_cookie(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                return await self._authenticate(user_input)
            except AuthError:
                errors["base"] = "invalid_auth"
            except ApiError:
                errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="cookie",
            data_schema=vol.Schema(
                {
                    vol.Required("cookie"): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                    vol.Required("user_agent", default=DEFAULT_AGENT): str,
                }
            ),
            errors=errors,
        )

    async def async_step_select(self, user_input=None):
        errors = {}
        if user_input is not None:
            allowed = {p["ppe"] for p in self._points}
            try:
                start = date.fromisoformat(user_input["start_date"])
                if (
                    not date(2022, 1, 1)
                    <= start
                    <= datetime.now(WARSAW).date() - timedelta(days=2)
                ):
                    raise ValueError
                if not user_input["ppes"] or not set(user_input["ppes"]) <= allowed:
                    raise ValueError
            except (ValueError, TypeError):
                errors["base"] = "invalid_selection"
            else:
                used = {
                    p
                    for entry in self._async_current_entries()
                    for p in entry.data.get("ppes", [])
                }
                if used & set(user_input["ppes"]):
                    return self.async_abort(reason="already_configured")
                await self.async_set_unique_id("|".join(sorted(user_input["ppes"])))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="E.ON Polska", data={**self._auth, **user_input}
                )
        default = (datetime.now(WARSAW).date() - timedelta(days=32)).isoformat()
        return self.async_show_form(
            step_id="select",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "ppes", default=[self._points[0]["ppe"]]
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            multiple=True,
                            options=[
                                {"value": p["ppe"], "label": p["name"]}
                                for p in self._points
                            ],
                        )
                    ),
                    vol.Required(
                        "start_date", default=default
                    ): selector.DateSelector(),
                    vol.Required("include_estimates", default=False): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data):
        return self.async_show_menu(
            step_id="reauth", menu_options=["reauth_browser", "reauth_confirm"]
        )

    async def async_step_reauth_browser(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                auth = decode_session(user_input["session_code"])
                return await self._reauthenticate(auth)
            except InvalidSessionCode:
                errors["base"] = "invalid_session_code"
            except AuthError as err:
                errors["base"] = (
                    "wrong_account" if str(err) == "wrong_account" else "invalid_auth"
                )
            except ApiError:
                errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="reauth_browser",
            data_schema=vol.Schema(
                {
                    vol.Required("session_code"): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def _reauthenticate(self, auth):
        entry = self._get_reauth_entry()
        async with aiohttp.ClientSession(
            cookie_jar=aiohttp.DummyCookieJar()
        ) as session:
            client = EonClient(session, auth["cookie"], auth["user_agent"])
            points = await client.accounts()
            if not set(entry.data["ppes"]) <= {p["ppe"] for p in points}:
                raise AuthError("wrong_account")
            await client.renew()
            return self.async_update_reload_and_abort(
                entry,
                data_updates={
                    "cookie": client.cookie,
                    "user_agent": auth["user_agent"],
                },
            )

    async def async_step_reauth_confirm(self, user_input=None):
        errors = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            try:
                return await self._reauthenticate(
                    {
                        "cookie": user_input["cookie"],
                        "user_agent": entry.data["user_agent"],
                    }
                )
            except AuthError as err:
                errors["base"] = (
                    "wrong_account" if str(err) == "wrong_account" else "invalid_auth"
                )
            except ApiError:
                errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required("cookie"): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    )
                }
            ),
            errors=errors,
        )
