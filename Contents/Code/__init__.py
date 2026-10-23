# coding=utf-8

from __future__ import absolute_import

from collections import OrderedDict
import json
import logging
import os
import struct
import requests
from urlparse import urlparse

import agents
from agents import BaseAgent, Metadata, MetadataAgent, PartialMetadataAgent, SearchAgent


version = "2026.03.1"

# Portraits shorter than this are thumbnails (DMM `ps.jpg` is 200px, pixhost thumbs 300px), not usable posters.
MIN_PORTRAIT_POSTER_HEIGHT = 400


def Start():
    Log.Info("Starting JAV Agent version %s", version)

    agents_logger = logging.getLogger("agents")
    if not agents_logger.handlers:
        agents_logger.addHandler(PlexLogHandler())
        agents_logger.setLevel(logging.DEBUG)
        agents_logger.propagate = False

    log_prefs()


def ValidatePrefs():
    fs_url = Prefs["flaresolverr_url"]
    if fs_url and fs_url.strip():
        parsed = urlparse(fs_url.strip())
        if not parsed.scheme or not parsed.netloc:
            return MessageContainer("Invalid Preference",
                                    "Flaresolverr URL is not a valid URL.")

    log_prefs()


class JAVAgent(Agent.Movies):
    name = "JAV (V2)"
    languages = [
        Locale.Language.NoLanguage,
        Locale.Language.Japanese,
        Locale.Language.English,
        Locale.Language.Chinese,
    ]
    primary_provider = True
    accepts_from = [
        "com.plexapp.agents.localmedia",
    ]

    def search(self, results, hints, lang, manual=False):
        filename = os.path.basename(hints.items[0].parts[0].file)
        directory = os.path.basename(
            os.path.dirname(hints.items[0].parts[0].file))

        name = getattr(hints, "name", "")
        Log.Info(
            "Search start name=%s filename=%s directory=%s lang=%s manual=%s",
            name, filename, directory, lang, manual
        )
        lang = self.normalize_lang(lang)

        # search with all search agents
        search_results = []
        for agent in filter(lambda a: isinstance(a, SearchAgent), self.agents):
            keywords = agent.guess_keywords(name, filename, directory)
            if not keywords:
                agent.logger.debug("No keywords guessed")
                continue
            agent.logger.debug("Guessed keywords: %s", keywords)
            try:
                agent_results = agent.search(keywords, lang)
                agent.logger.debug("Search results: %s", agent_results)
            except Exception as e:
                agent.logger.exception("Search failed: %s", e)
                continue

            # merge search results
            for ar in agent_results:
                for sr in search_results:
                    if ar.video_code == sr.video_code:
                        sr.id = update_metadata_id(sr.id, agent.name, ar.id)
                        break
                else:
                    ar.id = update_metadata_id(
                        ar.video_code, agent.name, ar.id)
                    search_results.append(ar)

        # convert to Plex search results
        search_results.sort(key=lambda r: r.score, reverse=True)
        for sr in search_results:
            results.Append(MetadataSearchResult(
                id=sr.id,
                name=self.uncensor_text(sr.title, lang),
                year=sr.year,
                score=sr.score,
                lang=lang,
                thumb=sr.thumb,
            ))

        # log final outcome
        best = None
        if len(search_results):
            best = search_results[0]
        if best:
            Log.Info("Search done count=%d best_metadata_id=%s best_title=%s",
                     len(search_results), best.id, best.title)
        else:
            Log.Info("Search done count=0")

    def update(self, movie, media, lang, force=False, periodic=False):
        Log.Info("Update start metadata_id=%s lang=%s force=%s periodic=%s",
                 movie.id, lang, force, periodic)
        lang = self.normalize_lang(lang)

        if is_legacy_metadata_id(movie.id):
            Log.Debug("Legacy metadata ID detected, running search: %s", movie.id)
            results = SearchResultCollection()
            self.search(results, media, lang, manual=False)
            if results:
                Log.Info("Resolved legacy metadata ID: %s -> %s",
                         movie.id, results[0].id)
                movie.id = results[0].id
            else:
                Log.Info("Search returned no results for legacy metadata ID: %s",
                         movie.id)

        video_code, agent_ids = parse_metadata_id(movie.id)
        metadata = Metadata()
        for agent in filter(lambda a: isinstance(a, MetadataAgent) or isinstance(
                a, PartialMetadataAgent), self.agents):
            if isinstance(agent, PartialMetadataAgent):
                try:
                    agent.partial_update(video_code, metadata, lang)
                except Exception as e:
                    agent.logger.exception("Partial update failed: %s", e)
                continue

            agent_id = agent_ids.get(agent.name)
            if not agent_id:
                continue

            try:
                agent_metadata = agent.get_metadata(agent_id, video_code, lang)
                agent.logger.debug("Metadata: %s", agent_metadata)
            except Exception as e:
                agent.logger.exception("Metadata retrieval failed: %s", e)
                continue

            # merge metadata
            for attr in dir(agent_metadata):
                new_value = getattr(agent_metadata, attr)
                if agent.should_contribute_to(metadata, attr, new_value):
                    current_value = getattr(metadata, attr)
                    contribution_value = agent.get_contribution_value(
                        new_value, attr, current_value)
                    setattr(metadata, attr, contribution_value)

        if force:
            self.clear_metadata(movie)

        self.apply_metadata(movie, metadata, lang)
        Log.Info("Update done: %s", repr(metadata))

    def clear_metadata(self, metadata):
        metadata.art.validate_keys([])
        metadata.rating = None
        metadata.collections.clear()
        metadata.directors.clear()
        metadata.duration = None
        metadata.genres.clear()
        metadata.originally_available_at = None
        metadata.original_title = ""
        metadata.posters.validate_keys([])
        metadata.roles.clear()
        metadata.similar.clear()
        metadata.studio = ""
        metadata.summary = ""
        metadata.tags.clear()
        metadata.title = ""
        metadata.title_sort = ""
        metadata.year = None

    def apply_metadata(self, movie, metadata, lang):
        movie.content_rating_age = 18
        movie.content_rating = "XXX"
        movie.countries.clear()
        movie.countries.add("JP")

        similar = set()
        tags = set()

        if metadata.code_group:
            similar.add(metadata.code_group)
        movie.title = self.uncensor_text(metadata.title, lang)
        if metadata.japanese_title:
            movie.original_title = self.uncensor_text(
                metadata.japanese_title, lang)
        if metadata.release_date:
            movie.originally_available_at = metadata.release_date
            movie.year = metadata.release_date.year
        if metadata.studio:
            movie.studio = metadata.studio
            similar.add(metadata.studio)
        if metadata.series:
            series = self.uncensor_text(metadata.series, lang)
            similar.add(series)
            tags.add(series)
            if Prefs["series_as_collection"]:
                movie.collections.add(series)
        if metadata.duration:
            movie.duration = metadata.duration

        if metadata.actresses:
            movie.roles.clear()
            for o in metadata.actresses:
                role = movie.roles.new()
                # Show the Japanese name in parentheses after the romaji name
                # (e.g. "Himesaki Hana (...)") when both are available.
                ja = getattr(o, "japanese_name", None)
                role.name = u"{0} ({1})".format(o, ja) if ja and ja != o else o
                role.photo = o.photo
        if metadata.directors:
            movie.directors.clear()
            for o in metadata.directors:
                director = movie.directors.new()
                ja = getattr(o, "japanese_name", None)
                director.name = u"{0} ({1})".format(o, ja) if ja and ja != o else o
                director.photo = o.photo

        # Clear stored images first so stale posters and art never linger, even when this match produced none.
        movie.posters.validate_keys([])
        movie.art.validate_keys([])

        # Download only the single highest-quality cover as the poster. The large cover often lives in the art list, so pool the
        # cover-quality art (score >= 50) with the posters. Lower-scored scene stills are skipped.
        poster_candidates = self.dedup_resources(
            list(metadata.posters or []) +
            [a for a in (metadata.art or []) if a.score >= 50])
        best_poster = self.pick_best_poster(poster_candidates)
        downloaded = {}
        if best_poster is not None:
            data = self.download_image(best_poster)
            if data is not None:
                # Keep the original (uncropped) bytes for art reuse below, but crop the front cover out for the poster.
                downloaded[best_poster] = data
                movie.posters[best_poster] = Proxy.Media(self.crop_front_cover(data))

        # Keep the largest cover-quality image as the fanart backdrop. Reuse the poster bytes when it is the same image.
        best_art = self.pick_largest_image(self.dedup_resources(
            [a for a in (metadata.art or []) if a.score >= 50]))
        if best_art is not None:
            data = downloaded.get(best_art)
            if data is None:
                data = self.download_image(best_art)
            if data is not None:
                movie.art[best_art] = Proxy.Media(data)

        if metadata.trailers:
            trailer = TrailerObject(
                file=metadata.trailers[0],
                thumb=metadata.trailers[0].thumb
            )
            movie.extras.add(trailer)

        title_sort = metadata.title_sort or metadata.title
        if title_sort:
            movie.title_sort = self.uncensor_text(title_sort, lang)
        if metadata.genres:
            movie.genres.clear()
            for g in metadata.genres:
                movie.genres.add(g)
        if metadata.labels:
            labels = {self.uncensor_text(l, lang) for l in metadata.labels}
            tags.update(labels)
            similar.update(labels)
        if metadata.summary:
            movie.summary = metadata.summary
        if metadata.rating is not None:
            movie.rating = metadata.rating

        if similar:
            movie.similar.clear()
            for s in similar:
                movie.similar.add(s)
        if tags:
            movie.tags.clear()
            for t in tags:
                movie.tags.add(t)

    def dedup_resources(self, resources):
        """Return the resources in order with duplicates and preview-thumb entries removed.

        Args:
            resources (list): Candidate image resources.

        Returns:
            list: The de-duplicated image resources, preserving order.
        """
        seen = set()
        out = []
        for r in resources:
            if r and not r.thumb and r not in seen:
                seen.add(r)
                out.append(r)
        return out

    def image_size(self, url):
        """Return the byte size of the image at `url` via a HEAD request.

        Args:
            url (str): The image URL to size.

        Returns:
            int: The Content-Length in bytes, or -1 when the request fails or the resource is not an image.
        """
        try:
            resp = requests.head(url, allow_redirects=True)
            resp.raise_for_status()
            if not resp.headers.get("Content-Type", "").startswith("image/"):
                return -1
            return int(resp.headers.get("Content-Length") or 0)
        except Exception as e:
            Log.Info("Failed to size image %s: %s", url, e)
            return -1

    def pick_largest_image(self, resources):
        """Return the resource whose image has the largest byte size.

        Falls back to the first (highest-scored) resource when no sizes can be measured.

        Args:
            resources (list): Candidate image resources, ordered by score.

        Returns:
            The chosen resource, or None when the list is empty.
        """
        best = None
        best_size = -1
        for r in resources:
            size = self.image_size(r)
            if size > best_size:
                best_size = size
                best = r
        if best is None and resources:
            best = resources[0]
        return best

    def image_dimensions(self, url):
        """Return the (width, height) of the image at `url`, or None.

        Range-reads only the first 64 KB so orientation can be checked cheaply without downloading the whole image.

        Args:
            url (str): The image URL to measure.

        Returns:
            tuple[int, int]: The (width, height), or None when it cannot be determined.
        """
        try:
            resp = requests.get(
                url, headers={"Range": "bytes=0-65535"}, timeout=15)
            resp.raise_for_status()
            return parse_jpeg_dimensions(resp.content)
        except Exception as e:
            Log.Info("Failed to read dimensions of %s: %s", url, e)
            return None

    def is_portrait(self, resource):
        """Return True when the image is a full-size native portrait (taller than wide).

        A portrait image is a ready-to-use front-cover poster. A landscape image is a wide front+back cover (or a promo
        montage / scene still) that would need cropping. Portrait thumbnails below `MIN_PORTRAIT_POSTER_HEIGHT` do not count.

        Args:
            resource: The image resource to check.

        Returns:
            bool: True when the image is portrait-oriented and at least `MIN_PORTRAIT_POSTER_HEIGHT` tall.
        """
        dims = self.image_dimensions(resource)
        return bool(dims and dims[0] < dims[1] and dims[1] >= MIN_PORTRAIT_POSTER_HEIGHT)

    def pick_best_poster(self, resources):
        """Return the best poster, preferring a native portrait cover over a landscape one.

        A native portrait (e.g. DMM's `jp-1` front cover) is used as-is with no cropping. When no candidate is a
        portrait, the best landscape cover is chosen (and cropped to the front later). Within the chosen orientation,
        score comes first so a high-quality cover is not displaced by a larger but lower-scored one, with file size only
        breaking ties.

        Args:
            resources (list): Candidate poster/cover resources.

        Returns:
            The chosen resource, or None when the list is empty.
        """
        if not resources:
            return None
        portraits = [r for r in resources if self.is_portrait(r)]
        pool = portraits or resources
        top_score = max(r.score for r in pool)
        return self.pick_largest_image(
            [r for r in pool if r.score == top_score])

    def download_image(self, url):
        """Download the raw image bytes at `url`.

        Args:
            url (str): The image URL to download.

        Returns:
            The raw image bytes, or None when the download fails.
        """
        try:
            resp = requests.get(url)
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            Log.Exception("Failed to download image from %s: %s", url, e)
            return None

    def crop_front_cover(self, data):
        """Crop the front cover (right portion) out of a wide front+back cover.

        Uses the bundled PIL when it loads. Wide double-covers (aspect > 1.2) are cropped to just the front cover on the right. Portrait covers, and any case where PIL is unavailable or fails, return the original bytes unchanged.

        Args:
            data (str): The raw image bytes.

        Returns:
            str: The cropped JPEG bytes, or the original bytes when cropping does not apply or is unavailable.
        """
        try:
            from PIL import Image
            from io import BytesIO
            img = Image.open(BytesIO(data))
            width, height = img.size
            if width <= 0 or height <= 0 or float(width) / float(height) < 1.2:
                return data
            front_width = int(round(width * 0.4725))
            crop = img.crop((width - front_width, 0, width, height)).convert("RGB")
            out = BytesIO()
            crop.save(out, format="JPEG", quality=95)
            Log.Info("Cropped front cover from %dx%d to %dx%d", width, height, front_width, height)
            return out.getvalue()
        except Exception as e:
            Log.Info("Front-cover crop skipped (%s)", e)
            return data

    @classmethod
    def normalize_lang(cls, lang):
        if lang != Locale.Language.NoLanguage and lang in cls.languages:
            return lang
        return Locale.Language.Japanese

    CENSORED_SYMBOLS = [u"\u25cb", u"\u25ef", u"\u3007"]  # ○ ◯ 〇
    CANONICAL_CENSORED = u"\u25cf"  # ●
    censored_words_cache = None

    @staticmethod
    def uncensor_text(title, lang):
        if not title:
            return title
        if JAVAgent.censored_words_cache is None:
            try:
                raw = Resource.Load('censored_words.ja.json')
                JAVAgent.censored_words_cache = json.loads(raw)
            except Exception as e:
                Log.Exception("Failed to load censored words: %s", e)
                return title
        for symbol in JAVAgent.CENSORED_SYMBOLS:
            title = title.replace(symbol, JAVAgent.CANONICAL_CENSORED)
        for censored, replacement in JAVAgent.censored_words_cache.items():
            title = title.replace(censored, replacement)
        return title

    cached_agents = None  # type: list | None

    @property
    def agents(self):
        """Return enabled agents sorted by weight (highest first).

        Returns:
            list[BaseAgent]: Enabled agents sorted by weight descending.
        """
        if self.cached_agents is None:
            self.cached_agents = []
            for cls in dir(agents):
                if not isinstance(getattr(agents, cls), type):
                    continue
                if not issubclass(getattr(agents, cls), BaseAgent):
                    continue
                agent = getattr(agents, cls)(Prefs)
                if not agent.name:
                    continue
                self.cached_agents.append(agent)
        return sorted([a for a in self.cached_agents if a.enabled],
                      key=lambda a: a.weight, reverse=True)


