from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from test_summaries import billing_payload, day_rows

from custom_components.eon_polska import coordinator as module
from custom_components.eon_polska.client import ApiError, AuthError
from custom_components.eon_polska.sensor import SENSORS, EonSensor


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
