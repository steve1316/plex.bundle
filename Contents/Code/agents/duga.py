# coding=utf-8

import re

from bs4 import BeautifulSoup


BASE_URL = "https://duga.jp"
PRODUCT_URL = BASE_URL + "/ppv/{product_id}/"

# Pulls the Duga product id (e.g. "doc-1990") out of a product or click url
# like "https://click.duga.jp/ppv/doc-1990/39588-1".
PRODUCT_ID_RE = re.compile(r"/ppv/([^/?]+)")

# Duga serves each product's sample movie at a fixed path built from the label and number of its id (e.g. "scocci-0170").
SAMPLE_MOVIE_URL = "https://flv.duga.jp/unsecure/{label}/{number}/noauth/temp.mp4"


def extract_product_id(url):
    """Return the Duga product id from a Duga product or click url.

    Args:
        url: A Duga product/click url (str), or None.

    Returns:
        str: The product id (e.g. 'doc-1990'), or None when the url is empty or carries no id.
    """
    if not url:
        return None
    match = PRODUCT_ID_RE.search(url)
    if match:
        return match.group(1)
    return None


def sample_movie_url(product_id):
    """Return the sample movie url of a Duga product.

    Args:
        product_id: The Duga product id (e.g. 'scocci-0170'), or None.

    Returns:
        str: The sample movie url, or None when the id has no label and number.
    """
    if not product_id or "-" not in product_id:
        return None
    label, number = product_id.rsplit("-", 1)
    return SAMPLE_MOVIE_URL.format(label=label, number=number)


def fetch_description(session, product_id, raise_for_status=None):
    """Fetch a Duga product page and return its full description.

    Args:
        session: A requests-like session exposing a `get` method.
        product_id: The Duga product id (e.g. 'doc-1990').
        raise_for_status: Optional callable invoked with the response to check its status.
            Defaults to the response's own `raise_for_status`. AVBase passes its own helper so a 403 surfaces as an AccessRestrictedError.

    Raises:
        Exception: Whatever `raise_for_status` or the session raises (e.g. AccessRestrictedError, HTTPError, network errors).

    Returns:
        str: The full description text, or None when it cannot be parsed.
    """
    url = PRODUCT_URL.format(product_id=product_id)
    resp = session.get(url)
    if raise_for_status is not None:
        raise_for_status(resp)
    else:
        resp.raise_for_status()
    html = resp.content
    # Decode bytes to unicode. `str` (not `bytes`) is the py2 idiom the Plex sandbox allows.
    if isinstance(html, str):
        html = html.decode("utf-8", "ignore")
    return parse_description(html)


def parse_description(html):
    """Parse the full description from Duga product-page HTML.

    Args:
        html: The Duga product-page HTML (str).

    Returns:
        str: The description text, or None when neither the introduction element nor the og:description meta tag is present.
    """
    soup = BeautifulSoup(html, "html.parser")
    el = soup.select_one('p.introduction[itemprop="description"]')
    if el:
        text = el.get_text(strip=True)
        if text:
            return text
    meta = soup.select_one('meta[property="og:description"]')
    if meta and meta.get("content"):
        return meta["content"].strip()
    return None