class SearchResultCollection(list):
    def Append(self, obj):
        self.append(obj)


class PlexLogHandler(logging.Handler):
    def emit(self, record):
        try:
            agent_name = record.name
            if agent_name.startswith("agents."):
                agent_name = agent_name[len("agents."):]
            msg = u"[%s] %s" % (agent_name, record.getMessage())
            if record.exc_info:
                Log.Exception(msg)
            elif record.levelno >= logging.CRITICAL:
                Log.Critical(msg)
            elif record.levelno >= logging.ERROR:
                Log.Error(msg)
            elif record.levelno >= logging.WARNING:
                Log.Warn(msg)
            elif record.levelno >= logging.INFO:
                Log.Info(msg)
            else:
                Log.Debug(msg)
            if getattr(record, "stack_info", None):
                Log.Stack()
        except Exception:
            self.handleError(record)


def mask_proxy_url(url):
    """Hide the user:pass credentials in a proxy URL before logging it.

    Args:
        url: The proxy URL, possibly containing credentials, or a falsy value.

    Returns:
        The URL with any credentials replaced by "***", or the value unchanged when there are none.
    """
    if not url or "@" not in url:
        return url
    if "://" in url:
        scheme, rest = url.split("://", 1)
        prefix = scheme + "://"
    else:
        prefix, rest = "", url
    return prefix + "***@" + rest.split("@", 1)[1]


