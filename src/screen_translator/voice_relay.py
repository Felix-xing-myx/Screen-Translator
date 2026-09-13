"""Sentence-level translated speech relay for virtual microphone devices."""

from __future__ import annotations

import base64
import json
import os
import queue
import subprocess
import tempfile
import threading
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from PySide6.QtCore import QThread, Signal

from .audio_capture import AudioCaptureError, PyAudioOutputSink
from .config import AppSettings


class VoiceRelayError(RuntimeError):
    """Raised when Windows speech synthesis or virtual output is unavailable."""


@dataclass(frozen=True)
class SapiVoice:
    name: str
    culture: str


@dataclass(frozen=True)
class WaveAudio:
    pcm: bytes
    sample_rate: int
    channels: int


class SpeechSynthesizer(Protocol):
    def synthesize(self, text: str, voice_name: str, rate: int) -> WaveAudio: ...

    def interrupt(self) -> None: ...


class AudioOutput(Protocol):
    def play(
        self,
        pcm: bytes,
        sample_rate: int,
        channels: int,
        *,
        volume_percent: int = 100,
    ) -> None: ...

    def interrupt(self) -> None: ...

    def close(self) -> None: ...


def _powershell_exe() -> str:
    if os.name != "nt":
        raise VoiceRelayError("语音转译输出仅支持 Windows")
    return "powershell.exe"


def _encode_powershell(script: str) -> str:
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def _utf8_base64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def list_sapi_voices() -> list[SapiVoice]:
    """Read installed SAPI voices without adding a Python COM dependency."""
    if os.name != "nt":
        return []
    script = r"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
  @($synth.GetInstalledVoices() | Where-Object { $_.Enabled } | ForEach-Object {
    [PSCustomObject]@{ name = $_.VoiceInfo.Name; culture = $_.VoiceInfo.Culture.Name }
  }) | ConvertTo-Json -Compress
} finally {
  $synth.Dispose()
}
"""
    try:
        completed = subprocess.run(
            [_powershell_exe(), "-NoProfile", "-NonInteractive", "-EncodedCommand", _encode_powershell(script)],
            capture_output=True,
            check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=8,
        )
        value = json.loads(completed.stdout.decode("utf-8-sig") or "[]")
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return []
    return [
        SapiVoice(str(item.get("name", "")), str(item.get("culture", "")))
        for item in value
        if isinstance(item, dict) and item.get("name")
    ]


class SapiWaveSynthesizer:
    """Windows SAPI adapter that renders text to a transient 16-bit WAV file."""

    def __init__(self) -> None:
        self._process: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()

    def synthesize(self, text: str, voice_name: str, rate: int) -> WaveAudio:
        text = " ".join(text.split())
        if not text:
            raise VoiceRelayError("没有可合成的译文")
        descriptor, temporary_name = tempfile.mkstemp(prefix="screen-translator-", suffix=".wav")
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        temporary_path.unlink(missing_ok=True)
        try:
            text64 = _utf8_base64(text)
            path64 = _utf8_base64(str(temporary_path))
            voice64 = _utf8_base64(voice_name.strip())
            safe_rate = max(-10, min(10, int(rate)))
            script = f"""
