"""HA actions (services) for the PocketSmith integration."""
import asyncio
import logging

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers.storage import Store
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .backfill import async_trigger_backfill
from .const import DOMAIN, BACKFILL_STATUS_RUNNING, CONF_ENABLE_BACKFILL, DEFAULT_ENABLE_BACKFILL
from .repairs import clear_backfill_failed_issue

_LOGGER = logging.getLogger(__name__)

_STORAGE_KEY = "%s.backfill" % DOMAIN
_STORAGE_VERSION = 1


def async_register_actions(hass: HomeAssistant) -> None:
    """Register all PocketSmith actions."""

    reset_lock = asyncio.Lock()

    def loaded_entries():
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries or any(entry.state is not ConfigEntryState.LOADED for entry in entries):
            raise ServiceValidationError("PocketSmith must be configured and loaded before running this action")
        return entries

    async def handle_refresh(call: ServiceCall) -> None:
        """Force an immediate coordinator refresh."""
        for entry in loaded_entries():
            coordinator = entry.runtime_data.coordinator
            try:
                await coordinator.async_request_refresh()
            except Exception as err:
                _LOGGER.exception("PocketSmith refresh action failed")
                raise HomeAssistantError("Unable to refresh PocketSmith data") from err
            _LOGGER.debug("PocketSmith manual refresh triggered")

    async def handle_reset_backfill(call: ServiceCall) -> None:
        """Clear progress and immediately start a sweep, without concurrent resets."""
        async with reset_lock:
            entries = loaded_entries()
            if any(entry.runtime_data.backfill.status == BACKFILL_STATUS_RUNNING for entry in entries):
                raise ServiceValidationError("A PocketSmith backfill is already running")
            if any(not entry.options.get(CONF_ENABLE_BACKFILL, DEFAULT_ENABLE_BACKFILL) for entry in entries):
                raise ServiceValidationError("Enable historical backfill before resetting it")
            store = Store(hass, _STORAGE_VERSION, _STORAGE_KEY)
            try:
                await store.async_remove()
                clear_backfill_failed_issue(hass)
            except Exception as err:
                _LOGGER.exception("PocketSmith backfill reset failed")
                raise HomeAssistantError("Unable to reset PocketSmith backfill progress") from err
            _LOGGER.info("PocketSmith backfill progress reset — starting a new sweep")

            for entry in loaded_entries():
                coordinator = entry.runtime_data.coordinator
                try:
                    await async_trigger_backfill(hass, coordinator, coordinator.data, entry, entry.runtime_data.backfill)
                except Exception as err:
                    _LOGGER.exception("PocketSmith backfill restart failed")
                    raise HomeAssistantError("Unable to restart PocketSmith backfill") from err

    async def handle_get_budget_summary(call: ServiceCall) -> ServiceResponse:
        """Return current budget summary as structured data."""
        for entry in loaded_entries():
            try:
                coordinator = entry.runtime_data.coordinator
                data = coordinator.data
                categories = data.get("enriched_categories", [])
                over_budget = [c for c in categories if c.get("over_budget")]
                return {
                    "total_categories": len(categories),
                    "over_budget_count": len(over_budget),
                    "over_budget_categories": [
                        {
                            "category_title": c.get("category_title"),
                            "parent_title": c.get("parent_title"),
                            "budgeted": c.get("budgeted"),
                            "actual": c.get("actual"),
                            "over_by": c.get("over_by"),
                            "percentage_used": c.get("percentage_used"),
                        }
                        for c in over_budget
                    ],
                    "uncategorised_count": data.get("uncategorised_count", 0),
                    "net_worth": sum(
                        acc.get("current_balance") or 0
                        for acc in data.get("accounts", [])
                    ),
                }
            except Exception as err:
                _LOGGER.exception("PocketSmith budget summary action failed")
                raise HomeAssistantError("Unable to read PocketSmith budget summary") from err
        return {}

    hass.services.async_register(DOMAIN, "refresh", handle_refresh)
    hass.services.async_register(DOMAIN, "reset_backfill", handle_reset_backfill)
    hass.services.async_register(
        DOMAIN,
        "get_budget_summary",
        handle_get_budget_summary,
        supports_response=SupportsResponse.ONLY,
    )
