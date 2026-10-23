# coding=utf-8

import datetime
import re
from urllib import unquote

from bs4 import BeautifulSoup

from .avbase import AVBase
from .base import AccessRestrictedError, MetadataAgent, SearchAgent
from .getchu import extract_dl_id, extract_soft_id, fetch_dl_item, fetch_soft, search_soft_id
from .types import Metadata, Person, Resource, SearchItem
from .utils import get_code_group


# konodare.wew.jp catalogs BUENA and its sister lines on separate pages:
#   /buena/   - cosplay releases (buenaNNN) as `table.product-list` entries, paginated. Page 2 holds the buenaS / buenaTS
#               specials and the buenap (たかまり) entries, which are the POW releases.
#   /asaichi/ - the older buena001-074 (朝一番) as one big table.
#   /pow/     - the POW amateur line (POW-NNN) as one row per release, with title, release date, duration, actress and cover.
# The /buena/ and /asaichi/ tables are runs of a header row (actress / cosplay) followed by code rows and their media rows.
BUENA_URL = u"https://konodare.wew.jp/buena/"
ASAICHI_URL = u"https://konodare.wew.jp/asaichi/"
POW_URL = u"https://konodare.wew.jp/pow/"

# Upper bound on followed `/buena/` pages, in case the pagination links loop.
MAX_BUENA_PAGES = 5

# Matches any supported code with optional separators and zero-padding, e.g. "buena075", "BUENA-075", "buenaS002",
# "asaichi001", "prin-042", "zarj070", "pow046".
CODE_RE = re.compile(r"(?i)(buena(?:ts|s|p)?|asaichi|pow|zarj|prin)[\s_\-]*0*(\d+)([a-z]?)")

# The primary code that starts an entry's code row, e.g. "buena001", "buenaTS003" or "buenap040". Variants like "buena075b" do not match.
PRIMARY_CODE_RE = re.compile(r"(?i)^(buena(?:ts|s|p)?)0*(\d+)$")

# Any code-like token in a catalog cell, e.g. "asaichi001", "ZARJ070" or "PRIN-042".
CODE_TOKEN_RE = re.compile(r"^[A-Za-z]+-?\d+[A-Za-z]?$")

# A POW code token, e.g. "POW023" or "pow-040".
POW_TOKEN_RE = re.compile(r"(?i)^pow-?\d+$")

# A FANZA product link (after unquoting the affiliate `lurl`), on either the new or the old site layout.
FANZA_LINK_RE = re.compile(r"dmm\.co\.jp/(?:(amateur|av)/content/\?id=|digital/(videoc|videoa)/-/detail/=/cid=)([a-z0-9_]+)")

# FANZA cover images on either image host (pics.dmm.co.jp or awsimgsrc.dmm.co.jp).
FANZA_AV_IMG_RE = re.compile(r"/digital/video/([a-z0-9_]+)/\1(?:ps|pt|pl)\.jpg$")
FANZA_AMATEUR_IMG_RE = re.compile(r"^(.*/digital/amateur/([a-z0-9_]+)/\2)j[a-z]?\.jpg$")

# A cosplay release code on its own, after `normalize_code()`, e.g. "BUENA369".
BUENA_KEY_RE = re.compile(r"^BUENA(\d+)$")

# The leading code and the trailing full-width bracket tag (e.g. "[cosplay]") around a Getchu product title.
GETCHU_TITLE_RE = re.compile(u"(?i)^\\s*buena\\d+\\s*|\\s*\uff3b[^\uff3d]*\uff3d\\s*$")

# Placeholders konodare uses for an empty cell or an unknown actress.
DASHES = (u"-", u"–", u"—", u"−", u"―")


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


def cid_to_code(cid):
    """Turn a FANZA content id into a display code, e.g. "prin00042" into "PRIN-042".

    Args:
        cid (str): The FANZA content id, e.g. `57eiki00078` or `zarj070`.

    Returns:
        str: The display code, or the upper-cased cid when it has no letters + number shape.
    """
    m = re.match(r"^\d*([a-z]+)0*(\d+)([a-z]?)$", cid.lower())
    if not m:
        return cid.upper()
    return u"%s-%03d%s" % (m.group(1).upper(), int(m.group(2)), m.group(3).upper())


