from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from test_summaries import billing_payload, day_rows

from custom_components.eon_polska import coordinator as module
from custom_components.eon_polska.client import ApiError, AuthError
from custom_components.eon_polska.sensor import SENSORS, EonSensor


@pytest.fixture
async def recovery_coordinator(tmp_path, monkeypatch):
    hass = HomeAssistant(str(tmp_path))
    entry = SimpleNamespace(
        data={
            "start_date": "2024-01-02",
            "ppes": ["synthetic"],
            "include_estimates": False,
            "cookie": "synthetic",
        },
        async_on_unload=Mock(),
        async_start_reauth_if_available=Mock(),
        pref_disable_polling=False,
    )
    client = SimpleNamespace(
        cookie="synthetic",
        accounts=AsyncMock(return_value=[{"ppe": "synthetic", "name": "Test"}]),
        report_form=AsyncMock(
            return_value={"FormData.ItemId": "item", "maxdate": "02.01.2024"}
        ),
        report=AsyncMock(return_value=day_rows(date(2024, 1, 2))),
        monthly=AsyncMock(side_effect=ApiError("Optional service unavailable")),
        billing=AsyncMock(return_value=billing_payload()),
        renew=AsyncMock(),
    )
    monkeypatch.setattr(module, "async_add_external_statistics", Mock())
    coordinator = module.EonCoordinator(hass, entry, client)
    yield coordinator
    await coordinator.async_shutdown()
    await hass.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["accounts", "report", "renew"])
async def test_data_failure_backoff_and_recovery_restore_availability(
    recovery_coordinator, monkeypatch, phase
):
    coordinator = recovery_coordinator
    # Use HA's actual refresh lifecycle: it reschedules after the update method
    # returns/raises and propagates availability changes to all sensor listeners.
    scheduled = []
    schedule_refresh = coordinator._schedule_refresh

    def schedule():
        scheduled.append(
            timedelta(seconds=coordinator._retry_after)
            if coordinator._retry_after is not None
            else coordinator.update_interval
        )
        schedule_refresh()

    monkeypatch.setattr(coordinator, "_schedule_refresh", schedule)
    listener = Mock()
    remove_listener = coordinator.async_add_listener(listener)
    scheduled.clear()
    try:
        await coordinator.async_refresh()
        sensors = [EonSensor(coordinator, "synthetic", key) for key in SENSORS]
        assert all(s.available for s in sensors if s.spec.source != "monthly")
        assert scheduled.pop() == timedelta(hours=24)
        successful_data = coordinator.data
        module.async_add_external_statistics.reset_mock()

        failing_fetch = getattr(coordinator.client, phase)
        failing_fetch.side_effect = ApiError("Unable to reach E.ON")
        for minutes in (5, 10, 20, 30, 30, 30):
            await coordinator.async_refresh()
            assert scheduled.pop() == timedelta(minutes=minutes)
            assert coordinator._unsub_refresh is not None
            assert not coordinator.last_update_success
            assert all(not s.available for s in sensors)
            assert coordinator.data is successful_data
        module.async_add_external_statistics.assert_not_called()
        coordinator.entry.async_start_reauth_if_available.assert_not_called()

        failing_fetch.side_effect = None
        await coordinator.async_refresh()
        assert coordinator.last_update_success
        assert EonSensor(coordinator, "synthetic", "daily_import").available
        assert scheduled.pop() == timedelta(hours=24)
        assert module.async_add_external_statistics.call_count == 2

        # A new outage starts at five minutes rather than retaining the old cap.
        failing_fetch.side_effect = ApiError("Unable to reach E.ON")
        await coordinator.async_refresh()
        assert scheduled.pop() == timedelta(minutes=5)
    finally:
        remove_listener()


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["accounts", "monthly", "renew"])
async def test_auth_failure_during_backoff_stops_retries_and_starts_reauth(
    recovery_coordinator, monkeypatch, phase
):
    coordinator = recovery_coordinator
    scheduled = Mock(wraps=coordinator._schedule_refresh)
    monkeypatch.setattr(coordinator, "_schedule_refresh", scheduled)
    remove_listener = coordinator.async_add_listener(Mock())
    try:
        coordinator.client.accounts.side_effect = ApiError("Unable to reach E.ON")
        await coordinator.async_refresh()
        assert coordinator.last_exception.retry_after == 300
        assert coordinator._unsub_refresh is not None
        coordinator.client.accounts.side_effect = None
        getattr(coordinator.client, phase).side_effect = AuthError("Expired")
        scheduled.reset_mock()
        await coordinator.async_refresh()
        assert isinstance(coordinator.last_exception, ConfigEntryAuthFailed)
        coordinator.entry.async_start_reauth_if_available.assert_called_once_with(
            coordinator.hass
        )
        scheduled.assert_not_called()
        assert coordinator._unsub_refresh is None
        module.async_add_external_statistics.assert_not_called()
    finally:
        remove_listener()


