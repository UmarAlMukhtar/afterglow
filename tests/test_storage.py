import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from afterglow.storage import load_settings, save_settings, resolve_lyrics, LatestRequest, fetch_bytes, cache_key, paths


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'XDG_CONFIG_HOME': self.tmp.name + '/config', 'XDG_CACHE_HOME': self.tmp.name + '/cache'})
        self.env.start()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.env.stop)
        self.track = dict(title='Original Fixture', artist='Afterglow', album='', duration=10, track_url='')

    def test_settings_roundtrip_validation_and_corruption(self):
        save_settings({'intensity': .4, 'offset': 2, 'light': False})
        self.assertEqual(load_settings()['intensity'], .4)
        self.assertFalse(load_settings()['light'])
        p = paths()[0] / 'settings.json'
        p.write_text('{broken')
        self.assertEqual(load_settings()['offset'], 0)
        save_settings(load_settings())
        self.assertEqual(p.with_suffix('.json.broken').read_text(), '{broken')
        p.write_text(json.dumps({'offset': 'oops', 'intensity': 400, 'style': 'unsafe'}))
        s = load_settings()
        self.assertEqual(s['offset'], 0)
        self.assertLessEqual(s['intensity'], 1)
        self.assertEqual(s['style'], 'fisheye_visual')

    def test_import_wins_and_is_cached(self):
        with patch('afterglow.storage.fetch_bytes', side_effect=AssertionError('network forbidden')):
            d = resolve_lyrics(self.track, '[00:01]Hello')
            self.assertEqual(d.lines[0].text, 'Hello')
            self.assertEqual(resolve_lyrics(self.track).lines[0].text, 'Hello')

    def test_ttml_before_fallback(self):
        track = dict(self.track, track_url='spotify:track:0123456789012345678901')
        xml = b'<tt><p begin="1s" end="3s"><span begin="1s" end="3s">Light</span></p></tt>'
        with patch('afterglow.storage.fetch_bytes', return_value=xml):
            self.assertEqual(resolve_lyrics(track).quality, 'word')

    def test_fallback_instrumental_missing_and_cache(self):
        for payload, quality in [({'instrumental': True}, 'instrumental'), ({'syncedLyrics': '[00:01]Light'}, 'estimated'), ({'plainLyrics': 'Light'}, 'unsynced')]:
            with self.subTest(payload=payload), patch('afterglow.storage.fetch_bytes', return_value=json.dumps(payload).encode()):
                track = dict(self.track, title=str(payload))
                self.assertEqual(resolve_lyrics(track).quality, quality)
                with patch('afterglow.storage.fetch_bytes', side_effect=AssertionError('cache should win')):
                    self.assertEqual(resolve_lyrics(track).quality, quality)
        with patch('afterglow.storage.fetch_bytes', side_effect=OSError('offline')):
            with self.assertRaises(OSError):
                resolve_lyrics(self.track)

    def test_generation_and_identity(self):
        g = LatestRequest()
        a = g.next()
        self.assertTrue(g.is_current(a))
        g.next()
        self.assertFalse(g.is_current(a))
        self.assertNotEqual(cache_key(self.track), cache_key(dict(self.track, artist='Other')))

    def test_reference_styles_and_lyric_colors_persist(self):
        for style in ('ship', 'fisheye', 'fisheye_visual', 'visual'):
            save_settings({'style': style, 'lyric_color': '#c7839d', 'lyric_highlight': '#b6486c'})
            self.assertEqual(load_settings()['style'], style)
            self.assertEqual(load_settings()['lyric_highlight'], '#b6486c')

    def test_fetch_rejects_credentials_local_schemes_and_oversize(self):
        for url in ['file:///etc/passwd', 'http://example.com/x', 'https://u:p@example.com/a']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                fetch_bytes(url, 10)
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def geturl(self): return 'https://example.com'
            def read(self, amount): return b'a' * amount
        with patch('urllib.request.urlopen', return_value=Response()), self.assertRaises(ValueError):
            fetch_bytes('https://example.com', 10)


if __name__ == '__main__': unittest.main()