class Entry(object):
    """A single parsed catalog entry (BUENA cosplay or POW amateur)."""

    def __init__(self):
        self.code = None            # canonical id, e.g. "BUENA-075" or "POW-046"
        self.title_text = None      # plain title (POW title or header nickname), used when there is no character / series
        self.actresses = []         # list of (name, reading) tuples
        self.character = None       # cosplay character name (BUENA)
        self.series = None          # source work name (BUENA)
        self.studio = u"BUENA"      # "POW" for POW entries / POW-labelled BUENA
        self.release_date = None    # datetime (POW entries)
        self.amateur_code = None    # e.g. "ZARJ-070" or "POW-023"
        self.av_code = None         # e.g. "PRIN-042"
        self.duration_ms = None
        self.fanza_av_ps = None       # .../digital/video/<cid>/<cid>ps.jpg
        self.fanza_amateur = None     # .../digital/amateur/<cid>/<cid>jp.jpg
        self.getchu_id = None         # Getchu product id, e.g. "1108622"
        self.dlgetchu_id = None       # DL.Getchu item id, e.g. "4038100"
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

    def has_data(self):
        """Return whether the entry carries anything beyond its code.

        konodare lists placeholder rows (grey, empty cells) for releases it knows nothing about.

        Returns:
            bool: True when the entry has a store id, a cross-ref code, a cover or a duration.
        """
        return bool(self.getchu_id or self.dlgetchu_id or self.amateur_code or self.av_code or
                    self.fanza_av_ps or self.fanza_amateur or self.duration_ms)


