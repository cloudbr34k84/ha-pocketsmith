"""Regression coverage for Bronze lifecycle, errors and identity migration."""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from homeassistant.exceptions import ServiceValidationError, ConfigEntryAuthFailed
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_pocketsmith import async_setup, async_unload_entry
from custom_components.ha_pocketsmith.api import raise_for_api_error
from custom_components.ha_pocketsmith.const import DOMAIN
from custom_components.ha_pocketsmith.migration import async_migrate_entity_ids
from custom_components.ha_pocketsmith.sensor import PocketSmithCategorySensor, PocketSmithCategoryRollupSensor


@pytest.mark.parametrize("action", ["refresh", "reset_backfill", "get_budget_summary"])
@pytest.mark.parametrize("has_entry", [False, True])
async def test_actions_unavailable_entry(hass, action, has_entry):
    if has_entry:
        entry = MockConfigEntry(domain=DOMAIN, data={"developer_key": "key"})
        entry.add_to_hass(hass)
    await async_setup(hass, {})
    assert hass.services.has_service(DOMAIN, action)
    with pytest.raises(ServiceValidationError) as error:
        await hass.services.async_call(DOMAIN, action, {}, blocking=True, return_response=action == "get_budget_summary")
    assert error.value.translation_key == "entry_not_loaded"


async def test_actions_survive_unload(hass):
    await async_setup(hass, {})
    with patch.object(hass.config_entries, "async_unload_platforms", return_value=True):
        assert await async_unload_entry(hass, MagicMock())
    assert all(hass.services.has_service(DOMAIN, name) for name in ("refresh", "reset_backfill", "get_budget_summary"))


@pytest.mark.parametrize(("old", "new"), [
    ("pocketsmith_1_old_name_balance", "pocketsmith_1_balance"),
    ("pocketsmith_category_10_old_name", "pocketsmith_category_10"),
    ("pocketsmith_rollup_10_old_name", "pocketsmith_rollup_10"),
])
async def test_registry_migration_preserves_entity(hass, old, new):
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    entity = registry.async_get_or_create("sensor", DOMAIN, old, config_entry=entry, suggested_object_id="my_custom_entity")
    registry.async_update_entity(entity.entity_id, name="My custom name")
    async_migrate_entity_ids(hass, entry)
    async_migrate_entity_ids(hass, entry)
    migrated = registry.async_get(entity.entity_id)
    assert migrated.unique_id == new
    assert migrated.name == "My custom name"


async def test_migration_collision_retains_both(hass):
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    old = registry.async_get_or_create("sensor", DOMAIN, "pocketsmith_1_old_balance", config_entry=entry)
    new = registry.async_get_or_create("sensor", DOMAIN, "pocketsmith_1_balance", config_entry=entry)
    async_migrate_entity_ids(hass, entry)
    assert registry.async_get(old.entity_id).unique_id == old.unique_id
    assert registry.async_get(new.entity_id).unique_id == new.unique_id


def test_category_rename_and_reload():
    coordinator = MagicMock()
    assert PocketSmithCategorySensor(coordinator, {"category_id": 10, "category_title": "Before"}).unique_id == PocketSmithCategorySensor(coordinator, {"category_id": 10, "category_title": "After"}).unique_id
    assert PocketSmithCategoryRollupSensor(coordinator, 10, "Before", 1, "AUD").unique_id == PocketSmithCategoryRollupSensor(coordinator, 10, "After", 1, "AUD").unique_id


@pytest.mark.parametrize("status", [401, 403])
async def test_credentials_require_reauthentication(status):
    with pytest.raises(ConfigEntryAuthFailed):
        await raise_for_api_error(MagicMock(status=status), "user")


@pytest.mark.parametrize("state", ["running", "disabled", "ready"])
async def test_reset_preconditions_before_storage_mutation(hass, state):
    from homeassistant.config_entries import ConfigEntryState
    from custom_components.ha_pocketsmith.const import BackfillState, PocketSmithData

    entry = MagicMock()
    entry.state = ConfigEntryState.LOADED
    entry.options = {"enable_backfill": state != "disabled"}
    entry.runtime_data = PocketSmithData(coordinator=MagicMock(), backfill=BackfillState(status="running" if state == "running" else "complete"))
    await async_setup(hass, {})
    with (
        patch.object(hass.config_entries, "async_entries", return_value=[entry]),
        patch("custom_components.ha_pocketsmith.actions.Store") as store,
        patch("custom_components.ha_pocketsmith.actions.async_trigger_backfill", new_callable=AsyncMock) as trigger,
        patch("custom_components.ha_pocketsmith.actions.clear_backfill_failed_issue"),
    ):
        store.return_value.async_remove = AsyncMock()
        if state == "ready":
            await hass.services.async_call(DOMAIN, "reset_backfill", {}, blocking=True)
            store.return_value.async_remove.assert_awaited_once()
            trigger.assert_awaited_once()
        else:
            with pytest.raises(ServiceValidationError) as error:
                await hass.services.async_call(DOMAIN, "reset_backfill", {}, blocking=True)
            assert error.value.translation_key == ("backfill_running" if state == "running" else "backfill_disabled")
            store.assert_not_called()
            trigger.assert_not_called()


def test_entity_platforms_declare_parallel_updates():
    from custom_components.ha_pocketsmith import binary_sensor, button, select, sensor

    assert all(module.PARALLEL_UPDATES == 0 for module in (binary_sensor, button, select, sensor))


@pytest.mark.parametrize("failure", ["connection", "timeout", "auth", "permissions"])
async def test_setup_failure_classification(hass, failure):
    import aiohttp
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.exceptions import ConfigEntryNotReady
    from custom_components.ha_pocketsmith import async_setup_entry

    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={"developer_key": "key"}, state=ConfigEntryState.SETUP_IN_PROGRESS)
    entry.add_to_hass(hass)
    exception = {"connection": aiohttp.ClientError(), "timeout": TimeoutError(), "auth": ConfigEntryAuthFailed(), "permissions": ConfigEntryAuthFailed()}[failure]
    with (
        patch("custom_components.ha_pocketsmith.coordinator.PocketSmithCoordinator._get", side_effect=exception),
        patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock) as forward,
    ):
        with pytest.raises(ConfigEntryAuthFailed if failure in ("auth", "permissions") else ConfigEntryNotReady):
            await async_setup_entry(hass, entry)
        forward.assert_not_called()
