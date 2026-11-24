import argparse
import asyncio
import json
from contextlib import nullcontext
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pyarrow.parquet as pq

from crawler import fetch_page
from extractor import (
    extract_css_urls,
    extract_inline_scripts,
    extract_internal_links,
    extract_meta_generator,
    extract_script_urls,
)
from redaction import redact_keys
from tech import DETECTION_HEADERS, LIST_SIGNAL_FIELDS, added_technology_names, detect_result, linked_technology_additions


CHECKPOINT_PATH = Path("results.partial.tmp")
MAX_LINKED_PAGES = 3
HTTPS_FALLBACK_STATUSES = {403, 404, 409}
HTTPS_FALLBACK_ERRORS = {"ConnectError", "ConnectTimeout", "ReadTimeout", "RemoteProtocolError"}


def print_results():
    with open("results.json", encoding="utf-8") as file:
        saved_results = redact_keys(json.load(file))

    for result in saved_results:
        print(f"\n{result['domain']}")

        if "error" in result:
            print(f"  Error: {result['error']}")
            continue

        if not result["technologies"]:
            print("  No technologies detected.")
            continue

        for technology in result["technologies"]:
            print(f"  {technology['name']}")

            for evidence in technology["evidence"]:
                print(f"    {evidence['value']}")


def read_domain(path):
    table = pq.read_table(path, columns=["root_domain"])
    return table["root_domain"].to_pylist()


async def crawl_page(client, semaphore, address, *, same_host_only=False):
    result = {
        "url": address,
        "script_urls": [],
        "css_urls": [],
        "headers": {},
        "meta_generator": None,
        "inline_scripts": [],
        "technologies": [],
    }

    try:
        async with semaphore:
            print(f"Fetching {redact_keys(address)}")
            response = await fetch_page(client, address, same_host_only=same_host_only)

        result["final_url"] = str(response.url)
        result["status_code"] = response.status_code
        response.raise_for_status()

    except (httpx.HTTPError, httpx.InvalidURL) as error:
        result["error_type"] = type(error).__name__
        result["error"] = str(error) or result["error_type"]
        if isinstance(error, httpx.RequestError):
            result["failed_url"] = str(error.request.url)
        if isinstance(error, httpx.HTTPStatusError):
            retry_after = error.response.headers.get("retry-after")
            if retry_after:
                result["retry_after"] = retry_after
        return redact_keys(result), None

    result["script_urls"] = extract_script_urls(response.text, result["final_url"])
    result["meta_generator"] = extract_meta_generator(response.text)
    result["inline_scripts"] = extract_inline_scripts(response.text)
    result["css_urls"] = extract_css_urls(response.text, result["final_url"])
    result["headers"] = {
        key: value for key, value in response.headers.items() if key in DETECTION_HEADERS
    }

    result = redact_keys(result)
    result["technologies"] = detect_result(result)
    return result, response


async def add_render_signals(result, render_page, url):
    rendered = redact_keys(await render_page(url))
    status = rendered.get("status_code")
    if "error" in rendered:
        result["render_error"] = rendered["error"]
    elif status is None:
        result["render_error"] = "No HTTP response from browser navigation"
    elif not 200 <= status < 300:
        result["render_error"] = f"Browser navigation returned HTTP {status}"

    if "render_error" in result:
        return

    added_signals = {}
    for field in LIST_SIGNAL_FIELDS:
        existing = dict.fromkeys(result.get(field, []))
        added_signals[field] = [
            value for value in dict.fromkeys(rendered.get(field, [])) if value not in existing
        ]
        result[field] = list(existing) + added_signals[field]

    generator = rendered["meta_generator"]
    added_signals["meta_generator"] = generator if generator != result["meta_generator"] else None
    result["meta_generator"] = result["meta_generator"] or generator
    result["render_added_signals"] = added_signals

    httpx_technologies = result["technologies"]
    if any(added_signals.values()):
        result["technologies"] = detect_result(result)
    result["render_added_technologies"] = added_technology_names(httpx_technologies, result["technologies"])


