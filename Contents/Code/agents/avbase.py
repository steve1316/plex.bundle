# coding=utf-8

import datetime
import json
import re

from .duga import extract_product_id, fetch_description
from .base import MetadataAgent, SearchAgent
from .types import Metadata, Person, Resource, SearchItem
from .utils import br_to_newlines, get_code_group, guess_video_code


BASE_URL = "https://www.avbase.net"
SEARCH_URL = BASE_URL + "/works"
DETAIL_URL = BASE_URL + "/works/{prefix}:{work_id}"


class AVBase(SearchAgent, MetadataAgent):
    """Agent that scrapes metadata from avbase.net via __NEXT_DATA__."""

    name = "AVBase"
    weight = 950

    @property
    def session(self):
        # avbase.net is behind Cloudflare, prefer FlareSolverr
        return self.flaresolverr_session or super(AVBase, self).session

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def guess_keywords(self, name, filename, directory):
        text = u" ".join([name or "", filename or "", directory or ""])
        code = guess_video_code(text)
        if code:
            return [code.upper()]
        return []

    def search(self, keywords, lang):
        video_code = keywords[0]
        resp = self.session.get(SEARCH_URL, params={"q": video_code})
        self.raise_for_status(resp)

        page_props = self.extract_page_props(resp)
        if not page_props:
            return []

        works = page_props.get("works", [])
        results = []
        for work in works:
            work_id = work.get("work_id", "")
            if not work_id:
                continue

            prefix = work.get("prefix", "")
            title = work.get("title", "")
            thumb = ""
            products = work.get("products", [])
            if products:
                thumb = products[0].get("thumbnail_url", "")

            year = None
            min_date = work.get("min_date", "")
            if min_date:
                year = self.parse_date(min_date)
                if year:
                    year = year.year

            score = 100 if work_id.upper() == video_code.upper() else 80

            item = SearchItem()
            item.id = u"{0}:{1}".format(prefix, work_id)
            item.video_code = work_id.upper()
            item.title = u"{0} {1}".format(work_id.upper(), title) if title else work_id.upper()
            item.year = year
            item.score = score
            item.thumb = thumb
            results.append(item)

        return results

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def should_contribute_to(self, metadata, attribute, new_value):
        # Replace actresses when AVBase has more complete cast info
        if attribute == "actresses" and new_value:
            current = getattr(metadata, attribute)
            if current is not None and len(new_value) > len(current):
                return True
        return super(AVBase, self).should_contribute_to(
            metadata, attribute, new_value)

    def get_metadata(self, agent_id, video_code, lang):
        # agent_id is "prefix:work_id"
        url = u"{0}/works/{1}".format(BASE_URL, agent_id)
        resp = self.session.get(url)
        self.raise_for_status(resp)

        page_props = self.extract_page_props(resp)
        if not page_props:
            raise Exception(u"No __NEXT_DATA__ found for {0}".format(agent_id))

        work = page_props.get("work", {})
        if not work:
            raise Exception(u"No work data found for {0}".format(agent_id))

        metadata = Metadata()
        metadata.code_group = get_code_group(video_code)

        # Title
        title = work.get("title", "")
        if title:
            metadata.title = u"{0} {1}".format(video_code, title)
            metadata.japanese_title = metadata.title
            metadata.title_sort = metadata.title

        # Release date (fall back to max_date when min_date is absent).
        for date_key in ("min_date", "max_date"):
            value = work.get(date_key, "")
            if value:
                metadata.release_date = self.parse_date(value)
                if metadata.release_date:
                    break

        # Actresses (from casts)
        casts = work.get("casts", [])
        if casts:
            actresses = []
            for cast in casts:
                actor = cast.get("actor", {})
                name = actor.get("name", "")
                if not name:
                    continue
                person = Person(name)
                ruby = actor.get("ruby", "")
                if ruby:
                    person.reading = ruby
                image_url = actor.get("image_url", "")
                if image_url:
                    person.photo = Resource(image_url)
                    person.photo.score = 55
                actresses.append(person)
            if actresses:
                metadata.actresses = actresses

        # Genres
        genres = work.get("genres", [])
        if genres:
            genre_names = set()
            for g in genres:
                name = g.get("name", "")
                # Skip the "sample video" genre tag
                if name and name != u"\u30b5\u30f3\u30d7\u30eb\u52d5\u753b":
                    genre_names.add(name)
            if genre_names:
                metadata.genres = genre_names

        # Extract product-level metadata across every product (studio, label,
        # series, director, summary, duration, dates, images). Scalar fields take
        # the first product that supplies them; art is aggregated from all.
        art_list = []
        poster_candidates = []
        for product in work.get("products", []):
            if not metadata.studio:
                maker = product.get("maker", {})
                if maker and maker.get("name"):
                    metadata.studio = maker["name"]

            if not metadata.labels:
                label = product.get("label", {})
                if label and label.get("name"):
                    metadata.labels = set([label["name"]])

            if not metadata.series:
                series = product.get("series", {})
                if series and series.get("name"):
                    metadata.series = series["name"]

            iteminfo = product.get("iteminfo", {}) or {}
            if not metadata.summary and iteminfo.get("description"):
                metadata.summary = br_to_newlines(iteminfo["description"])
            if not metadata.duration and iteminfo.get("volume"):
                m = re.search(r"(\d+)", u"{0}".format(iteminfo["volume"]))
                if m:
                    metadata.duration = int(m.group(1)) * 60 * 1000
            if not metadata.directors:
                directors = self.parse_directors(iteminfo.get("director"))
                if directors:
                    metadata.directors = directors

            if not metadata.release_date and product.get("date"):
                metadata.release_date = self.parse_date(product["date"])

            # Poster: the first product's full-size cover (fall back to thumb).
            image_url = product.get("image_url", "")
            if not metadata.posters:
                poster_url = image_url or product.get("thumbnail_url", "")
                if poster_url:
                    poster = Resource(poster_url)
                    poster.score = self.cover_score(poster_url)
                    metadata.posters = [poster]

            # Art: every product's full-size cover plus its sample images.
            samples = product.get("sample_image_urls", [])
            if image_url:
                cover = Resource(image_url)
                cover.score = self.cover_score(image_url)
                art_list.append(cover)
            for sample in samples:
                large_url = sample.get("l", "")
                if large_url:
                    sample_art = Resource(large_url)
                    sample_art.score = 30
                    art_list.append(sample_art)

            # The digital product's first sample is often the native portrait front cover (e.g. DMM's jp-1, whose wide
            # `pl.jpg` is only a promo montage). Offer it as a poster candidate; the picker keeps it only if it is a
            # portrait that matches the front panel of a wide cover, so scene stills are ignored.
            if samples and image_url and "digital" in image_url:
                first_large = samples[0].get("l", "")
                if first_large:
                    candidate = Resource(first_large)
                    candidate.score = 45
                    poster_candidates.append(candidate)

        if poster_candidates:
            metadata.posters = (metadata.posters or []) + poster_candidates

        # Backfill a truncated summary with the full Duga description when available.
        metadata.summary = self.hydrate_summary_from_duga(work, metadata.summary)

        if art_list:
            metadata.art = art_list

        return metadata

    def hydrate_summary_from_duga(self, work, summary):
        """Return a fuller summary fetched from Duga when `summary` is a truncated teaser.

        AVBase's `iteminfo.description` is a short preview capped at ~129 chars ending in the ellipsis. When that happens and the work has a
        Duga product, fetch the full description from the Duga product page and use it. This runs before the Translate agent, so the English
        summary comes out complete too. The original summary is returned unchanged on any miss or failure, so a broken Duga never degrades
        the metadata.

        Args:
            work: The AVBase work dict, whose `products` may include a Duga entry.
            summary: The summary assembled from AVBase (str or None).

        Returns:
            str: The full Duga description when it is longer, otherwise the original summary.
        """
        if not self.prefs["duga_enabled"]:
            return summary
        # A truncated teaser ends in the ellipsis U+2026.
        if not summary or not summary.rstrip().endswith(u"\u2026"):
            return summary

        duga_url = None
        for product in work.get("products", []):
            if product.get("source") == "duga":
                duga_url = product.get("url")
                break
        if not duga_url:
            return summary

        product_id = extract_product_id(duga_url)
        if not product_id:
            return summary

        try:
            full = fetch_description(
                self.session, product_id, self.raise_for_status)
        except Exception as e:
            self.logger.warning("Duga description fetch failed: %s", e)
            return summary

        if full and len(full) > len(summary):
            self.logger.debug("Replaced truncated summary with Duga full text")
            return full
        return summary

    @staticmethod
    def cover_score(url):
        """Return the poster/art score for a cover URL.

        The physical DVD cover (`pics.dmm.co.jp/mono/movie/`) is a clean front+back image that crops to a proper
        front-cover poster. Digital-floor and reseller covers are often wide promo montages (scene collage + text) that
        crop into a cluttered collage, so they rank lower and only win the poster when no DVD cover is present.

        Args:
            url: The cover image URL.

        Returns:
            int: 60 for a physical DVD cover, 50 otherwise.
        """
        return 60 if url and "/mono/movie/" in url else 50

    @staticmethod
    def parse_directors(director):
        """Return a list of `Person` directors from an iteminfo director value.

        Handles the string, list, and object shapes the field can take.

        Args:
            director: The raw `iteminfo.director` value (str, list, or dict).

        Returns:
            list[Person]: The parsed directors (possibly empty).
        """
        if not director:
            return []
        items = director if isinstance(director, list) else [director]
        names = []
        for item in items:
            name = item.get("name") if isinstance(item, dict) else item
            if name:
                names.append(Person(name))
        return names

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def extract_page_props(resp):
        """Extract pageProps from __NEXT_DATA__ in the response HTML."""
        html = resp.content
        if isinstance(html, str):
            html = html.decode("utf-8", "ignore")

        match = re.search(
            r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            html, re.DOTALL)
        if not match:
            return None

        try:
            data = json.loads(match.group(1))
        except (ValueError, TypeError):
            return None

        return data.get("props", {}).get("pageProps", {})

    @staticmethod
    def parse_date(date_str):
        """Parse a JavaScript Date string into a Python datetime.

        Handles formats like:
            "Fri May 16 2025 09:00:00 GMT+0900 (Japan Standard Time)"
            "Fri May 16 2025 00:00:00 GMT+0900 (Japan Standard Time)"
        """
        match = re.search(
            r"(\w{3})\s+(\w{3})\s+(\d{1,2})\s+(\d{4})", date_str)
        if not match:
            return None

        months = {
            "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
            "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
            "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
        }
        month_str = match.group(2)
        month = months.get(month_str)
        if not month:
            return None

        try:
            return datetime.datetime(
                int(match.group(4)), month, int(match.group(3)))
        except ValueError:
            return None
