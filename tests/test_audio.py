from array import array
import math
import unittest
from unittest.mock import patch
from afterglow.audio import Envelope, output_monitor, AudioWorker


class AudioTests(unittest.TestCase):
    def test_silence_tone_release_and_peak_bounds(self):
        env = Envelope()
        silence = bytes(1024 * 2)
        self.assertEqual(env.update(silence, 24000), (0, 0))
        tone = array('h', [int(16000 * math.sin(i * 2 * math.pi * 80 / 24000)) for i in range(1024)]).tobytes()
        for _ in range(20): level, bass = env.update(tone, 24000)
        self.assertGreater(level, .2)
        self.assertGreater(bass, .1)
        old = level
        level, _ = env.update(silence, 24000)
        self.assertLess(level, old)
        self.assertGreater(level, 0)
        for _ in range(100): level, bass = env.update(silence, 24000)
        self.assertLess(level, .01)
        level, bass = env.update(array('h', [32767] * 1024).tobytes(), 24000)
        self.assertTrue(0 <= level <= 1 and 0 <= bass <= 1)

    def test_monitor_must_belong_to_default_output(self):
        with patch('afterglow.audio.pactl', side_effect=['headphones', '1\theadphones.monitor\tmodule\ts16le\tRUNNING\n2\tmic\tmodule\ts16le\tRUNNING']):
            self.assertEqual(output_monitor(), 'headphones.monitor')
        with patch('afterglow.audio.pactl', side_effect=['headphones', '2\tmic\tmodule\ts16le\tRUNNING']):
            with self.assertRaises(OSError): output_monitor()

    def test_capture_closes_on_stop_and_route_changes(self):
        import io
        class Process:
            def __init__(self):
                self.stdout = io.BytesIO(b'')
                self.dead = False
            def poll(self): return 0 if self.dead else None
            def terminate(self): self.dead = True
            def wait(self, timeout): self.dead = True
            def kill(self): self.dead = True
        worker = AudioWorker(lambda *args: None)
        a, b = Process(), Process()
        with patch('afterglow.audio.subprocess.Popen', side_effect=[a, b]) as popen:
            worker.connect('first.monitor')
            worker.connect('second.monitor')
            self.assertTrue(a.dead)
            worker.stop()
            self.assertTrue(b.dead)
            self.assertIn('--device=second.monitor', popen.call_args.args[0])


if __name__ == '__main__': unittest.main()
