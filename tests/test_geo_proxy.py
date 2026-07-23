# coding=utf-8

from base import BaseTestCase

import unittest

from agents.avbase import AVBase
from agents.dmm import DMM
from agents.mgstage import MGStage
from agents.types import Metadata


GEO = u"http://id:pass@203.0.113.9:18080"
GLOBAL = u"http://10.0.0.1:3128"


# ---------------------------------------------------------------------------
# session_proxy scoping
# ---------------------------------------------------------------------------

class TestSessionProxyScoping(BaseTestCase):
    def test_geo_agent_uses_geo_proxy(self):
        self.update_prefs(geo_proxy=GEO, proxy=GLOBAL)
        self.assertEqual({"http": GEO, "https": GEO}, DMM(Prefs).session_proxy)
        self.assertEqual({"http": GEO, "https": GEO}, MGStage(Prefs).session_proxy)

    def test_non_geo_agent_uses_global_proxy(self):
        self.update_prefs(geo_proxy=GEO, proxy=GLOBAL)
        self.assertEqual({"http": GLOBAL, "https": GLOBAL}, AVBase(Prefs).session_proxy)

    def test_geo_agent_falls_back_to_global_when_geo_unset(self):
        self.update_prefs(geo_proxy=u"", proxy=GLOBAL)
        self.assertEqual({"http": GLOBAL, "https": GLOBAL}, DMM(Prefs).session_proxy)

    def test_empty_when_nothing_set(self):
        self.update_prefs(geo_proxy=u"", proxy=u"")
        self.assertEqual({}, DMM(Prefs).session_proxy)
        self.assertEqual({}, AVBase(Prefs).session_proxy)

    def test_geo_proxy_never_leaks_to_flaresolverr(self):
        # FlareSolverr keeps using the global proxy only, so geo_proxy must not reach it.
        self.update_prefs(geo_proxy=GEO, proxy=u"")
        self.assertEqual({}, DMM(Prefs).http_proxy)


# ---------------------------------------------------------------------------
# DMM / MGStage summary override (full summary wins over avbase's truncated one)
# ---------------------------------------------------------------------------

class TestSummaryOverride(BaseTestCase):
    def _meta(self, summary):
        m = Metadata()
        m.summary = summary
        return m

    def test_longer_summary_replaces_truncated(self):
        truncated = u"short teaser…"
        full = u"a much longer complete description than the teaser above"
        for agent in (DMM(Prefs), MGStage(Prefs)):
            self.assertTrue(
                agent.should_contribute_to(self._meta(truncated), "summary", full),
                msg="%s should replace a shorter summary" % agent.name)

    def test_shorter_summary_is_ignored(self):
        full = u"a much longer complete description already present here"
        short = u"short…"
        for agent in (DMM(Prefs), MGStage(Prefs)):
            self.assertFalse(
                agent.should_contribute_to(self._meta(full), "summary", short),
                msg="%s must not overwrite a longer summary" % agent.name)

    def test_fills_empty_summary(self):
        for agent in (DMM(Prefs), MGStage(Prefs)):
            self.assertTrue(
                agent.should_contribute_to(self._meta(None), "summary", u"anything"))

    def test_non_summary_attribute_keeps_default(self):
        # A non-container scalar that is already set must not be replaced.
        for agent in (DMM(Prefs), MGStage(Prefs)):
            m = Metadata()
            m.studio = u"Existing"
            self.assertFalse(agent.should_contribute_to(m, "studio", u"New"))


if __name__ == "__main__":
    unittest.main()
