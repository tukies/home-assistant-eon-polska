"""E.ON Polska hourly energy integration."""

import logging
from datetime import timedelta

import aiohttp
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.event import async_track_time_interval

from .client import ApiError, AuthError, EonClient
from .coordinator import EonCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry):
    session = aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar())
    try:
        client = EonClient(session, entry.data["cookie"], entry.data["user_agent"])
        coordinator = EonCoordinator(hass, entry, client)
        await coordinator.async_config_entry_first_refresh()
        entry.runtime_data = coordinator
        await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])
    except AuthError as err:
        await session.close()
        raise ConfigEntryAuthFailed(str(err)) from err
    except Exception:
        await session.close()
        raise

    async def renew(_now):
        try:
            async with coordinator.lock:
                await client.renew()
                coordinator.save_cookie()
        except AuthError:
            coordinator.async_set_update_error(
                ConfigEntryAuthFailed("E.ON session expired")
            )
            entry.async_start_reauth(hass)
        except ApiError:
            _LOGGER.debug("E.ON session renewal temporarily unavailable")

    entry.async_on_unload(async_track_time_interval(hass, renew, timedelta(minutes=10)))
    return True


async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR]):
        await entry.runtime_data.client.session.close()
        return True
    return False
