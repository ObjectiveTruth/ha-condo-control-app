"""Verify HTTP authentication, scope, renewal, and malformed-data handling."""

from contextlib import contextmanager
from copy import deepcopy
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)

from custom_components.condo_control.api import (
    CannotConnect,
    CondoControlClient,
    InvalidAuth,
    InvalidResponse,
    PackagesNotEnabled,
    TwoFactorRequired,
    parse_packages,
)
from custom_components.condo_control.const import BASE_URL

from .conftest import ROWS

WORKSPACE_RESPONSE = {
    "Id": 100,
    "Title": "Harbour Example",
    "userId": 200,
    "FirstName": "Alex",
    "LastName": "Example",
    "PackagesEnabled": True,
    "access_token": "workspace-token",
}


@contextmanager
def mock_http():
    mock = AiohttpClientMocker()
    with patch("aiohttp.ClientSession._request", new=mock.match_request):
        yield mock


def login_routes(mock):
    mock.post(BASE_URL + "api/Users/Login", json={"access_token": "login-token"})
    mock.get(BASE_URL + "api/Users/Workspace?id=100", json=WORKSPACE_RESPONSE)


async def test_scoped_token_and_expired_session_recovery():
    async with aiohttp.ClientSession() as session:
        client = CondoControlClient(session, "alex@example.com", "test-password")
        with mock_http() as mock:
            login_routes(mock)
            mock.get(
                BASE_URL + "api/Package/PackageList",
                side_effect=AsyncMock(
                    side_effect=[
                        AiohttpClientMockResponse(
                            "get", BASE_URL + "api/Package/PackageList", status=401
                        ),
                        AiohttpClientMockResponse(
                            "get", BASE_URL + "api/Package/PackageList", json=ROWS
                        ),
                    ]
                ),
            )
            await client.login()
            await client.select_workspace(100)
            packages = await client.get_packages()
            assert [p.is_picked_up for p in packages] == [False, True]
            package_calls = [
                call
                for call in mock.mock_calls
                if str(call[1]).endswith("api/Package/PackageList")
            ]
            assert len(package_calls) == 2
            assert all(
                call[3]["Authorization"] == "Bearer workspace-token"
                for call in package_calls
            )


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, InvalidAuth),
        (403, InvalidAuth),
        (429, CannotConnect),
        (503, CannotConnect),
    ],
)
async def test_error_status(status, error):
    async with aiohttp.ClientSession() as session:
        client = CondoControlClient(session, "alex@example.com", "test-password")
        with mock_http() as mock:
            mock.post(BASE_URL + "api/Users/Login", status=status)
            with pytest.raises(error):
                await client.login()


async def test_two_factor_does_not_use_provisional_token():
    async with aiohttp.ClientSession() as session:
        client = CondoControlClient(session, "alex@example.com", "test-password")
        with mock_http() as mock:
            mock.post(
                BASE_URL + "api/Users/Login",
                json={"access_token": "provisional", "twofaEnabled": True},
            )
            with pytest.raises(TwoFactorRequired):
                await client.login()
            assert client._token is None


@pytest.mark.parametrize(
    "payload",
    [None, {}, {"PackageList": None}, {"PackageList": [{"IsPickedUp": False}]}],
)
def test_missing_data_is_not_zero(payload):
    with pytest.raises(InvalidResponse):
        parse_packages(payload)


@pytest.mark.parametrize("status", [None, "false", 0])
def test_non_boolean_pickup_status_rejected(status):
    rows = deepcopy(ROWS)
    rows["PackageList"][0]["IsPickedUp"] = status
    with pytest.raises(InvalidResponse):
        parse_packages(rows)


def test_empty_and_duplicate_lists():
    assert parse_packages({"PackageList": []}) == ()
    rows = deepcopy(ROWS)
    rows["PackageList"].append(deepcopy(rows["PackageList"][0]))
    assert len(parse_packages(rows)) == 2
    rows["PackageList"][-1]["IsPickedUp"] = True
    with pytest.raises(InvalidResponse):
        parse_packages(rows)


async def test_disabled_packages():
    async with aiohttp.ClientSession() as session:
        client = CondoControlClient(session, "alex@example.com", "test-password")
        with mock_http() as mock:
            mock.get(
                BASE_URL + "api/Users/Workspace?id=100",
                json={**WORKSPACE_RESPONSE, "PackagesEnabled": False},
            )
            with pytest.raises(PackagesNotEnabled):
                await client.select_workspace(100)


async def test_workspace_and_units_discovery():
    async with aiohttp.ClientSession() as session:
        client = CondoControlClient(session, "alex@example.com", "test-password")
        with mock_http() as mock:
            mock.get(BASE_URL + "api/Users/Workspaces", json=[WORKSPACE_RESPONSE])
            mock.get(
                BASE_URL + "api/MyAccount/GetMyUnits",
                json={"Units": [{"UnitId": 123, "UnitName": "101"}]},
            )
            assert (await client.list_workspaces())[0].resident_name == "Alex Example"
            assert await client.get_units() == ("101",)
