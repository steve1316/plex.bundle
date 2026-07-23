# coding=utf-8

from base import BaseTestCase

import unittest

import mock

from agents.seesaawiki import SeesaaWiki


# ---------------------------------------------------------------------------
# Test data — add new entries here to extend coverage
# ---------------------------------------------------------------------------

# (video_code, [expected_actress_name, ...])
# Each tuple asserts that searching the wiki for *video_code* discovers the
# listed actresses.
VIDEO_CODE_TEST_CASES = [
    ("JBD-226", [u"篠田ゆう"]),
    ("DRPT-009", [u"綾川ふみ"]),
    ("MEYD-514", [u"篠田ゆう", u"黒川すみれ"]),
]

# (input_name, expected_canonical_name)
# Each tuple asserts that looking up *input_name* on the wiki yields
# *expected_canonical_name* (following redirects where necessary).
ACTRESS_NAME_TEST_CASES = [
    (u"白石みお", u"かなで自由"),
    (u"篠田ゆう", u"篠田ゆう"),
    (u"大槻ひびき", u"大槻ひびき"),
]


# ---------------------------------------------------------------------------
# get_actresses tests (by unique ID)
# ---------------------------------------------------------------------------

class TestGetActresses(BaseTestCase):
    """Verify :meth:`SeesaaWiki.get_actresses` discovers correct actresses."""

    def setUp(self):
        super(TestGetActresses, self).setUp()
        self.update_prefs(seesaawiki_enabled=True)
        self.agent = SeesaaWiki(Prefs)


def _make_get_actresses_test(video_code, expected_names):
    """Factory that creates a test method for *video_code*."""

    def test_method(self):
        actresses = self.agent.discover_actresses(video_code)
        for expected in expected_names:
            self.assertIn(
                expected,
                actresses,
                u"Expected actress '{}' not found in {} for {}".format(
                    expected, actresses, video_code,
                ),
            )

    return test_method


for _vc, _names in VIDEO_CODE_TEST_CASES:
    _test_name = "test_get_actresses_{}".format(_vc.replace("-", "_"))
    setattr(TestGetActresses, _test_name, _make_get_actresses_test(_vc, _names))


# ---------------------------------------------------------------------------
# get_actress_name tests (name correction / redirect following)
# ---------------------------------------------------------------------------

class TestGetActressName(BaseTestCase):
    """Verify :meth:`SeesaaWiki.get_actress_name` returns canonical names."""

    def setUp(self):
        super(TestGetActressName, self).setUp()
        self.update_prefs(seesaawiki_enabled=True)
        self.agent = SeesaaWiki(Prefs)


def _make_get_actress_name_test(input_name, expected_name):
    """Factory that creates a test method for *input_name*."""

    def test_method(self):
        result = self.agent.get_actress_name(input_name)
        self.assertEqual(
            result,
            expected_name,
            u"Expected '{}' but got '{}' for input '{}'".format(
                expected_name, result, input_name,
            ),
        )

    return test_method


for i, (_inp, _exp) in enumerate(ACTRESS_NAME_TEST_CASES):
    _test_name = "test_name_{}".format(i)
    setattr(TestGetActressName, _test_name,
            _make_get_actress_name_test(_inp, _exp))


# ---------------------------------------------------------------------------
# Cache tests
# ---------------------------------------------------------------------------

