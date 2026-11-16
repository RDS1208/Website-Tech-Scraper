import argparse
from crawler import fetch_page
import httpx
import pyarrow.parquet as pq

from extractor import extract_script_urls, extract_meta_generator
from tech import detect_tech
import json

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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="path to parquet file")
    args = parser.parse_args()

    domains = read_domain(args.path)
    # print(f"Loaded {len(domains)} domains")
    # print(domains[:5])

    results = []

    for domain in domains:
        print(f"Fetching {domain}")

        result = {
            "domain": domain,
            "script_urls": [],
            "meta_generator": None,
            "technologies": [],
        }

        try:
            response = fetch_page(domain)
            result["final_url"] = str(response.url)
            result["status_code"] = response.status_code
            response.raise_for_status()

            script_urls = extract_script_urls(response.text, result["final_url"])
            meta_generator = extract_meta_generator(response.text)

            result["script_urls"] = script_urls
            result["meta_generator"] = meta_generator
            result["technologies"] = detect_tech(script_urls, meta_generator)

        except httpx.HTTPError as error:
            result["error"] = str(error)

        results.append(result)

    with open("results.json", "w", encoding="utf-8") as file:
        json.dump(results, file, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()


