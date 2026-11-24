import json
from collections import Counter
from urllib.parse import urlsplit


from redaction import redact_keys
from tech import added_technology_names, detect_result, detect_tech, linked_technology_additions


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

            if field == "network_urls":
                signature = f"{url.hostname}{url.path}"
            elif url.hostname == page_host:
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


def show_meta_top(results, limit=20, title="Most common meta generators"):
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

    print(f"\n{title}")
    for generator, count in counts.most_common(limit):
        print(f"{count:3} sites  {generator}")


def show_inline_top(results, limit=20, title="Most common inline scripts"):
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

    print(f"\n{title}")
    for signature, count in counts.most_common(limit):
        print(f"{count:3} sites  {examples[signature][:300]}")


def has_render_comparison(result):
    return "render_added_signals" in result and "render_error" not in result


def show_render_added_top(results, limit=20):
    counts = Counter()
    rendered_sites = 0

    for result in results:
        if not has_render_comparison(result):
            continue

        rendered_sites += 1
        counts.update(result["render_added_technologies"])

    if not rendered_sites:
        return

    print(f"\nTechnologies found only after rendering ({rendered_sites} sites rendered)")
    for name, count in counts.most_common(limit):
        print(f"{count:3} sites  {name}")


def show_linked_added_top(results, limit=20):
    names_by_domain = {}
    for result in results:
        if "linked_pages" in result:
            names = names_by_domain.setdefault(result["domain"], set())
            names.update(result["linked_added_technologies"])

    if not names_by_domain:
        return

    counts = Counter(name for names in names_by_domain.values() for name in names)
    print("\nTechnologies found only on internal pages")
    if not counts:
        print("No additional technologies found.")
    for name, count in counts.most_common(limit):
        print(f"{count:3} sites  {name}")


def is_candidate_url(url, *, stylesheet=False):
    matches = detect_tech([], css_urls=[url]) if stylesheet else detect_tech([url])
    if not matches:
        return True

    # A WordPress match alone does not identify the plugin that owns this asset.
    return (
        urlsplit(url).path.startswith("/wp-content/plugins/")
        and {match["name"] for match in matches} == {"WordPress"}
    )


def show_unmatched_render_signals(results, limit=20):
    candidates = []
    for result in results:
        if not has_render_comparison(result):
            continue

        signals = result["render_added_signals"]
        generator = signals.get("meta_generator")
        candidates.append({
            "final_url": result["final_url"],
            "script_urls": [url for url in signals.get("script_urls", []) if is_candidate_url(url)],
            "css_urls": [url for url in signals.get("css_urls", []) if is_candidate_url(url, stylesheet=True)],
            "network_urls": [
                url for url in signals.get("network_urls", [])
                if not detect_tech([], network_urls=[url])
            ],
            "inline_scripts": [
                script for script in signals.get("inline_scripts", [])
                if not detect_tech([], inline_scripts=[script])
            ],
            "meta_generator": generator if not detect_tech([], meta_generator=generator) else None,
        })

    if not candidates:
        return

    print("\nPlaywright signals to review for new rules")
    show_url_top(candidates, "script_urls", "Script URLs", limit)
    show_url_top(candidates, "css_urls", "CSS URLs", limit)
    if any(result["network_urls"] for result in candidates):
        show_url_top(candidates, "network_urls", "Network URLs", limit)
    show_inline_top(candidates, limit, title="Inline scripts")
    show_meta_top(candidates, limit, title="Meta generators")


def refresh_detections(result):
    technologies = detect_result(result)
    changed = technologies != result["technologies"]
    result["technologies"] = technologies

    if has_render_comparison(result):
        httpx_technologies = detect_result(result, httpx_only=True)
        additions = added_technology_names(httpx_technologies, technologies)
        changed = changed or additions != result.get("render_added_technologies")
        result["render_added_technologies"] = additions

    if "linked_pages" in result:
        for page in result["linked_pages"]:
            if "error" not in page and refresh_detections(page):
                changed = True

        additions = linked_technology_additions(result)
        changed = changed or additions != result.get("linked_added_technologies")
        result["linked_added_technologies"] = additions

    return changed


def print_findings(label, technologies):
    if not technologies:
        return

    names = ", ".join(technology["name"] for technology in technologies)
    print(f"{label}: {names}")
    for technology in technologies:
        for evidence in technology["evidence"]:
            print(f"  {technology['name']}: {evidence['value']}")


def main():
    with open("results.json", encoding="utf-8") as file:
        saved_results = json.load(file)

    results = redact_keys(saved_results)
    redacted = results != saved_results
    updated_count = 0

    for result in results:
        if "error" in result:
            continue

        if refresh_detections(result):
            updated_count += 1

        print_findings(result["domain"], result["technologies"])
        for page in result.get("linked_pages", []):
            if "error" not in page:
                print_findings(page["final_url"], page["technologies"])

    if updated_count or redacted:
        with open("results.json", "w", encoding="utf-8") as file:
            json.dump(results, file, indent=2, ensure_ascii=False)

    print(f"\nUpdated {updated_count} domains.")
    show_script_top(results)
    show_meta_top(results)
    show_inline_top(results)
    show_header_top(results)
    show_css_top(results)
    if any(result.get("network_urls") for result in results):
        show_url_top(results, "network_urls", "Most common fetch/XHR endpoints", limit=20)
    show_render_added_top(results)
    show_linked_added_top(results)
    show_unmatched_render_signals(results)


if __name__ == "__main__":
    main()
