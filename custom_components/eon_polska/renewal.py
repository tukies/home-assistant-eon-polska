"""Run E.ON's independent status and activity timers."""

import logging
from copy import deepcopy
from datetime import UTC, datetime, timedelta

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.event import async_call_later

from .client import ApiError, AuthError

_LOGGER = logging.getLogger(__name__)


class SessionRenewal:
    def __init__(self, hass, entry, coordinator):
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.client = coordinator.client
        self._cancel = {}
        self._stopped = True
        self._diagnostics = {
            name: {
                "successes": 0,
                "consecutive_failures": 0,
                "last_attempt_at": None,
                "last_success_at": None,
                "next_attempt_at": None,
                "last_outcome": None,
            }
            for name in ("status", "keepalive")
        }

    def diagnostic_data(self):
        return {"running": not self._stopped, "timers": deepcopy(self._diagnostics)}

    def start(self):
        self.stop()
        self._stopped = False
        for name in self._diagnostics:
            self._schedule(name)

    def stop(self):
        self._stopped = True
        for cancel in self._cancel.values():
            cancel()
        self._cancel.clear()
        for timer in self._diagnostics.values():
            timer["next_attempt_at"] = None

    def timings_changed(self):
        """Apply fresh server timings to pending timers after a daily renewal."""
        for name in list(self._cancel):
            self._cancel.pop(name)()
            self._schedule(name)

    def _schedule(self, name, *, retry=False):
        if self._stopped:
            return
        interval = (
            self.client.status_interval
            if name == "status"
            else self.client.keepalive_interval
        )
        delay = min(interval, 60) if retry else interval
        self._diagnostics[name]["next_attempt_at"] = (
            datetime.now(UTC) + timedelta(seconds=delay)
        ).isoformat()

        async def run(_now):
            if self._cancel.get(name) is not cancel:
                return
            self._cancel.pop(name, None)
            await self._run(name)

        cancel = async_call_later(self.hass, delay, run)
        self._cancel[name] = cancel

    async def _run(self, name):
        timer = self._diagnostics[name]
        retry = False
        async with self.coordinator.lock:
            if self._stopped:
                return
            timer["next_attempt_at"] = None
            timer["last_attempt_at"] = datetime.now(UTC).isoformat()
            try:
                if name == "status":
                    await self.client.session_status()
                else:
                    # The HA integration remains an active consumer even when
                    # nobody is typing in the web page.
                    await self.client.keepalive()
            except AuthError:
                timer["consecutive_failures"] += 1
                timer["last_outcome"] = "authentication_failed"
                self.stop()
                _LOGGER.warning(
                    "E.ON session expired during %s; download integration "
                    "diagnostics for request outcomes and cookie rotation times",
                    name,
                )
                self.coordinator.async_set_update_error(
                    ConfigEntryAuthFailed("E.ON session expired")
                )
                self.entry.async_start_reauth(self.hass)
            except ApiError:
                timer["consecutive_failures"] += 1
                timer["last_outcome"] = "service_or_network_error"
                retry = True
                _LOGGER.debug("E.ON %s temporarily unavailable; retry scheduled", name)
            else:
                timer["successes"] += 1
                timer["consecutive_failures"] = 0
                timer["last_success_at"] = datetime.now(UTC).isoformat()
                timer["last_outcome"] = "success"
        self._schedule(name, retry=retry)
