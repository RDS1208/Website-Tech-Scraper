import json
from urllib.parse import urlsplit


with open("rules.json", encoding="utf-8") as file:
    RULES = json.load(file)


def matches_script_rule(url, rule):
    if "hostname" in rule and url.hostname != rule["hostname"]:
        return False

    if "paths" in rule and url.path not in rule["paths"]:
        return False

    if "path_prefix" in rule and not url.path.startswith(rule["path_prefix"]):
        return False

    if "path_suffix" in rule and not url.path.endswith(rule["path_suffix"]):
        return False

    return True


def detect_tech(script_urls, meta_generator=None):
    evidence_by_name = {}
    script_entries = [(script_url, urlsplit(script_url)) for script_url in script_urls]

    for rule in RULES:
        name = rule["name"]

        if "meta_generator_prefix" in rule:
            prefix = rule["meta_generator_prefix"].casefold()

            if isinstance(meta_generator, str):
                generator = meta_generator.strip().casefold()

                if generator == prefix or generator.startswith(prefix + " "):
                    evidence = {"source": "meta generator", "value": meta_generator}
                    evidence_list = evidence_by_name.setdefault(name, [])

                    if evidence not in evidence_list:
                        evidence_list.append(evidence)

            continue

        for script_url, url in script_entries:
            if matches_script_rule(url, rule):
                evidence = {"source": "script src", "value": script_url}
                evidence_list = evidence_by_name.setdefault(name, [])

                if evidence not in evidence_list:
                    evidence_list.append(evidence)

    return [
        {"name": name, "evidence": evidence}
        for name, evidence in evidence_by_name.items()
    ]