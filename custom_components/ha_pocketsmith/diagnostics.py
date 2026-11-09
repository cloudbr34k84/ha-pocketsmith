"""Diagnostics for the PocketSmith integration."""
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_ACTIVE_CURRENCY, CONF_ENABLE_BACKFILL, PocketSmithConfigEntry

TO_REDACT = ["developer_key"]


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PocketSmithConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a PocketSmith config entry."""
    coordinator = entry.runtime_data.coordinator
    data = coordinator.data

    enriched = data.get("enriched_categories", [])
    monthly_events: dict[int, float] = data.get("monthly_events", {})
    monthly_transactions: dict[int, float] = data.get("monthly_transactions", {})
    budget: list[dict[str, Any]] = data.get("budget", [])

    null_budgeted = [c for c in enriched if c.get("budgeted") is None]
    null_actual = [c for c in enriched if c.get("actual") is None]
    bill_categories = [c for c in enriched if c.get("is_bill")]

    # Keep diagnostic counts while excluding account identifiers, names, amounts,
    # personal profile data and unknown fields returned by the remote service.
    packages_with_current_period = 0
    for pkg in budget:
        if not isinstance(pkg, dict):
            continue
        cat = pkg.get("category")
        if not cat:
            continue
        analysis = pkg.get("expense") or pkg.get("income")
        periods = analysis.get("periods", []) if analysis else []
        current = next((p for p in periods if p.get("current")), None)
        packages_with_current_period += current is not None

    return {
        "entry_data": async_redact_data({"developer_key": entry.data.get("developer_key")}, TO_REDACT),
        "options": {key: entry.options[key] for key in (CONF_ACTIVE_CURRENCY, CONF_ENABLE_BACKFILL) if key in entry.options},
        "summary": {
            "accounts_count": len(data.get("accounts", [])),
            "enriched_categories_count": len(enriched),
            "budget_packages_count": len(budget),
            "monthly_events_category_count": len(monthly_events),
            "monthly_transactions_category_count": len(monthly_transactions),
            "categories_with_null_budgeted": len(null_budgeted),
            "categories_with_null_actual": len(null_actual),
            "bill_categories_count": len(bill_categories),
            "bill_categories_with_events": sum(c.get("category_id") in monthly_events for c in bill_categories),
            "budget_packages_with_current_period": packages_with_current_period,
        },
    }