def log_prefs():
    proxy_keys = ("proxy", "geo_proxy")
    prefs = []
    for key in [
        "series_as_collection",
        "proxy",
        "geo_proxy",
        "flaresolverr_url",
        "user_agent",
        "avbase_enabled",
        "duga_enabled",
        "buena_enabled",
        "javlibrary_enabled",
        "javlibrary_cf_clearance",
        "javdb_enabled",
        "dmm_enabled",
        "mgstage_enabled",
        "seesaawiki_enabled",
        "gfriends_enabled",
        "warashipornstars_enabled",
        "translate_enabled",
        "ollama_url",
        "ollama_model",
    ]:
        value = Prefs[key]
        if key in proxy_keys:
            value = mask_proxy_url(value)
        prefs.append((key, value))
    Log.Info("Current preferences: %s", prefs)


def parse_jpeg_dimensions(data):
    """Return the (width, height) of a JPEG from its leading bytes, or None.

    Walks the JPEG segment markers to the start-of-frame (SOF) header, which carries the height and width. A small
    prefix of the file (the first tens of KB) is enough, so callers can range-read instead of downloading the whole
    image. Pure ASCII/`struct` only, so it runs inside the Plex sandbox without PIL.

    Args:
        data: The leading bytes of a JPEG file.

    Returns:
        tuple[int, int]: The (width, height), or None when no SOF header is found in `data`.
    """
    sof_markers = "\xc0\xc1\xc2\xc3\xc5\xc6\xc7\xc9\xca\xcb\xcd\xce\xcf"
    i, n = 2, len(data)
    while i + 9 <= n:
        if data[i] != "\xff":
            i += 1
            continue
        marker = data[i + 1]
        if marker in sof_markers:
            height = struct.unpack(">H", data[i + 5:i + 7])[0]
            width = struct.unpack(">H", data[i + 7:i + 9])[0]
            return (width, height)
        # Standalone markers (SOI/EOI/RSTn) carry no length payload.
        if marker == "\xd8" or marker == "\xd9" or ("\xd0" <= marker <= "\xd7"):
            i += 2
            continue
        i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
    return None