class Buena(SearchAgent, MetadataAgent):
    """Agent that scrapes BUENA / POW cosplay-AV metadata from konodare.wew.jp."""

    name = "BUENA"
    weight = 1000

    # Parsed index (code key -> Entry), cached for the process lifetime. Set on
    # the instance the first time it is built, shadowing this class default.
    index = None

    # AVBase agent used to backfill fields from the FANZA cross-ref codes, built on first use.
    avbase = None

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Search

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
            entry = self.fetch_detail_entry(kw) or self.fetch_getchu_entry(kw)
            if entry:
                for key in entry.code_keys:
                    self.index.setdefault(key, entry)
                return [self.make_search_item(entry)]
        return []

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Metadata

    def get_metadata(self, agent_id, video_code, lang):
        self.ensure_index()
        entry = self.index.get(normalize_code(video_code)) or self.index.get(normalize_code(agent_id))
        if not entry:
            entry = self.fetch_detail_entry(video_code) or self.fetch_detail_entry(agent_id) or self.fetch_getchu_entry(video_code)
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

        if self.prefs["getchu_enabled"]:
            self.hydrate_from_getchu(entry, metadata)
        self.hydrate_from_avbase(entry, metadata, lang)

        return metadata

    def hydrate_from_avbase(self, entry, metadata, lang):
        """Fill the summary, labels and directors that are still empty from AVBase's page for the entry's FANZA cross-ref.

        The FANZA codes are compilations or re-releases, so their title, date, cast and covers are never used. A failed lookup only logs a
        warning.

        Args:
            entry (Entry): The catalog entry carrying the cross-ref codes.
            metadata (Metadata): The metadata to fill in place.
            lang (str): The metadata language.
        """
        codes = [code for code in [entry.av_code, entry.amateur_code] if code and code != entry.code]
        if not codes or (metadata.summary and metadata.labels and metadata.directors):
            return
        if self.avbase is None:
            self.avbase = AVBase(self.prefs)
        if not self.avbase.enabled:
            return
        for code in codes:
            try:
                items = [item for item in self.avbase.search([code], lang) if item.score == 100]
                if not items:
                    continue
                other = self.avbase.get_metadata(items[0].id, code, lang)
            except Exception as e:
                self.logger.warning("AVBase lookup of %s for %s failed: %s", code, entry.code, e)
                continue
            if other.summary and not metadata.summary:
                metadata.summary = other.summary
            if other.labels and not metadata.labels:
                metadata.labels = other.labels
            if other.directors and not metadata.directors:
                metadata.directors = other.directors
            if other.genres:
                metadata.genres.update(other.genres)
            self.logger.debug("Backfilled %s from AVBase %s", entry.code, code)
            return

    def hydrate_from_getchu(self, entry, metadata):
        """Fill the summary, release date, genres, duration and covers from the entry's Getchu pages.

        konodare has no synopsis or release date for BUENA entries. A failed fetch only logs a warning, so the konodare metadata is kept.

        Args:
            entry (Entry): The catalog entry carrying the Getchu ids.
            metadata (Metadata): The metadata to fill in place.
        """
        dl_info = self.fetch_getchu_page(fetch_dl_item, entry.dlgetchu_id, entry.code)
        soft_info = self.fetch_getchu_page(fetch_soft, entry.getchu_id, entry.code)

        # DL.Getchu has the full synopsis. The Getchu product page has the original package release date.
        for info in [dl_info, soft_info]:
            if info.get("description") and not metadata.summary:
                metadata.summary = info["description"]
        for info in [soft_info, dl_info]:
            if info.get("release_date") and not metadata.release_date:
                metadata.release_date = info["release_date"]
        for genre in dl_info.get("genres") or []:
            metadata.genres.add(genre)
        if soft_info.get("duration_min") and not metadata.duration:
            metadata.duration = soft_info["duration_min"] * 60 * 1000

        # The Getchu package is a square disc label and the DL.Getchu top image is a wide montage that crops badly, so both rank below FANZA.
        posters = list(metadata.posters or [])
        for info, score in [(soft_info, 45), (dl_info, 30)]:
            if info.get("cover_url"):
                poster = Resource(info["cover_url"])
                poster.score = score
                posters.append(poster)
        if posters:
            posters.sort(key=lambda r: r.score, reverse=True)
            metadata.posters = posters

    def fetch_getchu_page(self, fetch, item_id, code):
        """Fetch one Getchu page, returning an empty dict when there is no id or the fetch fails.

        Args:
            fetch: `fetch_soft()` or `fetch_dl_item()`.
            item_id (str): The Getchu product or DL.Getchu item id, or None.
            code (str): The entry code, used in the warning.

        Returns:
            dict: The parsed page fields, or an empty dict.
        """
        if not item_id:
            return {}
        try:
            return fetch(self.session, item_id, self.raise_for_status)
        except Exception as e:
            self.logger.warning("Getchu fetch %s for %s failed: %s", item_id, code, e)
            return {}

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Index cache

    def ensure_index(self):
        """Fetch and parse the catalog pages once, caching the result.

        POW is indexed first so that POW-NNN codes resolve to the dedicated POW entries rather than a BUENA cross-reference. The
        buenap rows on /buena/ are merged into their POW entry. Cached for the process lifetime once non-empty.
        """
        if self.index is not None:
            return

        index = {}
        for entry in self.parse_pow_page():
            for key in entry.code_keys:
                index.setdefault(key, entry)
        for entry in self.parse_buena_pages() + self.parse_catalog_page(ASAICHI_URL):
            target = entry
            if entry.code.startswith(u"BUENAP-"):
                pow_entry = index.get(normalize_code(entry.amateur_code))
                if pow_entry is not None and pow_entry.code.startswith(u"POW-"):
                    self.merge_into_pow(pow_entry, entry)
                    target = pow_entry
                elif entry.amateur_code and entry.amateur_code.startswith(u"POW-"):
                    # Newer than the POW page: the buenap row is the only record, so name it by its POW code.
                    entry.code = entry.amateur_code
            for key in entry.code_keys:
                index.setdefault(key, target)

        if index:
            self.index = index
        self.logger.debug("Indexed %d BUENA/POW codes", len(index))

    def merge_into_pow(self, pow_entry, entry):
        """Copy the store ids and cross-refs of a buenap row into the POW entry it describes.

        Args:
            pow_entry (Entry): The entry parsed from the POW page.
            entry (Entry): The buenap entry parsed from the BUENA page.
        """
        pow_entry.getchu_id = pow_entry.getchu_id or entry.getchu_id
        pow_entry.dlgetchu_id = pow_entry.dlgetchu_id or entry.dlgetchu_id
        pow_entry.av_code = pow_entry.av_code or entry.av_code
        pow_entry.fanza_av_ps = pow_entry.fanza_av_ps or entry.fanza_av_ps
        if not pow_entry.actresses:
            pow_entry.actresses = entry.actresses
        pow_entry.code_keys.update(entry.code_keys)

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

    def parse_buena_pages(self):
        """Return the entries from every `/buena/` page, following the pagination links.

        Returns:
            list[Entry]: The parsed BUENA entries.
        """
        entries = []
        url = BUENA_URL
        seen = set()
        while url and url not in seen and len(seen) < MAX_BUENA_PAGES:
            seen.add(url)
            soup = self.fetch_soup(url)
            if soup is None:
                break
            entries.extend(self.parse_catalog(soup))
            link = soup.find("link", rel="next")
            url = link.get("href") if link else None
        return entries

    def parse_catalog_page(self, url):
        """Return the entries from a single catalog page.

        Args:
            url (str): The page URL.

        Returns:
            list[Entry]: The parsed entries.
        """
        soup = self.fetch_soup(url)
        if soup is None:
            return []
        return self.parse_catalog(soup)

    def parse_catalog(self, soup):
        """Return an `Entry` for each code row in the catalog tables of a page.

        Args:
            soup: The parsed catalog page.

        Returns:
            list[Entry]: The parsed entries.
        """
        entries = []
        scope = soup.find(class_="entry-content") or soup
        for table in scope.find_all("table"):
            try:
                entries.extend(self.parse_catalog_table(table))
            except Exception as e:
                self.logger.debug("Failed to parse a catalog table: %s", e)
        return entries

    def parse_catalog_table(self, table):
        """Parse a catalog table into entries.

        A header row (a cell spanning 3-4 columns) holds the actress and cosplay of the code rows below it. Each code row starts
        with a primary code such as `buena075` and is followed by media rows for the same entry. Cells sitting beside the header
        (a `rowspan` cell shared with the next code row) belong to that next entry.

        Args:
            table: A BeautifulSoup `<table>` tag.

        Returns:
            list[Entry]: The parsed entries, without placeholder rows.
        """
        entries = []
        header = None
        header_cells = []
        entry = None
        for tr in table.find_all("tr"):
            if tr.find_parent("table") is not table:
                continue
            cells = tr.find_all(["td", "th"], recursive=False)
            if not cells:
                continue
            if cells[0].get("colspan") in ("3", "4"):
                header = cells[0]
                header_cells = cells[1:]
                entry = None
                continue
            code = self.primary_code(cells[0])
            if code and (entry is None or code != entry.code):
                entry = self.new_entry(code, header)
                entries.append(entry)
                # Header-side cells come last so the entry's own duration wins over a shared compilation's.
                for cell in cells + header_cells:
                    self.collect_cell(entry, cell)
                header_cells = []
            elif entry is not None:
                for cell in cells:
                    self.collect_cell(entry, cell)
        return [e for e in entries if e.has_data()]

    def primary_code(self, cell):
        """Return the canonical code when `cell` starts with a primary code, e.g. `BUENA-001` for "buena001 asaichi001".

        Args:
            cell: The first cell of a table row.

        Returns:
            str or None: The canonical code, or `None` when the row is not a code row.
        """
        tokens = cell.get_text(u" ", strip=True).split()
        m = PRIMARY_CODE_RE.match(tokens[0]) if tokens else None
        if not m:
            return None
        return u"%s-%03d" % (m.group(1).upper(), int(m.group(2)))

    def new_entry(self, code, header):
        """Create an entry for `code`, filled from its header row.

        Args:
            code (str): The canonical code.
            header: The header cell above the code row, or `None`.

        Returns:
            Entry: The new entry.
        """
        entry = Entry()
        entry.code = code
        entry.add_key(code)
        if header is not None:
            self.fill_header(entry, header)
        return entry

    def fill_header(self, entry, header):
        """Fill actresses, cosplay and the nickname title from a header cell.

        Headers either link `/actress/` and `/cosplay/` pages, or are plain text like "みごっち【ひなた澪】" with a
        `span.right` line label (朝一番 / たかまり) in front.

        Args:
            entry (Entry): The entry to populate.
            header: The header cell.
        """
        self.fill_actresses(entry, header)
        self.fill_cosplay(entry, header)
        text = u"".join(s for s in header.find_all(string=True) if not s.find_parent("span", class_="right"))
        text = u" ".join(text.split())
        if not entry.actresses:
            self.fill_actress_text(entry, text)
        title = u" ".join(re.sub(u"【.*?】", u" ", text).split())
        if title.count(u")") > title.count(u"("):
            title = title.rstrip(u")").strip()
        entry.title_text = title or None

    def collect_cell(self, entry, cell):
        """Collect codes, store ids, FANZA covers and the duration from one catalog cell.

        Args:
            entry (Entry): The entry to populate.
            cell: A BeautifulSoup `<td>` tag.
        """
        text = cell.get_text(u" ", strip=True)
        for token in text.split():
            if CODE_TOKEN_RE.match(token):
                entry.add_key(token)
                # A plain POW cross-ref code (e.g. "POW023") marks a POW-labelled release even without a FANZA link.
                if POW_TOKEN_RE.match(token) and not entry.amateur_code:
                    entry.amateur_code = cid_to_code(token)
                    entry.studio = u"POW"
        for a in cell.find_all("a", href=True):
            self.collect_url(entry, a["href"])
        for img in cell.find_all("img"):
            self.collect_url(entry, self.unwrap_image_url(img.get("src", "")))
        if not entry.duration_ms:
            dm = re.search(u"(\\d+)\\s*分", text)
            if dm:
                entry.duration_ms = int(dm.group(1)) * 60 * 1000

    def collect_url(self, entry, url):
        """Collect store ids, FANZA cross-ref codes and covers from a link or image url.

        Args:
            entry (Entry): The entry to populate.
            url (str): The href or image src.
        """
        if not url:
            return
        if u"%" in url:
            url = unquote(url.encode("utf-8")).decode("utf-8", "ignore")
        entry.getchu_id = entry.getchu_id or extract_soft_id(url)
        entry.dlgetchu_id = entry.dlgetchu_id or extract_dl_id(url)

        m = FANZA_LINK_RE.search(url)
        if m:
            code = cid_to_code(m.group(3))
            if m.group(1) == "amateur" or m.group(2) == "videoc":
                entry.amateur_code = entry.amateur_code or code
                if code.startswith(u"POW"):
                    entry.studio = u"POW"
            else:
                entry.av_code = entry.av_code or code
            entry.add_key(code)

        if FANZA_AV_IMG_RE.search(url) and not entry.fanza_av_ps:
            entry.fanza_av_ps = url
        m = FANZA_AMATEUR_IMG_RE.search(url)
        if m and not entry.fanza_amateur:
            entry.fanza_amateur = m.group(1) + u"jp.jpg"

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

        # Many rows name the actress as plain text instead of an /actress/ link.
        self.fill_actresses(entry, cells[-1])
        cast = cells[-1].get_text(u"", strip=True)
        if not entry.actresses and u"女優" in cast:
            self.fill_actress_text(entry, cast[cast.index(u"女優"):])

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

    def fill_actress_text(self, entry, text):
        """Add actresses named as plain text inside the first `【...】` of `text`.

        Args:
            entry (Entry): The entry to populate.
            text (str): Text such as "みごっち【ひなた澪】" or "女優：【高坂あいり】".
        """
        m = re.search(u"【(.*?)】", text or u"")
        if not m:
            return
        seen = set(name for name, reading in entry.actresses)
        for name in re.split(u"[、,/／]", m.group(1)):
            name = name.strip()
            if name and name not in DASHES and name not in seen:
                seen.add(name)
                entry.actresses.append((name, None))

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

    def fetch_getchu_entry(self, code):
        """Build an entry from the Getchu product page for a cosplay release that konodare has not listed yet.

        Args:
            code (str): A raw or normalized code such as `buena369`.

        Returns:
            Entry or None: The entry, or `None` when the code is not a `BUENA` code, Getchu is disabled or has no such product.
        """
        m = BUENA_KEY_RE.match(normalize_code(code) or u"")
        if not m or not self.prefs["getchu_enabled"]:
            return None
        slug = u"buena%03d" % int(m.group(1))
        try:
            soft_id = search_soft_id(self.session, slug, self.raise_for_status)
            info = fetch_soft(self.session, soft_id, self.raise_for_status) if soft_id else None
        except Exception as e:
            self.logger.warning("Getchu search for %s failed: %s", slug, e)
            return None
        if not info:
            return None

        entry = Entry()
        entry.code = u"BUENA-%03d" % int(m.group(1))
        entry.add_key(entry.code)
        entry.getchu_id = soft_id
        entry.title_text = GETCHU_TITLE_RE.sub(u"", info["title"] or u"") or None
        entry.release_date = info["release_date"]
        if info["duration_min"]:
            entry.duration_ms = info["duration_min"] * 60 * 1000
        self.logger.debug("Matched %s via Getchu product %s", entry.code, soft_id)
        return entry

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
            self.collect_url(entry, self.unwrap_image_url(img.get("src", "")))

        return entry

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Helpers

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
