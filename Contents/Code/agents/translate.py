# coding=utf-8

import json
import re

import requests

from .base import PartialMetadataAgent
from .romaji import romanize_reading
from .types import Person


DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "gemma3:12b"

# Matches any non-ASCII character, i.e. a scraped (Japanese) name that still
# needs romanizing. Romanized names are plain ASCII.
JAPANESE_RE = re.compile(u"[^\x00-\x7f]")

# Matches a CJK ideograph, hiragana/katakana, or fullwidth form. Used to detect a summary the model left untranslated.
CJK_RE = re.compile(u"[\u3040-\u30ff\u3400-\u9fff\uff00-\uffef]")

TRANSLATION_PROMPT = u"""You are translating Japanese adult video (JAV) metadata to English. Rules:

GENRES - use these exact translations:
"ハメ撮り"="POV", "素人"="Amateur", "中出し"="Creampie", "潮吹き"="Squirting", "おもちゃ"="Toys", "ベスト・総集編"="Best of / Compilation", "巨乳"="Big Tits", "美乳"="Beautiful Tits", "痴女"="Slut", "人妻"="Married Woman", "熟女"="MILF", "乱交"="Orgy", "フェラ"="Blowjob", "騎乗位"="Cowgirl"

ACTRESS NAMES - CRITICAL RULES:
- Each actress has a "name" (kanji) and a "reading" (hiragana). The reading tells you EXACTLY how to pronounce the name.
- You MUST romanize based on the reading, not the kanji. Do NOT guess from kanji.
- "なな" = "Nana" (NOT "Rara"). "奈々" is read as "なな" = "Nana".
- If the name contains "・" (middle dot), it separates name parts. Romanize each part independently.
- Output in Western order: given name first, family name last.
- Examples:
  - name "小倉奈々", reading "おぐらなな" -> "Nana Ogura" (おぐら=Ogura, なな=Nana)
  - name "椿りか", reading "つばきりか" -> "Rika Tsubaki" (つばき=Tsubaki, りか=Rika)
  - name "メロディー・雛・マークス", reading "めろでぃーひいなまーくす" -> "Melody Hiina Marks"
- For the actress list, return just the romanized name strings (not objects).

DIRECTOR NAMES: romanize the same way as actress names - use the reading when present, Western order (given name first). Return the director list as romanized name strings.

TITLE: translate naturally, keep "Vol.XX" as-is.
SUMMARY: translate naturally and completely.

Return ONLY a valid JSON object with the same keys as the input. No markdown, no explanation.

{input}"""