$text = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{text64}'))
$path = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{path64}'))
$voice = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{voice64}'))
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {{
  if ($voice) {{ $synth.SelectVoice($voice) }}
  $synth.Rate = {safe_rate}
  $synth.SetOutputToWaveFile($path)
  $synth.Speak($text)
}} finally {{
  $synth.Dispose()
}}
"""
            process = subprocess.Popen(
                [_powershell_exe(), "-NoProfile", "-NonInteractive", "-EncodedCommand", _encode_powershell(script)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            with self._lock:
                self._process = process
            _stdout, stderr = process.communicate()
            with self._lock:
                if self._process is process:
                    self._process = None
            if process.returncode != 0:
                detail = stderr.decode("utf-8", errors="replace").strip()
                raise VoiceRelayError(f"Windows 语音合成失败：{detail or process.returncode}")
            with wave.open(str(temporary_path), "rb") as wav:
                if wav.getcomptype() != "NONE" or wav.getsampwidth() != 2:
                    raise VoiceRelayError("Windows 语音合成未返回 16 位 PCM 音频")
                return WaveAudio(
                    wav.readframes(wav.getnframes()),
                    wav.getframerate(),
                    wav.getnchannels(),
                )
        except OSError as exc:
            raise VoiceRelayError(f"无法调用 Windows 语音合成：{exc}") from exc
        finally:
            temporary_path.unlink(missing_ok=True)

    def interrupt(self) -> None:
        with self._lock:
            process = self._process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass


class VoiceRelayWorker(QThread):
    """Queue completed translations and play them to one virtual output device.

    The module presents a deliberately small interface: ``start()``,
    ``enqueue(text)`` and ``stop()``. Queue bounding, SAPI invocation and
    output interruption remain local to the implementation.
    """

    state_changed = Signal(str)
    failed = Signal(str)
    speaking_changed = Signal(bool)
    queue_changed = Signal(int)

    def __init__(
        self,
        settings: AppSettings,
        *,
        synthesizer_factory: Callable[[], SpeechSynthesizer] = SapiWaveSynthesizer,
        output_factory: Callable[[int], AudioOutput] = PyAudioOutputSink,
    ) -> None:
        super().__init__()
        self.settings = settings
        self._synthesizer_factory = synthesizer_factory
        self._output_factory = output_factory
        self._queue: queue.Queue[str | None] = queue.Queue(
            maxsize=max(1, min(5, int(settings.audio_relay_queue_limit)))
        )
        self._stop_requested = threading.Event()
        self._synthesizer: SpeechSynthesizer | None = None
        self._output: AudioOutput | None = None

    def enqueue(self, translated: str) -> None:
        text = " ".join((translated or "").split())
        if self._stop_requested.is_set() or not text:
            return
        try:
            self._queue.put_nowait(text)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return
            self._queue.put_nowait(text)
            self.state_changed.emit("语音转译队列已满，已跳过较早的译文")
        self.queue_changed.emit(self._queue.qsize())

    def stop(self) -> None:
        self._stop_requested.set()
        synthesizer = self._synthesizer
        if synthesizer is not None:
            synthesizer.interrupt()
        output = self._output
        if output is not None:
            output.interrupt()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(None)
            except queue.Full:
                pass

    def run(self) -> None:
        try:
            self._synthesizer = self._synthesizer_factory()
            self._output = self._output_factory(self.settings.audio_relay_output_device_id)
            self.state_changed.emit("语音转译输出已就绪")
            while not self._stop_requested.is_set():
                try:
                    text = self._queue.get(timeout=0.2)
                except queue.Empty:
                    continue
                self.queue_changed.emit(self._queue.qsize())
                if text is None:
                    break
                self.speaking_changed.emit(True)
                try:
                    audio = self._synthesizer.synthesize(
                        text,
                        self.settings.audio_relay_voice_name,
                        self.settings.audio_relay_rate,
                    )
                    if not self._stop_requested.is_set():
                        self._output.play(
                            audio.pcm,
                            audio.sample_rate,
                            audio.channels,
                            volume_percent=self.settings.audio_relay_volume,
                        )
                except (AudioCaptureError, VoiceRelayError, OSError, ValueError) as exc:
                    if not self._stop_requested.is_set():
                        self.failed.emit(str(exc))
                finally:
                    self.speaking_changed.emit(False)
        except (AudioCaptureError, VoiceRelayError, OSError, ValueError) as exc:
            if not self._stop_requested.is_set():
                self.failed.emit(str(exc))
        finally:
            output = self._output
            self._output = None
            if output is not None:
                output.close()
            self._synthesizer = None
            self.queue_changed.emit(0)
            self.speaking_changed.emit(False)
            self.state_changed.emit("语音转译输出已停止")
