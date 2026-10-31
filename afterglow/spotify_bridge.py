"""Optional authenticated loopback receiver. Spotify credentials never enter it."""
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer
import hmac
import json
import math
import re
import secrets
import threading

from .lyrics import parse_lrc, MAX_TEXT
from .storage import paths, atomic_write

PORT = 43827
ALLOWED_ORIGINS = {'https://xpui.app.spotify.com', 'http://xpui.app.spotify.com'}


def bridge_token():
    path = paths()[0] / 'spotify-bridge-token'
    try:
        token = path.read_text().strip()
        if re.fullmatch(r'[0-9a-f]{64}', token):
            return token
    except OSError:
        pass
    token = secrets.token_hex(32)
    atomic_write(path, token)
    return token


def parse_spotify_lyrics(payload):
    try:
        track = payload['track_id']
        lyrics = payload['lyrics']
        duration = float(payload.get('duration_ms', 0)) / 1000
        if not isinstance(track, str) or not re.fullmatch(r'[A-Za-z0-9]{22}', track):
            raise ValueError('Invalid track ID')
        if not math.isfinite(duration) or not 0 <= duration <= 21600:
            raise ValueError('Invalid track duration')
        lines = lyrics['lines']
        if not isinstance(lines, list) or len(lines) > 10000:
            raise ValueError('Invalid lyric lines')
        output = []
        timed = lyrics.get('syncType') == 'LINE_SYNCED'
        for line in lines:
            text = line['words']
            if not isinstance(text, str) or len(text) > 10000:
                raise ValueError('Invalid lyric text')
            text = text.replace('\n', ' ').replace('\r', ' ')
            if timed:
                stamp = float(line['startTimeMs']) / 1000
                if not math.isfinite(stamp) or not 0 <= stamp <= 21600:
                    raise ValueError('Invalid lyric time')
                output.append(f'[{int(stamp)//60:02}:{stamp%60:06.3f}]' + text)
            else:
                output.append(text)
        text = '\n'.join(output)
        if len(text.encode()) > MAX_TEXT:
            raise ValueError('Lyrics are too large')
        document = parse_lrc(text, duration)
        return track, replace(document, source='Spotify local bridge')
    except (KeyError, TypeError, OverflowError) as error:
        raise ValueError('Invalid Spotify lyric payload') from error


class SpotifyBridge:
    def __init__(self, on_lyrics, port=PORT):
        self.on_lyrics, self.port = on_lyrics, port
        self.token = bridge_token()
        self.server = self.thread = None
        self.latest = None

    def start(self):
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(2)

            def log_message(self, *args):
                pass

            def reply(self, status):
                self.send_response(status)
                origin = self.headers.get('Origin')
                if origin in ALLOWED_ORIGINS:
                    self.send_header('Access-Control-Allow-Origin', origin)
                    self.send_header('Vary', 'Origin')
                    self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')
                    self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
                    self.send_header('Access-Control-Allow-Private-Network', 'true')
                self.send_header('Content-Length', '0')
                self.end_headers()

            def do_OPTIONS(self):
                self.reply(204 if self.headers.get('Origin') in ALLOWED_ORIGINS else 403)

            def do_POST(self):
                origin = self.headers.get('Origin')
                if self.path != '/v1/lyrics' or (origin and origin not in ALLOWED_ORIGINS) or not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + owner.token):
                    self.reply(403); return
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= MAX_TEXT or self.headers.get_content_type() != 'application/json':
                        self.reply(413); return
                    payload = json.loads(self.rfile.read(size))
                    track, document = parse_spotify_lyrics(payload)
                    owner.latest = (track, document)
                    owner.on_lyrics(track, document)
                    self.reply(204)
                except (ValueError, OSError):
                    self.reply(400)
        self.server = HTTPServer(('127.0.0.1', self.port), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=.2), name='afterglow-spotify-bridge', daemon=True)
        self.thread.start()

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=3)
            self.server = None
