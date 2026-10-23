# coding=utf-8

from base import AgentTestCase

import unittest

from agents import AVBase


class TestAVBaseAgent(AgentTestCase):

    def get_agent_instance(self):
        return AVBase(Prefs)

    def test_search_work_without_prefix(self):
        # POW-084 has no AVBase prefix, so its id is the bare work id
        results = self.agent.search([u"POW-084"], "ja")
        self.assertEqual([u"POW-084"], [r.id for r in results if r.score == 100])

    def test_metadata_work_without_prefix(self):
        metadata = self.agent.get_metadata(u"POW-084", u"POW-084", "ja")
        self.assertTrue(metadata.title.startswith(u"POW-084 "))
        # the FANZA and MGStage sample images become extrafanart
        self.assertTrue([a for a in metadata.art if a.score < 45])

    def test_metadata_legacy_empty_prefix_id(self):
        # ids saved before the fix kept the empty prefix as ":POW-084"
        metadata = self.agent.get_metadata(u":POW-084", u"POW-084", "ja")
        self.assertTrue(metadata.title.startswith(u"POW-084 "))


if __name__ == "__main__":
    unittest.main()
