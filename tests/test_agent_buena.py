# coding=utf-8

from base import AgentTestCase

import datetime
import unittest

import mock

from agents import Buena
from agents.buena import POW_URL, slug_name


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

    def test_search_getchu_fallback(self):
        # releases newer than konodare's catalog are still found on Getchu
        results = self.agent.search([u"buena355"], "ja")
        self.assertEqual(1, len(results))
        self.assertEqual(u"BUENA-355", results[0].video_code)
        self.assertTrue(results[0].title.startswith(u"[BUENA-355] "))

    def test_search_getchu_fallback_unknown_code(self):
        self.assertEqual([], self.agent.search([u"buena99999"], "ja"))

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
        # Getchu adds the synopsis, the package release date and its cover
        self.assertTrue(metadata.summary)
        self.assertReleaseDateIs(datetime.datetime(2020, 10, 13), metadata)
        self.assertIn(u"https://www.getchu.com/brandnew/1108622/c1108622package.jpg", metadata.posters)

    def test_metadata_getchu_disabled(self):
        self.update_prefs(getchu_enabled=False)
        metadata = self.agent.get_metadata(u"BUENA-075", u"BUENA-075", "ja")
        self.assertIsNone(metadata.release_date)
        self.assertNotIn(u"https://www.getchu.com/brandnew/1108622/c1108622package.jpg", metadata.posters)

    def test_metadata_avbase_backfill(self):
        # without Getchu, the summary comes from AVBase's page for the PRIN-042 re-release, but its title and date are not used
        self.update_prefs(getchu_enabled=False)
        metadata = self.agent.get_metadata(u"BUENA-075", u"BUENA-075", "ja")
        self.assertTrue(metadata.summary)
        self.assertTrue(metadata.title.startswith(u"[BUENA-075] "))
        self.assertIsNone(metadata.release_date)

    def test_metadata_avbase_disabled(self):
        self.update_prefs(getchu_enabled=False, avbase_enabled=False)
        metadata = self.agent.get_metadata(u"BUENA-075", u"BUENA-075", "ja")
        self.assertIsNone(metadata.summary)

    def test_metadata_dl_getchu_entry(self):
        # BUENA-002 links only to DL.Getchu, which has the synopsis and genre tags. Its delivery date is a re-listing date, so it is not used.
        metadata = self.agent.get_metadata(u"BUENA-002", u"BUENA-002", "ja")
        self.assertTrue(metadata.summary.startswith(u"圧倒的うぶっ娘"))
        self.assertIsNone(metadata.release_date)
        self.assertGenresInclude([u"コスプレ", u"お嬢様"], metadata)

    def test_metadata_getchu_fallback(self):
        metadata = self.agent.get_metadata(u"BUENA-369", u"BUENA-369", "ja")
        self.assertStudioIs(u"BUENA", metadata)
        self.assertReleaseDateIs(datetime.datetime(2026, 10, 24), metadata)
        self.assertDurationExists(metadata)
        self.assertTrue(metadata.posters)

    def test_metadata_pow_label_studio(self):
        # POW-labelled releases report POW as the studio
        metadata = self.agent.get_metadata(u"BUENA-082", u"BUENA-082", "ja")
        self.assertStudioIs(u"POW", metadata)

    def test_metadata_english_title(self):
        # the English title comes from the konodare cosplay slugs, so the model does not guess the character names
        cases = [
            (u"BUENA-075", u"Milim Nava (That Time I Got Reincarnated as a Slime)"),
            (u"BUENA-084", u"Tifa Lockhart (Final Fantasy 7)"),
            (u"BUENA-216", u"Sirius (Azur Lane)"),
            (u"BUENA-273", u"Suisei Hoshimachi (Hololive)"),
        ]
        for code, title in cases:
            self.assertEqual(title, self.agent.get_metadata(code, code, "ja").english_title)

    def test_metadata_buenap_media_row(self):
        # BUENA-084's media row starts with buenap023, which still belongs to BUENA-084 rather than a new entry
        metadata = self.agent.get_metadata(u"BUENA-084", u"BUENA-084", "ja")
        self.assertTrue(metadata.summary)
        self.assertTrue([p for p in metadata.posters if u"/pow023/pow023jp.jpg" in p])
        self.assertTrue(metadata.trailers)

    def test_index_rebuilt_after_failed_page(self):
        # an index built while a page failed is not cached, so the next call fetches it again
        get = self.agent.session.get

        def fail_pow(url, *args, **kwargs):
            if url == POW_URL:
                raise IOError("Try again")
            return get(url, *args, **kwargs)

        with mock.patch.object(self.agent.session, "get", side_effect=fail_pow):
            self.agent.ensure_index()
        partial = len(self.agent.index)
        self.assertFalse(self.agent.index_complete)
        self.agent.ensure_index()
        self.assertTrue(self.agent.index_complete)
        self.assertGreater(len(self.agent.index), partial)

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
        self.assertTrue(metadata.summary)
        self.assertNotIn(u"ダウンロード", metadata.summary)
        self.assertGenresInclude([u"ケモミミ"], metadata)


class TestSlugName(unittest.TestCase):

    def test_title_cased_slug(self):
        self.assertEqual(u"Mash Kyrielight", slug_name([u"fate", u"mash-kyrielight"], u"マシュ･キリエライト"))

    def test_ascii_text_kept(self):
        self.assertEqual(u"Fate/Grand Order", slug_name([u"fate"], u"Fate/Grand Order"))

    def test_faction_prefix_dropped(self):
        self.assertEqual(u"Sirius", slug_name([u"azur-lane", u"royal-navy-sirius"], u"シリアス"))

    def test_override(self):
        self.assertEqual(u"Kizuna AI", slug_name([u"vtuber", u"kizuna-ai"], u"キズナアイ"))
        self.assertEqual(u"Miko Sakura", slug_name([u"hololive", u"himiko-toga"], u"さくらみこ"))
        self.assertEqual(u"Himiko Toga", slug_name([u"my-hero-academia", u"himiko-toga"], u"トガヒミコ"))

    def test_trailing_number_kept(self):
        self.assertEqual(u"Final Fantasy 7", slug_name([u"final-fantasy"], u"ファイナルファンタジー7"))

    def test_unusable_slug(self):
        self.assertIsNone(slug_name([], u"レム"))
        self.assertIsNone(slug_name([u"%E3%83%AC%E3%83%A0"], u"レム"))


if __name__ == "__main__":
    unittest.main()
