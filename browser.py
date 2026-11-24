import asyncio
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from playwright.async_api import Error, async_playwright

from extractor import (
    extract_css_urls,
    extract_inline_scripts,
    extract_meta_generator,
    extract_script_urls,
)


async def render_page(browser, url):
    resource_urls = {"script": set(), "stylesheet": set()}
    network_urls = set()

    def collect_resource(response):
        resource_type = response.request.resource_type
        if resource_type in resource_urls and (response.ok or response.status == 304):
            resource_urls[resource_type].add(response.url)

    def collect_network_request(request):
        if request.resource_type not in ("fetch", "xhr"):
            return
        endpoint = urlsplit(request.url)
        hostname = endpoint.hostname
        if endpoint.scheme in ("http", "https") and hostname:
            if ":" in hostname:
                hostname = f"[{hostname}]"
            network_urls.add(f"{endpoint.scheme}://{hostname}{endpoint.path or '/'}")

    context = await browser.new_context()
    try:
        context.on("request", collect_network_request)
        page = await context.new_page()
        page.on("response", collect_resource)
        response = await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=30000,
        )

        await asyncio.sleep(3)
        html = await page.content()
        final_url = page.url
        resource_urls["script"].update(extract_script_urls(html, final_url))
        resource_urls["stylesheet"].update(extract_css_urls(html, final_url))

        return {
            "final_url": final_url,
            "status_code": response.status if response is not None else None,
            "script_urls": sorted(resource_urls["script"]),
            "css_urls": sorted(resource_urls["stylesheet"]),
            "network_urls": sorted(network_urls),
            "inline_scripts": extract_inline_scripts(html),
            "meta_generator": extract_meta_generator(html),
        }
    finally:
        await context.close()


@asynccontextmanager
async def open_renderer():
    semaphore = asyncio.Semaphore(2)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        try:
            async def render(url):
                async with semaphore:
                    try:
                        return await render_page(browser, url)
                    except Error as error:
                        return {"error": str(error)}

            yield render
        finally:
            await browser.close()


async def render_pages(urls):
    async with open_renderer() as render:
        return await asyncio.gather(*(render(url) for url in urls))


async def inspect_page(url):
    result, = await render_pages([url])
    if "error" in result:
        print(f"Browser error: {result['error']}")
        return

    print(f"Final URL: {result['final_url']}")
    if result["status_code"] is not None:
        print(f"Status: {result['status_code']}")

    script_urls = result["script_urls"]
    print(f"Found {len(script_urls)} unique script URLs.")
    for script_url in script_urls:
        print(script_url)


if __name__ == "__main__":
    asyncio.run(inspect_page("https://youtube.com"))
