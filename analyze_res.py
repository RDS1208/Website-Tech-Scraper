import json
from collections import Counter
from urllib.parse import urlsplit


from tech import detect_tech


def show_script_top(results, limit=20):
    show_url_top(results, "script_urls", "Most common script signatures", limit, suffix=".js")


def show_css_top(results, limit=20):
    show_url_top(results, "css_urls", "Most common stylesheet signatures", limit)


def show_url_top(results, field, title, limit, suffix=""):
    signature_counts = Counter()

    for result in results:
        if "error" in result:
            continue

        page_host = urlsplit(result["final_url"]).hostname
        page_signatures = set()

        for resource_url in result.get(field, []):
            url = urlsplit(resource_url)
            filename = url.path.rsplit("/", 1)[-1]

            if not url.hostname or not filename.endswith(suffix):
                continue

            if url.hostname == page_host:
                signature = url.path or "/"
            else:
                signature = f"{url.hostname} / {filename or '/'}"

            page_signatures.add(signature)

        signature_counts.update(page_signatures)

    print(f"\n{title}")
    for signature, count in signature_counts.most_common(limit):
        print(f"{count:3} sites  {signature}")


def show_header_top(results, limit=20):
    counts = Counter()
    for result in results:
        if "error" in result:
            continue
        for header, value in result.get("headers", {}).items():
            counts[f"{header.lower()}: {value}"] += 1

    print("\nMost common HTTP headers")
    for signature, count in counts.most_common(limit):
        print(f"{count:3} sites  {signature}")


def show_meta_top(results, limit=20):
    counts = Counter()

    for result in results:
        if "error" in result:
            continue

        generator = result.get("meta_generator")
        if not isinstance(generator, str):
            continue

        generator = generator.strip()
        if generator:
            counts[generator] += 1

    print("\nMost common meta generators")
    for generator, count in counts.most_common(limit):
        print(f"{count:3} sites  {generator}")


def show_inline_top(results, limit=20):
    counts = Counter()
    examples = {}

    for result in results:
        if "error" in result:
            continue

        page_signatures = set()
        for script in result.get("inline_scripts") or []:
            signature = " ".join(script.split())
            if not signature or signature in page_signatures:
                continue

            page_signatures.add(signature)
            examples.setdefault(signature, script)
            counts[signature] += 1

    print("\nMost common inline scripts")
    for signature, count in counts.most_common(limit):
        print(f"{count:3} sites  {examples[signature][:300]}")


def main():
    with open("results.json", encoding="utf-8") as file:
        results = json.load(file)

    updated_count = 0

    for result in results:
        if "error" in result:
            continue

        technologies = detect_tech(
            result["script_urls"],
            result.get("meta_generator"),
            result.get("inline_scripts", []),
            headers=result.get("headers", {}),
            css_urls=result.get("css_urls", []),
        )

        if technologies != result["technologies"]:
            result["technologies"] = technologies
            updated_count += 1

        if technologies:
            names = ", ".join(technology["name"] for technology in technologies)
            print(f"{result['domain']}: {names}")

            for technology in technologies:
                for evidence in technology["evidence"]:
                    print(f"  {technology['name']}: {evidence['value']}")

    if updated_count:
        with open("results.json", "w", encoding="utf-8") as file:
            json.dump(results, file, indent=2, ensure_ascii=False)

    print(f"\nUpdated {updated_count} domains.")
    show_script_top(results)
    show_meta_top(results)
    show_inline_top(results)
    show_header_top(results)
    show_css_top(results)


if __name__ == "__main__":
    main()