@pytest.mark.asyncio
async def test_optional_failure_preserves_hourly_and_no_extra_statistics(
    tmp_path, monkeypatch
):
    hass = HomeAssistant(str(tmp_path))
    entry = SimpleNamespace(
        data={
            "start_date": "2024-01-02",
            "ppes": ["synthetic"],
            "include_estimates": False,
            "cookie": "synthetic",
        },
        async_on_unload=Mock(),
    )
    client = SimpleNamespace(
        cookie="synthetic",
        accounts=AsyncMock(return_value=[{"ppe": "synthetic", "name": "Test"}]),
        report_form=AsyncMock(
            return_value={"FormData.ItemId": "item", "maxdate": "02.01.2024"}
        ),
        report=AsyncMock(return_value=day_rows(date(2024, 1, 2))),
        monthly=AsyncMock(side_effect=ApiError("Unavailable")),
        billing=AsyncMock(return_value=billing_payload()),
        renew=AsyncMock(),
    )
    imported = []
    monkeypatch.setattr(
        module, "async_add_external_statistics", lambda h, m, s: imported.append((m, s))
    )
    co = module.EonCoordinator(hass, entry, client)
    try:
        co.data = await co._async_update_data()
        assert len(imported) == 2
        assert co.data["synthetic"]["monthly"] is None
        assert co.data["synthetic"]["billing"]["billing_import"] == 20
        assert EonSensor(co, "synthetic", "daily_import").available
        assert not EonSensor(co, "synthetic", "month_import").available
        for key in SENSORS:
            assert EonSensor(co, "synthetic", key).state_class is None
    finally:
        await co.async_shutdown()
        await hass.async_stop()


@pytest.mark.asyncio
async def test_optional_auth_failure_still_requires_reauthentication(
    tmp_path, monkeypatch
):
    hass = HomeAssistant(str(tmp_path))
    entry = SimpleNamespace(
        data={
            "start_date": "2024-01-02",
            "ppes": ["synthetic"],
            "include_estimates": False,
            "cookie": "synthetic",
        },
        async_on_unload=Mock(),
    )
    client = SimpleNamespace(
        cookie="synthetic",
        accounts=AsyncMock(return_value=[{"ppe": "synthetic", "name": "Test"}]),
        report_form=AsyncMock(
            return_value={"FormData.ItemId": "item", "maxdate": "02.01.2024"}
        ),
        report=AsyncMock(return_value=day_rows(date(2024, 1, 2))),
        monthly=AsyncMock(side_effect=AuthError("Expired")),
        billing=AsyncMock(),
        renew=AsyncMock(),
    )
    imported = Mock()
    monkeypatch.setattr(module, "async_add_external_statistics", imported)
    co = module.EonCoordinator(hass, entry, client)
    try:
        with pytest.raises(ConfigEntryAuthFailed):
            await co._async_update_data()
        imported.assert_not_called()
    finally:
        await co.async_shutdown()
        await hass.async_stop()
