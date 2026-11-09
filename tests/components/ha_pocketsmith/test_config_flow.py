"""Exercise every flow, HTTP validation branch, and error recovery."""
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import json
import pytest
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_pocketsmith.const import DOMAIN, CONF_POCKETSMITH_USER_ID
from custom_components.ha_pocketsmith.config_flow import _validate_developer_key, _known_user_id

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
        entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={"developer_key": "old", CONF_POCKETSMITH_USER_ID: 42}, version=2, minor_version=1)
        entry.add_to_hass(hass)
        context["entry_id"] = entry.entry_id
    with (
        patch("custom_components.ha_pocketsmith.config_flow._validate_developer_key", new_callable=AsyncMock) as validate,
        patch("custom_components.ha_pocketsmith.async_setup_entry", return_value=True),
        patch.object(hass.config_entries, "async_reload", return_value=True),
    ):
        validate.return_value = 42
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
            assert result["data"] == {**KEY, CONF_POCKETSMITH_USER_ID: 42}
            assert result["result"].unique_id == DOMAIN
        else:
            assert result["type"] is FlowResultType.ABORT
            assert result["reason"] == f"{source}_successful"
            assert entry.data == {**KEY, CONF_POCKETSMITH_USER_ID: 42}
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
    response.json = AsyncMock(return_value={"id": 42})
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
            assert await _validate_developer_key(hass, "key") == 42
    assert session.get.call_args.kwargs["headers"]["Authorization"] == "Key key"


@pytest.mark.parametrize("profile", [{}, {"id": True}, {"id": "42"}, []])
async def test_validation_rejects_invalid_profile(hass, profile):
    response = MagicMock(status=200)
    response.json = AsyncMock(return_value=profile)
    session = MagicMock()
    session.get.return_value.__aenter__ = AsyncMock(return_value=response)
    with patch("custom_components.ha_pocketsmith.config_flow.async_get_clientsession", return_value=session):
        with pytest.raises(ValueError, match="invalid_response"):
            await _validate_developer_key(hass, "key")


async def test_validation_rejects_invalid_json(hass):
    response = MagicMock(status=200)
    response.json = AsyncMock(side_effect=json.JSONDecodeError("bad json", "invalid", 0))
    session = MagicMock()
    session.get.return_value.__aenter__ = AsyncMock(return_value=response)
    with patch("custom_components.ha_pocketsmith.config_flow.async_get_clientsession", return_value=session):
        with pytest.raises(ValueError, match="invalid_response"):
            await _validate_developer_key(hass, "key")


@pytest.mark.parametrize("source", ["reauth", "reconfigure"])
@pytest.mark.parametrize("original,expected", [(42, "wrong_account"), (None, "cannot_verify_account")])
async def test_replacement_rejects_unverified_identity(hass, source, original, expected):
    data = {"developer_key": "old"}
    if original is not None:
        data[CONF_POCKETSMITH_USER_ID] = original
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data=data, version=2, minor_version=1)
    entry.add_to_hass(hass)
    with patch("custom_components.ha_pocketsmith.config_flow._validate_developer_key", new_callable=AsyncMock, return_value=99):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": source, "entry_id": entry.entry_id}, data=entry.data if source == "reauth" else None)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], KEY)
    assert result["errors"] == {"base": expected}
    assert entry.data == data


async def test_legacy_identity_from_device_registry(hass):
    from homeassistant.helpers import device_registry as dr
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={"developer_key": "old"})
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(config_entry_id=entry.entry_id, identifiers={(DOMAIN, "42")})
    assert _known_user_id(hass, entry) == "42"
    registry.async_get_or_create(config_entry_id=entry.entry_id, identifiers={(DOMAIN, "99")})
    assert _known_user_id(hass, entry) is None


@pytest.mark.parametrize("source", ["reauth", "reconfigure"])
async def test_legacy_entry_accepts_same_account_key(hass, source):
    from homeassistant.helpers import device_registry as dr
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={"developer_key": "old"}, version=2, minor_version=1)
    entry.add_to_hass(hass)
    dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, identifiers={(DOMAIN, "42")})
    with patch("custom_components.ha_pocketsmith.config_flow._validate_developer_key", new_callable=AsyncMock, return_value=42), patch.object(hass.config_entries, "async_reload", return_value=True):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": source, "entry_id": entry.entry_id}, data=entry.data if source == "reauth" else None)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], KEY)
    assert result["reason"] == f"{source}_successful"
    assert entry.data == {**KEY, CONF_POCKETSMITH_USER_ID: 42}
