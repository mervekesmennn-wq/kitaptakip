from urllib.parse import quote

import requests
import truststore
from bs4 import BeautifulSoup


truststore.inject_into_ssl()

SEARCH_URL = "https://www.kitapyurdu.com/index.php?route=product/search&filter_name={}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}


def _get(url):
    response = requests.get(url, headers=HEADERS, timeout=5)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def search_books(query):
    soup = _get(SEARCH_URL.format(quote(query)))
    results = []
    for card in soup.select(".ky-product"):
        title_link = card.select_one("a.ky-product-title")
        if not title_link:
            continue
        author_node = card.select_one(".ky-product-author a")
        publisher_node = card.select_one(".ky-product-publisher a")
        cover_node = card.select_one("a.ky-product-cover img")
        cover_url = cover_node.get("src") or cover_node.get("data-src") if cover_node else None
        if cover_url and cover_url.startswith("//"):
            cover_url = "https:" + cover_url
        elif cover_url and cover_url.startswith("/"):
            cover_url = "https://www.kitapyurdu.com" + cover_url
        results.append(
            {
                "title": title_link.get_text(" ", strip=True),
                "author": author_node.get_text(" ", strip=True) if author_node else "",
                "publisher": publisher_node.get_text(" ", strip=True) if publisher_node else "",
                "cover_url": cover_url or "",
                "source_url": title_link.get("href", ""),
                "isbn": "",
            }
        )
    return results


def get_book_details(url):
    soup = _get(url)
    details = {
        "page_count": 0,
        "isbn": "",
        "publication_year": "",
        "cover_url": "",
    }
    cover = soup.select_one("a.ky-product-cover img")
    if cover:
        details["cover_url"] = cover.get("src") or cover.get("data-src") or ""
    for item in soup.select(".ky-pd-attributes__item"):
        text = item.get_text(" ", strip=True)
        label = text.lower()
        if "sayfa" in label:
            for token in text.replace(".", "").replace(",", "").split():
                if token.isdigit():
                    details["page_count"] = int(token)
                    break
        if "isbn" in label:
            for token in text.replace("-", "").split():
                if token.isdigit() and len(token) >= 10:
                    details["isbn"] = token
                    break
        if "yayın" in label or "yayin" in label:
            for token in text.replace(".", "").split():
                if token.isdigit() and len(token) == 4:
                    details["publication_year"] = token
                    break
    if details["cover_url"].startswith("//"):
        details["cover_url"] = "https:" + details["cover_url"]
    elif details["cover_url"].startswith("/"):
        details["cover_url"] = "https://www.kitapyurdu.com" + details["cover_url"]
    return details
