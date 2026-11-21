import argparse
import asyncio
import json
from contextlib import nullcontext
from pathlib import Path

import httpx
import pyarrow.parquet as pq

from crawler import fetch_page
from extractor import extract_css_urls, extract_inline_scripts, extract_meta_generator, extract_script_urls
from tech import DETECTION_HEADERS, detect_tech


CHECKPOINT_PATH = Path("results.partial.tmp")


def print_results():
    with open("results.json", encoding="utf-8") as file:
        saved_results = json.load(file)

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

async def crawl_domain(client, semaphore, domain, render_page=None):
    result = {
        "domain": domain,
        "script_urls": [],
        "css_urls": [],
        "headers": {},
        "meta_generator": None,
        "inline_scripts": [],
        "technologies": [],
    }

    try:
        async with semaphore:
            print(f"Fetching {domain}")
            response = await fetch_page(client, domain)

        result["final_url"] = str(response.url)
        result["status_code"] = response.status_code
        response.raise_for_status()

    except httpx.HTTPError as error:
        result["error"] = str(error)
        return result

    result["script_urls"] = extract_script_urls(response.text, result["final_url"])
    result["meta_generator"] = extract_meta_generator(response.text)
    result["inline_scripts"] = extract_inline_scripts(response.text)
    result["css_urls"] = extract_css_urls(response.text, result["final_url"])
    result["headers"] = {
        key: value for key, value in response.headers.items() if key in DETECTION_HEADERS
    }

    if render_page is not None:
        rendered = await render_page(result["final_url"])
        if "error" in rendered:
            result["render_error"] = rendered["error"]
        elif rendered["status_code"] is None:
            result["render_error"] = "No HTTP response from browser navigation"
        elif not 200 <= rendered["status_code"] < 300:
            result["render_error"] = f"Browser navigation returned HTTP {rendered['status_code']}"
        else:
            for field in ("script_urls", "css_urls", "inline_scripts"):
                result[field] = list(dict.fromkeys(result[field] + rendered[field]))
            result["meta_generator"] = result["meta_generator"] or rendered["meta_generator"]

    result["technologies"] = detect_tech(
        result["script_urls"],
        result["meta_generator"],
        result["inline_scripts"],
        headers=result["headers"],
        css_urls=result["css_urls"],
    )

    return result


async def crawl_domains(domains, results=None, *, render=False):
    if results is None:
        results = [None] * len(domains)

    semaphore = asyncio.Semaphore(10)
    renderer_context = nullcontext()
    if render and any(result is None for result in results):
        from browser import open_renderer

        renderer_context = open_renderer()

    async with httpx.AsyncClient() as client, renderer_context as render_page:
        async def store_result(index, domain):
            results[index] = await crawl_domain(client, semaphore, domain, render_page)

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
        json.dump(data, file, indent=2, ensure_ascii=False)
    temporary_path.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="path to parquet file")
    parser.add_argument("--render", action="store_true", help="collect signals with Chromium")
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
        results = checkpoint["results"]

    try:
        asyncio.run(crawl_domains(domains, results, render=args.render))
        save_json(Path("results.json"), results)
    except KeyboardInterrupt:
        save_json(CHECKPOINT_PATH, {"domains": domains, "results": results, "render": args.render})
        completed = sum(result is not None for result in results)
        print(f"Stopped. Saved {completed}/{len(domains)} results to {CHECKPOINT_PATH}.")
        raise SystemExit(130) from None

    CHECKPOINT_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()


