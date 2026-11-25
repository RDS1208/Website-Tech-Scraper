import argparse
import json
from collections import Counter

from .paths import RESULTS_PATH, TECHNOLOGY_GROUPS_PATH
from .redaction import redact_keys


SHOPIFY_COMPETITORS = (
    "Northbeam",
    "Littledata",
    "Elevar",
    "Triple Whale",
    "ThoughtMetric",
    "Attribuly",
    "Polar Analytics",
    "Analyzify",
)


def load_pages_by_domain(results_path):
    with open(results_path, encoding="utf-8") as file:
        results = json.load(file)

    pages_by_domain = {}
    for result in results:
        if "error" in result:
            continue

        pages = pages_by_domain.setdefault(result["domain"], [])
        pages.extend(page for page in [result, *result.get("linked_pages", [])] if "error" not in page)

    return pages_by_domain


def generate_report(results_path=RESULTS_PATH):
    pages_by_domain = load_pages_by_domain(results_path)

    counts = Counter()
    sites_with_technologies = 0
    for pages in pages_by_domain.values():
        technologies = {
            technology["name"]
            for page in pages
            for technology in page["technologies"]
        }
        counts.update(technologies)
        if technologies:
            sites_with_technologies += 1

    print(f"Websites accessed: {len(pages_by_domain)}")
    print(f"Accessible websites with technologies: {sites_with_technologies}")
    print(f"Distinct technologies and components: {len(counts)}")

    if not counts:
        print("No technologies found.")
        return

    print_grouped_technologies(counts)


def format_technology_count(name, count):
    unit = "website" if count == 1 else "websites"
    return f"{name} ({count} {unit})"


def print_grouped_technologies(counts):
    with TECHNOLOGY_GROUPS_PATH.open(encoding="utf-8") as file:
        config = json.load(file)

    groups = config["groups"]
    components = config["components"]
    known_names = {name for names in groups.values() for name in names}
    known_names.update(name for names in components.values() for name in names)
    groups["Other technologies"] = counts.keys() - known_names

    for group, names in groups.items():
        visible = [
            name for name in names
            if name in counts or any(child in counts for child in components.get(name, []))
        ]
        if not visible:
            continue

        print(f"\n{group}")
        for name in sorted(visible, key=lambda name: (-counts[name], name)):
            if name in counts:
                print(f"  {format_technology_count(name, counts[name])}")
            else:
                print(f"  {name} components")

            for child in components.get(name, []):
                if child in counts:
                    print(f"    {format_technology_count(child, counts[child])}")


def generate_shopify_report(results_path=RESULTS_PATH):
    stores = {}
    for domain, pages in load_pages_by_domain(results_path).items():
        findings = [
            (page, technology)
            for page in pages
            for technology in page["technologies"]
        ]
        if any(technology["name"] == "Shopify" for _, technology in findings):
            stores[domain] = [
                (page, technology)
                for page, technology in findings
                if technology["name"] in SHOPIFY_COMPETITORS
            ]

    print(f"Shopify stores detected: {len(stores)}")
    print(f"Stores with a tracked competitor detected: {sum(bool(matches) for matches in stores.values())}")
    print(f"Tracked competitors: {', '.join(SHOPIFY_COMPETITORS)}")

    for domain, matches in sorted(stores.items()):
        print(f"\n{redact_keys(domain)}")
        if not matches:
            print("  No tracked competitor detected.")
            continue

        for page, technology in matches:
            url = page.get("final_url") or page.get("url") or domain
            print(f"  {technology['name']} | {redact_keys(url)}")
            for evidence in technology.get("evidence", []):
                print(f"    {evidence['source']}: {redact_keys(evidence['value'])}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--shopify", action="store_true", help="report Shopify stores and competitor evidence")
    args = parser.parse_args()
    if args.shopify:
        generate_shopify_report()
    else:
        generate_report()
