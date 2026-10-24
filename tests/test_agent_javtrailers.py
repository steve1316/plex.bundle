# coding=utf-8

from base import BaseTestCase

import unittest

import mock

from agents import javtrailers
from agents.avbase import AVBase


class TestMirrorUrl(BaseTestCase):
    def test_hhb_sample(self):
        url = u"https://cc3001.dmm.co.jp/pv/EQA4Mj0IhGqGnlbv/1sun00045ahhb.mp4"
        self.assertEqual(u"https://media.javtrailers.com/hlsvideo/freepv/1/1su/1sun00045a/playlist.m3u8", javtrailers.mirror_url(url))

    def test_mhb_w_sample(self):
        url = u"https://cc3001.dmm.co.jp/pv/OA8IKhcHAHA_DcNj/ebod00889_mhb_w.mp4"
        self.assertEqual(u"https://media.javtrailers.com/hlsvideo/freepv/e/ebo/ebod00889/playlist.m3u8", javtrailers.mirror_url(url))

    def test_other_urls(self):
        self.assertIsNone(javtrailers.mirror_url(u"https://flv.duga.jp/unsecure/sun/0095/noauth/temp.mp4"))
        self.assertIsNone(javtrailers.mirror_url(u"https://cc3001.dmm.co.jp/pv/abc/apae00014_sm_s.mp4"))
        self.assertIsNone(javtrailers.mirror_url(None))


class TestAVBaseMirrorTrailer(BaseTestCase):
    SAMPLE = u"https://cc3001.dmm.co.jp/pv/EQA4Mj0IhGqGnlbv/1sun00045ahhb.mp4"
    MIRROR = u"https://media.javtrailers.com/hlsvideo/freepv/1/1su/1sun00045a/playlist.m3u8"

    def find(self, video_ok):
        self.update_prefs(duga_enabled=True, getchu_enabled=False)
        agent = AVBase(Prefs)
        work = {"products": [{"source": "fanza", "sample_movie_url": self.SAMPLE, "image_url": u"https://pics.dmm.co.jp/pl.jpg"}]}
        with mock.patch.object(agent, "validate_video", return_value=video_ok), mock.patch.object(agent, "validate_playlist", return_value=True):
            return agent.find_trailers(work)

    def test_blocked_sample_uses_mirror(self):
        trailers = self.find(False)
        self.assertEqual([self.MIRROR], trailers)
        self.assertEqual(u"https://pics.dmm.co.jp/pl.jpg", trailers[0].thumb)

    def test_playable_sample_skips_mirror(self):
        self.assertEqual([self.SAMPLE], self.find(True))


if __name__ == "__main__":
    unittest.main()
