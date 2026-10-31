"""The shared Cairo/Pango scene for desktop and fullscreen."""

import bisect
import math
import time
import cairo
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk, Gdk, GLib, Pango, PangoCairo

from .lyrics import locate
from .lyric_scene import STYLES
from .gpu_lyrics import LensLayer


def rgb(value):
    return tuple(int(value[i:i + 2], 16) / 255 for i in (1, 3, 5))


class Canvas(Gtk.DrawingArea):
    def __init__(self, owner, preview=False, desktop=False):
        super().__init__()
        self.owner, self.preview, self.desktop = owner, preview, desktop
        self.doc = None
        self.words = []
        self.focus = None
        self.connect('draw', self.draw_scene)
        self.get_accessible().set_name('Animated lyrics and audio-reactive light')

    def text(self, ctx, value, x, y, size, color='#F3F5EE', alpha=1., width=1000, bold=False):
        layout = PangoCairo.create_layout(ctx)
        font = Pango.FontDescription('Sans Bold' if bold else 'Sans')
        font.set_absolute_size(size * Pango.SCALE)
        layout.set_font_description(font)
        layout.set_text(str(value), -1)
        layout.set_width(int(width * Pango.SCALE))
        layout.set_alignment(Pango.Alignment.CENTER)
        layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        layout.set_height(int(size * 2.8 * Pango.SCALE))
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        _, height = layout.get_pixel_size()
        ctx.set_source_rgba(*rgb(color), max(0, min(1, alpha)))
        ctx.move_to(x - width / 2, y - height / 2)
        PangoCairo.show_layout(ctx, layout)

    def draw_scene(self, widget, ctx):
        width, height = self.get_allocated_width(), self.get_allocated_height()
        ctx.set_operator(cairo.OPERATOR_SOURCE)
        ctx.set_source_rgba(0, 0, 0, 0)
        ctx.paint()
        ctx.set_operator(cairo.OPERATOR_OVER)
        app, s = self.owner, self.owner.settings
        now = time.monotonic()
        palette = app.palette if s['palette'] == 'album' else (s['primary'], s['secondary'])
        if not self.desktop:
            ctx.set_source_rgb(*rgb('#101413'))
            ctx.paint()
            haze = cairo.RadialGradient(width * .5, height * .8, 0, width * .5, height * .8, max(width, height) * .7)
            haze.add_color_stop_rgba(0, *rgb(palette[0]), .08)
            haze.add_color_stop_rgba(1, *rgb(palette[1]), 0)
            ctx.set_source(haze); ctx.paint()
        if s['light']:
            level, bass = app.energy
            strength = s['intensity'] * (.25 + .55 * level + .2 * bass)
            span = s['width'] * (0.45 if self.preview else 1) * (1 + .35 * bass)
            edges = [(0, 0, 0, span, (0, 0, width, span), palette[0]),
                     (0, height, 0, height - span, (0, height - span, width, span), palette[1]),
                     (0, 0, span, 0, (0, 0, span, height), palette[0]),
                     (width, 0, width - span, 0, (width - span, 0, span, height), palette[1])]
            for a, b, c, d, rect, color in edges:
                gradient = cairo.LinearGradient(a, b, c, d)
                gradient.add_color_stop_rgba(0, *rgb(color), strength)
                gradient.add_color_stop_rgba(.15, *rgb(color), strength * .48)
                gradient.add_color_stop_rgba(1, *rgb(color), 0)
                ctx.set_source(gradient); ctx.rectangle(*rect); ctx.fill()
            ctx.set_line_width(1.5 if self.preview else 2.5 + 2 * bass)
            edge = cairo.LinearGradient(0, 0, width, height)
            edge.add_color_stop_rgba(0, *rgb(palette[0]), min(.9, strength + .2))
            edge.add_color_stop_rgba(1, *rgb(palette[1]), min(.9, strength + .2))
            ctx.set_source(edge); ctx.rectangle(2, 2, width - 4, height - 4); ctx.stroke()
        scale = min(width / 1920, height / 1000) if not self.preview else .38
        scale = max(.32, min(1.7, scale))
        lyric_center = height * (.51 if not self.preview else .45)
        text_width = width * (.80 if not self.preview else .91)
        doc, position = app.document, app.lyric_position()
        if doc is not self.doc:
            self.doc = doc
            self.words = [(word, i, j) for i, line in enumerate(doc.lines) for j, word in enumerate(line.words)]
            self.word_indices = {(i, j): n for n, (_, i, j) in enumerate(self.words)}
            self.focus = None
        i, j, progress = locate(doc, position)
        use_lens = s['style'] in STYLES and not getattr(app, 'gpu_error', '')
        if s['lyrics'] and (not use_lens or doc.quality in ('missing', 'instrumental', 'unsynced')):
            if doc.quality == 'unsynced' and doc.lines:
                lines = doc.lines[0].text.splitlines()
                index = int(now / 5) % max(1, len(lines))
                self.text(ctx, lines[index], width / 2, lyric_center, 48 * scale * s['size'], width=text_width, bold=True)
            elif i >= 0 and s['style'] != 'lines' and j >= 0:
                index = self.word_indices.get((i, j), 0)
                if self.focus is None or s['reduce_motion'] or abs(self.focus - index) > 6:
                    self.focus = float(index)
                self.focus += (index - self.focus) * .28
                center = self.focus
                neighbors = 1 if self.preview else 3
                for n in range(max(0, index - neighbors), min(len(self.words), index + neighbors + 1)):
                    distance = n - center
                    emphasis = max(0., 1 - abs(distance))
                    size = (38 + 30 * emphasis) * scale * s['size']
                    opacity = max(.06, 1 - abs(distance) * .31)
                    self.text(ctx, self.words[n][0].text, width / 2, lyric_center + distance * 88 * scale * s['size'], size,
                              palette[0] if n == index else '#F3F5EE', opacity, text_width, True)
                ctx.set_source_rgba(*rgb(palette[0]), .5)
                ctx.rectangle(width / 2 - 30 * scale, lyric_center + 49 * scale * s['size'], 60 * scale * progress, 2)
                ctx.fill()
            elif i >= 0:
                for n in range(max(0, i - 1), min(len(doc.lines), i + 2)):
                    self.text(ctx, doc.lines[n].text, width / 2, lyric_center + (n - i) * 105 * scale * s['size'],
                              (51 if n == i else 31) * scale * s['size'], palette[0] if n == i else '#F3F5EE',
                              1 if n == i else .22, text_width, n == i)
            else:
                message = {'missing': 'Play something you love', 'instrumental': 'Let the music breathe'}.get(doc.quality, '♪')
                if app.playback and doc.quality == 'missing':
                    message = 'Lyrics unavailable' if not app.loading else 'Finding the words…'
                self.text(ctx, message, width / 2, lyric_center, 48 * scale, alpha=.8, width=text_width, bold=True)
        if not self.desktop and (self.preview or not use_lens):
            self.text(ctx, 'AFTERGLOW  /  ' + ('DEMO' if app.demo else 'NOW PLAYING'), width / 2, 30 if self.preview else height * .10,
                      11 if self.preview else 13, '#A9B7AE', width=text_width)
            if app.playback:
                self.text(ctx, app.playback.title + ('  ·  ' + app.playback.artist if app.playback.artist else ''),
                          width / 2, height - (26 if self.preview else height * .12), 12 if self.preview else 17,
                          '#A9B7AE', width=text_width)
            if not self.preview:
                self.text(ctx, app.timing_label() + '   ·   Esc to return', width / 2, height * .93, 12, '#A9B7AE', width=text_width)
        return False


