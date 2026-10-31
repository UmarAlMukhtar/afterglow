"""Read only the current output monitor; never a microphone."""

from array import array
import math
import select
import subprocess
import sys
import threading
import time


def pactl(*args):
    return subprocess.check_output(['pactl', *args], timeout=2, text=True).strip()


def output_monitor() -> str:
    sink = pactl('get-default-sink')
    name = sink + '.monitor'
    sources = [line.split('\t')[1] for line in pactl('list', 'short', 'sources').splitlines() if '\t' in line]
    if not sink or name not in sources:
        raise OSError('The default output has no available monitor')
    return name


class Envelope:
    def __init__(self):
        self.level = self.bass = self.low = 0.

    def update(self, pcm: bytes, rate: int) -> tuple[float, float]:
        samples = array('h')
        samples.frombytes(pcm[:len(pcm) // 2 * 2])
        if sys.byteorder != 'little':
            samples.byteswap()
        if not samples:
            return self.level, self.bass
        alpha = 1 - math.exp(-2 * math.pi * 180 / rate)
        power = lowpower = 0.
        for value in samples:
            value /= 32768
            self.low += alpha * (value - self.low)
            power += value * value
            lowpower += self.low * self.low
        targets = [min(1., math.sqrt(power / len(samples)) * 3), min(1., math.sqrt(lowpower / len(samples)) * 4)]
        dt = len(samples) / rate
        for attr, target in zip(('level', 'bass'), targets):
            old = getattr(self, attr)
            weight = 1 - math.exp(-dt / (.045 if target > old else .22))
            setattr(self, attr, old + weight * (target - old))
        return self.level, self.bass


class AudioWorker:
    def __init__(self, on_update):
        self.on_update = on_update
        self.done = threading.Event()
        self.thread = threading.Thread(target=self.run, name='afterglow-audio', daemon=True)
        self.process = None
        self.lock = threading.RLock()
        self.monitor = ''

    def start(self):
        self.thread.start()

    def disconnect(self):
        with self.lock:
            proc, self.process = self.process, None
            if proc:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=1)
                proc.stdout.close()

    def connect(self, monitor):
        with self.lock:
            self.disconnect()
            if self.done.is_set():
                return
            if not monitor.endswith('.monitor'):
                raise ValueError('Capture requires an output monitor')
            self.process = subprocess.Popen(['parec', '--device=' + monitor, '--raw', '--format=s16le', '--rate=24000', '--channels=1', '--latency-msec=40'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            self.monitor = monitor

    def stop(self):
        self.done.set()
        self.disconnect()
        if self.thread.is_alive():
            self.thread.join(timeout=4)

    def run(self):
        retry = .5
        while not self.done.is_set():
            try:
                self.connect(output_monitor())
                if self.done.is_set():
                    break
                proc = self.process
                envelope = Envelope()
                route_check = time.monotonic() + 2
                last_data = time.monotonic()
                while not self.done.is_set():
                    if time.monotonic() >= route_check:
                        route_check = time.monotonic() + 2
                        if output_monitor() != self.monitor:
                            break
                    if proc.poll() is not None:
                        raise OSError('Output capture stopped')
                    ready, _, _ = select.select([proc.stdout], [], [], .2)
                    if ready:
                        data = proc.stdout.read1(2048)
                        if not data:
                            raise OSError('Output capture disconnected')
                        last_data = time.monotonic()
                        level, bass = envelope.update(data, 24000)
                        self.on_update(level, bass, 'Output · ' + self.monitor)
                        retry = .5
                    elif time.monotonic() - last_data > 4:
                        raise OSError('Output monitor stopped delivering audio')
            except (OSError, ValueError, subprocess.SubprocessError):
                if not self.done.is_set():
                    self.on_update(0., 0., 'Audio unavailable · reconnecting to output')
                    self.done.wait(retry)
                    retry = min(5, retry * 2)
            finally:
                self.disconnect()
