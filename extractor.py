from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup


def extract_script_urls(html, page_url):
    soup = BeautifulSoup(html, "html.parser")

    return [
        urljoin(page_url, script["src"].strip())
        for script in soup.find_all("script", src=True)
        if script["src"].strip()
    ]


def extract_css_urls(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    base = soup.find("base", href=True)
    if base:
        try:
            page_url = urljoin(page_url, base["href"].strip())
        except ValueError:
            pass

    css_urls = []
    for link in soup.find_all("link", href=True):
        href = link["href"].strip()
        if not href or "stylesheet" not in [rel.lower() for rel in link.get("rel", [])]:
            continue

        try:
            url = urljoin(page_url, href)
            parts = urlsplit(url)
            if parts.scheme in ("http", "https") and parts.hostname:
                css_urls.append(url)
        except ValueError:
            continue

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
