"""Read-only account smoke test; credentials and tokens stay in process memory."""

import asyncio
import getpass
import sys
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.condo_control.api import (  # noqa: E402
    CondoControlClient,
    CondoControlError,
)


async def main() -> None:
    email = input("Condo Control email: ").strip()
    password = getpass.getpass("Password: ")
    async with aiohttp.ClientSession() as session:
        client = CondoControlClient(session, email, password)
        try:
            await client.login()
            properties = await client.list_workspaces()
            for index, prop in enumerate(properties, start=1):
                print(f"{index}. {prop.name}")
            if not properties:
                print("No properties available.")
                return
            selection = int(input("Property number: ")) - 1
            if selection not in range(len(properties)):
                print("Invalid property selection.")
                return
            await client.select_workspace(properties[selection].id)
            packages = await client.get_packages()
        except CondoControlError as err:
            print(f"{type(err).__name__}: {err}")
            return
        print(f"Returned records: {len(packages)}")
        print(f"Waiting for pickup: {sum(not p.is_picked_up for p in packages)}")
        print(f"Already picked up: {sum(p.is_picked_up for p in packages)}")


if __name__ == "__main__":
    asyncio.run(main())
