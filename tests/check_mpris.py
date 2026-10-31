"""Integration check; invoke with dbus-run-session -- python3 tests/check_mpris.py."""
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from afterglow.media import MediaWorker


def wait_for(predicate):
    limit = time.monotonic() + 8
    while time.monotonic() < limit:
        if predicate(): return
        time.sleep(.05)
    raise AssertionError('MPRIS condition timed out')


def main():
    assert os.environ.get('DBUS_SESSION_BUS_ADDRESS'), 'Run under dbus-run-session'
    proc = subprocess.Popen([sys.executable, str(Path(__file__).with_name('mpris_fixture.py'))])
    state = {'current': None}
    worker = MediaWorker(lambda players, current, error: state.update(current=current))
    worker.start()
    try:
        wait_for(lambda: state['current'] and state['current'].title == 'First Light')
        assert state['current'].playing and not state['current'].can_previous
        worker.command('PlayPause')
        wait_for(lambda: state['current'] and not state['current'].playing)
        worker.command('Next')
        wait_for(lambda: state['current'] and state['current'].title == 'Second Light')
        proc.terminate(); proc.wait(timeout=3)
        wait_for(lambda: state['current'] is None)
        proc = subprocess.Popen([sys.executable, str(Path(__file__).with_name('mpris_fixture.py'))])
        wait_for(lambda: state['current'] and state['current'].title == 'First Light')
        print('MPRIS discovery, capabilities, pause, track change, disconnect and reconnect: PASS')
    finally:
        worker.stop()
        proc.terminate(); proc.wait(timeout=3)
        assert not worker.thread.is_alive()


if __name__ == '__main__': main()
