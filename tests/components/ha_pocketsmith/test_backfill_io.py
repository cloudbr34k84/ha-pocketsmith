"""Historical import persistence, retries and transaction filtering."""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.components.recorder.models import StatisticMeanType
from custom_components.ha_pocketsmith import backfill
from custom_components.ha_pocketsmith.const import BackfillState


@pytest.mark.parametrize("mode", ["complete", "resume", "failed", "success", "empty"])
async def test_historical_import(hass, mode):
    state = BackfillState()
    today = backfill.dt_util.now().date()
    data = {"user_id": 42, "accounts": [{"id": 1, "title": "Savings", "current_balance": 100}],
            "categories": [{"id": 10, "title": "Living", "children": [{"id": 11, "title": "Food"}]}],
            "enriched_categories": [{"category_id": 11, "currency": "USD"}]}
    if mode == "empty":
        data = {}
    stored = {"all_done": mode == "complete", "completed_accounts": [1] if mode == "resume" else []}
    sweep = (None, {}) if mode == "failed" else ({today: -5}, {(11, today.year, today.month): 5, (10, today.year, today.month): 2})
    with (
        patch.object(backfill, "Store") as store,
        patch.object(backfill, "_sweep_account", new_callable=AsyncMock, return_value=sweep),
        patch.object(backfill, "async_add_external_statistics") as insert,
        patch.object(backfill, "raise_backfill_failed_issue") as repair,
        patch.object(backfill, "clear_backfill_failed_issue") as clear_repair,
    ):
        store.return_value.async_load = AsyncMock(return_value=stored)
        store.return_value.async_save = AsyncMock()
        await backfill._run_backfill_inner(hass, MagicMock(), data, state)
        assert state.status == ("failed" if mode == "failed" else "complete")
        if mode == "failed":
            repair.assert_called_once()
            clear_repair.assert_not_called()
            assert not store.return_value.async_save.call_args.args[0]["all_done"]
        if mode == "success":
            clear_repair.assert_called_once_with(hass)
            assert insert.call_count == 4
            assert [call.args[1]["mean_type"] for call in insert.call_args_list[:2]] == [StatisticMeanType.ARITHMETIC] * 2
            assert all(call.args[1]["mean_type"] == StatisticMeanType.NONE for call in insert.call_args_list[2:])
            assert all("unit_class" in call.args[1] for call in insert.call_args_list)
            assert insert.call_args_list[0].args[2][-1]["mean"] == 100
            assert store.return_value.async_save.call_args.args[0]["all_done"]


async def test_background_failure_and_skips(hass):
    state = BackfillState()
    with patch.object(backfill, "_run_backfill_inner", side_effect=RuntimeError()), patch.object(backfill, "raise_backfill_failed_issue") as repair:
        await backfill._run_backfill(hass, MagicMock(), {}, state)
    assert state.status == "failed"
    repair.assert_called_once_with(hass, "Unknown")
    for options, status in [({"enable_backfill": False}, "idle"), ({}, "running")]:
        entry = MagicMock(options=options)
        state = BackfillState(status=status)
        await backfill.async_trigger_backfill(hass, MagicMock(), {}, entry, state)
        assert state.task is None


async def test_backfill_with_no_historical_balance_rows(hass):
    state = BackfillState()
    data = {"user_id": 42, "accounts": [{"id": 1, "title": "Empty", "current_balance": 100}]}
    with (
        patch.object(backfill, "Store") as store,
        patch.object(backfill, "_sweep_account", new_callable=AsyncMock, return_value=({}, {})),
        patch.object(backfill, "async_add_external_statistics") as insert,
        patch.object(backfill, "clear_backfill_failed_issue"),
    ):
        store.return_value.async_load = AsyncMock(return_value={})
        store.return_value.async_save = AsyncMock()
        await backfill._run_backfill_inner(hass, MagicMock(), data, state)
    insert.assert_not_called()
    assert state.status == "complete"


async def test_sweep_filters_transactions(hass):
    rows = [{}, {"date": "invalid"}, {"date": "2026-01-01", "amount": -5, "category": {"id": 11}},
            {"transaction_date": "2026-01-01", "amount": 2, "category": {"id": 12, "is_transfer": True}},
            {"date": "2026-01-02", "category": {}}, {"date": "2026-01-03", "category": {"title": "missing id"}}]
    with patch.object(backfill, "_fetch_page_with_retry", side_effect=[(rows, '<next>; rel="next"', False), ([], "", False)]), patch.object(backfill.asyncio, "sleep", new_callable=AsyncMock):
        nets, totals = await backfill._sweep_account(hass, MagicMock(), MagicMock(), 1, {})
        assert nets[date(2026, 1, 1)] == -3
        assert totals == {(11, 2026, 1): 5}
    with patch.object(backfill, "_fetch_page_with_retry", return_value=(None, "", True)):
        assert await backfill._sweep_account(hass, MagicMock(), MagicMock(), 1, {}) == (None, {})


@pytest.mark.parametrize("status", [200, 401, 404, 429, 500])
async def test_page_retry(status):
    response = MagicMock(status=status, headers={"Retry-After": "invalid", "Link": "next"})
    response.json = AsyncMock(return_value=[{"id": 1}])
    session = MagicMock()
    session.get.return_value.__aenter__ = AsyncMock(return_value=response)
    with patch.object(backfill.asyncio, "sleep", new_callable=AsyncMock):
        if status == 401:
            with pytest.raises(ConfigEntryAuthFailed):
                await backfill._fetch_page_with_retry(session, MagicMock(), "url", "accounts")
        else:
            result = await backfill._fetch_page_with_retry(session, MagicMock(), "url", "accounts")
            assert result[2] is (status != 200)
            assert session.get.call_count == (backfill._MAX_RETRIES if status in (429, 500) else 1)


@pytest.mark.parametrize("error", [TimeoutError(), aiohttp.ClientError()])
async def test_page_network_retry(error):
    session = MagicMock()
    session.get.side_effect = error
    with patch.object(backfill.asyncio, "sleep", new_callable=AsyncMock):
        assert await backfill._fetch_page_with_retry(session, MagicMock(), "url", "accounts") == (None, "", True)
    assert session.get.call_count == backfill._MAX_RETRIES


async def test_backfill_logs_outage_and_recovery_once(caplog):
    coordinator = MagicMock()
    session = MagicMock()
    session.get.side_effect = aiohttp.ClientError()
    with patch.object(backfill.asyncio, "sleep", new_callable=AsyncMock):
        for _ in range(2):
            await backfill._fetch_page_with_retry(session, coordinator, "url", "accounts")
    response = MagicMock(status=200, headers={})
    response.json = AsyncMock(return_value=[])
    session.get.side_effect = None
    session.get.return_value.__aenter__ = AsyncMock(return_value=response)
    for _ in range(2):
        await backfill._fetch_page_with_retry(session, coordinator, "url", "accounts")
    assert caplog.text.count("historical API unavailable") == 1
    assert caplog.text.count("historical API reconnected") == 1
