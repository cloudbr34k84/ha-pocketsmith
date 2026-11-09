"""Statistics, diagnostics, repairs, and health behavior."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.recorder.models import StatisticMeanType

from custom_components.ha_pocketsmith import diagnostics, repairs, statistics, system_health
from custom_components.ha_pocketsmith.const import DOMAIN


def test_statistics_snapshot(hass):
    data = {
        "user_id": 42, "uncategorised_count": 3,
        "accounts": [{"id": 1, "title": "Savings", "current_balance": 12, "currency_code": "AUD"},
                     {"id": 2, "current_balance": None}],
        "enriched_categories": [{"category_id": 10, "category_title": "Food", "actual": 5, "parent_title": "Living"},
                                {"category_id": 11, "actual": None},
                                {"category_id": 12, "actual": 0}],
    }
    with patch.object(statistics, "async_add_external_statistics") as insert:
        statistics.async_insert_statistics(hass, data)
        calls = insert.call_args_list
        assert len(calls) == 5
        assert calls[0].args[1]["statistic_id"] == f"{DOMAIN}:account_1_savings_balance"
        assert calls[0].args[1]["mean_type"] == StatisticMeanType.ARITHMETIC
        assert calls[1].args[1]["mean_type"] == StatisticMeanType.ARITHMETIC
        assert calls[2].args[1]["mean_type"] == StatisticMeanType.NONE
        assert calls[-1].args[1]["mean_type"] == StatisticMeanType.ARITHMETIC
        assert calls[0].args[2][0]["mean"] == 12
        assert calls[1].args[2][0]["mean"] == 12
        assert calls[2].args[2][0]["sum"] == 5
        assert calls[2].args[2][0]["last_reset"].day == 1
        assert calls[-1].args[2][0]["mean"] == 3
        insert.reset_mock()
        statistics.async_insert_statistics(hass, {})
        insert.assert_not_called()
    assert statistics._slug("!!!") == "unnamed"


async def test_diagnostics_redaction_and_budget_summary(hass, mock_entry):
    mock_entry.data = {"developer_key": "secret", "unexpected_private_field": "private-entry"}
    mock_entry.options = {"unexpected_private_option": "private-option"}
    mock_entry.runtime_data.coordinator.data = {
        "user": {"email": "private", "tell_a_friend_code": "code"},
        "enriched_categories": [{"category_id": 1, "category_title": "private-category", "is_bill": True, "actual": None, "budgeted": None}],
        "monthly_events": {1: 5},
        "budget": [None, {}, {"category": {"id": 1}, "expense": {"periods": [{"current": True}]}},
                   {"category": {"id": 2}}],
    }
    result = await diagnostics.async_get_config_entry_diagnostics(hass, mock_entry)
    assert result["entry_data"]["developer_key"] == "**REDACTED**"
    assert "private" not in str(result)
    assert "code" not in str(result)
    assert "secret" not in str(result)
    assert "private-entry" not in str(result)
    assert "private-option" not in str(result)
    assert "private-category" not in str(result)
    assert result["summary"]["bill_categories_with_events"] == 1
    assert result["summary"]["budget_packages_with_current_period"] == 1
    assert result["summary"]["categories_with_null_actual"] == 1


def test_repair_lifecycle(hass):
    with patch.object(repairs, "async_create_issue") as create, patch.object(repairs, "async_delete_issue") as delete:
        repairs.update_repair_issues(hass, {"uncategorised_count": 4})
        assert create.call_args.kwargs["translation_placeholders"] == {"count": "4"}
        repairs.update_repair_issues(hass, {"uncategorised_count": 0})
        delete.assert_called_with(hass, DOMAIN, repairs.ISSUE_UNCATEGORISED)
        repairs.raise_backfill_failed_issue(hass, "Savings")
        assert create.call_args.kwargs["translation_placeholders"] == {"account": "Savings"}
        repairs.clear_backfill_failed_issue(hass)
        delete.assert_called_with(hass, DOMAIN, repairs.ISSUE_BACKFILL_FAILED)


async def test_health_states(hass, mock_entry):
    registration = MagicMock()
    system_health.async_register(hass, registration)
    registration.async_register_info.assert_called_once_with(system_health.system_health_info)
    with patch.object(hass.config_entries, "async_entries", return_value=[]):
        assert await system_health.system_health_info(hass) == {"api_reachable": False}
    entry = MagicMock()
    del entry.runtime_data
    with patch.object(hass.config_entries, "async_entries", return_value=[entry]):
        assert await system_health.system_health_info(hass) == {"api_reachable": False}
    mock_entry.runtime_data.coordinator.data = {"user": {"last_activity_at": "today", "forecast_needs_recalculate": False}}
    with patch.object(hass.config_entries, "async_entries", return_value=[mock_entry]), patch.object(system_health.system_health, "async_check_can_reach_url", new_callable=AsyncMock, return_value=True):
        result = await system_health.system_health_info(hass)
        assert await result["api_reachable"]
        assert result["last_activity_at"] == "today"
