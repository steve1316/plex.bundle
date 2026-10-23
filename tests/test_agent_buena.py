# coding=utf-8

from base import AgentTestCase

import datetime
import unittest

from agents import Buena


class TestBuenaAgent(AgentTestCase):

    def get_agent_instance(self):
        return Buena(Prefs)

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Search test cases

    def test_guess_search_keywords(self):
        # site code and DMM cross-ref codes normalize to padding-insensitive keys
        self.assertGuessedKeywords(u"", u"buena075.mp4", u"", [u"BUENA75"])
        self.assertGuessedKeywords(u"", u"BUENA-075.mkv", u"", [u"BUENA75"])
        self.assertGuessedKeywords(u"", u"PRIN-042.mp4", u"", [u"PRIN42"])
        self.assertGuessedKeywords(u"", u"zarj070.mp4", u"", [u"ZARJ70"])
        self.assertGuessedKeywords(u"", u"buenaS002.mp4", u"", [u"BUENAS2"])
        self.assertGuessedKeywords(u"", u"buenaTS003.mp4", u"", [u"BUENATS3"])
        self.assertGuessedKeywords(u"", u"asaichi001.mp4", u"", [u"ASAICHI1"])
        self.assertGuessedKeywords(u"", u"POW-040.mp4", u"", [u"POW40"])
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

    def test_search_asaichi_code(self):
        # buena001-074 live on /asaichi/ and also carry an asaichiNNN code
        results = self.agent.search([u"asaichi002"], "ja")
        self.assertEqual(1, len(results))
        self.assertEqual(u"BUENA-002", results[0].video_code)

    def test_search_special_by_crossref_code(self):
        # the buenaS specials on /buena/2/ cross-reference FANZA codes too
        results = self.agent.search([u"ZARJ073"], "ja")
        self.assertEqual(1, len(results))
        self.assertEqual(u"BUENAS-002", results[0].video_code)

    def test_search_buenap_resolves_to_pow(self):
        # buenap rows are the POW releases, so they resolve to the richer POW entry
        results = self.agent.search([u"buenap040"], "ja")
        self.assertEqual(1, len(results))
        self.assertEqual(u"POW-040", results[0].video_code)

    def test_search_pow_beyond_pow_page(self):
        # POW releases missing from /pow/ are still named by their POW code
        results = self.agent.search([u"POW-084"], "ja")
        self.assertEqual(1, len(results))
        self.assertEqual(u"POW-084", results[0].video_code)

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Metadata test cases

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

    def test_metadata_asaichi_entry(self):
        metadata = self.agent.get_metadata(u"BUENA-001", u"BUENA-001", "ja")
        self.assertTitleEquals(u"[BUENA-001] みごっち", metadata)
        self.assertStudioIs(u"BUENA", metadata)
        self.assertActressesInclude([u"ひなた澪"], metadata)
        self.assertDurationExists(metadata)

    def test_metadata_special_entry(self):
        metadata = self.agent.get_metadata(u"BUENAS-002", u"BUENAS-002", "ja")
        self.assertTitleEquals(u"[BUENAS-002] パピコ (ギガント)", metadata)
        self.assertSeriesIs(u"ギガント", metadata)
        self.assertActressesInclude([u"木下彩芽"], metadata)

    def test_metadata_pow_plain_text_actress(self):
        # POW-051 names its actress as plain text rather than an /actress/ link
        metadata = self.agent.get_metadata(u"POW-051", u"POW-051", "ja")
        self.assertTitleEquals(u"[POW-051] ひなのなの", metadata)
        self.assertStudioIs(u"POW", metadata)
        self.assertActressesInclude([u"高坂あいり"], metadata)

    def test_metadata_pow_040(self):
        metadata = self.agent.get_metadata(u"POW-040", u"POW-040", "ja")
        self.assertTitleEquals(u"[POW-040] べりさ 2", metadata)
        self.assertStudioIs(u"POW", metadata)
        self.assertActressesInclude([u"田中ねね"], metadata)
        self.assertReleaseDateIs(datetime.datetime(2021, 2, 17), metadata)


if __name__ == "__main__":
    unittest.main()
