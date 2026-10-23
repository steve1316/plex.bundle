# coding=utf-8

import datetime
import re

from bs4 import BeautifulSoup


SOFT_URL = u"https://www.getchu.com/soft.phtml?id={soft_id}&gc=gc"
SEARCH_URL = u"https://www.getchu.com/php/search.phtml"
DL_ITEM_URL = u"https://dl.getchu.com/i/item{gcd}"
GETCHU_BASE_URL = u"https://www.getchu.com"

# Getchu shows an age gate instead of the product page unless this cookie is sent. DL.Getchu needs no cookie.
AGE_COOKIES = {"getchu_adalt_flag": "getchu.com"}

# Getchu product ids, from a product url ("soft.phtml?id=1108622"), an affiliate url (".../id/1108622/...") or an affiliate
# image ("afimg_1108622_160.jpg").
SOFT_ID_RES = [
    re.compile(r"getchu\.com/.*[?&]id=(\d+)"),
    re.compile(r"getchu\.com/.*/id/(\d+)/"),
    re.compile(r"afimg_(\d+)"),
]

# DL.Getchu item ids, from an affiliate url ("r.php?...&gcd=4031740"), an item url ("/i/item4038100") or an item image
# (".../item_img/40118/4011873/4011873small.jpg").
DL_ID_RES = [
    re.compile(r"getchu\.com/.*[?&](?:amp;)?gcd=(\d+)"),
    re.compile(r"dl\.getchu\.com/i/item(\d+)"),
    re.compile(r"getchu\.com/data/item_img/\d+/(\d+)/"),
]

DATE_RE = re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})")
MINUTES_RE = re.compile(u"(\\d+)\\s*分")


def extract_soft_id(url):
    """Return the Getchu product id from a Getchu product, affiliate or image url.

    Args:
        url: A Getchu url (str), or None.

    Returns:
        str: The product id (e.g. '1108622'), or None when the url carries no id.
    """
    return match_first(SOFT_ID_RES, url)


def extract_dl_id(url):
    """Return the DL.Getchu item id from a DL.Getchu affiliate, item or image url.

    Args:
        url: A DL.Getchu url (str), or None.

    Returns:
        str: The item id (e.g. '4038100'), or None when the url carries no id.
    """
    return match_first(DL_ID_RES, url)


def match_first(patterns, url):
    """Return the first group of the first pattern that matches `url`.

    Args:
        patterns (list): Compiled regexes with one capture group.
        url: The url to search (str), or None.

    Returns:
        str: The captured id, or None when nothing matches.
    """
    if not url:
        return None
    for pattern in patterns:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return None


def fetch_soft(session, soft_id, raise_for_status=None):
    """Fetch a Getchu product page and return its parsed fields.

    Args:
        session: A requests-like session exposing a `get` method.
        soft_id: The Getchu product id (e.g. '1108622').
        raise_for_status: Optional callable invoked with the response to check its status. Defaults to the response's own
            `raise_for_status`.

    Raises:
        Exception: Whatever `raise_for_status` or the session raises (e.g. AccessRestrictedError, HTTPError, network errors).

    Returns:
        dict: The fields from `parse_soft()`.
    """
    html = fetch_html(session, SOFT_URL.format(soft_id=soft_id), raise_for_status, cookies=AGE_COOKIES)
    return parse_soft(html)


def fetch_dl_item(session, gcd, raise_for_status=None):
    """Fetch a DL.Getchu item page and return its parsed fields.

    Args:
        session: A requests-like session exposing a `get` method.
        gcd: The DL.Getchu item id (e.g. '4038100').
        raise_for_status: Optional callable invoked with the response to check its status. Defaults to the response's own
            `raise_for_status`.

    Raises:
        Exception: Whatever `raise_for_status` or the session raises (e.g. AccessRestrictedError, HTTPError, network errors).

    Returns:
        dict: The fields from `parse_dl_item()`.
    """
    html = fetch_html(session, DL_ITEM_URL.format(gcd=gcd), raise_for_status)
    return parse_dl_item(html)


def search_soft_id(session, code, raise_for_status=None):
    """Search Getchu for `code` and return the id of the product whose title starts with it.

    Args:
        session: A requests-like session exposing a `get` method.
        code: The product code at the start of the Getchu title (e.g. 'buena369').
        raise_for_status: Optional callable invoked with the response to check its status. Defaults to the response's own
            `raise_for_status`.

    Raises:
        Exception: Whatever `raise_for_status` or the session raises (e.g. AccessRestrictedError, HTTPError, network errors).

    Returns:
        str: The Getchu product id, or None when no result title starts with `code`.
    """
    url = u"%s?search_keyword=%s&genre=all&list_count=30" % (SEARCH_URL, code)
    html = fetch_html(session, url, raise_for_status, cookies=AGE_COOKIES)
    return parse_search(html, code)


