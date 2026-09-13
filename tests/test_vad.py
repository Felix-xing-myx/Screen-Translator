import unittest

from screen_translator.audio_capture import pcm16_to_mono, scale_pcm16
from screen_translator.vad import EnergyVAD, SpeechSegmenter


class FakeVAD:
    def __init__(self, voiced_frames):
        self.voiced_frames = iter(voiced_frames)

    def is_speech(self, _frame, _sample_rate):
        return next(self.voiced_frames)


class AudioTests(unittest.TestCase):
    def test_pcm_downmix_and_resample(self):
        # 48 kHz stereo, 100 ms -> 16 kHz mono, 100 ms.
        data = b"\x00\x00\x00\x00" * 4800
        result = pcm16_to_mono(data, 48000, 2)
        self.assertEqual(len(result), 1600 * 2)

    def test_pcm_volume_scaling_clamps_samples(self):
        data = b"\xff\x7f\x00\x80"
        self.assertEqual(scale_pcm16(data, 0), b"\x00\x00\x00\x00")
        self.assertEqual(scale_pcm16(data, 200), data)

    def test_segmenter_keeps_pre_and_post_roll(self):
        # 20 ms frames, one pre-roll frame, one speech frame, two post-roll frames.
        flags = [False, True, True, False, False]
        segmenter = SpeechSegmenter(
            frame_ms=20,
            start_ms=20,
            pre_roll_ms=20,
            post_roll_ms=40,
            bridge_ms=0,
            vad_engine=FakeVAD(flags),
        )
        frame = b"x" * segmenter.frame_bytes
        self.assertEqual(segmenter.process(frame), [])
        self.assertEqual(segmenter.process(frame * 3), [])
        result = segmenter.process(frame)
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]), segmenter.frame_bytes * 5)


    def test_energy_vad_fallback_detects_signal(self):
        vad = EnergyVAD(mode=2)
        silence = b"\x00\x00" * 320
        signal = b"\x00\x10" * 320
        self.assertFalse(vad.is_speech(silence, 16000))
        self.assertTrue(vad.is_speech(signal, 16000))

    def test_energy_vad_mode_two_keeps_moderate_audio(self):
        vad = EnergyVAD(mode=2)
        moderate_signal = b"\x90\x01" * 320  # RMS 400, below the old 480 floor.
        self.assertTrue(vad.is_speech(moderate_signal, 16000))

    def test_segmenter_streams_active_audio_with_callback(self):
        flags = [False, True, True, False, False]
        segmenter = SpeechSegmenter(
            frame_ms=20,
            start_ms=20,
            pre_roll_ms=20,
            post_roll_ms=40,
            bridge_ms=0,
            vad_engine=FakeVAD(flags),
        )
        frame = b"x" * segmenter.frame_bytes
        streamed = []
        segmenter.process(frame, streamed.append)
        segmenter.process(frame * 4, streamed.append)
        self.assertEqual(b"".join(streamed), frame * 5)

    def test_bridge_window_keeps_fast_speech_in_one_segment(self):
        # Short pauses between words must not split one fast utterance.
        flags = [True, False, False, True, False, False, False, False]
        segmenter = SpeechSegmenter(
            frame_ms=20,
            start_ms=20,
            pre_roll_ms=0,
            post_roll_ms=40,
            bridge_ms=40,
            vad_engine=FakeVAD(flags),
        )
        frame = b"x" * segmenter.frame_bytes

        self.assertEqual(segmenter.process(frame * 7), [])
        result = segmenter.process(frame)

        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]), len(frame) * len(flags))

if __name__ == "__main__":
    unittest.main()
