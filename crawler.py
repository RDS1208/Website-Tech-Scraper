import httpx


async def fetch_page(client: httpx.AsyncClient, domain):
    return await client.get(
        f"http://{domain}/",
        follow_redirects=True,
        timeout=10,
    )
