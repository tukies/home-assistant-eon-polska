import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.eon_polska import diagnostics, renewal
from custom_components.eon_polska.client import ApiError, AuthError, EonClient


@pytest.fixture
def timers(monkeypatch):
    scheduled = []

    def schedule(hass, delay, callback):
        cancel = Mock()
        scheduled.append(SimpleNamespace(delay=delay, callback=callback, cancel=cancel))
        return cancel

    monkeypatch.setattr(renewal, "async_call_later", schedule)
    return scheduled


def manager():
    client = SimpleNamespace(
        status_interval=30,
        keepalive_interval=90,
        session_status=AsyncMock(),
        keepalive=AsyncMock(),
    )
    coordinator = SimpleNamespace(
        client=client, lock=asyncio.Lock(), async_set_update_error=Mock()
    )
    entry = SimpleNamespace(async_start_reauth=Mock())
    return renewal.SessionRenewal(Mock(), entry, coordinator)


@pytest.mark.asyncio
async def test_independent_timers_follow_server_intervals(timers):
    runner = manager()
    runner.start()
    assert [timer.delay for timer in timers] == [30, 90]
    await timers[0].callback(None)
    runner.client.session_status.assert_awaited_once()
    runner.client.keepalive.assert_not_awaited()
    assert timers[-1].delay == 30
    await timers[1].callback(None)
    runner.client.keepalive.assert_awaited_once()
    assert timers[-1].delay == 90
    assert runner.diagnostic_data()["timers"]["status"]["successes"] == 1
    runner.stop()


@pytest.mark.asyncio
async def test_transient_failure_retries_without_reauth_and_recovers(timers):
    runner = manager()
    runner.client.keepalive.side_effect = [ApiError("unavailable"), None]
    runner.start()
    await timers[1].callback(None)
    assert timers[-1].delay == 60
    assert runner.diagnostic_data()["timers"]["keepalive"]["consecutive_failures"] == 1
    runner.entry.async_start_reauth.assert_not_called()
    await timers[-1].callback(None)
    assert timers[-1].delay == 90
    assert runner.diagnostic_data()["timers"]["keepalive"]["consecutive_failures"] == 0
    runner.stop()


@pytest.mark.asyncio
async def test_updated_timings_replace_pending_callbacks(timers):
    runner = manager()
    runner.start()
    old = timers[:]
    runner.client.status_interval = 10
    runner.client.keepalive_interval = 20
    runner.timings_changed()
    assert [timer.delay for timer in timers] == [30, 90, 10, 20]
    for timer in old:
        timer.cancel.assert_called_once()
        await timer.callback(None)
    runner.client.session_status.assert_not_awaited()
    runner.client.keepalive.assert_not_awaited()
    await timers[2].callback(None)
    runner.client.session_status.assert_awaited_once()
    assert timers[-1].delay == 10
    runner.stop()


@pytest.mark.asyncio
async def test_auth_failure_stops_both_timers_and_reauths_once(timers):
    runner = manager()
    runner.client.session_status.side_effect = AuthError("expired")
    runner.start()
    await timers[0].callback(None)
    assert not runner.diagnostic_data()["running"]
    timers[1].cancel.assert_called_once()
    runner.entry.async_start_reauth.assert_called_once_with(runner.hass)
    # A callback already queued before cancellation must not touch the session.
    await timers[1].callback(None)
    runner.client.keepalive.assert_not_awaited()
    assert len(timers) == 2


@pytest.mark.asyncio
async def test_stop_while_waiting_for_lock_prevents_request(timers):
    runner = manager()
    runner.start()
    await runner.coordinator.lock.acquire()
    task = asyncio.create_task(timers[0].callback(None))
    await asyncio.sleep(0)
    runner.stop()
    runner.coordinator.lock.release()
    await task
    runner.client.session_status.assert_not_awaited()
    assert len(timers) == 2


@pytest.mark.asyncio
async def test_diagnostics_exclude_entry_and_runtime_secrets(timers):
    runner = manager()
    runner.client = EonClient(None, ".AspNet.Cookies=cookie-secret", "agent-secret")
    runner.coordinator.client = runner.client
    runner.coordinator.renewal = runner
    entry = SimpleNamespace(
        runtime_data=runner.coordinator,
        data={"cookie": "cookie-secret", "ppes": ["private-ppe"]},
    )
    result = await diagnostics.async_get_config_entry_diagnostics(None, entry)
    text = json.dumps(result)
    for secret in ("cookie-secret", "agent-secret", "private-ppe", ".AspNet.Cookies"):
        assert secret not in text
    assert result["session"]["status_interval_seconds"] == 600
    # The exported snapshot cannot mutate the live diagnostic state.
    result["renewal"]["timers"]["status"]["successes"] = 99
    assert runner.diagnostic_data()["timers"]["status"]["successes"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entry", [SimpleNamespace(), SimpleNamespace(runtime_data=None)]
)
async def test_diagnostics_when_runtime_unavailable(entry):
    assert await diagnostics.async_get_config_entry_diagnostics(None, entry) == {
        "runtime_available": False
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", [False, True])
async def test_setup_wires_cookie_persistence_before_first_refresh(
    timers, monkeypatch, fail
):
    from http.cookies import SimpleCookie

    from test_client import Response, Session

    import custom_components.eon_polska as integration

    cookies = SimpleCookie()
    cookies[".AspNet.Cookies"] = "rotated-secret"
    session = Session(
        Response('{"Status":200,"Interval":15,"ResetInterval":25}', cookies=cookies),
        Response("", status=503) if fail else Response('{"Status":200}'),
        Response('{"Status":200}'),
    )
    session.close = AsyncMock()
    monkeypatch.setattr(integration.aiohttp, "ClientSession", lambda **kwargs: session)
    entry = SimpleNamespace(
        data={"cookie": ".AspNet.Cookies=old-secret", "user_agent": "browser"},
        async_on_unload=Mock(),
    )

    def save(entry, *, data):
        entry.data = data

    hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_update_entry=Mock(side_effect=save),
            async_forward_entry_setups=AsyncMock(),
            async_unload_platforms=AsyncMock(return_value=True),
        )
    )
    real_coordinator = integration.EonCoordinator

    def make_coordinator(hass, entry, client):
        coordinator = SimpleNamespace(
            hass=hass, entry=entry, client=client, lock=asyncio.Lock()
        )
        coordinator.save_cookie = lambda: real_coordinator.save_cookie(coordinator)
        coordinator.async_config_entry_first_refresh = client.renew
        return coordinator

    monkeypatch.setattr(integration, "EonCoordinator", make_coordinator)
    if fail:
        with pytest.raises(ApiError):
            await integration.async_setup_entry(hass, entry)
        session.close.assert_awaited_once()
        assert timers == []
    else:
        assert await integration.async_setup_entry(hass, entry)
        assert [timer.delay for timer in timers] == [15, 25]
        assert await integration.async_unload_entry(hass, entry)
        for timer in timers:
            timer.cancel.assert_called_once()
        session.close.assert_awaited_once()
    assert entry.data["cookie"] == ".AspNet.Cookies=rotated-secret"
    assert entry.data["user_agent"] == "browser"
    hass.config_entries.async_update_entry.assert_called_once()
