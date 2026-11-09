"""HTTP errors and pagination contract."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from custom_components.ha_pocketsmith.api import parse_link_next, raise_for_api_error


@pytest.mark.parametrize("header,expected", [("", None), ('<https://api/next>; rel="next"', 'https://api/next'), ('broken; rel="next"', None), ('<first>; rel="prev", <next>; rel="next"', 'next')])
def test_pagination(header, expected):
    assert parse_link_next(header) == expected


@pytest.mark.parametrize("status", [200, 400, 401, 403, 404, 405, 429, 500, 503])
@pytest.mark.parametrize("invalid_json", [False, True])
async def test_http_errors(status, invalid_json):
    response = MagicMock(status=status)
    response.json = AsyncMock(return_value={"error": "bad request"}, side_effect=ValueError() if invalid_json else None)
    if status == 200:
        await raise_for_api_error(response, "accounts")
        response.raise_for_status.assert_called_once()
    else:
        with pytest.raises(ConfigEntryAuthFailed if status in (401, 403) else UpdateFailed):
            await raise_for_api_error(response, "accounts")
