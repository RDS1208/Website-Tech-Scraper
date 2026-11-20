import json
from collections import Counter


def generate_report(results_path="results.json"):
    """Print website counts and rank technologies by the number of websites."""
    with open(results_path, encoding="utf-8") as file:
        results = json.load(file)

    technologies_by_domain = {}
    for result in results:
        if "error" in result:
            continue

        technologies = technologies_by_domain.setdefault(result["domain"], set())
        technologies.update(technology["name"] for technology in result["technologies"])

    counts = Counter()
    sites_with_technologies = 0
    for technologies in technologies_by_domain.values():
        counts.update(technologies)
        if technologies:
            sites_with_technologies += 1

    print(f"Websites accessed: {len(technologies_by_domain)}")
    print(f"Accessible websites with technologies: {sites_with_technologies}")
    print("\nTechnology leaderboard")

    if not counts:
        print("No technologies found.")
        return

    leaderboard = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    for rank, (name, count) in enumerate(leaderboard, start=1):
        unit = "website" if count == 1 else "websites"
        print(f"{rank}. {name} ({count} {unit})")


if __name__ == "__main__":
    generate_report()
