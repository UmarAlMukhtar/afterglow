"""Native smoke check; requires an X11 display. Uses isolated config/cache."""
import os
from pathlib import Path
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gi.repository import GLib
from afterglow.app import AfterglowApp


def main():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ['XDG_CONFIG_HOME'] = tmp + '/config'
        os.environ['XDG_CACHE_HOME'] = tmp + '/cache'
        app = AfterglowApp(demo=True)
        errors = []
        def check():
            try:
                assert app.playback.at(time.monotonic()) > .5
                app.transport('PlayPause')
                position = app.playback.at(time.monotonic())
                assert not app.playback.playing
                assert app.playback.at(time.monotonic() + 2) == position
                app.settings['offset'] = 2
                assert app.lyric_position() >= position + 1.99
                app.show_visual('desktop')
                assert app.visual is not None and app.visual.mode == 'desktop'
                from gi.repository import Gtk
                for _ in range(10):
                    if Gtk.events_pending(): Gtk.main_iteration_do(False)
                assert app.visual.get_window().is_visible()
                import ctypes as c
                gi = __import__('gi'); gi.require_version('GdkX11', '3.0')
                from gi.repository import GdkX11
                x = c.CDLL('libX11.so.6'); ext = c.CDLL('libXext.so.6')
                x.XOpenDisplay.restype = c.c_void_p
                display = x.XOpenDisplay(None)
                ext.XShapeGetRectangles.argtypes = [c.c_void_p,c.c_ulong,c.c_int,c.POINTER(c.c_int),c.POINTER(c.c_int)]
                ext.XShapeGetRectangles.restype = c.c_void_p
                count, ordering = c.c_int(), c.c_int()
                region = ext.XShapeGetRectangles(display, app.visual.get_window().get_xid(), 2, c.byref(count), c.byref(ordering))
                x.XFree.argtypes = [c.c_void_p]; x.XFree(region)
                x.XCloseDisplay.argtypes = [c.c_void_p]; x.XCloseDisplay(display)
                assert count.value == 0, 'Overlay intercepts desktop input'
                app.show_visual('fullscreen')
                assert app.visual.mode == 'fullscreen'
                app.hide_visual()
                assert app.window.get_visible()
                print('GTK demo clock, pause, offset, desktop/fullscreen, controls recovery: PASS')
            except Exception as exc:
                import traceback
                traceback.print_exc()
                errors.append(exc)
            finally:
                app.quit()
            return False
        GLib.timeout_add(1600, check)
        app.run(['afterglow-test'])
        assert not errors, errors
        assert not [t.name for t in threading.enumerate() if t.name.startswith('afterglow-')], 'Worker leaked'
        assert app.audio.process is None
        print('GTK shutdown/worker cleanup: PASS')


if __name__ == '__main__': main()
