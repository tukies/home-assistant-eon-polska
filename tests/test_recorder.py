"""Exercise actual Home Assistant Recorder with a temporary SQLite database."""

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from homeassistant import loader
from homeassistant.bootstrap import async_from_config_dict
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticMeanType
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.components.recorder.tasks import SynchronizeTask
from homeassistant.core import HomeAssistant


@pytest.mark.asyncio
async def test_recorder_idempotent_and_correctable(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    loader.async_setup(hass)
    db = tmp_path / "test.db"
    try:
        assert await async_from_config_dict(
            {
                "homeassistant": {
                    "name": "Test",
                    "latitude": 0,
                    "longitude": 0,
                    "elevation": 0,
                    "time_zone": "Europe/Warsaw",
                    "unit_system": "metric",
                },
                "recorder": {"commit_interval": 0, "db_url": "sqlite:///" + str(db)},
            },
            hass,
        )
        await hass.async_start()
        recorder = get_instance(hass)

        async def flush():
            future = hass.loop.create_future()
            recorder.queue_task(SynchronizeTask(future))
            await future

        metadata = {
            "mean_type": StatisticMeanType.NONE,
            "has_sum": True,
            "name": "Test",
            "source": "eon_polska",
            "statistic_id": "eon_polska:synthetic_import",
            "unit_class": "energy",
            "unit_of_measurement": "kWh",
        }
        start = datetime(2026, 1, 1, tzinfo=UTC)
        data = [
            {"start": start + timedelta(hours=i), "sum": float(i)} for i in range(4)
        ]

        def read():
            with sqlite3.connect(db) as connection:
                return connection.execute(
                    "select count(*),max(sum) from statistics"
                ).fetchone()

        for _ in range(2):
            async_add_external_statistics(hass, metadata, data)
            await flush()
        assert await hass.async_add_executor_job(read) == (4, 3.0)
        corrected = [
            {**item, "sum": item["sum"] + (0.5 if i else 0)}
            for i, item in enumerate(data)
        ]
        async_add_external_statistics(hass, metadata, corrected)
        await flush()
        assert await hass.async_add_executor_job(read) == (4, 3.5)
    finally:
        await hass.async_stop()
