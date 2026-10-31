"""Original fake player. Run on a private dbus-run-session, never the user's bus."""
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
import time

DBusGMainLoop(set_as_default=True)
PLAYER = 'org.mpris.MediaPlayer2.Player'
ROOT = 'org.mpris.MediaPlayer2'


class Fixture(dbus.service.Object):
    def __init__(self):
        self.bus = dbus.SessionBus()
        self.bus_name = dbus.service.BusName(ROOT + '.afterglow_fixture', self.bus)
        super().__init__(self.bus_name, '/org/mpris/MediaPlayer2')
        self.playing = True
        self.base = 0
        self.stamp = time.monotonic()
        self.title = 'First Light'

    @dbus.service.method('org.freedesktop.DBus.Properties', in_signature='ss', out_signature='v')
    def Get(self, interface, name):
        if interface == ROOT and name == 'Identity': return 'Afterglow Fixture'
        return self.GetAll(interface)[name]

    @dbus.service.method('org.freedesktop.DBus.Properties', in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        if interface == ROOT: return {'Identity': 'Afterglow Fixture'}
        return {'PlaybackStatus': 'Playing' if self.playing else 'Paused',
                'Position': dbus.Int64((self.base + (time.monotonic() - self.stamp if self.playing else 0)) * 1e6),
                'Metadata': dbus.Dictionary({'xesam:title': self.title, 'xesam:artist': dbus.Array(['Afterglow'], signature='s'),
                            'xesam:album': 'Original Fixtures', 'mpris:length': dbus.Int64(30000000),
                            'xesam:url': 'afterglow:fixture', 'mpris:trackid': dbus.ObjectPath('/fixture/1')}, signature='sv'),
                'CanControl': True, 'CanPlay': True, 'CanPause': True, 'CanGoNext': True,
                'CanGoPrevious': False, 'CanSeek': True}

    @dbus.service.method(PLAYER)
    def PlayPause(self):
        self.base += time.monotonic() - self.stamp if self.playing else 0
        self.stamp = time.monotonic()
        self.playing = not self.playing

    @dbus.service.method(PLAYER)
    def Next(self):
        self.title = 'Second Light'
        self.base = 0
        self.stamp = time.monotonic()

    @dbus.service.method(PLAYER, in_signature='x')
    def Seek(self, offset):
        self.base = max(0, self.base + offset / 1e6)
        self.stamp = time.monotonic()


if __name__ == '__main__':
    fixture = Fixture()
    GLib.MainLoop().run()
