"""Exercise every flow, HTTP validation branch, and error recovery."""
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_pocketsmith.const import DOMAIN
from custom_components.ha_pocketsmith.config_flow import _validate_developer_key

@pytest.fixture(autouse=True)
def recorder_dependency(hass):
    """Flows do not access the recorder; treat that unrelated dependency as loaded."""
    hass.config.components.add("recorder")


KEY = {"developer_key": "new-key"}
ERRORS = [
    (ValueError("invalid_auth"), "invalid_auth"),
    (ValueError("insufficient_permissions"), "insufficient_permissions"),
    (aiohttp.ClientError(), "cannot_connect"),
    (TimeoutError(), "cannot_connect"),
    (RuntimeError(), "unknown"),
]


@pytest.mark.parametrize("source", ["user", "reauth", "reconfigure"])
@pytest.mark.parametrize(("exception", "error"), [(None, None), *ERRORS])
async def test_flows_and_recovery(hass, source, exception, error):
    entry = None
    context = {"source": source}
    if source != "user":
        entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={"developer_key": "old"}, version=2, minor_version=1)
        entry.add_to_hass(hass)
        context["entry_id"] = entry.entry_id
    with (
        patch("custom_components.ha_pocketsmith.config_flow._validate_developer_key", new_callable=AsyncMock) as validate,
        patch("custom_components.ha_pocketsmith.async_setup_entry", return_value=True),
        patch.object(hass.config_entries, "async_reload", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context=context, data=entry.data if source == "reauth" else None)
        assert result["type"] is FlowResultType.FORM
        if exception is not None:
            validate.side_effect = exception
            result = await hass.config_entries.flow.async_configure(result["flow_id"], KEY)
            assert result["type"] is FlowResultType.FORM
            assert result["errors"] == {"base": error}
            validate.side_effect = None
        result = await hass.config_entries.flow.async_configure(result["flow_id"], KEY)
        if source == "user":
            assert result["type"] is FlowResultType.CREATE_ENTRY
            assert result["data"] == KEY
            assert result["result"].unique_id == DOMAIN
        else:
            assert result["type"] is FlowResultType.ABORT
            assert result["reason"] == f"{source}_successful"
            assert entry.data == KEY
            assert entry.unique_id == DOMAIN
        await hass.async_block_till_done()


async def test_duplicate(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data=KEY)
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_preserve_currency(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data=KEY, options={"active_currency": "USD"})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert "update_interval_hours" not in result["data_schema"].schema
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"enable_backfill": False})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"active_currency": "USD", "enable_backfill": False}
    assert entry.unique_id == DOMAIN


@pytest.mark.parametrize(("status", "expected"), [(200, None), (401, "invalid_auth"), (403, "insufficient_permissions"), (500, "http")])
async def test_validation_http(hass, status, expected):
    response = MagicMock(status=status)
    if status == 500:
        response.raise_for_status.side_effect = aiohttp.ClientError()
    session = MagicMock()
    session.get.return_value.__aenter__ = AsyncMock(return_value=response)
    session.get.return_value.__aexit__ = AsyncMock(return_value=False)
    with patch("custom_components.ha_pocketsmith.config_flow.async_get_clientsession", return_value=session):
        if expected == "http":
            with pytest.raises(aiohttp.ClientError):
                await _validate_developer_key(hass, "key")
        elif expected:
            with pytest.raises(ValueError, match=expected):
                await _validate_developer_key(hass, "key")
        else:
            await _validate_developer_key(hass, "key")
    assert session.get.call_args.kwargs["headers"]["Authorization"] == "Key key"
