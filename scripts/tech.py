import json
from urllib.parse import parse_qs, urlsplit

from .paths import RULES_PATH


URL_FIELDS = {"hostname", "paths", "path_prefix", "path_suffix", "query_param_prefix"}
TEXT_RULE_FIELDS = ({"header", "header_product"}, {"inline_contains"}, {"meta_generator_prefix"})
LIST_SIGNAL_FIELDS = ("script_urls", "css_urls", "inline_scripts", "network_urls")


def _is_nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


def _valid_url_fields(fields):
    if not isinstance(fields, dict) or not fields or fields.keys() - URL_FIELDS:
        return False

    for key, value in fields.items():
        if key == "paths":
            if not isinstance(value, list) or not value:
                return False
            if not all(_is_nonempty_string(path) for path in value):
                return False
        elif key == "query_param_prefix":
            if not isinstance(value, dict) or not value:
                return False
            for param, prefix in value.items():
                if not _is_nonempty_string(param) or not _is_nonempty_string(prefix):
                    return False
        elif not _is_nonempty_string(value):
            return False

    return True


def validate_rules(rules):
    valid_rules = []

    for rule in rules:
        if not isinstance(rule, dict) or not _is_nonempty_string(rule.get("name")):
            continue

        fields = {key: value for key, value in rule.items() if key != "name"}
        if fields.keys() == {"css_url"}:
            valid = _valid_url_fields(fields["css_url"])
        elif fields.keys() == {"network_url"}:
            network_rule = fields["network_url"]
            valid = _valid_url_fields(network_rule) and "query_param_prefix" not in network_rule
        elif fields.keys() in TEXT_RULE_FIELDS:
            valid = all(_is_nonempty_string(value) for value in fields.values())
        else:
            valid = _valid_url_fields(fields)

        if valid:
            valid_rules.append(rule)

    return valid_rules


with RULES_PATH.open(encoding="utf-8") as file:
    RULES = json.load(file)

valid_rules = validate_rules(RULES)


DETECTION_HEADERS = {rule["header"].lower() for rule in valid_rules if "header" in rule}


def matches_url_rule(url, rule):
    if "hostname" in rule and url.hostname != rule["hostname"]:
        return False

    if "paths" in rule and url.path not in rule["paths"]:
        return False

    if "path_prefix" in rule and not url.path.startswith(rule["path_prefix"]):
        return False

    if "path_suffix" in rule and not url.path.endswith(rule["path_suffix"]):
        return False

    if "query_param_prefix" in rule:
        params = parse_qs(url.query)
        for name, prefix in rule["query_param_prefix"].items():
            if not any(value.startswith(prefix) for value in params.get(name, [])):
                return False

    return True


def detect_tech(
    script_urls, meta_generator=None, inline_scripts=None, headers=None, css_urls=None,
    *, rendered_meta_generator=None, network_urls=None,
):
    evidence_by_name = {}
    script_entries = [(script_url, urlsplit(script_url)) for script_url in script_urls]
    css_entries = [(css_url, urlsplit(css_url)) for css_url in (css_urls or [])]
    network_entries = [(network_url, urlsplit(network_url)) for network_url in (network_urls or [])]
    headers = {key.lower(): value for key, value in (headers or {}).items()}
    if inline_scripts is None:
        inline_scripts = []

    def add_evidence(name, source, value):
        evidence = {"source": source, "value": value}
        evidence_list = evidence_by_name.setdefault(name, [])
        if evidence not in evidence_list:
            evidence_list.append(evidence)

    for rule in valid_rules:
        name = rule["name"]

        if "header" in rule:
            header = rule["header"].lower()
            value = headers.get(header, "")
            product = rule["header_product"].casefold()
            for part in value.casefold().split(","):
                part = part.strip()
                if part == product or part.startswith((product + "/", product + " ")):
                    add_evidence(name, "http header", f"{header}: {value}")
                    break
            continue

        if "css_url" in rule:
            for css_url, url in css_entries:
                if matches_url_rule(url, rule["css_url"]):
                    add_evidence(name, "css href", css_url)
            continue

        if "network_url" in rule:
            for network_url, url in network_entries:
                if matches_url_rule(url, rule["network_url"]):
                    add_evidence(name, "network request", network_url)
            continue

        if "inline_contains" in rule:
            marker = rule["inline_contains"]
            if not marker:
                continue

            for script in inline_scripts:
                position = script.find(marker)
                if position != -1:
                    start = max(0, position - 50)
                    end = position + len(marker) + 100
                    add_evidence(name, "inline script", script[start:end])

            continue

        if "meta_generator_prefix" in rule:
            prefix = rule["meta_generator_prefix"].casefold()

            for value in (meta_generator, rendered_meta_generator):
                if not isinstance(value, str):
                    continue
                generator = value.strip().casefold()
                if generator == prefix or generator.startswith(prefix + " "):
                    add_evidence(name, "meta generator", value)

            continue

        for script_url, url in script_entries:
            if matches_url_rule(url, rule):
                add_evidence(name, "script src", script_url)

    return [
        {"name": name, "evidence": evidence}
        for name, evidence in evidence_by_name.items()
    ]


def detect_result(result, *, httpx_only=False):
    added_signals = result.get("render_added_signals", {})
    signals = {field: result.get(field, []) for field in LIST_SIGNAL_FIELDS}
    generator = result.get("meta_generator")
    rendered_generator = added_signals.get("meta_generator")

    if httpx_only:
        for field in LIST_SIGNAL_FIELDS:
            added = set(added_signals.get(field, []))
            signals[field] = [value for value in signals[field] if value not in added]
        # The merged field falls back to the browser if HTTPX had no generator.
        if generator == rendered_generator:
            generator = None
        rendered_generator = None

    return detect_tech(
        **signals,
        headers=result.get("headers"),
        meta_generator=generator,
        rendered_meta_generator=rendered_generator,
    )


def added_technology_names(before, after):
    return sorted({tech["name"] for tech in after} - {tech["name"] for tech in before})


def linked_technology_additions(result):
    findings = [
        technology
        for page in result.get("linked_pages", [])
        if "error" not in page
        for technology in page["technologies"]
    ]
    return added_technology_names(result["technologies"], findings)