def fetch_html(session, url, raise_for_status=None, cookies=None):
    """GET `url` and return the page decoded from EUC-JP.

    Args:
        session: A requests-like session exposing a `get` method.
        url (str): The page url.
        raise_for_status: Optional callable invoked with the response to check its status.
        cookies (dict): Optional cookies to send with the request.

    Raises:
        Exception: Whatever `raise_for_status` or the session raises.

    Returns:
        str: The decoded page HTML.
    """
    if cookies:
        resp = session.get(url, cookies=cookies)
    else:
        resp = session.get(url)
    if raise_for_status is not None:
        raise_for_status(resp)
    else:
        resp.raise_for_status()
    html = resp.content
    # Both Getchu sites serve EUC-JP. `str` (not `bytes`) is the py2 idiom the Plex sandbox allows.
    if isinstance(html, str):
        html = html.decode("euc_jp", "ignore")
    return html


def parse_soft(html):
    """Parse a Getchu product page.

    Args:
        html: The product-page HTML (str).

    Returns:
        dict: `title`, `release_date` (datetime), `duration_min` (int), `description` and `cover_url`. Missing fields are None.
    """
    soup = BeautifulSoup(html, "html.parser")
    info = {"title": None, "release_date": None, "duration_min": None, "description": None, "cover_url": None}

    title = soup.find(id="soft-title")
    if title:
        info["title"] = u" ".join(title.get_text(" ", strip=True).split())

    for td in soup.find_all("td"):
        if td.get_text(strip=True) == u"発売日：":
            value = td.find_next_sibling("td")
            if value:
                info["release_date"] = parse_date(value.get_text(strip=True))
            break

    heading = soup.find(lambda t: t.name == "h3" and t.get_text(strip=True) == u"作品紹介")
    body = heading.find_next_sibling("div") if heading else None
    if body:
        text = body.get_text("\n", strip=True)
        minutes = MINUTES_RE.search(text)
        if minutes:
            info["duration_min"] = int(minutes.group(1))
        info["description"] = clean_description(text, info["title"])

    info["cover_url"] = meta_image(soup)
    return info


def parse_dl_item(html):
    """Parse a DL.Getchu item page.

    Args:
        html: The item-page HTML (str).

    Returns:
        dict: `title`, `release_date` (datetime), `genres` (list), `description` and `cover_url`. Missing fields are None.
    """
    soup = BeautifulSoup(html, "html.parser")
    info = {"title": None, "release_date": None, "genres": [], "description": None, "cover_url": None}

    meta = soup.find("meta", attrs={"property": "og:title"})
    if meta and meta.get("content"):
        info["title"] = meta["content"].strip()

    for label in soup.find_all("td", class_="bluetext"):
        name = label.get_text(strip=True)
        value = label.find_next_sibling("td")
        if not value:
            continue
        if name == u"配信開始日":
            info["release_date"] = parse_date(value.get_text(strip=True))
        elif name == u"趣向":
            info["genres"] = [a.get_text(strip=True) for a in value.find_all("a") if a.get_text(strip=True)]
        elif name == u"作品内容":
            info["description"] = value.get_text("\n", strip=True) or None

    info["cover_url"] = meta_image(soup)
    return info


def parse_search(html, code):
    """Return the id of the first search result whose title starts with `code`.

    Args:
        html: The search-results HTML (str).
        code (str): The product code to match, case-insensitively.

    Returns:
        str: The Getchu product id, or None when no result matches.
    """
    soup = BeautifulSoup(html, "html.parser")
    pattern = re.compile(r"(?i)^\s*" + re.escape(code) + r"(?![0-9a-z])")
    for a in soup.find_all("a", href=re.compile(r"soft\.phtml\?id=\d+")):
        if pattern.match(a.get_text(" ", strip=True)):
            return re.search(r"id=(\d+)", a["href"]).group(1)
    return None


def clean_description(text, title):
    """Drop the spec lines and the repeated title from a Getchu introduction.

    Args:
        text (str): The introduction text, one line per `<br>`.
        title (str): The product title, or None.

    Returns:
        str: The remaining description, or None when only spec lines were left.
    """
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith(u"・") or u"分収録" in line:
            continue
        if title and title.startswith(line):
            continue
        lines.append(line)
    return u"\n".join(lines) or None


def parse_date(text):
    """Parse a `YYYY/MM/DD` date.

    Args:
        text (str): The text holding the date.

    Returns:
        datetime.datetime: The parsed date, or None when the text holds no valid date.
    """
    match = DATE_RE.search(text or u"")
    if not match:
        return None
    try:
        return datetime.datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def meta_image(soup):
    """Return the absolute `og:image` url of a page.

    Args:
        soup: The parsed page.

    Returns:
        str: The image url, or None when the page has no `og:image`.
    """
    meta = soup.find("meta", attrs={"property": "og:image"})
    if not meta or not meta.get("content"):
        return None
    url = meta["content"].strip()
    if url.startswith(u"/"):
        url = GETCHU_BASE_URL + url
    return url