def is_legacy_metadata_id(metadata_id):
    """Return True if *metadata_id* uses the legacy format.

    Legacy formats are:

    * bare video code with no separator: ``ABC-123``
    * old comma-separated format: ``ABC-123,agent.id``
    """
    return "," in metadata_id


def parse_metadata_id(metadata_id):
    """
    Parse a composite metadata ID string.

    The canonical format uses a pipe as the first separator:

        {video_code}|{agent_name1}.{agent_id1};{agent_name2}.{agent_id2};...

    For backward compatibility the legacy comma-separated format is also
    accepted:

        {video_code},{agent_name1}.{agent_id1};{agent_name2}.{agent_id2};...

    A bare video code with no separator is also accepted.

    Args:
        metadata_id (str): The raw metadata ID.

    Returns:
        tuple[str, dict[str, str]]: ``(video_code, agent_dict)`` where
        *agent_dict* maps agent names to their IDs.
    """
    if "|" in metadata_id:
        part = metadata_id.split("|", 1)
    elif "," in metadata_id:
        part = metadata_id.split(",", 1)
    else:
        part = [metadata_id]
    video_code = part[0]
    agent_dict = OrderedDict()
    if len(part) > 1 and part[1]:
        for segment in part[1].split(";"):
            if "." in segment:
                name, aid = segment.split(".", 1)
                agent_dict[name] = aid
    return video_code, agent_dict


def update_metadata_id(metadata_id, agent_name, agent_id):
    video_code, agent_ids = parse_metadata_id(metadata_id)
    agent_ids[agent_name] = agent_id
    segments = ";".join("%s.%s" % (n, i) for n, i in agent_ids.items())
    return "%s|%s" % (video_code, segments)
