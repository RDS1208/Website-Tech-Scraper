from urllib.parse import urljoin

from bs4 import BeautifulSoup


def extract_script_urls(html, page_url):
    soup = BeautifulSoup(html, "html.parser")

    return [
        urljoin(page_url, script["src"].strip())
        for script in soup.find_all("script", src=True)
        if script["src"].strip()
    ]


def extract_meta_generator(html):
    soup = BeautifulSoup(html, "html.parser")
    generator_tag = soup.find("meta", attrs={"name": "generator"})

    if generator_tag is None:
        return None

    generator = generator_tag.get("content", "").strip()
    return generator or None