class TestActressNameCache(BaseTestCase):
    """Verify that :meth:`SeesaaWiki.get_actress_name` uses its internal cache."""

    def setUp(self):
        super(TestActressNameCache, self).setUp()
        self.update_prefs(seesaawiki_enabled=True)
        self.agent = SeesaaWiki(Prefs)

    def test_second_call_uses_cache(self):
        self.agent.cache = {}
        with mock.patch.object(
            self.agent, "search_wiki",
            return_value=[(u"篠田ゆう",
                           "https://seesaawiki.jp/w/sougouwiki/d/%bc%c4%c5%c4%a4%e6%a4%a6")]
        ) as mock_search, mock.patch.object(
            self.agent, "resolve_page_name",
            return_value=u"篠田ゆう"
        ) as mock_resolve:
            first = self.agent.get_actress_name(u"篠田ゆう")
            second = self.agent.get_actress_name(u"篠田ゆう")

        self.assertEqual(first, second)
        mock_search.assert_called_once()
        mock_resolve.assert_called_once()

    def test_cache_stores_canonical_name(self):
        self.agent.cache = {}
        input_name = u"白石みお"  # 白石みお
        canonical = u"かなで自由"  # かなで自由
        with mock.patch.object(
            self.agent, "search_wiki",
            return_value=[
                (canonical, "https://seesaawiki.jp/w/sougouwiki/d/dummy")]
        ), mock.patch.object(
            self.agent, "resolve_page_name",
            return_value=canonical
        ):
            self.agent.get_actress_name(input_name)

        self.assertIn(input_name, self.agent.cache)
        self.assertEqual(self.agent.cache[input_name], canonical)

    def test_cache_is_keyed_per_name(self):
        self.agent.cache = {}
        cases = [
            (u"篠田ゆう", u"篠田ゆう"),
            (u"白石みお", u"かなで自由"),
        ]

        for inp, canonical in cases:
            with mock.patch.object(
                self.agent, "search_wiki",
                return_value=[
                    (canonical, "https://seesaawiki.jp/w/sougouwiki/d/dummy")]
            ), mock.patch.object(
                self.agent, "resolve_page_name",
                return_value=canonical
            ):
                self.agent.get_actress_name(inp)

        for inp, canonical in cases:
            self.assertIn(inp, self.agent.cache)
            self.assertEqual(self.agent.cache[inp], canonical)

    def test_cache_miss_on_unknown_name_stores_original(self):
        self.agent.cache = {}
        unknown = u"UNKNOWN_XYZ_99999"
        with mock.patch.object(self.agent, "search_wiki", return_value=[]) as mock_search:
            self.agent.get_actress_name(unknown)
            self.agent.get_actress_name(unknown)

        mock_search.assert_called_once()
        self.assertEqual(self.agent.cache[unknown], unknown)

    def test_pre_populated_cache_is_respected(self):
        self.agent.cache = {u"白石みお": u"かなで自由"}
        with mock.patch.object(self.agent, "search_wiki") as mock_search:
            result = self.agent.get_actress_name(u"白石みお")

        mock_search.assert_not_called()
        self.assertEqual(result, u"かなで自由")


# ---------------------------------------------------------------------------
# Reading extraction tests
# ---------------------------------------------------------------------------

from bs4 import BeautifulSoup  # noqa: E402

from agents.types import Metadata, Person  # noqa: E402


class TestExtractReading(BaseTestCase):
    """Verify :meth:`SeesaaWiki.extract_reading` parses the parenthesised reading."""

    def setUp(self):
        super(TestExtractReading, self).setUp()
        self.update_prefs(seesaawiki_enabled=True)
        self.agent = SeesaaWiki(Prefs)

    def test_reading_from_parenthesized_yomigana(self):
        html = (u'<div class="user-area"><h2>原紗央莉（はらさおり）</h2>'
                u'<p>body text</p></div>')
        soup = BeautifulSoup(html, "html.parser")
        self.assertEqual(u"はらさおり",
                         self.agent.extract_reading(soup, u"原紗央莉"))

    def test_reading_absent(self):
        html = u'<div class="user-area"><p>no reading here</p></div>'
        soup = BeautifulSoup(html, "html.parser")
        self.assertIsNone(self.agent.extract_reading(soup, u"原紗央莉"))

    def test_reading_none_page_name(self):
        soup = BeautifulSoup(u"<div></div>", "html.parser")
        self.assertIsNone(self.agent.extract_reading(soup, None))


class TestPartialUpdateReading(BaseTestCase):
    """Verify :meth:`SeesaaWiki.partial_update` attaches the wiki reading."""

    def setUp(self):
        super(TestPartialUpdateReading, self).setUp()
        self.update_prefs(seesaawiki_enabled=True)
        self.agent = SeesaaWiki(Prefs)

    def test_attaches_reading_to_actress(self):
        meta = Metadata()
        meta.actresses = [Person(u"原紗央莉")]
        self.agent.reading_cache = {u"原紗央莉": u"はらさおり"}
        with mock.patch.object(self.agent, "get_actress_name",
                               side_effect=lambda name: name):
            self.agent.partial_update(u"STAR-193", meta, "ja")

        self.assertEqual(1, len(meta.actresses))
        self.assertEqual(u"原紗央莉", meta.actresses[0])
        self.assertEqual(u"はらさおり", meta.actresses[0].reading)

    def test_existing_reading_is_not_overwritten(self):
        actress = Person(u"原紗央莉")
        actress.reading = u"はら さおり"  # e.g. supplied by AVBase ruby
        meta = Metadata()
        meta.actresses = [actress]
        self.agent.reading_cache = {u"原紗央莉": u"はらさおり"}
        with mock.patch.object(self.agent, "get_actress_name",
                               side_effect=lambda name: name):
            self.agent.partial_update(u"STAR-193", meta, "ja")

        self.assertEqual(u"はら さおり", meta.actresses[0].reading)


if __name__ == "__main__":
    unittest.main()
