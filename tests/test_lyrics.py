import unittest

from afterglow.lyrics import parse_lrc, parse_ttml, locate


class LyricsTests(unittest.TestCase):
    def test_line_timing_is_honestly_estimated(self):
        doc = parse_lrc('[00:01.00]Hello world\n[00:05.00]Again', 8)
        self.assertEqual(doc.quality, 'estimated')
        self.assertEqual(doc.lines[0].start, 1)
        self.assertEqual(locate(doc, 0), (-1, -1, 0))
        self.assertEqual(locate(doc, 1)[0:2], (0, 0))
        self.assertEqual(locate(doc, 7)[0], 1)
        self.assertEqual(locate(doc, 9), (-1, -1, 0))

    def test_enhanced_lrc_preserves_word_times_and_gaps(self):
        doc = parse_lrc('[00:01.00]<00:01.00>Hello <00:02.00>world<00:03.00>\n[00:06.00]Again', 9)
        self.assertEqual(doc.lines[0].words[1].start, 2)
        self.assertEqual(doc.lines[0].words[-1].end, 3)
        self.assertEqual(locate(doc, 4), (-1, -1, 0))
        self.assertEqual(parse_lrc('[00:01]<00:01>Hello <00:02>world<00:03>', 4).quality, 'word')

    def test_offsets_sorting_duplicates_and_unicode(self):
        doc = parse_lrc('[offset:500]\n[00:04]مرحبا بالعالم\n[00:01][00:02]Light', 7)
        self.assertEqual([x.start for x in doc.lines], [1.5, 2.5, 4.5])
        self.assertEqual(doc.lines[-1].text, 'مرحبا بالعالم')
        self.assertEqual(len(parse_lrc('[00:01]A\n[00:01]A', 3).lines), 1)

    def test_plain_empty_and_limits(self):
        self.assertEqual(parse_lrc('Hello\nworld').quality, 'unsynced')
        self.assertEqual(parse_lrc('').quality, 'missing')
        with self.assertRaises(ValueError):
            parse_lrc('x' * (2 * 1024 * 1024 + 1))
        self.assertEqual(parse_lrc('[00:nan]bad').quality, 'unsynced')

    def test_ttml_words_syllables_and_silence(self):
        doc = parse_ttml('<tt xmlns="http://www.w3.org/ns/ttml"><body><p begin="1s" end="4s"><span begin="1s" end="2s">Hel</span><span begin="2s" end="2.5s">lo</span> <span begin="3s" end="4s">world</span></p></body></tt>')
        self.assertEqual(doc.quality, 'word')
        self.assertEqual([w.text for w in doc.lines[0].words], ['Hello', 'world'])
        self.assertEqual(doc.lines[0].words[0].end, 2.5)
        self.assertEqual(locate(doc, 2.8)[1], -1)
        self.assertEqual(locate(doc, 3.5)[1], 1)

    def test_unsafe_xml_and_bad_timestamps(self):
        for value in ['<!DOCTYPE tt [<!ENTITY x "hello">]><tt>&x;</tt>', '<tt>', '<tt><p begin="NaNs" end="3s">bad</p></tt>']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_ttml(value)


if __name__ == '__main__':
    unittest.main()
