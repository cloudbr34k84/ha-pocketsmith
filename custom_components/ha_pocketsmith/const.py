"""Constants for the PocketSmith integration."""
from __future__ import annotations

from dataclasses import dataclass, field
from asyncio import Task
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry

if TYPE_CHECKING:
    from .coordinator import PocketSmithCoordinator

DOMAIN = "ha_pocketsmith"

CONF_ENABLE_BACKFILL = "enable_backfill"
CONF_ACTIVE_CURRENCY = "active_currency"
CONF_POCKETSMITH_USER_ID = "pocketsmith_user_id"

DEFAULT_UPDATE_INTERVAL_HOURS = 1
DEFAULT_ENABLE_BACKFILL = True
DEFAULT_CURRENCY = "AUD"

# Backfill status values
BACKFILL_STATUS_IDLE = "idle"
BACKFILL_STATUS_RUNNING = "running"
BACKFILL_STATUS_COMPLETE = "complete"
BACKFILL_STATUS_FAILED = "failed"


@dataclass
class BackfillState:
    """Mutable backfill progress shared between the background task and the sensor."""
    status: str = BACKFILL_STATUS_IDLE
    accounts_total: int = 0
    accounts_remaining: int = 0
    current_account: str | None = None
    task: Task[None] | None = field(default=None, repr=False)


@dataclass
class PocketSmithData:
    """Runtime data stored on the config entry."""
    coordinator: PocketSmithCoordinator
    backfill: BackfillState = field(default_factory=BackfillState)


type PocketSmithConfigEntry = ConfigEntry[PocketSmithData]
