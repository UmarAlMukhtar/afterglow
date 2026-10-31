"""Local preferences, bounded content requests and lyrics resolution."""

from dataclasses import asdict
from collections import Counter
import colorsys
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request

from .lyrics import MAX_TEXT, LyricDocument, Line, Word, parse_lrc, parse_ttml
from .media import spotify_track_id

DEFAULTS = dict(intensity=.65, width=42., size=1., offset=0., light=True,
                lyrics=True, reduce_motion=False, style='fisheye_visual', monitor=0,
                palette='album', primary='#A9E5C2', secondary='#EBAE84',
                lyric_color='#C7839D', lyric_highlight='#B6486C', lyric_secondary='#A07185', spotify_bridge=False)


def paths():
    config = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'afterglow-linux'
    cache = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'afterglow-linux'
    for p in (config, cache):
        p.mkdir(parents=True, exist_ok=True, mode=0o700)
    return config, cache


def validated(raw):
    result = DEFAULTS.copy()
    if not isinstance(raw, dict):
        return result
    ranges = dict(intensity=(0, 1), width=(8, 100), size=(.5, 2), offset=(-10, 10), monitor=(0, 32))
    for k, default in DEFAULTS.items():
        value = raw.get(k, default)
        if k in ranges and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            result[k] = max(ranges[k][0], min(ranges[k][1], value))
        elif isinstance(default, bool) and isinstance(value, bool):
            result[k] = value
        elif k in ('primary', 'secondary', 'lyric_color', 'lyric_highlight', 'lyric_secondary') and isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value):
            result[k] = value
        elif k == 'style' and value in ('words', 'lines', 'ship', 'fisheye', 'fisheye_visual', 'visual'):
            result[k] = 'ship' if value == 'words' else value
        elif k == 'palette' and value in ('album', 'manual'):
            result[k] = value
    result['monitor'] = int(result['monitor'])
    return result


def load_settings() -> dict:
    p = paths()[0] / 'settings.json'
    try:
        if p.stat().st_size > 65536:
            return DEFAULTS.copy()
        return validated(json.loads(p.read_text()))
    except (OSError, ValueError):
        return DEFAULTS.copy()


def atomic_write(path, text):
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.write-')
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def save_settings(settings: dict) -> None:
    p = paths()[0] / 'settings.json'
    if p.exists():
        try:
            if p.stat().st_size > 65536:
                raise ValueError('Oversized settings')
            json.loads(p.read_text())
        except (ValueError, UnicodeError):
            backup = p.with_suffix('.json.broken')
            if backup.exists():
                import time
                backup = p.with_suffix(f'.json.broken-{time.time_ns()}')
            os.replace(p, backup)
    atomic_write(p, json.dumps(validated(settings), indent=2))


def fetch_bytes(url: str, limit: int) -> bytes:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Only HTTPS content without credentials is allowed')
    request = urllib.request.Request(url, headers={'User-Agent': 'AfterglowLinux/0.1.0 (open-source desktop companion)'})
    with urllib.request.urlopen(request, timeout=8) as response:
        if urllib.parse.urlsplit(response.geturl()).scheme != 'https':
            raise ValueError('Insecure redirect')
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Content is too large')
    return data


def cache_key(track):
    identity = [str(track.get(k, '')) for k in ('title', 'artist', 'album', 'duration', 'track_url')]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


class LatestRequest:
    def __init__(self):
        self.generation = 0

    def next(self) -> int:
        self.generation += 1
        return self.generation

    def is_current(self, generation: int) -> bool:
        return generation == self.generation


