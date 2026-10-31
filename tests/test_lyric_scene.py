import unittest
from afterglow.lyric_scene import STYLES, icon_for, scene_rows
from afterglow.lyrics import parse_lrc


class SceneTests(unittest.TestCase):
    def test_four_distinct_verci_style_profiles(self):
        self.assertEqual(set(STYLES), {'ship', 'fisheye', 'fisheye_visual', 'visual'})
        self.assertFalse(STYLES['ship']['lens'])
        self.assertTrue(STYLES['fisheye']['lens'])
        self.assertFalse(STYLES['fisheye']['icons'])
        self.assertTrue(STYLES['fisheye_visual']['icons'])
        self.assertTrue(STYLES['visual']['icons'])
        self.assertFalse(STYLES['visual']['lens'])

    def test_stack_shows_sung_words_and_current_highlight(self):
        doc = parse_lrc('[00:00]<00:00>Let <00:01>the <00:02>light <00:04>glow<00:06>', 6)
        rows = scene_rows(doc, 2.5)
        self.assertEqual([r[0] for r in rows], ['Let', 'the', 'light'])
        self.assertEqual([r[2] for r in rows], [False, False, True])
        self.assertTrue(all(r[1] <= 0 for r in rows))
        self.assertFalse(any(r[2] for r in scene_rows(doc, 7)))

    def test_symbol_matching_ignores_case_and_punctuation(self):
        self.assertTrue(icon_for('Love!'))
        self.assertEqual(icon_for('LOVE'), icon_for('love'))
        self.assertTrue(icon_for('time'))
        self.assertEqual(icon_for('unmappedxyz'), '')


if __name__ == '__main__': unittest.main()
