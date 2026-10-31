import json
import os
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch

from afterglow.spotify_bridge import SpotifyBridge, parse_spotify_lyrics


PAYLOAD = {'track_id': '0123456789012345678901', 'duration_ms': 10000, 'lyrics': {
    'syncType': 'LINE_SYNCED', 'lines': [{'startTimeMs': '1000', 'words': 'Original light'}, {'startTimeMs': '5000', 'words': 'Original sound'}]}}


class BridgeTests(unittest.TestCase):
    def test_line_timing_is_estimated_and_source_is_explicit(self):
        track, document = parse_spotify_lyrics(PAYLOAD)
        self.assertEqual(track, '0123456789012345678901')
        self.assertEqual(document.quality, 'estimated')
        self.assertEqual(document.source, 'Spotify local bridge')
        self.assertEqual(document.lines[0].start, 1)

    def test_invalid_payloads_rejected(self):
        for data in [{}, dict(PAYLOAD, track_id='bad'), dict(PAYLOAD, lyrics={'syncType': 'LINE_SYNCED', 'lines': [{'startTimeMs': 'NaN', 'words': 'x'}]}), dict(PAYLOAD, lyrics={'lines': [None]})]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                parse_spotify_lyrics(data)

    def test_lyric_text_is_literal_and_never_becomes_word_timing(self):
        for text in ('[offset:5000]hello', 'hello [01:00]world', '<00:01>hello<00:02>'):
            payload = dict(PAYLOAD, lyrics={'syncType':'LINE_SYNCED','lines':[{'startTimeMs':'1000','words':text}]})
            _, document = parse_spotify_lyrics(payload)
            self.assertEqual(document.lines[0].start, 1)
            self.assertEqual(document.lines[0].text, text)
            self.assertEqual(document.quality, 'estimated')

    def test_empty_bridge_does_not_erase_usable_external_lyrics(self):
        from types import SimpleNamespace
        from afterglow.app import AfterglowApp
        from afterglow.lyrics import LyricDocument, parse_lrc
        from afterglow.media import Playback
        from dataclasses import replace
        valid = replace(parse_lrc('[00:01]Original light', 10),source='LRCLIB')
        owner = SimpleNamespace(closing=False,demo=False,playback=Playback(track_url='spotify:track:'+PAYLOAD['track_id']),document=valid)
        AfterglowApp.accept_spotify_lyrics(owner,PAYLOAD['track_id'],LyricDocument())
        self.assertIs(owner.document, valid)

    def test_loopback_requires_token_and_does_not_forward_auth(self):
        seen = threading.Event(); received = []
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_CONFIG_HOME': tmp+'/config','XDG_CACHE_HOME': tmp+'/cache'}):
            bridge = SpotifyBridge(lambda *args: (received.append(args), seen.set()), port=0)
            bridge.start()
            try:
                url = f'http://127.0.0.1:{bridge.port}/v1/lyrics'
                data = json.dumps(PAYLOAD).encode()
                bad = urllib.request.Request(url, data=data, headers={'Content-Type':'application/json'})
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(bad, timeout=2)
                self.assertEqual(error.exception.code, 403)
                error.exception.close()
                good = urllib.request.Request(url, data=data, headers={'Content-Type':'application/json','Authorization':'Bearer '+bridge.token})
                with urllib.request.urlopen(good, timeout=2) as response:
                    self.assertEqual(response.status, 204)
                self.assertTrue(seen.wait(2))
                self.assertEqual(received[0][0], PAYLOAD['track_id'])
                with urllib.request.urlopen(good,timeout=2): pass
                self.assertEqual(len(received),1)
                self.assertEqual(bridge.server.server_address[0], '127.0.0.1')
            finally:
                bridge.stop()
                self.assertFalse(bridge.thread.is_alive())


if __name__ == '__main__': unittest.main()
