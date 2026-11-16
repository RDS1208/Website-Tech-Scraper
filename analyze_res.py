import json
from collections import Counter
from urllib.parse import urlsplit

from tech import detect_tech


def main():
    with open("results.json", encoding="utf-8") as file:
        results = json.load(file)

    updated_count = 0
    signature_counts = Counter()

    for result in results:
        if "error" in result:
            continue

        script_urls = result["script_urls"]
        technologies = detect_tech(script_urls, result.get("meta_generator"))

        if technologies != result["technologies"]:
            result["technologies"] = technologies
            updated_count += 1

        if technologies:
            names = ", ".join(technology["name"] for technology in technologies)
            print(f"{result['domain']}: {names}")

            for technology in technologies:
                for evidence in technology["evidence"]:
                    print(f"  {technology['name']}: {evidence['value']}")

        page_host = urlsplit(result["final_url"]).hostname
        page_signatures = set()

        for script_url in script_urls:
            url = urlsplit(script_url)
            filename = url.path.rsplit("/", 1)[-1]

            if not url.hostname or not filename.endswith(".js"):
                continue

            if url.hostname == page_host:
                signature = url.path
            else:
                signature = f"{url.hostname} / {filename}"

            page_signatures.add(signature)

        signature_counts.update(page_signatures)

    if updated_count:
        with open("results.json", "w", encoding="utf-8") as file:
            json.dump(results, file, indent=2, ensure_ascii=False)

    print(f"\nUpdated {updated_count} domains.")
    print("\nMost common script signatures")

    for signature, count in signature_counts.most_common(20):
        print(f"{count:3} sites  {signature}")


if __name__ == "__main__":
    main()