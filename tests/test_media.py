import unittest
from afterglow.media import Playback, choose_player, snapshot, allowed_command


class MediaTests(unittest.TestCase):
    def test_active_selection_is_stable_and_explicit_selection_wins(self):
        a = Playback(player='a', playing=True)
        b = Playback(player='b', playing=True)
        self.assertEqual(choose_player([a, b], '', 'b'), b)
        self.assertEqual(choose_player([a, b], 'a', 'b'), a)
        self.assertIsNone(choose_player([b], 'a', 'b'))
        self.assertEqual(choose_player([Playback(player='a'), b], '', 'a'), b)
        self.assertIsNone(choose_player([], '', ''))

    def test_position_handles_pause_seek_missing_and_duration(self):
        self.assertEqual(Playback(position=5, stamp=10, playing=True, duration=8).at(20), 8)
        self.assertEqual(Playback(position=5, stamp=10, playing=False).at(20), 5)
        self.assertEqual(Playback(position=1, stamp=20, playing=True).at(21), 2)
        self.assertEqual(Playback(position=0, stamp=10, playing=True, position_valid=False).at(20), 0)

    def test_incomplete_browser_metadata_is_usable(self):
        p = snapshot('org.mpris.MediaPlayer2.brave', {'PlaybackStatus': 'Playing', 'Metadata': {'xesam:title': 'Fixture'}}, 'Brave')
        self.assertEqual(p.title, 'Fixture')
        self.assertEqual(p.artist, '')
        self.assertFalse(p.position_valid)
        self.assertFalse(p.can_next)
        self.assertFalse(allowed_command(p, 'Next'))

    def test_capabilities_prevent_unsupported_commands(self):
        p = Playback(can_control=True, can_play=True, can_pause=False, playing=True, can_next=True)
        self.assertFalse(allowed_command(p, 'PlayPause'))
        self.assertTrue(allowed_command(p, 'Next'))
        self.assertFalse(allowed_command(p, 'Unknown'))
        self.assertFalse(allowed_command(Playback(can_control=False, can_next=True), 'Next'))


if __name__ == '__main__': unittest.main()