class Translate(PartialMetadataAgent):
    """Agent that translates Japanese metadata to English via Ollama."""

    name = "Translate"
    # Runs last, after the name-correction and avatar agents. Those look the
    # actress up by her Japanese name, so translation must not rewrite it first.
    weight = -400

    def partial_update(self, video_code, metadata, lang):
        self.preserve_japanese_names(metadata)
        self.llm_translate(video_code, metadata, lang)
        self.apply_deterministic_romaji(metadata)

    def preserve_japanese_names(self, metadata):
        """Snapshot each cast member's Japanese name before it is romanized.

        Runs before `llm_translate` rewrites names to romaji. A scraped name is
        the Japanese display name (kanji/kana), so it is stored on
        `japanese_name` for later display next to the romaji. Only names that
        actually contain Japanese characters are snapshotted, and an existing
        `japanese_name` is never overwritten.

        Args:
            metadata (Metadata): The movie metadata to update in place.
        """
        for people in (metadata.actresses, metadata.directors):
            for person in people or []:
                if getattr(person, "japanese_name", None):
                    continue
                if JAPANESE_RE.search(person):
                    person.japanese_name = unicode(person)

    def apply_deterministic_romaji(self, metadata):
        """Fix actress romanization and order using the hiragana reading.

        Runs after `llm_translate`. When the reading is delimited into name parts
        (e.g. `はら さおり`), romanize it directly in Western order. When it is
        undelimited (e.g. `はらさおり`), the LLM supplies the split; if the LLM
        romanized the reading in source (family-first) order, flip it to Western.
        The reading anchors both cases, so the result does not depend on the LLM
        choosing the right order.

        Args:
            metadata (Metadata): The movie metadata to update in place.
        """
        if not metadata.actresses:
            return
        metadata.actresses = [
            self.romanize_actress(actress) for actress in metadata.actresses]

    def romanize_actress(self, actress):
        """Return the actress with a Western-order romaji name when derivable.

        Args:
            actress (Person): The (LLM-romanized) actress.

        Returns:
            Person: The actress, possibly rebuilt with a corrected name.
        """
        reading = getattr(actress, "reading", None)
        romaji = romanize_reading(reading) if reading else None
        if not romaji:
            return actress
        # A space means romanize_reading split the reading itself (Western order).
        if u" " in romaji:
            return self.with_name(actress, romaji)
        # Undelimited reading: the LLM split it. If its two tokens spell the
        # reading in order, they are family-first, so flip them to Western order.
        tokens = unicode(actress).split()
        if len(tokens) == 2 and u"".join(tokens).lower() == romaji.lower():
            return self.with_name(
                actress, u"{0} {1}".format(tokens[1], tokens[0]))
        return actress

    def with_name(self, actress, name):
        """Return a copy of *actress* with *name*, carrying its other attributes.

        Args:
            actress (Person): The source person.
            name (unicode): The new romanized name.

        Returns:
            Person: The rebuilt person.
        """
        person = Person(name)
        person.photo = actress.photo
        person.reading = getattr(actress, "reading", None)
        person.japanese_name = getattr(actress, "japanese_name", None)
        return person

    def is_bad_translation(self, text):
        """Return True when a translated summary looks malformed or untranslated.

        Guards against two observed model failures: leaking its JSON wrapper into the value (a leading `{` or `[`), and
        returning the text still largely in Japanese (it starts with, or is mostly, CJK). Either way the caller keeps the
        clean original instead of storing a corrupted English summary.

        Args:
            text: The model's translated summary string.

        Returns:
            bool: True when the translation should be discarded.
        """
        stripped = (text or u"").strip()
        if not stripped:
            return True
        if stripped[0] in u"{[":
            return True
        if CJK_RE.match(stripped):
            return True
        cjk = len(CJK_RE.findall(stripped))
        if cjk and cjk * 4 >= len(stripped):
            return True
        return False

    def llm_translate(self, video_code, metadata, lang):
        ollama_url = self.prefs["ollama_url"] or DEFAULT_OLLAMA_URL
        ollama_url = ollama_url.rstrip("/")
        model = self.prefs["ollama_model"] or DEFAULT_MODEL

        # Build the input payload with fields to translate
        input_data = {}
        if metadata.japanese_title:
            title = metadata.japanese_title
            parts = title.split(" ", 1)
            if len(parts) > 1 and "-" in parts[0]:
                input_data["title"] = parts[1]
            else:
                input_data["title"] = title

        if metadata.summary:
            input_data["summary"] = metadata.summary

        if metadata.genres:
            input_data["genres"] = list(metadata.genres)

        if metadata.actresses:
            actress_entries = []
            for actress in metadata.actresses:
                ruby = getattr(actress, "reading", None)
                if ruby:
                    actress_entries.append({
                        "name": unicode(actress),
                        "reading": ruby,
                    })
                else:
                    actress_entries.append({"name": unicode(actress)})
            input_data["actresses"] = actress_entries

        if metadata.directors:
            director_entries = []
            for director in metadata.directors:
                ruby = getattr(director, "reading", None)
                if ruby:
                    director_entries.append({
                        "name": unicode(director),
                        "reading": ruby,
                    })
                else:
                    director_entries.append({"name": unicode(director)})
            input_data["directors"] = director_entries

        if not input_data:
            return

        # Call Ollama
        prompt = TRANSLATION_PROMPT.format(input=json.dumps(
            input_data, ensure_ascii=False))

        try:
            translated = self.call_ollama(ollama_url, model, prompt)
        except Exception as e:
            self.logger.exception("Translation failed: %s", e)
            return

        if not translated:
            return

        # Apply translations
        if "title" in translated and translated["title"]:
            metadata.title = u"{0} {1}".format(video_code, translated["title"])
            metadata.title_sort = metadata.title

        if "summary" in translated and translated["summary"]:
            # Keep the English translation on top and the original below it.
            english = translated["summary"]
            original = metadata.summary
            if self.is_bad_translation(english):
                # Model leaked JSON or left the text untranslated. Keep the clean original rather than a corrupted mix.
                self.logger.warning(
                    "Discarding malformed summary translation, keeping original")
            elif original and original.strip() != english.strip():
                metadata.summary = u"{0}\n\n{1}".format(english, original)
            else:
                metadata.summary = english

        if "genres" in translated and translated["genres"]:
            metadata.genres = set(translated["genres"])

        if "actresses" in translated and translated["actresses"]:
            merged = self.merge_translated_people(
                translated["actresses"], metadata.actresses)
            if merged:
                metadata.actresses = merged

        if "directors" in translated and translated["directors"]:
            merged = self.merge_translated_people(
                translated["directors"], metadata.directors)
            if merged:
                metadata.directors = merged

    def merge_translated_people(self, entries, originals):
        """Build romanized Person objects, carrying photo/reading/japanese_name.

        Args:
            entries (list): The LLM-translated names (strings or {name: ...} objects).
            originals (list[Person]): The pre-translation people, index-aligned.

        Returns:
            list[Person]: The romanized people (possibly empty).
        """
        people = []
        for i, entry in enumerate(entries):
            name = entry.get("name", "") if isinstance(entry, dict) else entry
            if not name:
                continue
            person = Person(name)
            if originals and i < len(originals):
                person.photo = originals[i].photo
                person.reading = getattr(originals[i], "reading", None)
                person.japanese_name = getattr(originals[i], "japanese_name", None)
            people.append(person)
        return people

    def call_ollama(self, ollama_url, model, prompt):
        """Send a prompt to Ollama and parse the JSON response. Retries once on failure."""
        result = self.send_ollama_request(ollama_url, model, prompt)
        if result is None:
            self.logger.debug("Retrying translation...")
            result = self.send_ollama_request(ollama_url, model, prompt)
        return result

    def send_ollama_request(self, ollama_url, model, prompt):
        """Send a single request to Ollama and parse the JSON response."""
        url = u"{0}/api/generate".format(ollama_url)
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }

        resp = requests.post(url, json=payload, timeout=300)
        resp.raise_for_status()

        data = resp.json()
        response_text = data.get("response", "")

        # Strip markdown code fences if present
        response_text = re.sub(
            r"^```(?:json)?\s*\n?", "", response_text.strip())
        response_text = re.sub(r"\n?```\s*$", "", response_text.strip())

        # Try to extract JSON object even if there's extra text
        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(0)

        try:
            return json.loads(response_text)
        except (ValueError, TypeError) as e:
            self.logger.warning(
                "Failed to parse translation response: %s\nRaw: %s",
                e, response_text[:200])
            return None
