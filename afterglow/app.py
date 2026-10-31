"""Native application lifecycle and controls."""

from dataclasses import replace
import math
from pathlib import Path
import queue
import threading
import time
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Gio, Pango

from .audio import AudioWorker
from .lyrics import LyricDocument, parse_lrc, MAX_TEXT
from .media import Playback, MediaWorker, allowed_command, spotify_track_id
from .storage import load_settings, save_settings, resolve_lyrics, load_artwork, LatestRequest
from .visuals import Stage, VisualWindow
from .lyric_scene import STYLES
from .spotify_bridge import SpotifyBridge

DEMO_LRC = '''[00:00.00]<00:00.00>Let <00:01.00>the <00:01.50>room <00:02.50>glow<00:04.00>
[00:04.00]<00:04.00>Follow <00:05.20>every <00:06.40>little <00:07.30>sound<00:09.00>
[00:09.00]<00:09.00>Colors <00:10.50>rise <00:11.60>and <00:12.20>fall<00:14.00>
[00:14.00]<00:14.00>Let <00:15.00>the <00:15.50>words <00:16.70>surround<00:19.00>
[00:19.00]<00:19.00>A <00:19.60>little <00:20.50>light <00:22.00>for <00:22.70>you<00:25.00>
[00:25.00]<00:25.00>Stay <00:26.40>here <00:27.70>in <00:28.30>the <00:29.00>music<00:32.00>'''

CSS = b'''
window { background-color: #101413; color: #F3F5EE; font-family: Sans; font-size: 14px; }
button, combobox, entry { border-radius: 6px; }
button { background-image: none; background-color: #1B2421; border: 1px solid #35473D; color: #F3F5EE; padding: 8px 12px; box-shadow: none; }
button:hover { background-color: #2C3B33; }
button:focus { border-color: #A9E5C2; }
button:disabled { color: #66776B; }
button.accent { background-color: #A9E5C2; color: #101413; border-color: #A9E5C2; }
label.muted { color: #A9B7AE; font-size: 12px; }
label.heading { font-size: 28px; font-weight: bold; }
label.section { color: #A9E5C2; font-size: 11px; font-weight: bold; }
scale trough { background-color: #35473D; min-height: 3px; }
scale highlight { background-color: #A9E5C2; }
separator { background-color: #35473D; min-height: 1px; }
scrolledwindow { border: none; }
'''


