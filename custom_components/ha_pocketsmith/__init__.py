"""PocketSmith Integration."""
import logging
import asyncio
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .actions import async_register_actions
from .backfill import async_trigger_backfill
from .const import (
    DEFAULT_UPDATE_INTERVAL_HOURS,
    CONF_POCKETSMITH_USER_ID,
    DOMAIN,
    BackfillState,
    PocketSmithData,
    PocketSmithConfigEntry,
)
from .coordinator import PocketSmithCoordinator
from .migration import async_migrate_entity_ids

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor", "button", "select"]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

async def async_migrate_entry(hass: HomeAssistant, entry: PocketSmithConfigEntry) -> bool:
    """Migrate old config entry versions to the current schema."""
    _LOGGER.debug("Migrating PocketSmith config entry from version %s.%s", entry.version, entry.minor_version)

    if entry.version == 1:
        # v1 → v2: no data changes; version bump establishes migration scaffold.
        hass.config_entries.async_update_entry(entry, version=2, minor_version=1)
        _LOGGER.info("Migrated PocketSmith config entry to version 2.1")

    return True


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register actions independently of config entry availability."""
    async_register_actions(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: PocketSmithConfigEntry) -> bool:
    """Set up PocketSmith from a config entry."""
    coordinator = PocketSmithCoordinator(
        hass,
        developer_key=entry.data["developer_key"],
        update_interval=timedelta(hours=DEFAULT_UPDATE_INTERVAL_HOURS),
        entry=entry,
    )
    await coordinator.async_config_entry_first_refresh()
    if CONF_POCKETSMITH_USER_ID not in entry.data:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_POCKETSMITH_USER_ID: coordinator.data["user_id"]}
        )
    entry.runtime_data = PocketSmithData(coordinator=coordinator, backfill=BackfillState())

    async_migrate_entity_ids(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await async_trigger_backfill(hass, coordinator, coordinator.data, entry, entry.runtime_data.backfill)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: PocketSmithConfigEntry) -> bool:
    """Handle unloading of an entry."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    task = entry.runtime_data.backfill.task
    if isinstance(task, asyncio.Task) and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    return True
