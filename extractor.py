from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup


PREFERRED_LINK_PARTS = (
    {"product", "products", "produs", "produse"},
    {"collection", "collections", "colectii"},
    {"contact", "contact-us", "contacte"},
)
SKIPPED_LINK_PARTS = {"account", "admin", "cart", "checkout", "login", "logout", "search", "wp-admin", "wp-login.php"}
PAGE_EXTENSIONS = (".html", ".htm", ".php", ".asp", ".aspx", ".jsp")


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


def extract_internal_links(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    base_url = _document_base_url(soup, page_url)
    page = urlsplit(page_url)
    seen_paths = {"", page.path.rstrip("/")}
    preferred_links = [[] for _ in PREFERRED_LINK_PARTS]
    other_links = []

    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if tag.has_attr("download") or href.startswith(("#", "?")):
            continue
        url = _resolve_asset_url(base_url, href)
        if not url:
            continue

        link = urlsplit(url)
        path = link.path.rstrip("/")
        if link.hostname != page.hostname or link.username is not None or path in seen_paths:
            continue

        parts = path.lower().split("/")
        if SKIPPED_LINK_PARTS.intersection(parts):
            continue
        filename = parts[-1]
        if "." in filename and not filename.endswith(PAGE_EXTENSIONS):
            continue

        seen_paths.add(path)
        clean_url = link._replace(query="", fragment="").geturl()
        for group, links in zip(PREFERRED_LINK_PARTS, preferred_links):
            if group.intersection(parts):
                links.append(clean_url)
                break
        else:
            other_links.append(clean_url)

    first_choices = [links[0] for links in preferred_links if links]
    more_choices = [url for links in preferred_links for url in links[1:]]
    return first_choices + more_choices + other_links
