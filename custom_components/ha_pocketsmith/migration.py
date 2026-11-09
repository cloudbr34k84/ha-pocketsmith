"""Preserve registered entity IDs when removing mutable names from unique IDs."""
import logging
import re

from homeassistant.core import callback
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, PocketSmithConfigEntry

_LOGGER = logging.getLogger(__name__)


@callback
def async_migrate_entity_ids(hass: HomeAssistant, entry: PocketSmithConfigEntry) -> None:
    """Migrate this entry only, without deleting history or conflicting entities."""
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.domain != "sensor" or entity.platform != DOMAIN:
            continue
        new_id = entity.unique_id
        if match := re.fullmatch(r"pocketsmith_(\d+)_.*_balance", new_id):
            new_id = f"pocketsmith_{match[1]}_balance"
        elif match := re.fullmatch(r"pocketsmith_(category|rollup)_(\d+)_.*", new_id):
            new_id = f"pocketsmith_{match[1]}_{match[2]}"
        if new_id == entity.unique_id:
            continue
        if registry.async_get_entity_id("sensor", DOMAIN, new_id):
            _LOGGER.warning("Preserving %s: target unique ID %s already exists", entity.entity_id, new_id)
            continue
        registry.async_update_entity(entity.entity_id, new_unique_id=new_id)
