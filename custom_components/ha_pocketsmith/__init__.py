"""PocketSmith Integration."""
import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import config_validation as cv

from .actions import async_register_actions
from .backfill import async_trigger_backfill
from .const import (
    DEFAULT_UPDATE_INTERVAL_HOURS,
    DOMAIN,
    BackfillState,
    PocketSmithData,
)
from .coordinator import PocketSmithCoordinator
from .migration import async_migrate_entity_ids

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor", "button", "select"]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type PocketSmithConfigEntry = ConfigEntry[PocketSmithData]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entry versions to the current schema."""
    _LOGGER.debug("Migrating PocketSmith config entry from version %s.%s", entry.version, entry.minor_version)

    if entry.version == 1:
        # v1 → v2: no data changes; version bump establishes migration scaffold.
        hass.config_entries.async_update_entry(entry, version=2, minor_version=1)
        _LOGGER.info("Migrated PocketSmith config entry to version 2.1")

    return True


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
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
    entry.runtime_data = PocketSmithData(coordinator=coordinator, backfill=BackfillState())

    async_migrate_entity_ids(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await async_trigger_backfill(hass, coordinator, coordinator.data, entry, entry.runtime_data.backfill)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: PocketSmithConfigEntry) -> bool:
    """Handle unloading of an entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