class Stage(Gtk.Overlay):
    def __init__(self, owner, preview=False, desktop=False):
        super().__init__()
        self.canvas = Canvas(owner, preview, desktop)
        self.lens = LensLayer(owner, preview)
        self.add(self.canvas)
        self.add_overlay(self.lens)
        self.set_overlay_pass_through(self.lens, True)
        self.get_accessible().set_name('Animated lyrics and audio-reactive light')

    def queue_draw(self):
        self.canvas.queue_draw()
        self.lens.queue_render()


class VisualWindow(Gtk.ApplicationWindow):
    def __init__(self, owner, mode):
        super().__init__(application=owner)
        self.owner, self.mode = owner, mode
        self.set_title('Afterglow — ' + mode)
        self.set_decorated(False)
        self.set_app_paintable(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        if mode == 'desktop':
            self.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
            self.set_accept_focus(False)
            visual = self.get_screen().get_rgba_visual()
            if visual:
                self.set_visual(visual)
            self.input_shape_combine_region(cairo.Region())
        self.stage = Stage(owner, desktop=mode == 'desktop')
        self.add(self.stage)
        self.connect('key-press-event', self.key)
        self.connect('delete-event', self.closed)
        self.position()
        self.show_all()
        if mode == 'desktop':
            self.pass_through()
            self.connect('map-event', lambda *args: GLib.idle_add(self.pass_through))
            self.connect('size-allocate', lambda *args: GLib.idle_add(self.pass_through))
        if mode == 'fullscreen':
            self.fullscreen_on_monitor(self.get_screen(), owner.monitor_index())

    def pass_through(self):
        window = self.get_window()
        if window:
            self.input_shape_combine_region(cairo.Region())
            window.input_shape_combine_region(cairo.Region(), 0, 0)
        return False

    def position(self):
        monitor = Gdk.Display.get_default().get_monitor(self.owner.monitor_index())
        geometry = monitor.get_geometry()
        self.move(geometry.x, geometry.y)
        self.resize(geometry.width, geometry.height)

    def key(self, window, event):
        if event.keyval == Gdk.KEY_Escape:
            self.owner.hide_visual()
            return True
        if event.keyval == Gdk.KEY_space:
            self.owner.transport('PlayPause')
            return True
        return False

    def closed(self, *args):
        self.owner.hide_visual()
        return True
