import httpx

def fetch_page(domain):
    return httpx.get(
        f"http://{domain}/",
        follow_redirects=True,
        timeout=10,
    )