async def crawl_domain(client, semaphore, domain, render_page=None, *, follow_links=False):
    homepage, response = await crawl_page(client, semaphore, domain)
    failed_url = homepage.get("failed_url") or homepage.get("final_url", "")
    if (
        response is None
        and "://" not in str(domain)
        and urlsplit(failed_url).scheme == "http"
        and (
            homepage.get("status_code") in HTTPS_FALLBACK_STATUSES
            or homepage["error_type"] in HTTPS_FALLBACK_ERRORS
        )
    ):
        https_page, https_response = await crawl_page(client, semaphore, f"https://{domain}/")
        attempt_fields = ("url", "final_url", "failed_url", "status_code", "error", "error_type", "retry_after")
        if https_response is None:
            homepage["https_attempt"] = {key: https_page[key] for key in attempt_fields if key in https_page}
        else:
            https_page["http_attempt"] = {key: homepage[key] for key in attempt_fields if key in homepage}
            homepage, response = https_page, https_response

    homepage.pop("url")
    result = {"domain": domain, **homepage}
    if response is None:
        return result

    page_url = str(response.url)
    if render_page is not None:
        await add_render_signals(result, render_page, page_url)

    if follow_links:
        links = extract_internal_links(response.text, page_url)[:MAX_LINKED_PAGES]
        pages = await asyncio.gather(
            *(crawl_page(client, semaphore, link, same_host_only=True) for link in links)
        )
        result["linked_pages"] = [page for page, _ in pages]
        result["linked_added_technologies"] = linked_technology_additions(result)

    return result


async def crawl_domains(domains, results=None, *, render=False, follow_links=False):
    if results is None:
        results = [None] * len(domains)

    semaphore = asyncio.Semaphore(10)
    renderer_context = nullcontext()
    if render and any(result is None for result in results):
        from browser import open_renderer

        renderer_context = open_renderer()

    async with httpx.AsyncClient() as client, renderer_context as render_page:
        async def store_result(index, domain):
            results[index] = await crawl_domain(client, semaphore, domain, render_page, follow_links=follow_links)

        pending = (
            store_result(index, domain)
            for index, domain in enumerate(domains)
            if results[index] is None
        )
        await asyncio.gather(*pending)

    return results


def save_json(path, data):
    temporary_path = path.with_name(path.name + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(redact_keys(data), file, indent=2, ensure_ascii=False)
    temporary_path.replace(path)


def print_linked_summary(results):
    pages = [page for result in results for page in result.get("linked_pages", [])]
    accessed = sum("error" not in page for page in pages)
    additions = {
        (result["domain"], name)
        for result in results
        for name in result.get("linked_added_technologies", [])
    }
    domains = {domain for domain, _ in additions}

    print(f"Internal pages accessed: {accessed}/{len(pages)}")
    print(f"Additional detections from internal pages: {len(additions)} across {len(domains)} domains")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="path to parquet file")
    parser.add_argument("--render", action="store_true", help="collect signals with Chromium")
    parser.add_argument("--follow-links", action="store_true", help="crawl up to three pages linked from each homepage")
    parser.add_argument("-resume", "--resume", action="store_true", help="continue a stopped crawl")
    args = parser.parse_args()

    domains = read_domain(args.path)
    results = [None] * len(domains)
    if args.resume:
        try:
            with CHECKPOINT_PATH.open(encoding="utf-8") as file:
                checkpoint = json.load(file)
        except (OSError, ValueError) as error:
            parser.error(f"could not load {CHECKPOINT_PATH}: {error}")

        if checkpoint["domains"] != domains or len(checkpoint["results"]) != len(domains):
            parser.error("saved progress does not match the domain list in the parquet file")
        if checkpoint.get("render", False) != args.render:
            parser.error("resume with the same --render setting as the stopped crawl")
        if checkpoint.get("follow_links", False) != args.follow_links:
            parser.error("resume with the same --follow-links setting as the stopped crawl")
        results = checkpoint["results"]

    try:
        asyncio.run(crawl_domains(domains, results, render=args.render, follow_links=args.follow_links))
        save_json(Path("results.json"), results)
    except KeyboardInterrupt:
        save_json(CHECKPOINT_PATH, {
            "domains": domains,
            "results": results,
            "render": args.render,
            "follow_links": args.follow_links,
        })
        completed = sum(result is not None for result in results)
        print(f"Stopped. Saved {completed}/{len(domains)} results to {CHECKPOINT_PATH}.")
        raise SystemExit(130) from None

    CHECKPOINT_PATH.unlink(missing_ok=True)
    if args.follow_links:
        print_linked_summary(results)


if __name__ == "__main__":
    main()


