"""Audio capture -> VAD -> Alibaba Gummy translation worker."""

from __future__ import annotations

import math
import os
import threading
from array import array

from PySide6.QtCore import QThread, Signal

from .audio_capture import AudioCaptureError, create_audio_source, pcm16_to_mono
from .config import AppSettings
from .vad import SpeechSegmenter


def _language_code(value: str) -> str:
    value = (value or "auto").strip()
    return {"zh-CN": "zh", "en-US": "en", "ja-JP": "ja", "ko-KR": "ko"}.get(value, value)


class _GummyClient:
    """Lazy DashScope wrapper; dashscope is imported only when speech starts."""

    def __init__(self, settings: AppSettings, on_event, on_error, on_state):
        try:
            from dashscope.audio.asr import TranslationRecognizerCallback, TranslationRecognizerRealtime
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("DashScope SDK is not installed") from exc
        api_key = settings.dashscope_api_key.strip() or os.environ.get("DASHSCOPE_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("DashScope API key is not configured")
        parent = self

        class Callback(TranslationRecognizerCallback):
            def on_open(self) -> None:
                on_state("API connected")

            def on_close(self) -> None:
                on_state("API connection closed")

            def on_complete(self) -> None:
                on_state("API session completed")

            def on_error(self, result) -> None:
                on_error(str(result))

            def on_event(self, request_id, transcription_result, translation_result, usage) -> None:
                original = getattr(transcription_result, "text", "") if transcription_result else ""
                translated = ""
                sentence_end = bool(
                    getattr(transcription_result, "is_sentence_end", False)
                    or getattr(translation_result, "is_sentence_end", False)
                )
                if translation_result is not None:
                    try:
                        target = _language_code(settings.audio_target_language)
                        item = translation_result.get_translation(target)
                        translated = getattr(item, "text", "")
                        sentence_end = sentence_end or bool(getattr(item, "is_sentence_end", False))
                    except Exception as exc:  # noqa: BLE001
                        on_error(f"Cannot read translation result: {exc}")
                if original or translated:
                    on_event(original, translated, sentence_end, request_id, usage)

        import dashscope

        dashscope.api_key = api_key
        self._callback = Callback()
        self._recognizer = TranslationRecognizerRealtime(
            model="gummy-realtime-v1",
            format="pcm",
            sample_rate=16_000,
            source_language=_language_code(settings.audio_source_language),
            transcription_enabled=True,
            translation_enabled=True,
            translation_target_languages=[_language_code(settings.audio_target_language)],
            callback=self._callback,
        )

    def start(self) -> None:
        self._recognizer.start()

    def send(self, data: bytes) -> None:
        self._recognizer.send_audio_frame(data)

    def stop(self) -> None:
        self._recognizer.stop()


class AudioTranslationWorker(QThread):
    partial = Signal(str, str)
    completed = Signal(str, str)
    state_changed = Signal(str)
    source_changed = Signal(str)
    level_changed = Signal(int)
    speech_changed = Signal(bool)
    failed = Signal(str)

    def __init__(self, settings: AppSettings):
        super().__init__()
        self.settings = settings
        self._stop_requested = False
        self._client: _GummyClient | None = None
        self._source = None
        self._send_buffer = bytearray()
        self._api_error_message: str | None = None

    def stop(self) -> None:
        self._stop_requested = True
        self.requestInterruption()
        source = self._source
        if source is not None:
            try:
                source.interrupt()
            except (AttributeError, RuntimeError, OSError, ValueError):
                pass

    def _emit_state(self, state: str, force: bool = False) -> None:
        if force or not self._stop_requested:
            self.state_changed.emit(state)

    def _sleep_retry(self) -> None:
        for _ in range(10):
            if self._stop_requested:
                return
            self.msleep(100)

    def _event(self, original: str, translated: str, sentence_end: bool, _request_id, _usage) -> None:
        if self._stop_requested:
            return
        if sentence_end:
            self.completed.emit(original, translated)
        else:
            self.partial.emit(original, translated)

    def run(self) -> None:
        try:
            while not self._stop_requested:
                try:
                    self._run_session()
                except (AudioCaptureError, RuntimeError, ValueError) as exc:
                    if self._stop_requested:
                        break
                    message = str(exc)
                    self.failed.emit(message)
                    self._emit_state(
                        f"Audio monitor error: {self._monitor_error_summary(message)}; retrying..."
                    )
                    self._reset_client()
                    self._send_buffer.clear()
                    self._sleep_retry()
                except Exception as exc:  # noqa: BLE001
                    if self._stop_requested:
                        break
                    message = str(exc)
                    self.failed.emit(message)
                    self._emit_state(
                        f"Audio monitor error: {self._monitor_error_summary(message)}; retrying..."
                    )
                    self._reset_client()
                    self._send_buffer.clear()
                    self._sleep_retry()
        finally:
            self.level_changed.emit(0)
            self.speech_changed.emit(False)
            self._emit_state("Stopped", force=True)

    @staticmethod
    def _monitor_error_summary(message: str) -> str:
        """Keep the main-window status useful without making it excessively long."""
        message = " ".join(str(message).split())
        if "0x80070002" in message:
            return "process audio loopback unavailable (0x80070002)"
        if len(message) > 96:
            return message[:93] + "..."
        return message or "unknown error"

    def _run_session(self) -> None:
        source = None
        try:
            self._emit_state("Opening audio source...")
            source = create_audio_source(self.settings)
            self._source = source
            self.source_changed.emit(self._source_description())
            segmenter = SpeechSegmenter(
                sample_rate=16_000,
                frame_ms=20,
                mode=max(0, min(3, self.settings.audio_vad_mode)),
                start_ms=max(20, self.settings.audio_vad_start_ms),
                pre_roll_ms=max(0, self.settings.audio_vad_pre_roll_ms),
                post_roll_ms=max(20, self.settings.audio_vad_post_roll_ms),
            )
            self.speech_changed.emit(False)
            self._emit_state(
                f"Listening for speech ({segmenter.vad_name}, local gate)..."
            )
            while not self._stop_requested:
                if self._api_error_message:
                    message = self._api_error_message
                    self._api_error_message = None
                    raise RuntimeError(f"API error: {message}")
                raw = source.read(timeout=0.2)
                if not raw:
                    continue
                pcm = pcm16_to_mono(raw, source.sample_rate, source.channels)
                self.level_changed.emit(self._audio_level(pcm))
                was_active = segmenter.active
                segmenter.process(pcm, on_active_audio=self._queue_audio)
                if self._stop_requested:
                    break
                if segmenter.active and not was_active:
                    self.speech_changed.emit(True)
                    self._emit_state("Speech detected; streaming to API...")
                elif was_active and not segmenter.active:
                    self.speech_changed.emit(False)
                    self._finish_client()
                    self._emit_state(
                        f"Listening for speech ({segmenter.vad_name}, local gate)..."
                    )
            self._finish_client()
        finally:
            if source is not None:
                if self._source is source:
                    self._source = None
                source.close()

    def _handle_api_error(self, message) -> None:
        if self._stop_requested:
            return
        self._api_error_message = str(message)
        self.failed.emit(self._api_error_message)

    def _reset_client(self) -> None:
        client = self._client
        self._client = None
        if client is not None:
            try:
                client.stop()
            except Exception:
                pass

    @staticmethod
    def _stop_client_safely(client) -> None:
        try:
            client.stop()
        except Exception:
            pass

    def _finish_client(self) -> None:
        if self._stop_requested:
            self._send_buffer.clear()
        else:
            self._flush_audio_buffer(force=True)
        client = self._client
        self._client = None
        self._send_buffer.clear()
        if client is not None:
            if self._stop_requested:
                threading.Thread(
                    target=self._stop_client_safely,
                    args=(client,),
                    daemon=True,
                ).start()
            else:
                self._emit_state("Finishing API sentence...")
                client.stop()

    def _source_description(self) -> str:
        mode = getattr(self.settings, "audio_source_mode", "global")
        if mode == "microphone":
            return "Microphone"
        if mode == "process":
            name = getattr(self.settings, "audio_process_name", "")
            pid = getattr(self.settings, "audio_process_id", 0)
            return f"Process: {name or pid}"
        return "System audio (global)"

    @staticmethod
    def _audio_level(pcm: bytes) -> int:
        if not pcm:
            return 0
        samples = array("h")
        samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
        if not samples:
            return 0
        rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
        if rms <= 1:
            return 0
        db = 20 * math.log10(rms / 32768.0)
        return max(0, min(100, int((db + 60) * 100 / 60)))

    def _queue_audio(self, data: bytes) -> None:
        if self._stop_requested or not data:
            return
        self._send_buffer.extend(data)
        self._flush_audio_buffer()

    def _flush_audio_buffer(self, force: bool = False) -> None:
        packet_size = 16_000 * 2 // 10
        while self._send_buffer and (len(self._send_buffer) >= packet_size or force):
            if self._client is None:
                self._client = _GummyClient(
                    self.settings, self._event, self._handle_api_error, self._emit_state
                )
                self._client.start()
            packet = bytes(self._send_buffer[:packet_size])
            del self._send_buffer[:packet_size]
            if not self._stop_requested or force:
                self._client.send(packet)
