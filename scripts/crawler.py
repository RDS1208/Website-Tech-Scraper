import httpx


async def fetch_page(client: httpx.AsyncClient, address, *, same_host_only=False):
    address = str(address)
    url = address if address.startswith(("http://", "https://")) else f"http://{address}/"
    if not same_host_only:
        return await client.get(url, follow_redirects=True, timeout=10)

    request = client.build_request("GET", url, timeout=10)
    hostname = request.url.host
    for _ in range(client.max_redirects + 1):
        response = await client.send(request, follow_redirects=False)
        next_request = response.next_request
        if next_request is None:
            return response
        if next_request.url.host != hostname or next_request.url.scheme not in ("http", "https"):
            return response
        request = next_request

    raise httpx.TooManyRedirects("Too many redirects on an internal page", request=request)
