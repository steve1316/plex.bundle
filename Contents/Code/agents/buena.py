# coding=utf-8

import datetime
import re
from urllib import unquote

from bs4 import BeautifulSoup

from .base import AccessRestrictedError, MetadataAgent, SearchAgent
from .types import Metadata, Person, Resource, SearchItem
from .utils import get_code_group


# konodare.wew.jp catalogs two related makers on separate pages:
#   /buena/ - cosplay releases (buenaNNN) as `table.product-list` entries, each
#             with actress, cosplay character, source series and cross-ref codes.
#   /pow/   - the POW amateur line (POW-NNN) as one row per release, with title,
#             release date, duration, actress and cover. Richer than /buena/.
# The older buena001-075 (/asaichi/) and the buenap compilation pages use yet
# other layouts and are not indexed here.
BUENA_URL = u"https://konodare.wew.jp/buena/"
POW_URL = u"https://konodare.wew.jp/pow/"

# Matches any supported code (buena/pow/zarj/prin) with optional separators and
# zero-padding, e.g. "buena075", "BUENA-075", "prin-042", "zarj070", "pow046".
CODE_RE = re.compile(r"(?i)(buena|pow|zarj|prin)[\s_\-]*0*(\d+)([a-z]?)")


def normalize_code(code):
    """Normalize a code to a padding-insensitive lookup key.

    Strips separators, upper-cases, and drops leading zeros from the number so
    that "prin-042" and "prin00042" both map to "PRIN42".

    Args:
        code (str): A raw code such as `buena075` or `PRIN-042`.

    Returns:
        str: The normalized key, e.g. `BUENA75`, or an empty string.
    """
    if not code:
        return u""
    s = re.sub(r"[^0-9A-Za-z]", "", code).upper()
    m = re.match(r"^([A-Z]+)0*(\d+)([A-Z]*)$", s)
    if m:
        return m.group(1) + m.group(2) + m.group(3)
    return s


class Entry(object):
    """A single parsed catalog entry (BUENA cosplay or POW amateur)."""

    def __init__(self):
        self.code = None            # canonical id, e.g. "BUENA-075" or "POW-046"
        self.title_text = None      # plain title (POW entries); BUENA builds from char/series
        self.actresses = []         # list of (name, reading) tuples
        self.character = None       # cosplay character name (BUENA)
        self.series = None          # source work name (BUENA)
        self.studio = u"BUENA"      # "POW" for POW entries / POW-labelled BUENA
        self.release_date = None    # datetime (POW entries)
        self.amateur_code = None    # e.g. "ZARJ070" or "POW023"
        self.av_code = None         # e.g. "PRIN-042"
        self.duration_ms = None
        self.fanza_av_ps = None       # pics.dmm.co.jp/digital/video/<cid>/<cid>ps.jpg
        self.fanza_amateur = None     # awsimgsrc.dmm.co.jp/.../amateur/<cid>/<cid>jp.jpg
        self.code_keys = set()

    def add_key(self, code):
        """Register `code` as a lookup key for this entry.

        Args:
            code (str): A raw code to normalize and index.
        """
        key = normalize_code(code)
        if key:
            self.code_keys.add(key)

    def thumb(self):
        """Return the best available cover thumbnail URL.

        Returns:
            str or None: A cover URL, or `None` if none was found.
        """
        return self.fanza_av_ps or self.fanza_amateur


