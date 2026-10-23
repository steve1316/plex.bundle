# coding=utf-8

from base import AgentTestCase

import datetime
import unittest

from agents import JavDB


class TestJavDBAgent(AgentTestCase):

    def get_agent_instance(self):
        return JavDB(Prefs)

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Search test cases

    def test_guess_search_keywords(self):
        self.assertGuessedKeywords(
            u"230OREMO-042", u"230OREMO-042.mp4", u"230OREMO-042", [u"230OREMO-042"])
        self.assertGuessedKeywords(
            u"JBD-226", u"jbd226", u"JBD-226", [u"JBD-226"])

    def test_search_230OREMO_042(self):
        results = self.agent.search(["230OREMO-042"], "ja")
        self.assertEqual(1, len(results))
        self.assertEqual("me5WJM", results[0].id)
        self.assertEqual("OREMO-042", results[0].video_code)
        self.assertEqual(u"OREMO-042 ラグビー部マネージャーN", results[0].title)
        self.assertEqual(2023, results[0].year)
        self.assertEqual(100, results[0].score)

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Metadata test cases

    def test_metadata_OREMO_042(self):
        metadata = self.agent.get_metadata("me5WJM", "OREMO-042", "ja")
        self.assertTitleEquals(u"OREMO-042 ラグビー部マネージャーN", metadata)
        self.assertReleaseDateIs(datetime.datetime(2023, 10, 16), metadata)
        self.assertDurationExists(metadata)
        self.assertActressesInclude([u"星乃夏月"], metadata)
        self.assertGenresInclude([u"Amateur"], metadata)
        self.assertRatingExists(metadata)
        self.assertPostersInclude(
            [u"https://c0.jdbstatic.com/covers/me/me5WJM.jpg"], metadata)

    def test_metadata_JBD_226_skips_male_actors(self):
        metadata = self.agent.get_metadata("QNmy7", "JBD-226", "ja")
        self.assertEqual([u"篠田ゆう"], metadata.actresses)
        self.assertDirectorsInclude([u"朝霧浄"], metadata)
        self.assertSeriesIs(u"拷問無残", metadata)
        self.assertLabelsInclude([u"蛇縛"], metadata)


if __name__ == "__main__":
    unittest.main()
