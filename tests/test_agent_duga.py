# coding=utf-8

from base import AgentTestCase, BaseTestCase

import unittest

import mock

from agents import duga
from agents.avbase import AVBase
from agents.base import AccessRestrictedError


# A stand-in full description (longer than any truncated teaser below).
FULL_DESC = (
    u"ド変態の素人さん同士、朝ま"
    u"で楽しくハメ撮りしちゃおう"
    u"な企画！！以上、最強素人4名"
    u"の生々しいハメ撮りSEXの記録を"
    u"収録！")

# A truncated teaser ending in the ellipsis U+2026 (shorter than FULL_DESC).
TRUNCATED = u"ド変態の素人さん同士\u2026"

DUGA_URL = u"https://click.duga.jp/ppv/doc-1990/39588-1"


# ---------------------------------------------------------------------------
# Fake session used by fetch_description tests
# ---------------------------------------------------------------------------

class FakeResponse(object):
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass


class FakeSession(object):
    def __init__(self, content):
        self.content = content
        self.requested_url = None

    def get(self, url):
        self.requested_url = url
        return FakeResponse(self.content)


# ---------------------------------------------------------------------------
# extract_product_id
# ---------------------------------------------------------------------------

class TestExtractProductId(BaseTestCase):
    def test_click_url(self):
        self.assertEqual(u"doc-1990", duga.extract_product_id(DUGA_URL))

    def test_plain_product_url(self):
        self.assertEqual(
            u"doc-1990",
            duga.extract_product_id(u"https://duga.jp/ppv/doc-1990/"))

    def test_no_match(self):
        self.assertIsNone(
            duga.extract_product_id(u"https://example.com/foo/bar"))

    def test_empty(self):
        self.assertIsNone(duga.extract_product_id(u""))
        self.assertIsNone(duga.extract_product_id(None))


class TestSampleMovieUrl(BaseTestCase):
    def test_label_and_number(self):
        self.assertEqual(u"https://flv.duga.jp/unsecure/scocci/0170/noauth/temp.mp4", duga.sample_movie_url(u"scocci-0170"))

    def test_invalid_id(self):
        self.assertIsNone(duga.sample_movie_url(u"scocci"))
        self.assertIsNone(duga.sample_movie_url(None))


# ---------------------------------------------------------------------------
# parse_description
# ---------------------------------------------------------------------------

class TestParseDescription(BaseTestCase):
    def test_introduction_element(self):
        html = (
            u'<html><body><p class="introduction" itemprop="description">'
            u'%s</p></body></html>' % FULL_DESC)
        self.assertEqual(FULL_DESC, duga.parse_description(html))

    def test_og_description_fallback(self):
        html = (
            u'<html><head><meta property="og:description" content="%s">'
            u'</head><body></body></html>' % FULL_DESC)
        self.assertEqual(FULL_DESC, duga.parse_description(html))

    def test_prefers_introduction_over_og(self):
        html = (
            u'<html><head><meta property="og:description" content="OG">'
            u'</head><body><p class="introduction" itemprop="description">'
            u'%s</p></body></html>' % FULL_DESC)
        self.assertEqual(FULL_DESC, duga.parse_description(html))

    def test_neither_present(self):
        html = u"<html><body><p>nope</p></body></html>"
        self.assertIsNone(duga.parse_description(html))


# ---------------------------------------------------------------------------
# fetch_description
# ---------------------------------------------------------------------------

class TestFetchDescription(BaseTestCase):
    def test_builds_url_and_parses(self):
        html = (
            u'<p class="introduction" itemprop="description">%s</p>'
            % FULL_DESC).encode("utf-8")
        session = FakeSession(html)
        result = duga.fetch_description(session, u"doc-1990")
        self.assertEqual(FULL_DESC, result)
        self.assertEqual(u"https://duga.jp/ppv/doc-1990/",
                         session.requested_url)

    def test_status_check_propagates(self):
        session = FakeSession(b"<html></html>")

        def raise_restricted(resp):
            raise AccessRestrictedError("blocked")

        self.assertRaises(
            AccessRestrictedError,
            duga.fetch_description, session, u"doc-1990", raise_restricted)


# ---------------------------------------------------------------------------
# AVBase.hydrate_summary_from_duga
# ---------------------------------------------------------------------------

