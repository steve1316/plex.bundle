# coding=utf-8

from base import BaseTestCase

import datetime
import unittest

import requests

from agents import getchu


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Id extraction

class TestExtractIds(BaseTestCase):
    def test_soft_id_from_affiliate_url(self):
        url = u"https://www.getchu.com/api/geturl.phtml/af/1740/aftype/1/sid/2546/id/1108622/url/soft.phtml-/?id=1108622"
        self.assertEqual(u"1108622", getchu.extract_soft_id(url))

    def test_soft_id_from_affiliate_image(self):
        url = u"https://image.getchu.com/afimage/1108000/1108622/afimg_1108622_160.jpg"
        self.assertEqual(u"1108622", getchu.extract_soft_id(url))

    def test_soft_id_ignores_dl_urls(self):
        self.assertIsNone(getchu.extract_soft_id(u"https://dl.getchu.com/r.php?aff=114753-01-51&t=2&gcd=4031740"))

    def test_dl_id_from_affiliate_url(self):
        self.assertEqual(u"4031740", getchu.extract_dl_id(u"https://dl.getchu.com/r.php?aff=114753-01-51&t=2&gcd=4031740"))

    def test_dl_id_from_item_image(self):
        url = u"https://order.getchu.com/data/item_img/40118/4011873/4011873small.jpg"
        self.assertEqual(u"4011873", getchu.extract_dl_id(url))

    def test_no_id(self):
        self.assertIsNone(getchu.extract_soft_id(None))
        self.assertIsNone(getchu.extract_dl_id(u"https://example.com/"))


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Description cleanup

class TestCleanDescription(BaseTestCase):
    def test_spec_lines_only(self):
        title = u"buena354 五〇分の花嫁＠中〇二乃【ヌルテカオイルSEX編】［コスプレ］"
        text = u"buena354 五〇分の花嫁＠中〇二乃【ヌルテカオイルSEX編】\n・収録時間：約94分\n・フレームサイズ：1920×1080"
        self.assertIsNone(getchu.clean_description(text, title))

    def test_keeps_story_lines(self):
        text = u"溢れるほどのザー汁を美味しそうにゴク飲み！\nDVD-ROM / 117分収録"
        self.assertEqual(u"溢れるほどのザー汁を美味しそうにゴク飲み！", getchu.clean_description(text, None))


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Live pages

class TestLivePages(BaseTestCase):
    def setUp(self):
        super(TestLivePages, self).setUp()
        self.session = requests.Session()

    def test_fetch_soft(self):
        info = getchu.fetch_soft(self.session, u"1108622")
        self.assertTrue(info["title"].startswith(u"buena075 "))
        self.assertEqual(datetime.datetime(2020, 10, 13), info["release_date"])
        self.assertEqual(117, info["duration_min"])
        self.assertTrue(info["description"])
        self.assertEqual(u"https://www.getchu.com/brandnew/1108622/c1108622package.jpg", info["cover_url"])

    def test_fetch_dl_item(self):
        info = getchu.fetch_dl_item(self.session, u"4038100")
        self.assertEqual(datetime.datetime(2021, 11, 25), info["release_date"])
        self.assertIn(u"お嬢様", info["genres"])
        self.assertTrue(info["description"].startswith(u"圧倒的うぶっ娘"))
        self.assertEqual(u"https://dl.getchu.com/data/item_img/40381/4038100/4038100top.jpg", info["cover_url"])

    def test_search_soft_id(self):
        self.assertEqual(u"1370192", getchu.search_soft_id(self.session, u"buena354"))
        self.assertIsNone(getchu.search_soft_id(self.session, u"buena99999"))


if __name__ == "__main__":
    unittest.main()
