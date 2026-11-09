"""Silver action failures and ownership of background work."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError

from custom_components.ha_pocketsmith import async_setup, async_unload_entry
from custom_components.ha_pocketsmith.const import DOMAIN, BackfillState, PocketSmithData
from custom_components.ha_pocketsmith.backfill import async_trigger_backfill


@pytest.mark.parametrize("broken", [False, True])
async def test_budget_summary(hass, broken):
    entry = MagicMock(state=ConfigEntryState.LOADED)
    entry.runtime_data.coordinator.data = None if broken else {"accounts": [{"current_balance": 12}], "enriched_categories": [{"over_budget": True, "actual": 5}]}
    await async_setup(hass, {})
    with patch.object(hass.config_entries, "async_entries", return_value=[entry]):
        if broken:
            with pytest.raises(HomeAssistantError):
                await hass.services.async_call(DOMAIN, "get_budget_summary", {}, blocking=True, return_response=True)
        else:
            result = await hass.services.async_call(DOMAIN, "get_budget_summary", {}, blocking=True, return_response=True)
            assert result["net_worth"] == 12
            assert result["over_budget_count"] == 1


async def test_setup_and_migration(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.ha_pocketsmith import async_setup_entry, async_migrate_entry
    from custom_components.ha_pocketsmith.migration import async_migrate_entity_ids
    from homeassistant.helpers import entity_registry as er

    entry = MockConfigEntry(domain=DOMAIN, data={"developer_key": "key"}, version=1)
    entry.add_to_hass(hass)
    assert await async_migrate_entry(hass, entry)
    assert entry.version == 2
    assert await async_migrate_entry(hass, entry)
    registry = er.async_get(hass)
    registry.async_get_or_create("button", DOMAIN, "button", config_entry=entry)
    async_migrate_entity_ids(hass, entry)
    with (
        patch("custom_components.ha_pocketsmith.PocketSmithCoordinator") as coordinator,
        patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock),
        patch("custom_components.ha_pocketsmith.async_trigger_backfill", new_callable=AsyncMock),
    ):
        coordinator.return_value.async_config_entry_first_refresh = AsyncMock()
        assert await async_setup_entry(hass, entry)
        assert entry.runtime_data.coordinator is coordinator.return_value


@pytest.mark.parametrize("failure", [False, True])
async def test_refresh_reports_coordinator_result(hass, failure):
    coordinator = MagicMock(last_update_success=not failure, last_exception=OSError("offline"))
    coordinator.async_request_refresh = AsyncMock()
    entry = MagicMock(state=ConfigEntryState.LOADED)
    entry.runtime_data = PocketSmithData(coordinator=coordinator)
    await async_setup(hass, {})
    with patch.object(hass.config_entries, "async_entries", return_value=[entry]):
        if failure:
            with pytest.raises(HomeAssistantError) as exc:
                await hass.services.async_call(DOMAIN, "refresh", {}, blocking=True)
            assert exc.value.translation_key == "refresh_failed"
        else:
            await hass.services.async_call(DOMAIN, "refresh", {}, blocking=True)
        coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.parametrize("unload_ok", [False, True])
async def test_unload_cancels_backfill_only_after_platforms_unload(hass, unload_ok):
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def sweep(*args):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    entry = MagicMock(options={"enable_backfill": True})
    entry.runtime_data = PocketSmithData(coordinator=MagicMock(), backfill=BackfillState())
    with patch("custom_components.ha_pocketsmith.backfill._run_backfill", side_effect=sweep):
        await async_trigger_backfill(hass, entry.runtime_data.coordinator, {}, entry, entry.runtime_data.backfill)
        await started.wait()
    task = entry.runtime_data.backfill.task
    with patch.object(hass.config_entries, "async_unload_platforms", return_value=unload_ok):
        assert await async_unload_entry(hass, entry) is unload_ok
    assert cancelled.is_set() is unload_ok
    if not unload_ok:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.parametrize("stage", ["storage", "start"])
async def test_reset_operational_failures(hass, stage):
    entry = MagicMock(state=ConfigEntryState.LOADED, options={"enable_backfill": True})
    entry.runtime_data = PocketSmithData(coordinator=MagicMock(), backfill=BackfillState())
    await async_setup(hass, {})
    with (
        patch.object(hass.config_entries, "async_entries", return_value=[entry]),
        patch("custom_components.ha_pocketsmith.actions.Store") as store,
        patch("custom_components.ha_pocketsmith.actions.clear_backfill_failed_issue"),
        patch("custom_components.ha_pocketsmith.actions.async_trigger_backfill", new_callable=AsyncMock) as trigger,
    ):
        store.return_value.async_remove = AsyncMock(side_effect=OSError() if stage == "storage" else None)
        trigger.side_effect = OSError() if stage == "start" else None
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(DOMAIN, "reset_backfill", {}, blocking=True)
