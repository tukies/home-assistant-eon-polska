"""Fetch a stable history window and reconcile revised historical statistics."""

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta

from homeassistant.components.recorder.models import StatisticMeanType
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import ApiError, AuthError
from .const import DOMAIN
from .parser import (
    WARSAW,
    ReportError,
    complete_history,
    date_windows,
    quality,
    statistics,
)
from .summaries import SummaryError, billing_summary, hourly_summary, monthly_summary

_LOGGER = logging.getLogger(__name__)


class EonCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(hours=24),
        )
        self.entry, self.client = entry, client
        self.lock = asyncio.Lock()

    def save_cookie(self):
        if self.client.cookie != self.entry.data["cookie"]:
            self.hass.config_entries.async_update_entry(
                self.entry, data={**self.entry.data, "cookie": self.client.cookie}
            )

    async def _async_update_data(self):
        async with self.lock:
            try:
                points = await self.client.accounts()
                selected = {p["ppe"]: p for p in points}
                form = await self.client.report_form()
                start = date.fromisoformat(self.entry.data["start_date"])
                end = datetime.now(WARSAW).date() - timedelta(days=2)
                if form.get("maxdate"):
                    end = min(
                        end, datetime.strptime(form["maxdate"], "%d.%m.%Y").date()
                    )
                if end < start:
                    raise ApiError("No report dates available yet")
                data = {}
                for ppe in self.entry.data["ppes"]:
                    if ppe not in selected:
                        raise ApiError(
                            "A configured supply point is no longer accessible"
                        )
                    point, readings = selected[ppe], []
                    for first, last in date_windows(start, end):
                        readings.extend(
                            await self.client.report(
                                point, first, last, form["FormData.ItemId"]
                            )
                        )
                    if not readings:
                        raise ApiError("No report data available")
                    readings = complete_history(readings, start, end)
                    data[ppe] = {
                        "point": point,
                        "readings": readings,
                        "quality": quality(readings),
                        "summary": hourly_summary(
                            readings, self.entry.data["include_estimates"]
                        ),
                        "refreshed_at": datetime.now(UTC),
                        "history_start": start,
                        "history_end": end,
                    }
                    for source, fetch, parse in (
                        ("monthly", self.client.monthly, monthly_summary),
                        ("billing", self.client.billing, billing_summary),
                    ):
                        try:
                            data[ppe][source] = parse(await fetch(point, end.year))
                        except (
                            ApiError,
                            SummaryError,
                            ValueError,
                            KeyError,
                            TypeError,
                            AttributeError,
                        ):
                            # Optional source failure never discards valid hourly energy.
                            data[ppe][source] = None
                            _LOGGER.debug("Optional E.ON %s data unavailable", source)
                await self.client.renew()
                self.save_cookie()
                # Required requests must succeed before statistics are scheduled.
                for ppe, result in data.items():
                    for direction in ("import", "export"):
                        metadata = {
                            "mean_type": StatisticMeanType.NONE,
                            "has_sum": True,
                            "name": f"{result['point']['name']} grid {direction}",
                            "source": DOMAIN,
                            "statistic_id": f"{DOMAIN}:{ppe}_{direction}",
                            "unit_class": "energy",
                            "unit_of_measurement": "kWh",
                        }
                        async_add_external_statistics(
                            self.hass,
                            metadata,
                            statistics(
                                result["readings"],
                                direction,
                                self.entry.data["include_estimates"],
                            ),
                        )
                return data
            except AuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except (ApiError, ReportError, ValueError) as err:
                raise UpdateFailed(str(err)) from err
