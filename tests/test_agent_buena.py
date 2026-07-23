# coding=utf-8

from base import AgentTestCase

import unittest

from agents import Buena


class TestBuenaAgent(AgentTestCase):

    def get_agent_instance(self):
        return Buena(Prefs)

    # ---------------------------------------------------------------------------
    # Search test cases
    # ---------------------------------------------------------------------------

    def test_guess_search_keywords(self):
        # site code and DMM cross-ref codes normalize to padding-insensitive keys
        self.assertGuessedKeywords(u"", u"buena075.mp4", u"", [u"BUENA75"])
        self.assertGuessedKeywords(u"", u"BUENA-075.mkv", u"", [u"BUENA75"])
        self.assertGuessedKeywords(u"", u"PRIN-042.mp4", u"", [u"PRIN42"])
        self.assertGuessedKeywords(u"", u"zarj070.mp4", u"", [u"ZARJ70"])
        self.assertNegativeGuessedKeywords(u"", u"Some Random Movie 2020.mp4", u"")

    def test_search_buena_075(self):
        results = self.agent.search([u"buena075"], "ja")
        self.assertEqual(1, len(results))
        self.assertEqual(u"BUENA-075", results[0].id)
        self.assertEqual(u"BUENA-075", results[0].video_code)
        self.assertEqual(
            u"[BUENA-075] ミリム･ナーヴァ (転生したらスライムだった件)", results[0].title)
        self.assertEqual(100, results[0].score)

    def test_search_by_crossref_code(self):
        # the DMM AV code cross-references the same BUENA entry
        results = self.agent.search([u"PRIN-042"], "ja")
        self.assertEqual(1, len(results))
        self.assertEqual(u"BUENA-075", results[0].video_code)

    # ---------------------------------------------------------------------------
    # Metadata test cases
    # ---------------------------------------------------------------------------

    def test_metadata_buena_075(self):
        metadata = self.agent.get_metadata(u"BUENA-075", u"BUENA-075", "ja")
        self.assertTitleEquals(
            u"[BUENA-075] ミリム･ナーヴァ (転生したらスライムだった件)", metadata)
        self.assertJapaneseTitleEquals(
            u"[BUENA-075] ミリム･ナーヴァ (転生したらスライムだった件)", metadata)
        self.assertStudioIs(u"BUENA", metadata)
        self.assertSeriesIs(u"転生したらスライムだった件", metadata)
        self.assertActressesInclude([u"乙アリス"], metadata)
        self.assertGenresInclude([u"コスプレ"], metadata)
        self.assertDurationExists(metadata)
        # the large FANZA AV cover is preferred as the poster (higher resolution
        # than the small ps.jpg thumbnail); it doubles as the background art
        self.assertEqual(
            u"https://pics.dmm.co.jp/digital/video/prin00042/prin00042pl.jpg",
            metadata.posters[0])
        self.assertTrue(metadata.art)
        self.assertIn(
            metadata.art[0],
            [u"https://pics.dmm.co.jp/digital/video/prin00042/prin00042pl.jpg",
             u"https://awsimgsrc.dmm.co.jp/pics_dig/digital/amateur/zarj070/zarj070jp.jpg"])

    def test_metadata_pow_label_studio(self):
        # POW-labelled releases report POW as the studio
        metadata = self.agent.get_metadata(u"BUENA-082", u"BUENA-082", "ja")
        self.assertStudioIs(u"POW", metadata)

    def test_metadata_actressless_entry(self):
        # an entry with an empty 【】 header still resolves with no cast
        metadata = self.agent.get_metadata(u"BUENA-077", u"BUENA-077", "ja")
        self.assertTitleEquals(
            u"[BUENA-077] 乃木◢:マウスダイナー (アイドル)", metadata)
        self.assertTrue(not metadata.actresses)


if __name__ == "__main__":
    unittest.main()
