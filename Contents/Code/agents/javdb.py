# coding=utf-8

import datetime
import re

from bs4 import BeautifulSoup

from .base import MetadataAgent, SearchAgent
from .types import Metadata, Person, Resource, SearchItem
from .utils import get_code_group, guess_video_code


BASE_URL = "https://javdb.com"
SEARCH_URL = BASE_URL + "/search"
DETAIL_URL = BASE_URL + "/v/{agent_id}"


class JavDB(SearchAgent, MetadataAgent):
    """Agent that scrapes metadata from javdb.com. Low weight, so it mostly fills in titles the other sources lack."""

    name = "JavDB"
    weight = 300

    def create_session(self):
        """
        Return a new session with the JavDB age-check cookie pre-set.

        Returns:
            requests.Session: The new session.
        """
        s = super(JavDB, self).create_session()
        s.cookies.set("over18", "1", domain="javdb.com")
        return s

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Search

    def guess_keywords(self, name, filename, directory):
        text = u" ".join([name or "", filename or "", directory or ""])
        code = guess_video_code(text)
        if code:
            return [code.upper()]
        return []

    def search(self, keywords, lang):
        keyword = keywords[0]
        resp = self.session.get(SEARCH_URL, params={"q": keyword, "f": "all", "locale": "en"})
        self.raise_for_status(resp)
        soup = BeautifulSoup(resp.content.decode("utf-8", "ignore"), "html.parser")

        target = self.normalize_code(keyword)
        found = []
        for div in soup.select("div.movie-list div.item"):
            link = div.select_one("a[href]")
            if not link:
                continue
            m = re.search(r"/v/([A-Za-z0-9]+)", link.get("href", ""))
            if not m:
                continue

            title_el = div.select_one(".video-title")
            code_el = title_el.select_one("strong") if title_el else None
            if not code_el:
                continue
            video_code = code_el.get_text(strip=True).upper()
            if self.normalize_code(video_code) != target:
                continue

            title = link.get("title", "").strip()
            img = div.select_one("img")

            item = SearchItem()
            item.id = m.group(1)
            item.video_code = video_code
            item.title = u"{0} {1}".format(video_code, title) if title else video_code
            item.score = 100
            item.thumb = img.get("src", "") if img else ""
            meta = div.select_one(".meta")
            if meta:
                date = self.parse_date(meta.get_text(strip=True))
                if date:
                    item.year = date.year
            found.append(item)

        return found

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Metadata

    def get_metadata(self, agent_id, video_code, lang):
        resp = self.session.get(DETAIL_URL.format(agent_id=agent_id), params={"locale": "en"})
        self.raise_for_status(resp)
        soup = BeautifulSoup(resp.content.decode("utf-8", "ignore"), "html.parser")

        metadata = Metadata()
        metadata.code_group = get_code_group(video_code)

        # Title
        heading = soup.select_one("h2.title")
        if heading:
            code_el = heading.select_one("strong")
            title_el = heading.select_one("strong.current-title")
            code = code_el.get_text(strip=True) if code_el else video_code
            title = title_el.get_text(strip=True) if title_el else ""
            if title:
                metadata.title = u"{0} {1}".format(code, title)
                metadata.japanese_title = metadata.title
                metadata.title_sort = metadata.title

        panel = self.extract_panel(soup)

        value = panel.get("Released Date")
        if value:
            metadata.release_date = self.parse_date(value.get_text(strip=True))

        value = panel.get("Duration")
        if value:
            m = re.search(r"\d+", value.get_text())
            if m:
                metadata.duration = int(m.group(0)) * 60 * 1000

        value = panel.get("Rating")
        if value:
            m = re.search(r"(\d+(?:\.\d+)?)", value.get_text())
            if m:
                metadata.rating = float(m.group(1)) * 2  # 5-star -> 10-point

        value = panel.get("Tags")
        if value:
            genres = set(a.get_text(strip=True) for a in value.select("a") if a.get_text(strip=True))
            if genres:
                metadata.genres = genres

        value = panel.get("Actor(s)")
        if value:
            links = value.select("a")
            # Female cast members are tagged with `actor-female`. Fall back to everyone when no tag is present.
            female = [a for a in links if "actor-female" in (a.get("class") or [])]
            actresses = [Person(a.get_text(strip=True)) for a in (female or links) if a.get_text(strip=True)]
            if actresses:
                metadata.actresses = actresses

        value = panel.get("Director")
        if value:
            directors = [Person(a.get_text(strip=True)) for a in value.select("a") if a.get_text(strip=True)]
            if directors:
                metadata.directors = directors

        value = panel.get("Maker")
        if value and value.get_text(strip=True):
            metadata.studio = value.get_text(strip=True)

        value = panel.get("Publisher")
        if value and value.get_text(strip=True):
            metadata.labels = set([value.get_text(strip=True)])

        value = panel.get("Series")
        if value and value.get_text(strip=True):
            metadata.series = value.get_text(strip=True)

        # The cover is a wide front+back image. Offer it as art and as a poster so the central picker can crop it.
        cover = soup.select_one("img.video-cover")
        if cover and cover.get("src"):
            metadata.art = [Resource(cover["src"])]
            metadata.posters = [Resource(cover["src"])]

        return metadata

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Helpers

    @staticmethod
    def extract_panel(soup):
        """
        Map each info panel label (e.g. "Released Date") to its value element.

        Args:
            soup (BeautifulSoup): The parsed detail page.

        Returns:
            dict: Label text without the trailing colon mapped to the `span.value` element.
        """
        panel = {}
        for block in soup.select("nav.movie-panel-info div.panel-block"):
            label = block.find("strong")
            value = block.select_one("span.value")
            if label and value:
                panel[label.get_text(strip=True).rstrip(":")] = value
        return panel

    @staticmethod
    def normalize_code(code):
        """
        Normalize a video code for comparison by dropping the numeric amateur prefix, dashes and spaces.

        Args:
            code (str): A video code such as "230OREMO-042".

        Returns:
            str: The normalized code, e.g. "OREMO042".
        """
        return re.sub(r"[\s-]", "", code.upper()).lstrip("0123456789")

    @staticmethod
    def parse_date(text):
        """
        Parse a JavDB date in either "YYYY-MM-DD" or "MM/DD/YYYY" form.

        Args:
            text (str): The date text.

        Returns:
            datetime.datetime or None: The parsed date, or None when no date is found.
        """
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
        if m:
            year, month, day = m.group(1), m.group(2), m.group(3)
        else:
            m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
            if not m:
                return None
            month, day, year = m.group(1), m.group(2), m.group(3)
        try:
            return datetime.datetime(int(year), int(month), int(day))
        except ValueError:
            return None
