"""Coordinated refresh, pagination, outage, and recovery behavior."""
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed
from custom_components.ha_pocketsmith.coordinator import PocketSmithCoordinator


@pytest.fixture
def coordinator(hass, mock_entry):
    return PocketSmithCoordinator(hass, "key", timedelta(hours=1), mock_entry)


async def test_get_uses_headers_and_link(coordinator):
    response = MagicMock(status=200, headers={"Link": "next"})
    response.json = AsyncMock(return_value=[{"id": 1}])
    session = MagicMock()
    session.get.return_value.__aenter__ = AsyncMock(return_value=response)
    assert await coordinator._get(session, "url", "accounts") == ([{"id": 1}], "next")
    assert session.get.call_args.kwargs["headers"]["Authorization"] == "Key key"


async def test_all_fetchers(coordinator):
    tx = [{"category": None, "amount": 1}, {"category": {"id": 10}, "amount": -5}]
    with patch.object(coordinator, "_get", new_callable=AsyncMock) as get:
        get.return_value = ({"id": 42}, "")
        assert (await coordinator._fetch_user_id(MagicMock()))[0] == 42
        get.return_value = ({}, "")
        with pytest.raises(UpdateFailed):
            await coordinator._fetch_user_id(MagicMock())
        get.return_value = ([], "")
        assert await coordinator._fetch_accounts(MagicMock(), 42) == []
        for method in (coordinator._fetch_categories, coordinator._fetch_budget):
            get.side_effect = [([{"id": 1}], '<next>; rel="next"'), ([{"id": 2}], "")]
            assert len(await method(MagicMock(), 42)) == 2
        get.side_effect = [(tx, '<next>; rel="next"'), ([], "")]
        assert await coordinator._fetch_uncategorised_count(MagicMock(), 42) == 1
        get.side_effect = [(tx, '<next>; rel="next"'), ([], "")]
        assert await coordinator._fetch_monthly_transactions(MagicMock(), 42) == ({10: 5}, {10: 1})
        get.side_effect = [(tx, '<next>; rel="next"'), ([], "")]
        assert await coordinator._fetch_monthly_events(MagicMock(), 42) == {10: 5}


@pytest.mark.parametrize("failure", [None, aiohttp.ClientError(), TimeoutError()])
async def test_refresh_result_and_failures(coordinator, failure):
    with (
        patch.object(coordinator, "_fetch_user_id", new_callable=AsyncMock, return_value=(42, {"id": 42}), side_effect=failure),
        patch.object(coordinator, "_fetch_accounts", new_callable=AsyncMock, return_value=[]),
        patch.object(coordinator, "_fetch_uncategorised_count", new_callable=AsyncMock, return_value=0),
        patch.object(coordinator, "_fetch_categories", new_callable=AsyncMock, return_value=[]),
        patch.object(coordinator, "_fetch_budget", new_callable=AsyncMock, return_value=[]),
        patch.object(coordinator, "_fetch_monthly_transactions", new_callable=AsyncMock, return_value=({}, {})),
        patch.object(coordinator, "_fetch_monthly_events", new_callable=AsyncMock, return_value={}),
        patch("custom_components.ha_pocketsmith.coordinator.async_insert_statistics", side_effect=RuntimeError()),
        patch("custom_components.ha_pocketsmith.coordinator.update_repair_issues", side_effect=RuntimeError()),
    ):
        if failure:
            with pytest.raises(UpdateFailed):
                await coordinator._async_update_data()
        else:
            assert (await coordinator._async_update_data())["user_id"] == 42


@pytest.mark.parametrize("period", [
    {}, {"current": True},
    {"current": True, "forecast_amount": 10, "start_date": "bad", "end_date": "bad"},
    {"current": True, "forecast_amount": 10, "start_date": "2026-01-02", "end_date": "2026-01-01"},
])
def test_incomplete_budget_periods(coordinator, period):
    categories = [{"id": 1, "title": "Food", "parent_id": 99}, {"id": 2, "title": "Bills", "is_bill": True}]
    budget = [None, {}, {"category": {"id": 1}}, {"category": {"id": 1}, "expense": {"periods": [period]}},
              {"category": {"id": 2}}, {"category": {"id": 2}, "income": {"currency_code": "usd"}}]
    result = coordinator._build_enriched_categories(categories, budget, {}, {2: 10}, {})
    assert result[0]["budgeted"] is None
    assert result[0]["actual"] == 0
    assert result[1]["currency"] == "USD"


async def test_outage_availability_and_recovery_logged_once(coordinator, caplog):
    from custom_components.ha_pocketsmith.sensor import PocketSmithUncategorisedTransactions

    coordinator.async_set_updated_data({"user_id": 42, "uncategorised_count": 3})
    entity = PocketSmithUncategorisedTransactions(coordinator)
    with patch.object(coordinator, "_async_update_data", new_callable=AsyncMock) as fetch:
        fetch.side_effect = UpdateFailed("service offline")
        for _ in range(2):
            await coordinator.async_refresh()
            assert not entity.available
        assert caplog.text.count("Error fetching ha_pocketsmith data") == 1
        fetch.side_effect = None
        fetch.return_value = {"user_id": 42, "uncategorised_count": 0}
        for _ in range(2):
            await coordinator.async_refresh()
            assert entity.available
        assert caplog.text.count("Fetching ha_pocketsmith data recovered") == 1
