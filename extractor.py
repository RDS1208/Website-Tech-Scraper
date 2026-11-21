from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup


def _resolve_asset_url(page_url, value):
    value = value.strip()
    if not value:
        return None

    try:
        url = urljoin(page_url, value)
        parts = urlsplit(url)
        if parts.scheme in ("http", "https") and parts.hostname:
            return url
    except ValueError:
        return None

    return None


def _document_base_url(soup, page_url):
    base = soup.find("base", href=True)
    if base is None:
        return page_url

    return _resolve_asset_url(page_url, base["href"]) or page_url


def extract_script_urls(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    base_url = _document_base_url(soup, page_url)

    script_urls = []
    for script in soup.find_all("script", src=True):
        url = _resolve_asset_url(base_url, script["src"])
        if url:
            script_urls.append(url)

    return script_urls


def extract_css_urls(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    base_url = _document_base_url(soup, page_url)

    css_urls = []
    for link in soup.find_all("link", href=True):
        if "stylesheet" not in [rel.lower() for rel in link.get("rel", [])]:
            continue

        url = _resolve_asset_url(base_url, link["href"])
        if url:
            css_urls.append(url)

    return css_urls


def extract_inline_scripts(html):
    soup = BeautifulSoup(html, "html.parser")
    inline_scripts = []

    for script in soup.find_all("script", src=False):
        script_type = script.get("type", "").strip().lower()
        if script_type not in ("", "text/javascript", "application/javascript", "module"):
            continue

        content = script.get_text().strip()
        if content:
            inline_scripts.append(content)

    return inline_scripts


def extract_meta_generator(html):
    soup = BeautifulSoup(html, "html.parser")
    generator_tag = soup.find("meta", attrs={"name": "generator"})

    if generator_tag is None:
        return None

    generator = generator_tag.get("content", "").strip()
    return generator or None