class Buena(SearchAgent, MetadataAgent):
    """Agent that scrapes BUENA / POW cosplay-AV metadata from konodare.wew.jp."""

    name = "BUENA"
    weight = 1000

    # Parsed index (code key -> Entry), cached for the process lifetime. Set on
    # the instance the first time it is built, shadowing this class default.
    index = None

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def guess_keywords(self, name, filename, directory):
        text = u" ".join([name or u"", filename or u"", directory or u""])
        keywords = []
        for prefix, num, suffix in CODE_RE.findall(text):
            key = normalize_code(prefix + num + suffix)
            if key and key not in keywords:
                keywords.append(key)
        return keywords

    def search(self, keywords, lang):
        self.ensure_index()
        for kw in keywords:
            entry = self.index.get(normalize_code(kw))
            if entry:
                return [self.make_search_item(entry)]
        # Fallback: a code missing from the index (e.g. a POW release beyond the
        # index range) may still have its own konodare detail page.
        for kw in keywords:
            entry = self.fetch_detail_entry(kw)
            if entry:
                for key in entry.code_keys:
                    self.index.setdefault(key, entry)
                return [self.make_search_item(entry)]
        return []

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def get_metadata(self, agent_id, video_code, lang):
        self.ensure_index()
        entry = self.index.get(normalize_code(video_code)) or self.index.get(normalize_code(agent_id))
        if not entry:
            entry = self.fetch_detail_entry(video_code) or self.fetch_detail_entry(agent_id)
        if not entry:
            raise Exception(u"No BUENA/POW entry for %s" % video_code)

        metadata = Metadata()
        metadata.code_group = get_code_group(entry.code)

        title = self.build_title(entry)
        metadata.title = title
        metadata.japanese_title = title
        metadata.title_sort = title

        metadata.studio = entry.studio
        if entry.series:
            metadata.series = entry.series
        if entry.release_date:
            metadata.release_date = entry.release_date
        metadata.genres = set([u"コスプレ"])  # "cosplay"

        if entry.actresses:
            people = []
            for name, reading in entry.actresses:
                person = Person(name)
                if reading:
                    person.reading = reading
                people.append(person)
            metadata.actresses = people

        if entry.duration_ms:
            metadata.duration = entry.duration_ms

        posters, art = self.build_images(entry)
        if posters:
            metadata.posters = posters
        if art:
            metadata.art = art

        return metadata

    # ------------------------------------------------------------------
    # Index cache
    # ------------------------------------------------------------------

    def ensure_index(self):
        """Fetch and parse both catalog pages once, caching the result.

        POW is indexed first so that POW-NNN codes resolve to the dedicated POW
        entries rather than a BUENA cross-reference. Cached for the process
        lifetime once non-empty.
        """
        if self.index is not None:
            return

        index = {}
        for entry in self.parse_pow_page():
            for key in entry.code_keys:
                index.setdefault(key, entry)
        for entry in self.parse_buena_page():
            for key in entry.code_keys:
                index.setdefault(key, entry)

        if index:
            self.index = index
        self.logger.debug("Indexed %d BUENA/POW codes", len(index))

    def fetch_soup(self, url, warn=True):
        """Fetch a page and return its parsed soup, or `None` on failure.

        Args:
            url (str): The page URL.
            warn (bool): Whether to log a warning on failure. Set `False` when
                probing candidate URLs that are expected to 404.

        Returns:
            BeautifulSoup or None: The parsed document, or `None`.

        Raises:
            AccessRestrictedError: If the site returns a 403.
        """
        try:
            resp = self.session.get(url)
            self.raise_for_status(resp)
            html = resp.content.decode("utf-8", "ignore")
        except AccessRestrictedError:
            raise
        except Exception as e:
            if warn:
                self.logger.warning("Failed to fetch %s: %s", url, e)
            return None
        return BeautifulSoup(html, "html.parser")

    def parse_buena_page(self):
        """Return an `Entry` for each `table.product-list` on the BUENA page.

        Returns:
            list[Entry]: The parsed BUENA entries.
        """
        entries = []
        soup = self.fetch_soup(BUENA_URL)
        if soup is None:
            return entries
        for table in soup.select("table.product-list"):
            try:
                entry = self.parse_table(table)
            except Exception as e:
                self.logger.debug("Failed to parse a product-list table: %s", e)
                continue
            if entry and entry.code:
                entries.append(entry)
        return entries

    def parse_pow_page(self):
        """Return an `Entry` for each POW release row on the POW page.

        Returns:
            list[Entry]: The parsed POW entries.
        """
        entries = []
        soup = self.fetch_soup(POW_URL)
        if soup is None:
            return entries
        for tr in soup.find_all("tr"):
            try:
                entry = self.parse_pow_row(tr)
            except Exception as e:
                self.logger.debug("Failed to parse a POW row: %s", e)
                continue
            if entry and entry.code:
                entries.append(entry)
        return entries

    def parse_table(self, table):
        """Parse a single `table.product-list` element into an `Entry`.

        Args:
            table: A BeautifulSoup `<table class="product-list">` tag.

        Returns:
            Entry or None: The parsed entry, or `None` when it lacks a code.
        """
        entry = Entry()

        # The header spans all columns; it may be a <th> or a <td class="...">.
        header = table.find(lambda t: t.name in ("th", "td") and t.get("colspan") == "4")
        if header:
            self.fill_actresses(entry, header)
            self.fill_cosplay(entry, header)

        # Code row: the first row whose leading cell is exactly the primary buenaNNN
        # code. Cells are plain <td> - width attributes are inconsistent across entries.
        code_cells = None
        for tr in table.find_all("tr"):
            cells = tr.find_all("td", recursive=False)
            if cells and re.match(r"(?i)^buena0*\d+$", cells[0].get_text(strip=True) or u""):
                code_cells = cells
                break
        if not code_cells:
            return None
        codes = [self.clean_code(td.get_text(strip=True)) for td in code_cells[:4]]
        while len(codes) < 4:
            codes.append(None)
        primary, variant, amateur, av = codes[0], codes[1], codes[2], codes[3]
        m = re.match(r"(?i)buena0*(\d+)", primary or u"")
        if not m:
            return None
        entry.code = u"BUENA-%03d" % int(m.group(1))
        entry.amateur_code = amateur
        entry.av_code = av
        if amateur and amateur.upper().startswith(u"POW"):
            entry.studio = u"POW"
        for code in [primary, variant, amateur, av, entry.code]:
            if code:
                entry.add_key(code)

        # Duration: the first minutes marker in the table (the primary release).
        dm = re.search(u"(\\d+)\\s*分", table.get_text())
        if dm:
            entry.duration_ms = int(dm.group(1)) * 60 * 1000

        # Cover images embedded in the media cells (unwrap the i0.wp.com proxy).
        for img in table.find_all("img"):
            src = self.unwrap_image_url(img.get("src", ""))
            if "pics.dmm.co.jp/digital/video/" in src and not entry.fanza_av_ps:
                entry.fanza_av_ps = src
            elif "awsimgsrc.dmm.co.jp" in src and "/amateur/" in src and not entry.fanza_amateur:
                entry.fanza_amateur = src

        return entry

    def parse_pow_row(self, tr):
        """Parse a single POW release row into an `Entry`.

        A POW row is a `<tr>` with a cover cell and a text cell laid out as
        `POW-NNN / title / 発売日:date / 時間:Nmin / 女優:【actress】`.

        Args:
            tr: A BeautifulSoup `<tr>` tag.

        Returns:
            Entry or None: The parsed entry, or `None` when it is not a POW row.
        """
        cells = tr.find_all("td", recursive=False)
        if len(cells) < 2:
            return None
        text = cells[-1].get_text("\n", strip=True)
        lines = [l for l in text.split("\n") if l.strip()]
        if not lines:
            return None
        m = re.match(r"(?i)^POW-?0*(\d+)", lines[0])
        if not m:
            return None

        entry = Entry()
        entry.code = u"POW-%03d" % int(m.group(1))
        entry.studio = u"POW"
        entry.add_key(entry.code)
        entry.add_key(lines[0])

        # Title: the first non-labelled line after the code.
        for line in lines[1:]:
            if u"：" in line or u":" in line:
                break
            entry.title_text = line.strip()
            break

        dm = re.search(u"発売日[：:]\\s*(\\d{4})[-/](\\d{2})[-/](\\d{2})", text)
        if dm:
            try:
                entry.release_date = datetime.datetime(
                    int(dm.group(1)), int(dm.group(2)), int(dm.group(3)))
            except ValueError:
                pass

        tm = re.search(u"時間[：:]\\s*(\\d+)", text)
        if tm:
            entry.duration_ms = int(tm.group(1)) * 60 * 1000

        self.fill_actresses(entry, cells[-1])

        # Cover: prefer the full-size jp.jpg in the <a href>, else the thumbnail.
        link = cells[0].find("a", href=re.compile(r"awsimgsrc\.dmm\.co\.jp"))
        src = self.unwrap_image_url(link.get("href", "")) if link else u""
        if not src:
            img = cells[0].find("img")
            src = self.unwrap_image_url(img.get("src", "")) if img else u""
        if "awsimgsrc.dmm.co.jp" in src and "/amateur/" in src:
            entry.fanza_amateur = src

        return entry

    def make_search_item(self, entry):
        """Build a `SearchItem` from an `Entry`.

        Args:
            entry (Entry): The catalog entry.

        Returns:
            SearchItem: The search result.
        """
        return SearchItem(
            id=entry.code,
            video_code=entry.code,
            title=self.build_title(entry),
            score=100,
            thumb=entry.thumb(),
        )

    def fill_actresses(self, entry, scope):
        """Add actresses (with readings) from `/actress/` links within `scope`.

        Handles both relative and absolute hrefs and de-duplicates by name.

        Args:
            entry (Entry): The entry to populate.
            scope: A BeautifulSoup element to search within.
        """
        seen = set(name for name, reading in entry.actresses)
        for a in scope.select('a[href*="/actress/"]'):
            name = a.get_text(strip=True)
            if name and name not in seen:
                seen.add(name)
                entry.actresses.append((name, self.slug_reading(a.get("href", ""))))

    def fill_cosplay(self, entry, scope):
        """Set character / series from `/cosplay/` links within `scope`.

        A `/cosplay/<series>/<character>/` link is the character, a
        `/cosplay/<series>/` link is the series.

        Args:
            entry (Entry): The entry to populate.
            scope: A BeautifulSoup element to search within.
        """
        for a in scope.select('a[href*="/cosplay/"]'):
            text = a.get_text(strip=True)
            if not text:
                continue
            segments = [s for s in a.get("href", "").split("/") if s]
            if "cosplay" not in segments:
                continue
            depth = len(segments) - segments.index("cosplay") - 1
            if depth >= 2 and not entry.character:
                entry.character = text
            elif depth == 1 and not entry.series:
                entry.series = text

    def fetch_detail_entry(self, code):
        """Fetch and parse a konodare per-item detail page for `code`.

        Used for codes absent from the index pages (e.g. POW releases beyond the
        index range) that still have their own detail page.

        Args:
            code (str): A raw or normalized code such as `POW-084`.

        Returns:
            Entry or None: The parsed entry, or `None` if no page matches.
        """
        key = normalize_code(code)
        m = re.match(r"^([A-Z]+)(\d+)$", key)
        if not m:
            return None
        prefix, num = m.group(1), int(m.group(2))
        plow = prefix.lower()
        for slug in [u"%s%03d" % (plow, num), u"%s-%03d" % (plow, num)]:
            soup = self.fetch_soup(u"https://konodare.wew.jp/%s/" % slug, warn=False)
            if soup is None:
                continue
            h1 = soup.find("h1", class_="entry-title")
            if not h1 or normalize_code(h1.get_text(strip=True)) != key:
                continue
            try:
                entry = self.parse_detail_page(soup, prefix, num)
            except Exception as e:
                self.logger.debug("Failed to parse detail page %s: %s", slug, e)
                continue
            if entry and (entry.actresses or entry.character or
                          entry.fanza_amateur or entry.fanza_av_ps):
                self.logger.debug("Matched %s via detail page /%s/", entry.code, slug)
                return entry
        return None

    def parse_detail_page(self, soup, prefix, num):
        """Parse a konodare per-item detail page into an `Entry`.

        Args:
            soup: The parsed detail page.
            prefix (str): The code prefix, e.g. `POW`.
            num (int): The code number.

        Returns:
            Entry: The parsed entry.
        """
        entry = Entry()
        entry.code = u"%s-%03d" % (prefix.upper(), num)
        if prefix.upper() == u"POW":
            entry.studio = u"POW"
        entry.add_key(entry.code)

        scope = soup.find(class_="entry-content") or soup
        self.fill_actresses(entry, scope)
        self.fill_cosplay(entry, scope)

        # Theme title from <title>, used only when there is no character / series.
        title_tag = soup.find("title")
        if title_tag:
            title = re.sub(u"\\s*[|｜].*$", u"", title_tag.get_text(strip=True)).strip()
            if title and normalize_code(title) != normalize_code(entry.code):
                entry.title_text = title

        text = scope.get_text(u"\n", strip=True)
        dm = re.search(u"(\\d+)\\s*分", text)
        if dm:
            entry.duration_ms = int(dm.group(1)) * 60 * 1000
        rd = re.search(u"発売日[：:]\\s*(\\d{4})[-/](\\d{2})[-/](\\d{2})", text)
        if rd:
            try:
                entry.release_date = datetime.datetime(
                    int(rd.group(1)), int(rd.group(2)), int(rd.group(3)))
            except ValueError:
                pass

        for img in scope.find_all("img"):
            src = self.unwrap_image_url(img.get("src", ""))
            if "pics.dmm.co.jp/digital/video/" in src and not entry.fanza_av_ps:
                entry.fanza_av_ps = src
            elif "awsimgsrc.dmm.co.jp" in src and "/amateur/" in src and not entry.fanza_amateur:
                entry.fanza_amateur = src

        return entry

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def build_title(self, entry):
        """Build the display title `[CODE] character (series)` or `[CODE] title`.

        Args:
            entry (Entry): The catalog entry.

        Returns:
            str: The constructed title.
        """
        if entry.character and entry.series:
            inner = u"%s (%s)" % (entry.character, entry.series)
        elif entry.character:
            inner = entry.character
        elif entry.series:
            inner = entry.series
        else:
            inner = entry.title_text
        if inner:
            return u"[%s] %s" % (entry.code, inner)
        return u"[%s]" % entry.code

    def build_images(self, entry):
        """Build poster and art `Resource` lists from the FANZA covers.

        Prefers the large FANZA AV cover as the poster (deriving `pl.jpg` from
        `ps.jpg` and validating it), falling back to the small `ps.jpg`
        thumbnail and then the FANZA amateur cover.

        Args:
            entry (Entry): The catalog entry.

        Returns:
            tuple[list[Resource], list[Resource]]: The `(posters, art)` lists.
        """
        posters = []
        art = []
        if entry.fanza_av_ps:
            # Prefer the large pl.jpg as the poster - it is far higher resolution than the small ps.jpg thumbnail, and it doubles as the background art.
            # Fall back to the ps.jpg thumbnail only when the large cover is unavailable.
            large = re.sub(r"(?<=/)([^/]+)(?:ps|pt)\.jpg$", r"\1pl.jpg", entry.fanza_av_ps)
            if large != entry.fanza_av_ps and self.validate_resource(large, "image/"):
                poster = Resource(large)
                poster.score = 60
                posters.append(poster)
                cover = Resource(large)
                cover.score = 60
                art.append(cover)
            else:
                poster = Resource(entry.fanza_av_ps)
                poster.score = 60
                posters.append(poster)
        if entry.fanza_amateur:
            poster = Resource(entry.fanza_amateur)
            poster.score = 50
            posters.append(poster)
            if not art:
                cover = Resource(entry.fanza_amateur)
                cover.score = 50
                art.append(cover)
        posters.sort(key=lambda r: r.score, reverse=True)
        art.sort(key=lambda r: r.score, reverse=True)
        return posters, art

    def clean_code(self, text):
        """Return a code cell's text, or `None` for an empty / dash cell.

        Args:
            text (str): The stripped cell text.

        Returns:
            str or None: The code, or `None`.
        """
        text = (text or u"").strip()
        if not text or text in (u"-", u"–", u"—", u"−"):
            return None
        return text

    def unwrap_image_url(self, src):
        """Strip the Jetpack Photon (`i0.wp.com`) wrapper and query from `src`.

        Args:
            src (str): The raw image `src` attribute.

        Returns:
            str: The direct image URL, or an empty string.
        """
        if not src:
            return u""
        src = src.strip()
        m = re.match(r"https?://i\d\.wp\.com/(.+)", src)
        if m:
            src = u"https://" + m.group(1)
        return src.split(u"?", 1)[0]

    def slug_reading(self, href):
        """Derive an actress-name reading from an `/actress/<slug>/` href.

        The slug is the hiragana reading with a hyphen between family and given
        names. Handles both relative (`/actress/...`) and absolute
        (`https://.../actress/...`) hrefs, and percent-encoded slugs.

        Args:
            href (str): The actress link href.

        Returns:
            str or None: The space-separated hiragana reading, or `None`.
        """
        segments = [s for s in (href or u"").split("/") if s]
        slug = None
        for i, segment in enumerate(segments):
            if segment.lower() == "actress" and i + 1 < len(segments):
                slug = segments[i + 1]
                break
        if not slug:
            return None
        if u"%" in slug:
            try:
                slug = unquote(slug.encode("ascii")).decode("utf-8", "ignore")
            except Exception:
                return None
        return slug.replace(u"-", u" ").strip() or None
