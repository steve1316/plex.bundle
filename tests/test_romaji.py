# coding=utf-8

from base import BaseTestCase

import unittest

from agents.romaji import romanize_reading


class TestRomanizeReading(BaseTestCase):
    """Verify :func:`romanize_reading` output order and delimiter handling."""

    def test_delimited_two_part_is_western_order(self):
        # A family-first reading is emitted given-first (Western order).
        self.assertEqual(u"Saori Hara", romanize_reading(u"はら さおり"))
        self.assertEqual(u"Hitomi Honda", romanize_reading(u"ほんだ ひとみ"))

    def test_middle_dot_delimiter(self):
        self.assertEqual(u"Rika Tsubaki", romanize_reading(u"つばき・りか"))

    def test_undelimited_reading_is_single_word(self):
        # No part boundary, so the whole reading romanizes to one word. This
        # keeps it out of the deterministic override, which requires a space.
        result = romanize_reading(u"はらさおり")
        self.assertEqual(u"Harasaori", result)
        self.assertNotIn(u" ", result)

    def test_empty_reading(self):
        self.assertIsNone(romanize_reading(u""))
        self.assertIsNone(romanize_reading(None))


if __name__ == "__main__":
    unittest.main()
