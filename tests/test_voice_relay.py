import time
import unittest

from screen_translator.config import AppSettings
from screen_translator.voice_relay import VoiceRelayWorker, WaveAudio


class FakeSynthesizer:
    def __init__(self):
        self.requests = []

    def synthesize(self, text, voice_name, rate):
        self.requests.append((text, voice_name, rate))
        return WaveAudio(b"\x00\x00" * 16, 16_000, 1)

    def interrupt(self):
        pass


class FakeOutput:
    def __init__(self):
        self.played = []

    def play(self, pcm, sample_rate, channels, *, volume_percent=100):
        self.played.append((pcm, sample_rate, channels, volume_percent))

    def interrupt(self):
        pass

    def close(self):
        pass


class VoiceRelayTests(unittest.TestCase):
    def test_completed_translation_is_synthesized_and_played(self):
        synth = FakeSynthesizer()
        output = FakeOutput()
        settings = AppSettings(audio_relay_output_device_id=7)
        worker = VoiceRelayWorker(
            settings,
            synthesizer_factory=lambda: synth,
            output_factory=lambda _device_id: output,
        )
        worker.start()
        worker.enqueue("hello")
        deadline = time.monotonic() + 1
        while not output.played and time.monotonic() < deadline:
            time.sleep(0.01)
        worker.stop()
        worker.wait(1000)

        self.assertEqual(synth.requests, [("hello", "", 0)])
        self.assertEqual(output.played[0][1:], (16_000, 1, 100))

    def test_queue_keeps_latest_translation_when_full(self):
        settings = AppSettings(audio_relay_output_device_id=7, audio_relay_queue_limit=2)
        worker = VoiceRelayWorker(settings)
        worker.enqueue("first")
        worker.enqueue("second")
        worker.enqueue("latest")

        self.assertEqual(worker._queue.get_nowait(), "second")
        self.assertEqual(worker._queue.get_nowait(), "latest")