class TestHydrateSummaryFromDuga(BaseTestCase):
    def setUp(self):
        super(TestHydrateSummaryFromDuga, self).setUp()
        self.update_prefs(duga_enabled=True, flaresolverr_url="")
        self.agent = AVBase(Prefs)
        self.work = {"products": [{"source": "duga", "url": DUGA_URL}]}

    def test_swaps_when_truncated(self):
        with mock.patch("agents.avbase.fetch_description",
                               return_value=FULL_DESC) as fetch:
            result = self.agent.hydrate_summary_from_duga(
                self.work, TRUNCATED)
        self.assertEqual(FULL_DESC, result)
        self.assertEqual(u"doc-1990", fetch.call_args[0][1])

    def test_pref_off(self):
        self.update_prefs(duga_enabled=False)
        with mock.patch("agents.avbase.fetch_description") as fetch:
            result = self.agent.hydrate_summary_from_duga(
                self.work, TRUNCATED)
        self.assertEqual(TRUNCATED, result)
        self.assertFalse(fetch.called)

    def test_not_truncated(self):
        full = u"A complete summary with no ellipsis."
        with mock.patch("agents.avbase.fetch_description") as fetch:
            result = self.agent.hydrate_summary_from_duga(self.work, full)
        self.assertEqual(full, result)
        self.assertFalse(fetch.called)

    def test_empty_summary(self):
        with mock.patch("agents.avbase.fetch_description") as fetch:
            self.assertIsNone(
                self.agent.hydrate_summary_from_duga(self.work, None))
            self.assertEqual(
                u"", self.agent.hydrate_summary_from_duga(self.work, u""))
        self.assertFalse(fetch.called)

    def test_no_duga_product(self):
        work = {"products": [{"source": "fanza", "url": u"https://x"}]}
        with mock.patch("agents.avbase.fetch_description") as fetch:
            result = self.agent.hydrate_summary_from_duga(work, TRUNCATED)
        self.assertEqual(TRUNCATED, result)
        self.assertFalse(fetch.called)

    def test_duga_product_without_id(self):
        work = {"products": [{"source": "duga", "url": u"https://duga.jp/x"}]}
        with mock.patch("agents.avbase.fetch_description") as fetch:
            result = self.agent.hydrate_summary_from_duga(work, TRUNCATED)
        self.assertEqual(TRUNCATED, result)
        self.assertFalse(fetch.called)

    def test_fetch_raises_is_swallowed(self):
        with mock.patch("agents.avbase.fetch_description",
                               side_effect=Exception("boom")):
            result = self.agent.hydrate_summary_from_duga(
                self.work, TRUNCATED)
        self.assertEqual(TRUNCATED, result)

    def test_fetch_returns_none(self):
        with mock.patch("agents.avbase.fetch_description", return_value=None):
            result = self.agent.hydrate_summary_from_duga(
                self.work, TRUNCATED)
        self.assertEqual(TRUNCATED, result)

    def test_fetch_not_longer_is_ignored(self):
        shorter = u"short"
        with mock.patch("agents.avbase.fetch_description",
                               return_value=shorter):
            result = self.agent.hydrate_summary_from_duga(
                self.work, TRUNCATED)
        self.assertEqual(TRUNCATED, result)


# ---------------------------------------------------------------------------
# Live end-to-end fetch (skipped on blocked networks via AccessRestrictedError)
# ---------------------------------------------------------------------------

class TestDugaLiveFetch(AgentTestCase):
    """Verify the real Duga product page still parses into a full description."""

    def get_agent_instance(self):
        return AVBase(Prefs)

    def test_fetch_full_description(self):
        # doc-1990 is the Duga product for MGTD-045, whose AVBase summary is truncated.
        text = duga.fetch_description(
            self.agent.session, u"doc-1990", self.agent.raise_for_status)
        self.assertTrue(text)
        # The full description is not the truncated teaser and includes the closing line.
        self.assertFalse(text.rstrip().endswith(u"\u2026"))
        self.assertIn(u"収録", text)
        self.assertTrue(len(text) > 129)


# ---------------------------------------------------------------------------
# AVBase.cover_score (prefer the physical DVD cover over promo montages)
# ---------------------------------------------------------------------------

class TestCoverScore(BaseTestCase):
    def test_physical_dvd_cover_ranks_highest(self):
        self.assertEqual(60, AVBase.cover_score(
            u"https://pics.dmm.co.jp/mono/movie/adult/1start375/1start375pl.jpg"))

    def test_digital_promo_cover_ranks_lower(self):
        self.assertEqual(50, AVBase.cover_score(
            u"https://awsimgsrc.dmm.co.jp/pics_dig/digital/video/1start00375/1start00375pl.jpg"))

    def test_reseller_cover_ranks_lower(self):
        self.assertEqual(50, AVBase.cover_score(
            u"https://pic.duga.jp/unsecure/sodcreate/9014/noauth/jacket.jpg"))

    def test_empty(self):
        self.assertEqual(50, AVBase.cover_score(u""))
        self.assertEqual(50, AVBase.cover_score(None))


if __name__ == "__main__":
    unittest.main()
