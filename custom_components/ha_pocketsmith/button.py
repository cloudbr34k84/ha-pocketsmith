"""PocketSmith button platform."""
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PocketSmithCoordinator
from .sensor import _make_device_info

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PocketSmith button entities from a config entry."""
    coordinator: PocketSmithCoordinator = entry.runtime_data.coordinator
    async_add_entities([
        PocketSmithRefreshButton(coordinator),
        PocketSmithResetBackfillButton(coordinator, entry),
    ])


class PocketSmithRefreshButton(CoordinatorEntity, ButtonEntity):
    """Button that triggers an immediate PocketSmith data refresh."""

    _attr_has_entity_name = True
    _attr_translation_key = "refresh"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: PocketSmithCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = "pocketsmith_%s_refresh" % coordinator.data["user_id"]
        self._attr_device_info = _make_device_info(coordinator)

    async def async_press(self) -> None:
        """Handle button press — request coordinator refresh."""
        await self.coordinator.async_request_refresh()


class PocketSmithResetBackfillButton(CoordinatorEntity, ButtonEntity):
    """Button that resets historical backfill progress."""

    _attr_has_entity_name = True
    _attr_translation_key = "reset_backfill"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: PocketSmithCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = "pocketsmith_%s_reset_backfill" % coordinator.data["user_id"]
        self._attr_device_info = _make_device_info(coordinator)

    async def async_press(self) -> None:
        """Handle button press — clear backfill store and re-trigger."""
        await self.hass.services.async_call(
            DOMAIN, "reset_backfill", {}, blocking=True
        )
