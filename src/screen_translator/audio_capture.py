"""Audio input backends for the audio translation feature."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Protocol

TARGET_SAMPLE_RATE = 16_000


class AudioCaptureError(RuntimeError):
    pass


@dataclass(frozen=True)
class AudioDevice:
    index: int
    name: str
    kind: str
    sample_rate: int
    channels: int


@dataclass(frozen=True)
class AudioOutputDevice:
    index: int
    name: str
    sample_rate: int
    channels: int


class AudioSource(Protocol):
    sample_rate: int
    channels: int

    def read(self, timeout: float = 0.2) -> bytes: ...
    def interrupt(self) -> None: ...
    def close(self) -> None: ...


def _import_pyaudio():
    try:
        import pyaudiowpatch as pyaudio
    except ImportError as exc:  # pragma: no cover
        raise AudioCaptureError("PyAudioWPatch is not installed") from exc
    return pyaudio

def list_audio_devices() -> list[AudioDevice]:
    pyaudio = _import_pyaudio()
    result: list[AudioDevice] = []
    with pyaudio.PyAudio() as manager:
        for info in manager.get_device_info_generator():
            channels = int(info.get("maxInputChannels", 0) or 0)
            if channels <= 0:
                continue
            result.append(AudioDevice(
                int(info["index"]), str(info.get("name", "Device")),
                "global" if info.get("isLoopbackDevice", False) else "microphone",
                max(1, int(float(info.get("defaultSampleRate", 16000)))), channels,
            ))
    return result


def list_audio_output_devices() -> list[AudioOutputDevice]:
    """Return playback devices, including virtual cable inputs when present."""
    pyaudio = _import_pyaudio()
    result: list[AudioOutputDevice] = []
    with pyaudio.PyAudio() as manager:
        for info in manager.get_device_info_generator():
            channels = int(info.get("maxOutputChannels", 0) or 0)
            if channels <= 0:
                continue
            result.append(
                AudioOutputDevice(
                    int(info["index"]),
                    str(info.get("name", "Output device")),
                    max(1, int(float(info.get("defaultSampleRate", 16_000)))),
                    channels,
                )
            )
    return result


class PyAudioSource:
    def __init__(self, *, device_id: int = -1, loopback: bool = False):
        pyaudio = _import_pyaudio()
        self._manager = pyaudio.PyAudio()
        try:
            if device_id >= 0:
                info = self._manager.get_device_info_by_index(device_id)
            elif loopback:
                info = self._manager.get_default_wasapi_loopback()
            else:
                info = self._manager.get_default_input_device_info()
            self.device_id = int(info["index"])
            self.sample_rate = max(1, int(float(info.get("defaultSampleRate", 48000))))
            self.channels = max(1, int(info.get("maxInputChannels", 1)))
            self._stream = self._manager.open(
                format=pyaudio.paInt16, channels=self.channels, rate=self.sample_rate,
                input=True, input_device_index=self.device_id,
                frames_per_buffer=max(160, round(self.sample_rate / 10)),
            )
        except Exception as exc:
            self._manager.terminate()
            raise AudioCaptureError(f"Cannot open audio device: {exc}") from exc

    def read(self, timeout: float = 0.2) -> bytes:
        del timeout
        try:
            return self._stream.read(
                max(160, round(self.sample_rate / 10)),
                exception_on_overflow=False,
            )
        except Exception as exc:
            raise AudioCaptureError(f"Cannot read audio: {exc}") from exc

    def interrupt(self) -> None:
        stream = getattr(self, "_stream", None)
        if stream is None:
            return
        try:
            abort = getattr(stream, "abort_stream", None)
            if abort is not None:
                abort()
            else:
                stream.stop_stream()
        except Exception:
            pass

    def close(self) -> None:
        stream = getattr(self, "_stream", None)
        if stream is not None:
            for action in (stream.stop_stream, stream.close):
                try:
                    action()
                except Exception:
                    pass
        manager = getattr(self, "_manager", None)
        if manager is not None:
            manager.terminate()


def scale_pcm16(data: bytes, volume_percent: int) -> bytes:
    """Apply volume to little-endian signed 16-bit PCM without new dependencies."""
    volume = max(0, min(200, int(volume_percent))) / 100
    if not data or volume == 1:
        return data
    usable_length = len(data) - (len(data) % 2)
    values = struct.unpack("<%dh" % (usable_length // 2), data[:usable_length])
    scaled = [max(-32768, min(32767, round(value * volume))) for value in values]
    return struct.pack("<%dh" % len(scaled), *scaled) + data[usable_length:]


class PyAudioOutputSink:
    """Blocking PCM playback adapter for a selected Windows output device."""

    def __init__(self, device_id: int):
        if int(device_id) < 0:
            raise AudioCaptureError("请选择虚拟麦克风输出设备")
        pyaudio = _import_pyaudio()
        self._pyaudio = pyaudio
        self._manager = pyaudio.PyAudio()
        self.device_id = int(device_id)
        self._stream = None
        self._interrupted = False
        try:
            info = self._manager.get_device_info_by_index(self.device_id)
            if int(info.get("maxOutputChannels", 0) or 0) <= 0:
                raise AudioCaptureError("选择的设备不支持音频输出")
        except AudioCaptureError:
            self._manager.terminate()
            raise
        except Exception as exc:
            self._manager.terminate()
            raise AudioCaptureError(f"无法打开音频输出设备：{exc}") from exc

    def play(
        self,
        pcm: bytes,
        sample_rate: int,
        channels: int,
        *,
        volume_percent: int = 100,
    ) -> None:
        if not pcm:
            return
        if channels <= 0 or sample_rate <= 0:
            raise AudioCaptureError("无效的合成音频格式")
        self._interrupted = False
        stream = None
        try:
            stream = self._manager.open(
                format=self._pyaudio.paInt16,
                channels=int(channels),
                rate=int(sample_rate),
                output=True,
                output_device_index=self.device_id,
                frames_per_buffer=max(160, round(sample_rate / 10)),
            )
            self._stream = stream
            data = scale_pcm16(pcm, volume_percent)
            bytes_per_chunk = max(2 * channels, round(sample_rate / 10) * 2 * channels)
            for offset in range(0, len(data), bytes_per_chunk):
                if self._interrupted:
                    return
                stream.write(data[offset : offset + bytes_per_chunk])
        except Exception as exc:
            if not self._interrupted:
                raise AudioCaptureError(f"无法播放合成语音：{exc}") from exc
        finally:
            if self._stream is stream:
                self._stream = None
            if stream is not None:
                for action in (stream.stop_stream, stream.close):
                    try:
                        action()
                    except Exception:
                        pass

    def interrupt(self) -> None:
        self._interrupted = True
        stream = self._stream
        if stream is not None:
            try:
                stream.stop_stream()
            except Exception:
                pass

    def close(self) -> None:
        self.interrupt()
        manager = getattr(self, "_manager", None)
        if manager is not None:
            try:
                manager.terminate()
            except Exception:
                pass


def pcm16_to_mono(data: bytes, sample_rate: int, channels: int) -> bytes:
    """Downmix and linearly resample signed 16-bit PCM to 16 kHz mono."""
    channels, sample_rate = max(1, int(channels)), max(1, int(sample_rate))
    count = len(data) // 2 // channels
    if count <= 0:
        return b""
    values = struct.unpack("<%dh" % (count * channels), data[: count * channels * 2])
    mono = [
        int(sum(values[i:i + channels]) / channels)
        for i in range(0, len(values), channels)
    ]
    if sample_rate == TARGET_SAMPLE_RATE:
        return struct.pack("<%dh" % len(mono), *mono)
    output_count = max(1, round(len(mono) * TARGET_SAMPLE_RATE / sample_rate))
    result: list[int] = []
    scale = sample_rate / TARGET_SAMPLE_RATE
    for index in range(output_count):
        position = index * scale
        left = min(len(mono) - 1, int(position))
        right = min(len(mono) - 1, left + 1)
        result.append(max(
            -32768,
            min(32767, round(mono[left] + (mono[right] - mono[left]) * (position - left))),
        ))
    return struct.pack("<%dh" % len(result), *result)


def create_audio_source(settings) -> AudioSource:
    mode = getattr(settings, "audio_source_mode", "global")
    if mode == "microphone":
        return PyAudioSource(
            device_id=int(getattr(settings, "audio_device_id", -1)),
            loopback=False,
        )
    if mode == "process":
        from .windows_loopback import ApplicationLoopbackSource
        return ApplicationLoopbackSource(
            int(getattr(settings, "audio_process_id", 0)),
            bool(getattr(settings, "audio_include_children", True)),
        )
    return PyAudioSource(
        device_id=int(getattr(settings, "audio_device_id", -1)),
        loopback=True,
    )
