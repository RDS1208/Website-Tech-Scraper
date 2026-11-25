import re


GOOGLE_API_KEY = re.compile(r"AIza[0-9A-Za-z_-]{35}")
URL_KEY = re.compile(r"""((?:[?&]|&amp;|\\u0026)key=)[^\s&#"'<>\\]+""", re.IGNORECASE)
SEGMENT_WRITE_KEY = re.compile(
    r"""((?:https?:)?//cdn\.segment\.com/v1/projects/)[^/\s?#"'<>\\]+(?=/settings\b)""",
    re.IGNORECASE,
)


def redact_keys(value):
    """Redact API keys in strings and nested JSON values."""
    if isinstance(value, str):
        value = URL_KEY.sub(r"\g<1>REDACTED", value)
        value = SEGMENT_WRITE_KEY.sub(r"\g<1>REDACTED", value)
        return GOOGLE_API_KEY.sub("REDACTED", value)
    if isinstance(value, list):
        return [redact_keys(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_keys(item) for key, item in value.items()}
    return value
