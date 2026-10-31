"""Observe MPRIS players without accessing music-service credentials."""

from dataclasses import dataclass, field
import math
import queue
import re
import threading
import time

PLAYER = 'org.mpris.MediaPlayer2.Player'
ROOT = 'org.mpris.MediaPlayer2'
PROPS = 'org.freedesktop.DBus.Properties'
OBJECT = '/org/mpris/MediaPlayer2'


def spotify_track_id(url):
    match = re.search(r'(?:spotify:track:|open\.spotify\.com/track/)([A-Za-z0-9]{22})(?:\b|$)', str(url))
    return match[1] if match else ''


@dataclass(frozen=True)
class Playback:
    player: str = ''
    name: str = ''
    title: str = ''
    artist: str = ''
    album: str = ''
    duration: float = 0
    position: float = 0
    stamp: float = field(default_factory=time.monotonic)
    playing: bool = False
    position_valid: bool = True
    track_url: str = ''
    art_url: str = ''
    can_control: bool = False
    can_play: bool = False
    can_pause: bool = False
    can_next: bool = False
    can_previous: bool = False
    can_seek: bool = False

    def at(self, now: float) -> float:
        position = max(0., self.position + (max(0., now - self.stamp) if self.playing and self.position_valid else 0))
        return min(self.duration, position) if self.duration > 0 else position

    def track(self):
        return dict(title=self.title, artist=self.artist, album=self.album,
                    duration=self.duration, track_url=self.track_url)

    def key(self):
        return self.player, self.title, self.artist, self.track_url


def choose_player(players: list[Playback], preferred: str, previous: str) -> Playback | None:
    if preferred:
        return next((p for p in players if p.player == preferred), None)
    playing = [p for p in players if p.playing]
    choices = playing or players
    return next((p for p in choices if p.player == previous), choices[0] if choices else None)


def numeric(value):
    try:
        f = float(value)
        return max(0, f) if math.isfinite(f) else 0
    except (ValueError, TypeError, OverflowError):
        return 0


def snapshot(bus_name, props, identity):
    meta = props.get('Metadata', {})
    artists = meta.get('xesam:artist', [])
    if isinstance(artists, str):
        artists = [artists]
    return Playback(player=bus_name, name=str(identity)[:200],
                    title=str(meta.get('xesam:title', ''))[:2000],
                    artist=', '.join(str(a) for a in artists)[:2000],
                    album=str(meta.get('xesam:album', ''))[:2000],
                    duration=numeric(meta.get('mpris:length', 0)) / 1e6,
                    position=numeric(props.get('Position', 0)) / 1e6,
                    position_valid='Position' in props,
                    playing=props.get('PlaybackStatus') == 'Playing',
                    track_url=str(meta.get('xesam:url', ''))[:4096],
                    art_url=str(meta.get('mpris:artUrl', ''))[:8192],
                    **{key: bool(props.get(value, False)) for key, value in
                       [('can_control', 'CanControl'), ('can_play', 'CanPlay'), ('can_pause', 'CanPause'),
                        ('can_next', 'CanGoNext'), ('can_previous', 'CanGoPrevious'), ('can_seek', 'CanSeek')]})


def allowed_command(p, action):
    return bool(p and p.can_control and
                {'PlayPause': p.can_pause if p.playing else p.can_play,
                 'Next': p.can_next, 'Previous': p.can_previous}.get(action, False))


class MediaWorker:
    def __init__(self, on_update):
        self.on_update = on_update
        self.preferred = ''
        self.current = None
        self.commands = queue.Queue(maxsize=8)
        self.done = threading.Event()
        self.thread = threading.Thread(target=self.run, name='afterglow-media', daemon=True)

    def start(self):
        self.thread.start()

    def select(self, bus_name: str):
        self.preferred = bus_name

    def command(self, action: str):
        if allowed_command(self.current, action):
            try:
                self.commands.put_nowait((self.current.key(), action))
            except queue.Full:
                pass

    def stop(self):
        self.done.set()
        if self.thread.is_alive():
            self.thread.join(timeout=5)

    def run(self):
        import dbus
        bus, identities = None, {}
        while not self.done.is_set():
            players, error = [], ''
            try:
                if bus is None:
                    bus = dbus.SessionBus(private=True)
                names = [str(n) for n in bus.list_names() if n.startswith(ROOT + '.') and n != ROOT + '.playerctld']
                names.sort(key=lambda n: (n != self.preferred, n != (self.current.player if self.current else ''), n))
                for name in names[:8]:
                    if self.done.is_set():
                        break
                    try:
                        obj = bus.get_object(name, OBJECT, introspect=False)
                        properties = dbus.Interface(obj, PROPS)
                        props = properties.GetAll(PLAYER, timeout=.4)
                        if name not in identities:
                            identities[name] = str(properties.Get(ROOT, 'Identity', timeout=.4))
                        players.append(snapshot(name, props, identities[name]))
                    except (dbus.DBusException, ValueError, TypeError):
                        continue
                identities = {n: i for n, i in identities.items() if n in names}
                self.current = choose_player(players, self.preferred, self.current.player if self.current else '')
                while not self.commands.empty() and not self.done.is_set():
                    key, action = self.commands.get_nowait()
                    if self.current and self.current.key() == key and allowed_command(self.current, action):
                        try:
                            obj = bus.get_object(self.current.player, OBJECT, introspect=False)
                            getattr(dbus.Interface(obj, PLAYER), action)(timeout=.6)
                        except dbus.DBusException:
                            error = 'Player did not accept the command'
            except (dbus.DBusException, OSError) as exc:
                error = 'Media controls unavailable: ' + str(exc).split('\n')[0][:160]
                self.current = None
                if bus:
                    bus.close()
                bus = None
            self.on_update(players, self.current, error)
            self.done.wait(.5)
        if bus:
            bus.close()