class AfterglowApp(Gtk.Application):
    def __init__(self, demo=False):
        super().__init__(application_id='io.github.UmarAlMukhtar.Afterglow', flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.demo = demo
        self.settings = load_settings()
        self.document = LyricDocument()
        self.palette = ('#A9E5C2', '#EBAE84')
        self.playback = None
        self.energy = (0., 0.)
        self.audio_status = 'Connecting to output…'
        self.content_status = ''
        self.loading = False
        self.closing = False
        self.visual = None
        self.bridge = None
        self.window = None
        self.generation = LatestRequest()
        self.requests = {'lyrics': self.generation, 'art': LatestRequest()}
        self.jobs = {kind: queue.Queue(maxsize=1) for kind in ('lyrics', 'art')}
        self.content_done = threading.Event()
        self.content_threads = []
        self.media = MediaWorker(lambda *args: GLib.idle_add(self.update_media, *args))
        self.audio = AudioWorker(self.update_audio)
        self.tick_id = 0
        self.last_frame = 0
        self.last_labels = 0
        self.combo_updating = False
        self.players_signature = None

    def do_activate(self):
        if self.window:
            self.window.present()
            return
        if Gdk.Display.get_default().__class__.__name__.lower().find('wayland') >= 0:
            print('Afterglow v0.1 targets X11. Use an X11 session for desktop overlays.')
        css = Gtk.CssProvider()
        css.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme', True)
        self.build_window()
        for kind in self.jobs:
            thread = threading.Thread(target=self.content_loop, args=(kind,), name='afterglow-' + kind, daemon=True)
            self.content_threads.append(thread)
            thread.start()
        self.media.start()
        self.audio.start()
        if self.settings['spotify_bridge']:
            self.configure_bridge(True)
        if self.demo:
            self.set_demo(True)
        self.tick_id = GLib.timeout_add(33, self.tick)
        display = Gdk.Display.get_default()
        display.connect('monitor-added', self.monitors_changed)
        display.connect('monitor-removed', self.monitors_changed)

    def label(self, text, style=None):
        label = Gtk.Label(label=text, xalign=0)
        label.set_line_wrap(True)
        label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        if style:
            label.get_style_context().add_class(style)
        return label

    def button(self, label, callback, accent=False):
        button = Gtk.Button(label=label)
        button.connect('clicked', lambda _: callback())
        if accent:
            button.get_style_context().add_class('accent')
        return button

    def row(self, *widgets):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_homogeneous(True)
        for widget in widgets:
            box.pack_start(widget, True, True, 0)
        return box

    def section(self, box, title):
        label = self.label(title, 'section')
        label.set_margin_top(10)
        box.pack_start(label, False, False, 0)

    def build_window(self):
        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title('Afterglow Linux')
        self.window.set_default_size(520, 920)
        self.window.set_size_request(380, 600)
        self.window.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.window.connect('delete-event', lambda *args: (self.quit(), True)[1])
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.window.add(scroll)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_border_width(24)
        scroll.add(box)
        box.pack_start(self.label('AFTERGLOW / LINUX', 'section'), False, False, 0)
        box.pack_start(self.label('Give your music a little light.', 'heading'), False, False, 0)
        box.pack_start(self.label('Play in your favorite app. The words and light follow.', 'muted'), False, False, 0)
        self.preview = Stage(self, preview=True)
        self.preview.set_size_request(-1, 205)
        box.pack_start(self.preview, False, False, 2)
        self.track_label = self.label('Waiting for your music…')
        box.pack_start(self.track_label, False, False, 0)
        self.source_label = self.label('No music player detected', 'muted')
        box.pack_start(self.source_label, False, False, 0)
        self.previous = self.button('Previous', lambda: self.transport('Previous'))
        self.play = self.button('Play / pause', lambda: self.transport('PlayPause'), True)
        self.next_button = self.button('Next', lambda: self.transport('Next'))
        box.pack_start(self.row(self.previous, self.play, self.next_button), False, False, 0)
        self.section(box, 'CONNECT YOUR MUSIC')
        services = [('Spotify', 'https://open.spotify.com/'), ('YouTube Music', 'https://music.youtube.com/'),
                    ('Apple Music', 'https://music.apple.com/'), ('SoundCloud', 'https://soundcloud.com/')]
        for pair in (services[:2], services[2:]):
            box.pack_start(self.row(*(self.button(name + ' ↗', lambda url=url: self.open_service(url)) for name, url in pair)), False, False, 0)
        box.pack_start(self.label('Sign in in the player. Compatible apps connect automatically through Linux media controls.', 'muted'), False, False, 0)
        self.source_combo = Gtk.ComboBoxText()
        self.source_combo.append('', 'Auto · follow the active player')
        self.source_combo.set_active(0)
        self.source_combo.connect('changed', self.select_source)
        box.pack_start(self.source_combo, False, False, 0)
        bridge_toggle = Gtk.CheckButton(label='Use Spotify lyric bridge · requires the optional Spicetify extension')
        bridge_toggle.set_active(self.settings['spotify_bridge'])
        bridge_toggle.connect('toggled', lambda w: self.configure_bridge(w.get_active()))
        box.pack_start(bridge_toggle, False, False, 0)
        self.section(box, 'YOUR SPACE')
        box.pack_start(self.row(self.button('Desktop glow', lambda: self.show_visual('desktop')),
                                self.button('Fullscreen', lambda: self.show_visual('fullscreen'), True),
                                self.button('Hide', self.hide_visual)), False, False, 0)
        toggles = []
        for name, key in [('Edge light', 'light'), ('Lyrics', 'lyrics'), ('Reduce motion', 'reduce_motion')]:
            toggle = Gtk.CheckButton(label=name)
            toggle.set_active(self.settings[key])
            toggle.connect('toggled', lambda w, k=key: self.change(k, w.get_active()))
            toggles.append(toggle)
        box.pack_start(self.row(*toggles), False, False, 0)
        style = Gtk.ComboBoxText()
        for key, profile in STYLES.items():
            style.append(key, profile['name'])
        style.append('lines', 'Lines · a quieter view')
        style.set_active_id(self.settings['style'])
        style.connect('changed', lambda w: self.change('style', w.get_active_id()))
        box.pack_start(style, False, False, 0)
        self.monitors = Gtk.ComboBoxText()
        self.refresh_monitors()
        self.monitors.connect('changed', lambda w: self.change('monitor', max(0, w.get_active())))
        box.pack_start(self.monitors, False, False, 0)
        self.section(box, 'TUNE THE FEEL')
        for name, key, low, high, step in [('Light intensity', 'intensity', 0, 1, .05), ('Glow width', 'width', 8, 100, 1),
                                           ('Lyric size', 'size', .5, 2, .05), ('Lyric offset (seconds)', 'offset', -10, 10, .1)]:
            box.pack_start(self.label(name, 'muted'), False, False, 0)
            slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, low, high, step)
            slider.set_value(self.settings[key])
            slider.set_digits(1 if key == 'offset' else (2 if key in ('size', 'intensity') else 0))
            slider.connect('value-changed', lambda w, k=key: self.change(k, w.get_value()))
            box.pack_start(slider, False, False, 0)
        palette = Gtk.ComboBoxText()
        palette.append('album', 'Colors · follow the album')
        palette.append('manual', 'Colors · use my palette')
        palette.set_active_id(self.settings['palette'])
        palette.connect('changed', lambda w: self.change('palette', w.get_active_id()))
        box.pack_start(palette, False, False, 0)
        color_buttons = []
        for key in ('primary', 'secondary'):
            color = Gdk.RGBA()
            color.parse(self.settings[key])
            button = Gtk.ColorButton.new_with_rgba(color)
            button.set_title('Choose ' + key + ' light color')
            button.get_accessible().set_name(key + ' light color')
            button.connect('color-set', lambda w, k=key: self.change(k, '#' + ''.join(f'{round(v * 255):02x}' for v in (w.get_rgba().red, w.get_rgba().green, w.get_rgba().blue))))
            color_buttons.append(button)
        box.pack_start(self.row(*color_buttons), False, False, 0)
        box.pack_start(self.label('Lyric colors · text / highlight / secondary (manual palette)', 'muted'), False, False, 0)
        lyric_colors = []
        for key, name in [('lyric_color', 'Lyric text'), ('lyric_highlight', 'Word highlight'), ('lyric_secondary', 'Secondary text')]:
            rgba = Gdk.RGBA(); rgba.parse(self.settings[key])
            button = Gtk.ColorButton.new_with_rgba(rgba)
            button.set_title(name); button.get_accessible().set_name(name)
            button.connect('color-set', lambda w, k=key: self.change(k, '#' + ''.join(f'{round(v*255):02x}' for v in (w.get_rgba().red,w.get_rgba().green,w.get_rgba().blue))))
            lyric_colors.append(button)
        box.pack_start(self.row(*lyric_colors), False, False, 0)
        box.pack_start(self.row(self.button('Import LRC…', self.import_lyrics), self.button('Retry lyrics', self.retry_lyrics)), False, False, 0)
        self.demo_toggle = Gtk.CheckButton(label='Try the original visual demo · no music login needed')
        self.demo_toggle.set_active(self.demo)
        self.demo_toggle.connect('toggled', lambda w: self.set_demo(w.get_active()))
        box.pack_start(self.demo_toggle, False, False, 0)
        self.status_label = self.label('', 'muted')
        box.pack_start(self.status_label, False, False, 0)
        box.pack_start(self.label('Lyrics lookups send song details to LRCLIB / AMLL. Audio stays on this computer. No microphone capture.', 'muted'), False, False, 0)
        box.pack_start(self.button('Quit Afterglow', self.quit), False, False, 0)
        self.window.show_all()

    def monitor_index(self):
        return min(max(0, int(self.settings['monitor'])), max(0, Gdk.Display.get_default().get_n_monitors() - 1))

    def refresh_monitors(self):
        self.monitors.remove_all()
        display = Gdk.Display.get_default()
        for i in range(display.get_n_monitors()):
            monitor = display.get_monitor(i)
            g = monitor.get_geometry()
            self.monitors.append_text(f'{monitor.get_model() or "Display"} · {g.width} × {g.height}')
        self.monitors.set_active(self.monitor_index())

    def monitors_changed(self, *args):
        self.refresh_monitors()
        if self.visual:
            mode = self.visual.mode
            self.show_visual(mode)

    def change(self, key, value):
        self.settings[key] = value
        if key == 'monitor' and self.visual:
            self.visual.position()

    def open_service(self, url):
        try:
            Gio.AppInfo.launch_default_for_uri(url, None)
            self.content_status = 'Start a song in the player; then select it above if needed.'
        except GLib.Error:
            self.content_status = 'Could not open the browser. Open the music player manually.'

    def select_source(self, combo):
        if not self.combo_updating:
            self.media.select(combo.get_active_id() or '')
            if self.demo_toggle.get_active():
                self.demo_toggle.set_active(False)

    def update_media(self, players, current, error):
        if self.closing:
            return False
        signature = tuple((p.player, p.name) for p in players)
        if signature != self.players_signature:
            self.players_signature = signature
            self.combo_updating = True
            chosen = self.media.preferred
            self.source_combo.remove_all()
            self.source_combo.append('', 'Auto · follow the active player')
            for p in players:
                self.source_combo.append(p.player, p.name)
            if chosen and chosen not in [p.player for p in players]:
                self.source_combo.append(chosen, 'Selected player · waiting to reconnect')
            self.source_combo.set_active_id(chosen)
            self.combo_updating = False
        self.media_error = error
        if not self.demo:
            self.accept_playback(current)
        return False

    def accept_playback(self, current):
        previous = self.playback
        changed = (current.key() if current else None) != (previous.key() if previous else None)
        lyrics_changed = changed or (current and previous and current.track() != previous.track())
        art_changed = changed or (current and previous and current.art_url != previous.art_url)
        self.playback = current
        if changed:
            self.document = LyricDocument()
            self.palette = ('#A9E5C2', '#EBAE84')
            self.content_status = ''
        if lyrics_changed:
            generation = self.requests['lyrics'].next()
            self.loading = bool(current and current.title)
            if self.loading:
                self.enqueue('lyrics', (generation, current, None))
        if art_changed:
            generation = self.requests['art'].next()
            if current:
                self.enqueue('art', (generation, current, None))
        bridge = getattr(self, 'bridge', None)
        if bridge and bridge.latest:
            self.accept_spotify_lyrics(*bridge.latest)

    def enqueue(self, kind, job):
        q = self.jobs[kind]
        try:
            q.get_nowait()
        except queue.Empty:
            pass
        q.put_nowait(job)

    def content_loop(self, kind):
        while not self.content_done.is_set():
            try:
                generation, track, override = self.jobs[kind].get(timeout=.2)
            except queue.Empty:
                continue
            if not self.requests[kind].is_current(generation):
                continue
            try:
                result = resolve_lyrics(track.track(), override) if kind == 'lyrics' else load_artwork(track.art_url)
                error = ''
            except Exception as exc:
                result = None
                error = ('Lyrics unavailable · retry or import an LRC file' if kind == 'lyrics' else 'Album colors unavailable · using the default palette')
            if not self.content_done.is_set():
                GLib.idle_add(self.content_ready, kind, generation, result, error)

    def content_ready(self, kind, generation, result, error):
        if self.closing or not self.requests[kind].is_current(generation):
            return False
        if kind == 'lyrics':
            self.loading = False
            bridge = getattr(self, 'bridge', None)
            if bridge and bridge.latest and self.playback and spotify_track_id(self.playback.track_url) == bridge.latest[0] and (not result or (result.quality != 'word' and result.source != 'LRC')):
                result = bridge.latest[1]
                error = ''
            self.document = result or LyricDocument()
            self.content_status = error
        elif result:
            self.palette = result[1]
        return False

    def configure_bridge(self, enabled):
        self.settings['spotify_bridge'] = enabled
        if self.bridge:
            self.bridge.stop()
            self.bridge = None
        if enabled:
            try:
                self.bridge = SpotifyBridge(lambda *args: GLib.idle_add(self.accept_spotify_lyrics, *args))
                self.bridge.start()
                self.content_status = 'Spotify bridge ready · waiting for the optional extension'
            except OSError:
                self.bridge = None
                self.content_status = 'Spotify bridge could not bind its local port; another Afterglow may be running'

    def accept_spotify_lyrics(self, track_id, document):
        if self.closing or self.demo or not self.playback or spotify_track_id(self.playback.track_url) != track_id:
            return False
        if self.document.quality == 'word' or self.document.source == 'LRC':
            return False
        self.document = document
        self.loading = False
        self.content_status = 'Lyrics received from Spotify · word timing is estimated when Spotify supplies line timing'
        return False

    def update_audio(self, level, bass, status):
        self.energy = (level, bass)
        self.audio_status = status

    def set_demo(self, enabled):
        self.demo = enabled
        for request in self.requests.values():
            request.next()
        self.loading = False
        self.content_status = ''
        if enabled:
            self.playback = Playback(player='demo', name='Original visual demo', title='A Little Light', artist='Afterglow', duration=32,
                                     playing=True, can_control=True, can_play=True, can_pause=True, can_next=True, can_previous=True)
            self.document = parse_lrc(DEMO_LRC, 32)
            self.palette = ('#A9E5C2', '#EBAE84')
        else:
            self.playback = None
            self.accept_playback(self.media.current)

    def transport(self, action):
        if self.demo and self.playback:
            if action == 'PlayPause':
                self.playback = replace(self.playback, position=self.playback.at(time.monotonic()), stamp=time.monotonic(), playing=not self.playback.playing)
            else:
                self.set_demo(True)
        else:
            self.media.command(action)

    def lyric_position(self):
        return (self.playback.at(time.monotonic()) if self.playback else 0) + self.settings['offset']

    def timing_label(self):
        if self.playback and not self.playback.position_valid:
            return 'Player does not report lyric timing'
        return {'word': 'Word-synced lyrics', 'estimated': 'Estimated word timing', 'unsynced': 'Unsynced lyrics',
                'instrumental': 'Instrumental', 'missing': 'Finding lyrics…' if self.loading else 'No synced lyrics'}.get(self.document.quality, '')

    def tick(self):
        if self.closing:
            return False
        now = time.monotonic()
        active = bool(self.playback and self.playback.playing)
        if self.demo and self.playback:
            if self.playback.at(now) >= 32:
                self.playback = replace(self.playback, position=0, stamp=now)
            beat = max(0, math.sin(self.playback.at(now) * math.pi * 3.4)) ** 4 if active else 0
            self.energy = (.14 + beat * .55, beat * .8) if active else (0, 0)
        if now - self.last_frame >= (.032 if active else .25):
            self.last_frame = now
            self.preview.queue_draw()
            if self.visual:
                self.visual.stage.queue_draw()
        if now - self.last_labels >= .4:
            self.last_labels = now
            p = self.playback
            self.track_label.set_text((p.title + (' · ' + p.artist if p.artist else '')) if p else 'Waiting for your music…')
            self.source_label.set_text((p.name + (' · playing' if p.playing else ' · paused')) if p else 'Open a music player or try the demo below')
            for button, action in [(self.previous, 'Previous'), (self.play, 'PlayPause'), (self.next_button, 'Next')]:
                button.set_sensitive(allowed_command(p, action))
            self.play.set_label('Pause' if p and p.playing else 'Play')
            self.status_label.set_text('\n'.join(filter(None, [self.timing_label(), 'Visual demo · simulated audio reaction' if self.demo else self.audio_status, self.content_status, getattr(self, 'media_error', ''), getattr(self, 'gpu_error', '')])))
        return True

    def show_visual(self, mode):
        if mode == 'desktop' and not Gdk.Screen.get_default().is_composited():
            self.content_status = 'Desktop transparency needs a compositor. Try fullscreen, or start your compositor.'
            return
        if self.visual:
            self.visual.destroy()
        self.visual = VisualWindow(self, mode)

    def hide_visual(self):
        if self.visual:
            visual, self.visual = self.visual, None
            visual.destroy()
        if self.window:
            self.window.present()

    def retry_lyrics(self):
        if self.playback and not self.demo:
            self.loading = True
            self.enqueue('lyrics', (self.generation.next(), self.playback, None))

    def import_lyrics(self):
        if not self.playback or self.demo:
            self.content_status = 'Play a song first; imported lyrics attach to that song.'
            return
        target = self.playback
        dialog = Gtk.FileChooserDialog(title='Import timed lyrics', parent=self.window, action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Import', Gtk.ResponseType.OK)
        file_filter = Gtk.FileFilter()
        file_filter.set_name('LRC lyric files'); file_filter.add_pattern('*.lrc')
        dialog.add_filter(file_filter)
        if dialog.run() == Gtk.ResponseType.OK:
            if not self.playback or self.playback.key() != target.key():
                self.content_status = 'The song changed while choosing the file. Import again for the intended song.'
                dialog.destroy()
                return
            target = self.playback
            try:
                with Path(dialog.get_filename()).open('r', encoding='utf-8-sig') as stream:
                    text = stream.read(MAX_TEXT + 1)
                parse_lrc(text, target.duration)
                self.loading = True
                self.enqueue('lyrics', (self.generation.next(), target, text))
            except (OSError, ValueError) as error:
                self.content_status = 'Could not import lyrics: ' + str(error)[:120]
        dialog.destroy()

    def do_shutdown(self):
        self.closing = True
        for request in self.requests.values():
            request.next()
        self.content_done.set()
        if self.bridge:
            self.bridge.stop()
        if self.tick_id:
            GLib.source_remove(self.tick_id)
        if self.visual:
            self.visual.destroy()
            self.visual = None
        self.audio.stop()
        self.media.stop()
        for thread in self.content_threads:
            thread.join(timeout=.3)
        try:
            save_settings(self.settings)
        except OSError as error:
            print('Could not save preferences:', error)
        Gtk.Application.do_shutdown(self)
