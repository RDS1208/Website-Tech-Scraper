import argparse
import asyncio
import json

import httpx
import pyarrow.parquet as pq

from crawler import fetch_page
from extractor import extract_css_urls, extract_inline_scripts, extract_meta_generator, extract_script_urls
from tech import DETECTION_HEADERS, detect_tech


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

async def crawl_domain(client, semaphore, domain):
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

        script_urls = extract_script_urls(response.text, result["final_url"])
        meta_generator = extract_meta_generator(response.text)
        inline_scripts = extract_inline_scripts(response.text)
        css_urls = extract_css_urls(response.text, result["final_url"])
        headers = {key: value for key, value in response.headers.items() if key in DETECTION_HEADERS}

        result["script_urls"] = script_urls
        result["meta_generator"] = meta_generator
        result["inline_scripts"] = inline_scripts
        result["css_urls"] = css_urls
        result["headers"] = headers
        result["technologies"] = detect_tech(
            script_urls, meta_generator, inline_scripts, headers=headers, css_urls=css_urls
        )

    except httpx.HTTPError as error:
        result["error"] = str(error)

    return result


async def crawl_domains(domains):
    semaphore = asyncio.Semaphore(10)
    async with httpx.AsyncClient() as client:
        return await asyncio.gather(
            *(crawl_domain(client, semaphore, domain) for domain in domains)
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="path to parquet file")
    args = parser.parse_args()

    domains = read_domain(args.path)
    results = asyncio.run(crawl_domains(domains))

    with open("results.json", "w", encoding="utf-8") as file:
        json.dump(results, file, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()


