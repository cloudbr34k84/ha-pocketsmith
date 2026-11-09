"""Entity platforms expose coordinated snapshots and route user actions."""
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.util import dt as dt_util
from custom_components.ha_pocketsmith import binary_sensor, button, select, sensor


async def test_platform_entities(hass, mock_entry):
    coordinator = mock_entry.runtime_data.coordinator
    coordinator.data = {"user_id": 42, "user": {"id": 42, "name": "Brad"},
                        "accounts": [{"id": 1, "title": "Savings", "current_balance": 12}],
                        "enriched_categories": [{"category_id": 10, "category_title": "Living"},
                                                {"category_id": 11, "parent_id": 10, "actual": 5, "budgeted": 2, "over_budget": True}],
                        "uncategorised_count": 3, "categories": []}
    entities = []
    for platform in (sensor, binary_sensor, button, select):
        await platform.async_setup_entry(hass, mock_entry, entities.extend)
    assert len(entities) == 15
    for entity in entities:
        entity.hass = hass
        assert entity.unique_id
        assert entity.device_info
        for prop in ("name", "native_value", "native_unit_of_measurement", "extra_state_attributes", "is_on", "icon"):
            if prop in type(entity).__dict__:
                getattr(entity, prop)
    rollup = next(e for e in entities if isinstance(e, sensor.PocketSmithCategoryRollupSensor))
    assert rollup.native_value == 5
    assert rollup.extra_state_attributes["over_by"] == 3
    assert rollup.translation_placeholders == {"category": "Living"}
    account = next(e for e in entities if isinstance(e, sensor.PocketSmithSensor))
    assert account.translation_placeholders == {"account": "Savings"}
    coordinator.data["accounts"][0]["title"] = "Emergency fund"
    coordinator.data["enriched_categories"][0]["category_title"] = "Household"
    account.__dict__["name"] = "old name"
    rollup.__dict__["name"] = "old name"
    with patch("homeassistant.helpers.update_coordinator.CoordinatorEntity._handle_coordinator_update"):
        account._handle_coordinator_update()
        rollup._handle_coordinator_update()
    assert account.translation_placeholders == {"account": "Emergency fund"}
    assert rollup.translation_placeholders == {"category": "Household"}
    assert "name" not in account.__dict__
    assert "name" not in rollup.__dict__
    assert rollup.native_unit_of_measurement == "AUD"
    currency = next(e for e in entities if isinstance(e, select.PocketSmithActiveCurrencySelect))
    assert currency.options == ["AUD"]
    assert currency.current_option == "AUD"
    mock_entry.options = {"active_currency": "USD"}
    coordinator.data["accounts"][0]["currency_code"] = "USD"
    assert currency.current_option == "USD"
    with patch.object(hass.config_entries, "async_update_entry") as update:
        await currency.async_select_option("USD")
        assert update.call_args.kwargs["options"]["active_currency"] == "USD"
    with patch.object(type(hass.services), "async_call", new_callable=AsyncMock) as call:
        for entity in entities:
            if isinstance(entity, (button.PocketSmithRefreshButton, button.PocketSmithResetBackfillButton)):
                await entity.async_press()
        assert call.await_count == 2
    forecast = next(e for e in entities if isinstance(e, binary_sensor.PocketSmithForecastNeedsRecalculateBinarySensor))
    for age in (0, 25):
        coordinator.data["forecast_last_updated"] = dt_util.utcnow() - timedelta(hours=age)
        assert forecast.is_on is (age > 24)
    coordinator.data["accounts"] = []
    coordinator.data["enriched_categories"] = []
    coordinator.data["uncategorised_count"] = 0
    coordinator.data["user"] = {}
    assert currency.options == ["AUD"]
    assert currency.current_option == "AUD"
    assert rollup.native_value == 0
    assert rollup.translation_placeholders == {"category": "Household"}
    assert not rollup.extra_state_attributes["over_budget"]
    for entity in entities:
        for prop in ("name", "native_value", "extra_state_attributes", "is_on", "icon"):
            if prop in type(entity).__dict__:
                getattr(entity, prop)
