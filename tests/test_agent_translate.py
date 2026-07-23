# coding=utf-8

from base import BaseTestCase

import unittest

from agents.translate import Translate
from agents.types import Metadata, Person, Resource


class TestApplyDeterministicRomaji(BaseTestCase):
    """Verify :meth:`Translate.apply_deterministic_romaji` overrides only when
    the reading is delimited into name parts."""

    def setUp(self):
        super(TestApplyDeterministicRomaji, self).setUp()
        self.update_prefs(translate_enabled=True)
        self.agent = Translate(Prefs)

    def make_actress(self, name, reading=None, photo=None, japanese_name=None):
        p = Person(name)
        p.reading = reading
        p.photo = photo
        p.japanese_name = japanese_name
        return p

    def test_undelimited_western_llm_name_kept(self):
        # The LLM already produced Western order from the reading - keep it.
        meta = Metadata()
        meta.actresses = [self.make_actress(u"Saori Hara", reading=u"はらさおり")]
        self.agent.apply_deterministic_romaji(meta)
        self.assertEqual([u"Saori Hara"], list(meta.actresses))

    def test_undelimited_family_first_flipped_to_western(self):
        # The LLM output family-first order; since the two tokens spell the
        # reading in order, flip them to Western order.
        meta = Metadata()
        meta.actresses = [self.make_actress(u"Hara Saori", reading=u"はらさおり")]
        self.agent.apply_deterministic_romaji(meta)
        self.assertEqual([u"Saori Hara"], list(meta.actresses))

    def test_delimited_reading_overrides_with_western_order(self):
        # A delimited reading can be split, so deterministic romaji wins, and is
        # emitted in Western (given-first) order.
        meta = Metadata()
        meta.actresses = [self.make_actress(u"Saho Hara", reading=u"はら さおり")]
        self.agent.apply_deterministic_romaji(meta)
        self.assertEqual([u"Saori Hara"], list(meta.actresses))

    def test_reading_photo_and_japanese_name_preserved(self):
        photo = Resource(u"http://example.test/x.jpg")
        meta = Metadata()
        meta.actresses = [self.make_actress(
            u"Saho Hara", reading=u"はら さおり", photo=photo,
            japanese_name=u"原紗央莉")]
        self.agent.apply_deterministic_romaji(meta)
        actress = meta.actresses[0]
        self.assertEqual(u"Saori Hara", actress)
        self.assertEqual(u"はら さおり", actress.reading)
        self.assertEqual(u"原紗央莉", actress.japanese_name)
        self.assertEqual(photo, actress.photo)

    def test_no_reading_keeps_name(self):
        meta = Metadata()
        meta.actresses = [self.make_actress(u"Saho Hara")]
        self.agent.apply_deterministic_romaji(meta)
        self.assertEqual([u"Saho Hara"], list(meta.actresses))


class TestPreserveJapaneseNames(BaseTestCase):
    """Verify :meth:`Translate.preserve_japanese_names` snapshots the kanji name."""

    def setUp(self):
        super(TestPreserveJapaneseNames, self).setUp()
        self.update_prefs(translate_enabled=True)
        self.agent = Translate(Prefs)

    def test_snapshots_japanese_name(self):
        meta = Metadata()
        meta.actresses = [Person(u"原紗央莉")]
        self.agent.preserve_japanese_names(meta)
        self.assertEqual(u"原紗央莉", meta.actresses[0].japanese_name)

    def test_ignores_already_romanized_name(self):
        # A Latin name has nothing Japanese to snapshot.
        meta = Metadata()
        meta.actresses = [Person(u"Saori Hara")]
        self.agent.preserve_japanese_names(meta)
        self.assertIsNone(meta.actresses[0].japanese_name)

    def test_does_not_overwrite_existing(self):
        actress = Person(u"原紗央莉")
        actress.japanese_name = u"原 紗央莉"
        meta = Metadata()
        meta.actresses = [actress]
        self.agent.preserve_japanese_names(meta)
        self.assertEqual(u"原 紗央莉", meta.actresses[0].japanese_name)


class TestIsBadTranslation(BaseTestCase):
    """Verify malformed/untranslated summaries are rejected."""

    def setUp(self):
        super(TestIsBadTranslation, self).setUp()
        self.agent = Translate(Prefs)

    def test_clean_english_is_accepted(self):
        self.assertFalse(self.agent.is_bad_translation(
            u"FANZA doujin floor triple crown achievement! A great treatment."))

    def test_leading_json_artifact_is_rejected(self):
        # The real START-375 failure: the model leaked its JSON wrapper.
        self.assertTrue(self.agent.is_bad_translation(
            u'{"超人気デカ乳同人漫画×Ocupおっぱい最狂コラボ解禁！！】The only one of a kind 2D BODY.'))

    def test_leading_japanese_is_rejected(self):
        self.assertTrue(self.agent.is_bad_translation(
            u"超人気デカ乳同人漫画 The only one of a kind BODY."))

    def test_mostly_japanese_is_rejected(self):
        self.assertTrue(self.agent.is_bad_translation(
            u"超人気デカ乳同人漫画×Ocupおっぱい最狂コラボ解禁"))

    def test_empty_is_rejected(self):
        self.assertTrue(self.agent.is_bad_translation(u""))
        self.assertTrue(self.agent.is_bad_translation(None))


if __name__ == "__main__":
    unittest.main()