def resolve_lyrics(track: dict, override: str | None = None) -> LyricDocument:
    config, cache = paths()
    key = cache_key(track)
    overrides = config / 'lyrics'
    overrides.mkdir(exist_ok=True, mode=0o700)
    local = overrides / (key + '.lrc')
    saved = cache / (key + '.json')
    duration = float(track.get('duration') or 0)
    if override is not None:
        doc = parse_lrc(override, duration)
        atomic_write(local, override)
        return doc
    if local.exists():
        with local.open('r') as stream:
            return parse_lrc(stream.read(MAX_TEXT + 1), duration)
    try:
        if saved.stat().st_size <= MAX_TEXT:
            data = json.loads(saved.read_text())
            return LyricDocument(tuple(Line(l['text'], l['start'], l['end'], tuple(Word(**w) for w in l['words'])) for l in data['lines']), data['quality'], data['source'])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    doc = None
    track_id = spotify_track_id(track.get('track_url', ''))
    if track_id:
        try:
            data = fetch_bytes('https://raw.githubusercontent.com/amll-dev/amll-ttml-db/main/spotify-lyrics/' + track_id + '.ttml', MAX_TEXT)
            candidate = parse_ttml(data.decode('utf-8'))
            if candidate.lines:
                doc = candidate
        except (OSError, ValueError):
            pass
    if doc is None:
        query = {k: str(track.get(v, ''))[:1000] for k, v in [('track_name', 'title'), ('artist_name', 'artist'), ('album_name', 'album')]}
        if duration:
            query['duration'] = str(round(duration))
        try:
            payload = json.loads(fetch_bytes('https://lrclib.net/api/get?' + urllib.parse.urlencode(query), MAX_TEXT))
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
            payload = {}
        if not isinstance(payload, dict):
            raise ValueError('Unexpected lyrics response')
        if payload.get('instrumental'):
            doc = LyricDocument((), 'instrumental', 'LRCLIB')
        else:
            raw = payload.get('syncedLyrics') or payload.get('plainLyrics') or ''
            if not isinstance(raw, str):
                raise ValueError('Unexpected lyrics text')
            parsed = parse_lrc(raw, duration)
            doc = LyricDocument(parsed.lines, parsed.quality, 'LRCLIB')
    if doc.quality != 'missing':
        encoded = json.dumps(asdict(doc), ensure_ascii=False)
        if len(encoded.encode()) <= MAX_TEXT:
            atomic_write(saved, encoded)
        for old in sorted(cache.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[500:]:
            old.unlink(missing_ok=True)
    return doc


def load_artwork(url: str) -> tuple[object | None, tuple[str, str]]:
    import gi
    gi.require_version('GdkPixbuf', '2.0')
    from gi.repository import GdkPixbuf
    fallback = ('#A9E5C2', '#EBAE84')
    if not url:
        return None, fallback
    parts = urllib.parse.urlsplit(url)
    if parts.scheme == 'file' and parts.netloc in ('', 'localhost'):
        with Path(urllib.parse.unquote(parts.path)).open('rb') as stream:
            data = stream.read(8 * 1024 * 1024 + 1)
    else:
        data = fetch_bytes(url, 8 * 1024 * 1024)
    if len(data) > 8 * 1024 * 1024 or not data.startswith((b'\x89PNG', b'\xff\xd8', b'GIF8', b'RIFF', b'BM')):
        raise ValueError('Unsupported or oversized artwork')
    loader = GdkPixbuf.PixbufLoader()
    loader.connect('size-prepared', lambda instance, w, h: instance.set_size(max(1, int(w * min(256 / max(w, h), 1))), max(1, int(h * min(256 / max(w, h), 1)))))
    loader.write(data)
    loader.close()
    pixbuf = loader.get_pixbuf()
    small = pixbuf.scale_simple(24, 24, GdkPixbuf.InterpType.BILINEAR)
    pixels = small.get_pixels()
    counts = Counter()
    channels, stride = small.get_n_channels(), small.get_rowstride()
    for y in range(24):
        for x in range(24):
            i = y * stride + x * channels
            r, g, b = pixels[i:i + 3]
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if v > .12 and s > .15:
                counts[round(h * 24) % 24] += 1
    hues = [h for h, _ in counts.most_common()]
    if not hues:
        return pixbuf, fallback
    first = hues[0] / 24
    second = next((h / 24 for h in hues[1:] if .12 < abs(h / 24 - first) < .88), (first + .16) % 1)
    colors = tuple('#' + ''.join(f'{round(v * 255):02x}' for v in colorsys.hsv_to_rgb(h, .55, .95)) for h in (first, second))
    return pixbuf, colors
