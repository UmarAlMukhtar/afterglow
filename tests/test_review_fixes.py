from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from afterglow.lyrics import parse_lrc, locate, LyricDocument
from afterglow.media import Playback
from afterglow.storage import LatestRequest
from afterglow.app import AfterglowApp


class ReviewFixTests(unittest.TestCase):
    def test_explicit_long_word_timings_are_not_estimation_capped(self):
        doc = parse_lrc('[00:00]<00:00>First <00:08>second<00:12>\n[00:15]Next', 20)
        self.assertEqual(doc.lines[0].words[1].end, 12)
        self.assertEqual(locate(doc, 9)[0:2], (0, 1))
        self.assertTrue(all(w.end > w.start for line in doc.lines for w in line.words))

    def test_repeated_timestamps_cannot_expand_unbounded_events(self):
        raw = ''.join(f'[{i // 60:02}:{i % 60:02}]' for i in range(1000)) + 'word ' * 100
        with self.assertRaises(ValueError):
            parse_lrc(raw, 1200)

    def fake_owner(self, playback):
        jobs = []
        lyrics, art = LatestRequest(), LatestRequest()
        owner = SimpleNamespace(playback=playback, document=LyricDocument(), palette=('', ''),
                                content_status='', loading=False, generation=lyrics,
                                requests={'lyrics': lyrics, 'art': art}, enqueue=lambda *args: jobs.append(args))
        return owner, jobs

    def test_late_metadata_and_artwork_refresh_only_affected_content(self):
        p = Playback(player='test', title='Song', artist='Artist')
        owner, jobs = self.fake_owner(p)
        AfterglowApp.accept_playback(owner, replace(p, duration=30, album='Album'))
        self.assertEqual([kind for kind, _ in jobs], ['lyrics'])
        p = owner.playback
        jobs.clear()
        AfterglowApp.accept_playback(owner, replace(p, art_url='https://example.com/art.jpg'))
        self.assertEqual([kind for kind, _ in jobs], ['art'])

    def test_import_rejects_track_change_and_disconnect(self):
        for new in (Playback(player='test', title='B'), None):
            with self.subTest(new=new), tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / 'test.lrc'; p.write_text('[00:01]Original fixture')
                owner, jobs = self.fake_owner(Playback(player='test', title='A'))
                owner.demo = False
                owner.window = None
                class Dialog:
                    def __init__(self, **kwargs): pass
                    def add_buttons(self, *args): pass
                    def add_filter(self, *args): pass
                    def run(self):
                        owner.playback = new
                        return -5  # Gtk.ResponseType.OK
                    def get_filename(self): return str(p)
                    def destroy(self): pass
                with patch('afterglow.app.Gtk.FileChooserDialog', Dialog):
                    AfterglowApp.import_lyrics(owner)
                self.assertEqual(jobs, [])
                self.assertIn('changed', owner.content_status.lower())

    def test_retry_does_not_cancel_artwork(self):
        owner, jobs = self.fake_owner(Playback(player='test', title='A'))
        owner.demo = False
        owner.closing = False
        owner.generation.next()
        generation = owner.requests['art'].next()
        AfterglowApp.retry_lyrics(owner)
        AfterglowApp.content_ready(owner, 'art', generation, (None, ('#123456', '#abcdef')), '')
        self.assertEqual(owner.palette, ('#123456', '#abcdef'))


if __name__ == '__main__': unittest.main()
