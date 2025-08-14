from httpx import AsyncClient

import asyncio

async def main():
    server_url = input("Enter server url: ")
    username = input("Enter username: ")
    password = input("Enter password: ")

    async with AsyncClient(base_url=server_url) as client:
        resp = await client.post(
            "/Users/AuthenticateByName",
            json={
                "Username": username,
                "Pw": password,
            },
            headers={
                # They don't use ANY of it for auth! And it throws 400 despite throwing exception in logs!
                # Also not documented as requirement of AuthenticateByName endpoint
                # UPD: DeviceId is used. Then, random device id to avoid collisions. You anyway need only single such service on a server.
                "Authorization": 'MediaBrowser Client="stub", Version="stub", DeviceId="gPJu1AKwNAQmH9wFwwbWSD3pHBD1tveF", Device="stub"'
            }
        )
        resp.raise_for_status()
        resp = resp.json()
        print(f"Token: {resp["AccessToken"]}")
        print(f"UserId: {resp["User"]["Id"]}")

if __name__ == '__main__':
    asyncio.run(main())
