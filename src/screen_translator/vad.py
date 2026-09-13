"""WebRTC VAD based speech segmentation."""

from __future__ import annotations

from array import array
from collections import deque
from typing import Callable


DEFAULT_VAD_BRIDGE_MS = 320


class VADUnavailableError(RuntimeError):
    pass


class EnergyVAD:
    """Small dependency-free fallback for environments without WebRTC VAD."""

    # RMS thresholds.  The fallback is commonly used on Python 3.14, where
    # the native WebRTC VAD wheel is not available.  The old mode-2 threshold
    # (480) rejected quiet syllables from games and browser audio; keep the
    # same four sensitivity levels but lower the floor for live speech.
    _THRESHOLDS = (80, 160, 320, 640)

    def __init__(self, mode: int = 2):
        self.threshold_squared = self._THRESHOLDS[mode] ** 2

    def is_speech(self, frame: bytes, _sample_rate: int) -> bool:
        samples = array("h")
        samples.frombytes(frame[: len(frame) - (len(frame) % 2)])
        if not samples:
            return False
        mean_square = sum(sample * sample for sample in samples) / len(samples)
        return mean_square >= self.threshold_squared


class SpeechSegmenter:
    def __init__(
        self,
        *,
        sample_rate: int = 16_000,
        frame_ms: int = 20,
        mode: int = 2,
        start_ms: int = 60,
        pre_roll_ms: int = 240,
        post_roll_ms: int = 800,
        bridge_ms: int = DEFAULT_VAD_BRIDGE_MS,
        vad_engine=None,
    ):
        if sample_rate not in (8000, 16000, 32000, 48000):
            raise ValueError("Unsupported WebRTC VAD sample rate")
        if frame_ms not in (10, 20, 30):
            raise ValueError("WebRTC VAD frame length must be 10, 20, or 30 ms")
        if not 0 <= mode <= 3:
            raise ValueError("VAD mode must be between 0 and 3")
        self.vad_name = "WebRTC VAD"
        if vad_engine is None:
            try:
                import webrtcvad
                vad_engine = webrtcvad.Vad(mode)
            except ImportError:  # pragma: no cover - depends on local wheels
                vad_engine = EnergyVAD(mode)
                self.vad_name = "Energy VAD fallback"
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.frame_bytes = sample_rate * frame_ms // 1000 * 2
        self.start_frames = max(1, round(start_ms / frame_ms))
        self.pre_roll = deque(maxlen=max(0, round(pre_roll_ms / frame_ms)))
        self.post_frames = max(1, round(post_roll_ms / frame_ms))
        # Short unvoiced dips are common between words in fast speech. Keep
        # the segment open for a grace window before declaring its end.
        self.bridge_frames = max(0, round(bridge_ms / frame_ms))
        self._vad = vad_engine
        self._pending = bytearray()
        self._active = False
        self._voiced_count = 0
        self._unvoiced_count = 0
        self._segment = bytearray()

    @property
    def active(self) -> bool:
        return self._active

    def process(
        self,
        data: bytes,
        on_active_audio: Callable[[bytes], None] | None = None,
    ) -> list[bytes]:
        self._pending.extend(data)
        result: list[bytes] = []
        while len(self._pending) >= self.frame_bytes:
            frame = bytes(self._pending[:self.frame_bytes])
            del self._pending[:self.frame_bytes]
            result.extend(self._process_frame(frame, on_active_audio))
        return result

    def _process_frame(
        self,
        frame: bytes,
        on_active_audio: Callable[[bytes], None] | None = None,
    ) -> list[bytes]:
        voiced = bool(self._vad.is_speech(frame, self.sample_rate))
        if not self._active:
            self._voiced_count = self._voiced_count + 1 if voiced else 0
            if self._voiced_count >= self.start_frames:
                self._active = True
                self._unvoiced_count = 0
                pre_roll = b"".join(self.pre_roll)
                self._segment = bytearray(pre_roll + frame)
                self.pre_roll.clear()
                if on_active_audio is not None:
                    on_active_audio(pre_roll + frame)
            else:
                self.pre_roll.append(frame)
            return []

        self._segment.extend(frame)
        if on_active_audio is not None:
            on_active_audio(frame)
        self._unvoiced_count = 0 if voiced else self._unvoiced_count + 1
        if self._unvoiced_count < self.post_frames + self.bridge_frames:
            return []
        segment = bytes(self._segment)
        self._active = False
        self._voiced_count = 0
        self._unvoiced_count = 0
        self._segment.clear()
        self.pre_roll.clear()
        return [segment]

    def flush(self) -> list[bytes]:
        if not self._active:
            return []
        segment = bytes(self._segment)
        self._active = False
        self._segment.clear()
        self._pending.clear()
        self.pre_roll.clear()
        return [segment] if segment else []
