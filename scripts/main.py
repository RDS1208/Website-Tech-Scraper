import argparse
import asyncio
import json
from contextlib import nullcontext
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit

import httpx
import pyarrow.parquet as pq

from .crawler import fetch_page
from .extractor import extract_page
from .paths import CHECKPOINT_PATH, RESULTS_PATH
from .redaction import redact_keys
from .tech import DETECTION_HEADERS, LIST_SIGNAL_FIELDS, added_technology_names, detect_result, linked_technology_additions


MAX_LINKED_PAGES = 4
HTTPS_FALLBACK_STATUSES = {403, 404, 409}
HTTPS_FALLBACK_ERRORS = {"ConnectError", "ConnectTimeout", "ReadTimeout", "RemoteProtocolError"}


def print_results():
    with RESULTS_PATH.open(encoding="utf-8") as file:
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


async def crawl_page(client, semaphore, address, *, same_host_only=False, follow_links=False):
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
        return redact_keys(result), None, []

    page_url = result["final_url"]
    signals, links = extract_page(response.text, page_url, follow_links=follow_links)
    result.update(signals)
    result["headers"] = {
        key: value for key, value in response.headers.items() if key in DETECTION_HEADERS
    }

    result = redact_keys(result)
    result["technologies"] = detect_result(result)
    return result, page_url, links


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
    homepage, page_url, links = await crawl_page(client, semaphore, domain, follow_links=follow_links)
    failed_url = homepage.get("failed_url") or homepage.get("final_url", "")
    if (
        page_url is None
        and "://" not in str(domain)
        and urlsplit(failed_url).scheme == "http"
        and (
            homepage.get("status_code") in HTTPS_FALLBACK_STATUSES
            or homepage["error_type"] in HTTPS_FALLBACK_ERRORS
        )
    ):
        https_page, https_url, https_links = await crawl_page(client, semaphore, f"https://{domain}/", follow_links=follow_links)
        attempt_fields = ("url", "final_url", "failed_url", "status_code", "error", "error_type", "retry_after")
        if https_url is None:
            homepage["https_attempt"] = {key: https_page[key] for key in attempt_fields if key in https_page}
        else:
            https_page["http_attempt"] = {key: homepage[key] for key in attempt_fields if key in homepage}
            homepage, page_url, links = https_page, https_url, https_links

    homepage.pop("url")
    result = {"domain": domain, **homepage}
    if page_url is None:
        return result

    if render_page is not None:
        await add_render_signals(result, render_page, page_url)

    if follow_links:
        pages = await asyncio.gather(
            *(crawl_page(client, semaphore, link, same_host_only=True) for link in links[:MAX_LINKED_PAGES])
        )
        result["linked_pages"] = [page for page, _, _ in pages]
        result["linked_added_technologies"] = linked_technology_additions(result)

    return result


async def crawl_domains(domains, results=None, *, render=False, follow_links=False):
    if results is None:
        results = [None] * len(domains)

    semaphore = asyncio.Semaphore(10)
    renderer_context = nullcontext()
    if render and any(result is None for result in results):
        from .browser import open_renderer

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
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", dir=path.parent, prefix=path.name + ".", suffix=".tmp",
                            encoding="utf-8", delete=False) as file:
        temporary_path = Path(file.name)
        json.dump(redact_keys(data), file, indent=2, ensure_ascii=False)
    try:
        temporary_path.replace(path)
    except PermissionError:
        raise SystemExit(
            f"Could not replace {path}. The complete output is saved in {temporary_path}. "
            f"Close any application using {path.name}, then replace it with the saved file."
        ) from None


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
    parser.add_argument("--follow-links", action="store_true", help=f"crawl up to {MAX_LINKED_PAGES} pages linked from each homepage")
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
        save_json(RESULTS_PATH, results)
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


