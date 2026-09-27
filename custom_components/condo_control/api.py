"""Small async client for the documented Condo Control resident API.

Only login and read operations are implemented. Tokens never leave this client.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import aiohttp

from .const import BASE_URL


class CondoControlError(Exception):
    """Base API error. Messages must not include credentials or response bodies."""


class CannotConnect(CondoControlError):
    """Network, server, or rate-limit failure."""


class InvalidAuth(CondoControlError):
    """Credentials or session rejected."""


class TwoFactorRequired(InvalidAuth):
    """The API requires an as-yet unsupported second-factor flow."""


class InvalidResponse(CondoControlError):
    """An unexpected response must never be mistaken for no packages."""


class PackagesNotEnabled(CondoControlError):
    """The account does not have packages enabled for this property."""


@dataclass(frozen=True)
class Workspace:
    """An accessible property and the user's identity there."""

    id: int
    name: str
    user_id: int
    resident_name: str
    packages_enabled: bool


@dataclass(frozen=True)
class Package:
    """One concierge log entry; it can represent multiple physical boxes."""

    reference: int
    description: str
    received_at: datetime
    is_picked_up: bool

    def as_attribute(self) -> dict[str, Any]:
        """Keep the API's local/offset timestamp semantics in the raw attributes."""
        return {
            "reference": self.reference,
            "description": self.description,
            "received_at": self.received_at.isoformat(),
            "is_picked_up": self.is_picked_up,
        }


def parse_workspace(data: Any) -> Workspace:
    """Validate identity without retaining tokens or unrelated account data."""
    if not isinstance(data, dict):
        raise InvalidResponse("Invalid property response")
    if (
        type(data.get("Id")) is not int
        or type(data.get("userId")) is not int
        or not isinstance(data.get("Title"), str)
        or not data["Title"]
        or type(data.get("PackagesEnabled")) is not bool
    ):
        raise InvalidResponse("Missing property identity or permissions")
    name = " ".join(
        str(data.get(key) or "").strip() for key in ("FirstName", "LastName")
    ).strip()
    return Workspace(
        data["Id"], data["Title"], data["userId"], name, data["PackagesEnabled"]
    )


def parse_packages(data: Any) -> tuple[Package, ...]:
    """Reject partial/malformed data and deduplicate stable package references."""
    if not isinstance(data, dict) or not isinstance(data.get("PackageList"), list):
        raise InvalidResponse("Missing package list")
    packages: dict[int, Package] = {}
    for row in data["PackageList"]:
        if (
            not isinstance(row, dict)
            or type(row.get("PackageNumber")) is not int
            or type(row.get("IsPickedUp")) is not bool
            or not isinstance(row.get("Description"), str)
            or not isinstance(row.get("DateRecieved"), str)
        ):
            raise InvalidResponse("Malformed package record")
        try:
            received = datetime.fromisoformat(row["DateRecieved"])
        except ValueError:
            raise InvalidResponse("Invalid package timestamp") from None
        item = Package(
            row["PackageNumber"], row["Description"], received, row["IsPickedUp"]
        )
        if item.reference in packages and packages[item.reference] != item:
            raise InvalidResponse("Conflicting package records")
        packages[item.reference] = item
    return tuple(packages.values())


class CondoControlClient:
    """Keep a separate bearer session for each configured account/property."""

    def __init__(
        self, session: aiohttp.ClientSession, email: str, password: str
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._token: str | None = None
        self._workspace: Workspace | None = None
        self._lock = asyncio.Lock()

    async def _request(self, path: str, payload: dict | None = None) -> Any:
        headers = {"Accept": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            async with self._session.request(
                "POST" if payload is not None else "GET",
                BASE_URL + path,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
                allow_redirects=False,
            ) as response:
                if response.status in (401, 403):
                    raise InvalidAuth("Authentication or access denied")
                if response.status == 429 or response.status >= 500:
                    raise CannotConnect(f"Service unavailable (HTTP {response.status})")
                if response.status >= 300:
                    raise InvalidResponse(f"Unexpected HTTP status {response.status}")
                try:
                    return await response.json()
                except ValueError, aiohttp.ContentTypeError:
                    raise InvalidResponse("Expected a JSON response") from None
        except aiohttp.ClientError, TimeoutError:
            raise CannotConnect("Unable to reach Condo Control") from None

    @staticmethod
    def _get_token(data: Any) -> str:
        if not isinstance(data, dict):
            raise InvalidResponse("Missing authentication response")
        if data.get("twofaEnabled"):
            raise TwoFactorRequired("Two-factor authentication is not supported yet")
        if not isinstance(data.get("access_token"), str) or not data["access_token"]:
            raise InvalidAuth("No access token returned")
        return data["access_token"]

    async def login(self) -> None:
        """Exchange credentials for an in-memory bearer token."""
        self._token = None
        data = await self._request(
            "api/Users/Login",
            {
                "Username": self._email,
                "Password": self._password,
                "ObjectType": None,
                "ObjectID": None,
                "DeviceID": None,
            },
        )
        self._token = self._get_token(data)

    async def list_workspaces(self) -> list[Workspace]:
        data = await self._request("api/Users/Workspaces")
        if not isinstance(data, list):
            raise InvalidResponse("Invalid property list")
        return [parse_workspace(row) for row in data]

    async def select_workspace(self, workspace_id: int) -> Workspace:
        data = await self._request(f"api/Users/Workspace?id={workspace_id}")
        workspace = parse_workspace(data)
        if workspace.id != workspace_id:
            raise InvalidResponse("The selected property does not match")
        if not workspace.packages_enabled:
            raise PackagesNotEnabled("Package access is not enabled at this property")
        self._token = self._get_token(data)
        self._workspace = workspace
        return workspace

    async def get_units(self) -> tuple[str, ...]:
        data = await self._request("api/MyAccount/GetMyUnits")
        if not isinstance(data, dict) or not isinstance(data.get("Units"), list):
            raise InvalidResponse("Invalid unit list")
        if any(
            not isinstance(unit, dict) or not isinstance(unit.get("UnitName"), str)
            for unit in data["Units"]
        ):
            raise InvalidResponse("Invalid unit record")
        return tuple(unit["UnitName"] for unit in data["Units"])

    async def get_packages(self) -> tuple[Package, ...]:
        """Refresh an expired session once, retaining account/property identity."""
        if self._workspace is None:
            raise InvalidAuth("Select a property before reading packages")
        async with self._lock:
            expected = self._workspace
            try:
                data = await self._request("api/Package/PackageList")
            except InvalidAuth:
                await self.login()
                selected = await self.select_workspace(expected.id)
                if selected.user_id != expected.user_id:
                    self._token = None
                    raise InvalidAuth("Resident identity changed") from None
                data = await self._request("api/Package/PackageList")
            return parse_packages(data)
