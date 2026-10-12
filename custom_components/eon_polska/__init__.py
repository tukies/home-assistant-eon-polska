"""E.ON Polska hourly energy integration."""

import aiohttp
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryAuthFailed

from .client import AuthError, EonClient
from .coordinator import EonCoordinator
from .renewal import SessionRenewal


async def async_setup_entry(hass, entry):
    session = aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar())
    try:
        client = EonClient(session, entry.data["cookie"], entry.data["user_agent"])
        coordinator = EonCoordinator(hass, entry, client)
        client.on_cookie_change = coordinator.save_cookie
        coordinator.renewal = SessionRenewal(hass, entry, coordinator)
        client.on_timing_change = coordinator.renewal.timings_changed
        await coordinator.async_config_entry_first_refresh()
        entry.runtime_data = coordinator
        await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])
    except AuthError as err:
        await session.close()
        raise ConfigEntryAuthFailed(str(err)) from err
    except Exception:
        await session.close()
        raise

    coordinator.renewal.start()
    entry.async_on_unload(coordinator.renewal.stop)
    return True


async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR]):
        entry.runtime_data.renewal.stop()
        await entry.runtime_data.client.session.close()
        return True
    return False
