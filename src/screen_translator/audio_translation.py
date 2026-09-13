"""Audio capture -> local VAD -> Alibaba realtime translation worker."""

from __future__ import annotations

import math
import os
import threading
import base64
import json
import time
from array import array
from collections import deque
from dataclasses import dataclass
from urllib.parse import quote

from PySide6.QtCore import QThread, Signal

from .audio_capture import AudioCaptureError, create_audio_source, pcm16_to_mono
from .config import AppSettings
from .performance import PerformanceStats
from .vad import DEFAULT_VAD_BRIDGE_MS, SpeechSegmenter


def _language_code(value: str) -> str:
    value = (value or "auto").strip()
    return {"zh-CN": "zh", "en-US": "en", "ja-JP": "ja", "ko-KR": "ko"}.get(value, value)


AUDIO_TRANSLATION_MODEL_OPTIONS = (
    (
        "qwen3.5-livetranslate-flash-realtime",
        "Qwen3.5 LiveTranslate（推荐）",
    ),
    (
        "qwen3-livetranslate-flash-realtime",
        "Qwen3 LiveTranslate（旧版）",
    ),
    ("gummy-realtime-v1", "Gummy（计划下线，仅兼容）"),
    ("custom", "自定义模型"),
)


def selected_audio_translation_model(settings: AppSettings) -> str:
    """Resolve the model ID used by the provider adapter."""
    if settings.audio_translation_model == "custom":
        custom_id = settings.audio_custom_translation_model_id.strip()
        if custom_id:
            return custom_id
        return "qwen3.5-livetranslate-flash-realtime"
    return settings.audio_translation_model


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
        self._sentence_index = 0
        self._sentence_original_final = False
        self._sentence_translation_final = False

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
                original_final = bool(
                    getattr(transcription_result, "is_sentence_end", False)
                )
                translation_final = bool(
                    getattr(translation_result, "is_sentence_end", False)
                )
                if translation_result is not None:
                    try:
                        target = _language_code(settings.audio_target_language)
                        item = translation_result.get_translation(target)
                        translated = getattr(item, "text", "")
                        item_final = bool(getattr(item, "is_sentence_end", False))
                        translation_final = translation_final or item_final
                        sentence_end = sentence_end or item_final
                    except Exception as exc:  # noqa: BLE001
                        on_error(f"Cannot read translation result: {exc}")
                if original or translated:
                    # Gummy keeps one request ID for a continuous session.
                    # Add a local sentence ordinal so the worker cannot join
                    # the tail of one sentence to the next after an unusual
                    # partial/final event sequence.
                    sentence_key = f"{request_id or 'gummy'}:{parent._sentence_index}"
                    final_side = ""
                    if original_final and translation_final:
                        final_side = "both"
                    elif original_final:
                        final_side = "original"
                    elif translation_final:
                        final_side = "translation"
                    on_event(
                        original,
                        translated,
                        sentence_end,
                        sentence_key,
                        usage,
                        final_side,
                    )
                    parent._sentence_original_final |= original_final
                    parent._sentence_translation_final |= translation_final
                    if (
                        parent._sentence_original_final
                        and parent._sentence_translation_final
                    ):
                        parent._sentence_index += 1
                        parent._sentence_original_final = False
                        parent._sentence_translation_final = False

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

    def finish_segment(self) -> None:
        """Keep the recognizer alive; it reports sentence boundaries itself."""
        return

    def stop(self) -> None:
        self._recognizer.stop()


class _RawQwenRealtimeConversation:
    """Small, explicit WebSocket adapter for the Qwen LiveTranslate protocol.

    The DashScope SDK exposes ``commit()`` on the same conversation object as
    server-VAD mode.  Keeping the transport here makes it impossible for the
    audio workflow to accidentally send a Manual-mode event while using
    server VAD.  It also keeps the wire protocol visible and testable.
    """

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        workspace: str,
        on_open,
        on_close,
        on_event,
        on_error,
    ) -> None:
        try:
            import websocket
        except ImportError as exc:  # pragma: no cover - supplied by DashScope
            raise RuntimeError("WebSocket 客户端依赖未安装") from exc

        self._websocket = websocket
        self._model = model
        self._api_key = api_key
        self._workspace = workspace
        self._on_open = on_open
        self._on_close = on_close
        self._on_event = on_event
        self._on_error = on_error
        self._socket = None
        self._thread = None
        self._send_lock = threading.Lock()
        self._connected = threading.Event()
        self._finished = threading.Event()
        self._closed = False
        self._finishing = False

    @property
    def url(self) -> str:
        model = quote(self._model, safe="")
        if self._workspace:
            return (
                f"wss://{self._workspace}.cn-beijing.maas.aliyuncs.com/"
                f"api-ws/v1/realtime?model={model}"
            )
        return f"wss://dashscope.aliyuncs.com/api-ws/v1/realtime?model={model}"

    def connect(self, timeout: float = 5.0) -> None:
        self._closed = False
        self._finishing = False
        self._finished.clear()
        self._connected.clear()
        headers = [f"Authorization: Bearer {self._api_key}"]
        self._socket = self._websocket.WebSocketApp(
            self.url,
            header=headers,
            on_open=self._handle_open,
            on_message=self._handle_message,
            on_error=self._handle_error,
            on_close=self._handle_close,
        )
        self._thread = threading.Thread(
            target=self._socket.run_forever,
            name="qwen-realtime-websocket",
            daemon=True,
        )
        self._thread.start()
        deadline = time.monotonic() + max(0.1, timeout)
        while not self._connected.wait(timeout=0.05):
            if self._closed:
                raise ConnectionError("WebSocket connection closed while connecting")
            if time.monotonic() >= deadline:
                self.close()
                raise TimeoutError("WebSocket connection could not be established")

    def _handle_open(self, _socket) -> None:
        self._connected.set()
        self._on_open()

    def _handle_message(self, _socket, message) -> None:
        if not isinstance(message, str):
            return
        try:
            response = json.loads(message)
        except (TypeError, ValueError) as exc:
            self._on_error(f"无法解析阿里云实时事件：{exc}")
            return
        if not isinstance(response, dict):
            return
        if response.get("type") == "session.finished":
            self._finished.set()
        self._on_event(response)

    def _handle_error(self, _socket, error) -> None:
        if not self._closed:
            self._on_error(str(error))

    def _handle_close(self, _socket, code, message) -> None:
        self._connected.clear()
        self._finished.set()
        self._on_close(code, message)

    def _send_event(self, event_type: str, **payload) -> None:
        with self._send_lock:
            socket = self._socket
            if (
                self._closed
                or socket is None
                or socket.sock is None
                or not socket.sock.connected
            ):
                raise ConnectionError(
                    "WebSocket connection is not established or has been closed"
                )
            event = {
                "event_id": f"event_{time.time_ns():x}",
                "type": event_type,
                **payload,
            }
            socket.send(json.dumps(event, ensure_ascii=False))

    def update_session(self, session: dict) -> None:
        self._send_event("session.update", session=session)

    def append_audio(self, data: bytes) -> None:
        self._send_event(
            "input_audio_buffer.append",
            audio=base64.b64encode(data).decode("ascii"),
        )

    def finish(self, timeout: float = 5.0) -> None:
        if self._closed or not self._connected.is_set():
            return
        self._finished.clear()
        self._finishing = True
        self._send_event("session.finish")
        if not self._finished.wait(timeout=max(0.1, timeout)):
            raise TimeoutError("Session end timeout")

    def close(self) -> None:
        self._closed = True
        self._connected.clear()
        socket = self._socket
        if socket is not None:
            try:
                socket.close()
            except Exception:
                pass


@dataclass
class _QwenSegmentState:
    segment_key: str = ""
    input_item_id: str = ""
    translation_item_id: str = ""
    response_id: str = ""
    original: str = ""
    translated: str = ""
    original_completed: bool = False
    translation_completed: bool = False
    response_completed: bool = False
    emitted: bool = False
    local_finished: bool = False


@dataclass
class _PendingTranslationPair:
    """Provider events accumulated until both sides of a result are ready."""

    original: str = ""
    translated: str = ""
    original_final: bool = False
    translated_final: bool = False


@dataclass
class _ReplayAudioSegment:
    """Audio that may need to be replayed after a broken API connection."""

    data: bytes
    segment_key: str = ""
    response_id: str = ""


class _QwenLiveTranslateClient:
    """Explicit WebSocket adapter for one Qwen LiveTranslate session."""

    def __init__(self, settings: AppSettings, on_event, on_error, on_state):
        api_key = settings.dashscope_api_key.strip() or os.environ.get(
            "DASHSCOPE_API_KEY", ""
        ).strip()
        if not api_key:
            raise RuntimeError("DashScope API key is not configured")

        self._on_event = on_event
        self._on_error = on_error
        self._on_state = on_state
        self.__settings = settings
        self._segments = deque()
        self._segments_by_item: dict[str, _QwenSegmentState] = {}
        self._segments_by_response: dict[str, _QwenSegmentState] = {}
        self._state_lock = threading.RLock()
        self._connected = threading.Event()
        self._session_ready = threading.Event()
        self._segment_counter = 0
        self._session_error = ""
        self._closed = False
        self._closing = False
        # The local VAD is the upload gate.  Qwen remains in its continuous
        # server-VAD mode so the service owns the protocol-level turn
        # boundary.  This is important for a long-running session: manually
        # committing a buffer can race the service's own turn state and close
        # the WebSocket.  Only speech plus the local post-roll is uploaded.
        workspace = settings.dashscope_workspace_id.strip()
        self._conversation = _RawQwenRealtimeConversation(
            model=selected_audio_translation_model(settings),
            api_key=api_key,
            workspace=workspace or None,
            on_open=self._connected.set,
            on_close=self._on_socket_close,
            on_event=self._handle_event,
            on_error=self._on_error,
        )

    def _on_socket_close(self, _code, _message) -> None:
        self._connected.clear()
        self._session_ready.clear()
        if not self._closed and not self._closing:
            detail = ""
            if _code is not None or _message:
                detail = f" (code={_code}, {_message or 'no reason'})"
            self._on_error(f"API connection closed{detail}")

    def start(self) -> None:
        with self._state_lock:
            self._segments.clear()
            self._segments_by_item.clear()
            self._segments_by_response.clear()
            self._segment_counter = 0
            self._session_error = ""
        self._session_ready.clear()
        self._conversation.connect()
        source_language = _language_code(self._settings.audio_source_language)
        target_language = _language_code(self._settings.audio_target_language)
        transcription = {"model": "qwen3-asr-flash-realtime"}
        if source_language != "auto":
            transcription["language"] = source_language
        self._conversation.update_session(
            {
                "modalities": ["text"],
                "sample_rate": 16_000,
                "input_audio_format": "pcm",
                "input_audio_transcription": transcription,
                "translation": {"language": target_language},
                # Server VAD mode owns commit and response creation.  The
                # client sends append events only; Manual-mode commit is
                # intentionally impossible in this adapter.
                "turn_detection": {
                    "type": "server_vad",
                    "prefix_padding_ms": max(
                        0, min(300, int(self._settings.audio_vad_pre_roll_ms))
                    ),
                    "silence_duration_ms": max(
                        200,
                        min(
                            6000,
                            int(self._settings.audio_vad_post_roll_ms)
                            + DEFAULT_VAD_BRIDGE_MS,
                        ),
                    ),
                    "create_response": True,
                    "interrupt_response": False,
                },
            }
        )
        # Keep the wait interruptible: stopping the application while the
        # provider is still acknowledging session.update must not leave the
        # worker blocked for the full timeout.
        for _ in range(50):
            if self._session_ready.wait(timeout=0.1):
                return
            if self._session_error:
                raise RuntimeError(self._session_error)
            if self._closed or not self._connected.is_set():
                raise ConnectionError(
                    "WebSocket closed before the audio translation session was ready"
                )
        raise TimeoutError("Audio translation session.update was not acknowledged")

    @property
    def _settings(self) -> AppSettings:
        return self.__settings

    def send(self, data: bytes) -> None:
        if self._closed or not data:
            return
        # Do not let the capture loop race a socket close while a session is
        # being acknowledged or restarted.
        if not self._connected.wait(timeout=1.0):
            raise ConnectionError(
                "WebSocket connection is not ready; audio packet was not sent"
            )
        if self._closed or not self._connected.is_set():
            raise ConnectionError(
                "WebSocket connection is not established or has been closed"
            )
        with self._state_lock:
            if not self._segments or self._segments[-1].local_finished:
                self._segment_counter = getattr(self, "_segment_counter", 0) + 1
                self._segments.append(
                    _QwenSegmentState(
                        segment_key=f"qwen-segment-{self._segment_counter}"
                    )
                )
        try:
            self._conversation.append_audio(data)
        except Exception:
            # Preserve the packet in the worker's send buffer.  The worker
            # treats this as a transport failure and replays the unfinished
            # local VAD segments after reconnecting.
            self._connected.clear()
            raise

    def active_segment_key(self) -> str:
        with self._state_lock:
            if not self._segments:
                return ""
            return self._segments[-1].segment_key

    def stop(self) -> None:
        if self._closed or self._closing:
            return
        self._closing = True
        connected = self._connected.is_set()
        self._connected.clear()
        if not connected:
            try:
                self._conversation.close()
            except Exception:
                pass
            self._closed = True
            self._closing = False
            return
        try:
            self._conversation.finish(timeout=5)
        except Exception as exc:  # noqa: BLE001 - shutdown must remain best effort
            self._on_error(str(exc))
        finally:
            self._closed = True
            self._closing = False
            with self._state_lock:
                self._segments.clear()
                self._segments_by_item.clear()
                self._segments_by_response.clear()
                self._segment_counter = 0
            try:
                self._conversation.close()
            except Exception:
                pass

    def abort(self) -> None:
        """Close a broken transport without trying to send session.finish."""
        if self._closed:
            return
        self._closing = False
        self._closed = True
        self._connected.clear()
        with self._state_lock:
            self._segments.clear()
            self._segments_by_item.clear()
            self._segments_by_response.clear()
            self._segment_counter = 0
        try:
            self._conversation.close()
        except Exception:
            pass

    def finish_segment(self) -> None:
        """Mark a local segment while leaving turn closure to server VAD."""
        if self._closed:
            return
        with self._state_lock:
            if self._segments:
                self._segments[-1].local_finished = True

    def _handle_event(self, response) -> None:
        if self._closed or not isinstance(response, dict):
            return
        with self._state_lock:
            self._handle_event_locked(response)

    def _handle_event_locked(self, response: dict) -> None:
        if not isinstance(response, dict):
            return
        event_type = response.get("type", "")
        if event_type == "error":
            error = response.get("error") or {}
            if isinstance(error, dict):
                self._session_error = str(error.get("message", str(error)))
            else:
                self._session_error = str(error)
            self._on_error(self._session_error)
            return
        if event_type == "session.updated":
            # The socket can be writable before the server has applied the
            # translation/VAD configuration.  Do not send the first audio
            # packet until this acknowledgement has arrived.
            self._session_ready.set()
            return
        state = self._state_for_event(event_type, response)
        if state is None:
            return
        if event_type in {
            "session.created",
            "session.updated",
            "input_audio_buffer.speech_started",
            "input_audio_buffer.speech_stopped",
            "conversation.item.created",
            "response.created",
            "response.output_item.added",
        }:
            return
        if event_type in {
            "conversation.item.input_audio_transcription.text",
            "conversation.item.input_audio_transcription.delta",
        }:
            if state.emitted:
                return
            if event_type.endswith(".delta"):
                state.original = (
                    state.original + str(response.get("delta", ""))
                ).strip()
            else:
                state.original = (
                    str(response.get("text", ""))
                    + str(response.get("stash", ""))
                ).strip()
            self._emit_partial(state)
        elif event_type == "conversation.item.input_audio_transcription.completed":
            if not state.emitted:
                final_original = str(response.get("transcript", "")).strip()
                # A late/empty final event should not erase useful text that
                # was already streamed in an earlier recognition event.
                if final_original:
                    state.original = final_original
                state.original_completed = True
                self._emit_partial(state, final_side="original")
                self._maybe_emit_completed(state)
        elif event_type in {
            "response.text.text",
            "response.audio_transcript.text",
            "response.text.delta",
            "response.audio_transcript.delta",
        }:
            if state.emitted:
                return
            if event_type.endswith(".delta"):
                state.translated = (
                    state.translated + str(response.get("delta", ""))
                ).strip()
            else:
                state.translated = (
                    str(response.get("text", ""))
                    + str(response.get("stash", ""))
                ).strip()
            self._emit_partial(state)
        elif event_type in {
            "response.text.done",
            "response.audio_transcript.done",
        }:
            if not state.emitted:
                final_translation = str(
                    response.get("text") or response.get("transcript") or ""
                ).strip()
                if final_translation:
                    state.translated = final_translation
                state.translation_completed = True
                self._emit_partial(state, final_side="translation")
                self._maybe_emit_completed(state)
        elif event_type in {
            "response.content_part.done",
            "response.output_item.done",
        }:
            # Some SDK/service combinations include the final text in the
            # enclosing content/output event as well as (or just before) the
            # modality-specific done event.  Keep it as a fallback; the
            # response.done event still closes the segment.
            part = response.get("part") or {}
            item = response.get("item") or {}
            content = item.get("content") or []
            candidates = [part]
            if isinstance(content, dict):
                candidates.append(content)
            else:
                candidates.extend(content)
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                final_translation = str(
                    candidate.get("text") or candidate.get("transcript") or ""
                ).strip()
                if final_translation:
                    state.translated = final_translation
                    self._emit_partial(state)
                    break
        elif event_type == "response.done":
            self._extract_response_done(response, state)
            state.translation_completed = True
            state.response_completed = True
            self._maybe_emit_completed(state)
            self._retire_completed_segments()

    def _event_state(self) -> _QwenSegmentState | None:
        self._retire_completed_segments()
        return self._segments[0] if self._segments else None

    def _state_for_event(
        self, event_type: str, response: dict
    ) -> _QwenSegmentState | None:
        item_id = str(response.get("item_id") or "")
        response_body = response.get("response") or {}
        response_id = str(
            response.get("response_id") or response_body.get("id") or ""
        )
        state = (
            self._segments_by_item.get(item_id)
            if item_id
            else None
        )
        if state is None and response_id:
            state = self._segments_by_response.get(response_id)

        if event_type in {"session.created", "session.updated"}:
            return None

        if event_type == "conversation.item.created":
            previous_item_id = str(response.get("previous_item_id") or "")
            item = response.get("item") or {}
            item_id = str(item.get("id") or "")
            role = str(item.get("role") or "").lower()
            # The item-created event can race the transcription event.  If
            # the item ID was already learned from a transcription/response
            # event, always keep that binding instead of selecting the next
            # segment heuristically.
            state = self._segments_by_item.get(item_id) if item_id else None
            if state is not None:
                pass
            elif previous_item_id:
                state = self._segments_by_item.get(previous_item_id)
                if state is None:
                    state = self._first_unbound_translation()
            elif role != "assistant":
                # A server-VAD input item has no previous_item_id.  Do not
                # use the first response state here: the next input item can
                # be created while the previous translation is still running.
                state = self._first_unbound_input()
            else:
                state = self._first_unbound_translation()
            if state is not None and item_id:
                self._bind_item(
                    state,
                    item_id,
                    translation=bool(previous_item_id or role == "assistant"),
                )
            return state

        if event_type in {
            "input_audio_buffer.speech_started",
            "input_audio_buffer.speech_stopped",
        }:
            state = self._first_unbound_segment(
                prefer_active=event_type == "input_audio_buffer.speech_started"
            )
            if state is not None and item_id:
                self._bind_item(state, item_id, translation=False)
            return state

        if event_type == "response.created":
            state = self._first_unbound_segment(require_no_response=True)
            if state is not None and response_id:
                self._bind_response(state, response_id)
            return state

        if event_type == "response.output_item.added":
            state = self._segments_by_response.get(response_id)
            if state is None:
                state = self._first_unbound_translation()
            item = response.get("item") or {}
            if state is not None and item.get("id"):
                self._bind_item(state, str(item["id"]), translation=True)
            return state

        if event_type.startswith("conversation.item.input_audio_transcription"):
            # ASR completion may arrive after response.done.  In that case the
            # response has already been marked complete, so the generic
            # "active response" lookup must not be used: it would skip the
            # correct state and attach the original text to the next segment.
            if state is None:
                state = self._first_pending_original()
            if state is not None and item_id:
                self._bind_item(state, item_id, translation=False)
            return state

        if state is None:
            state = self._first_unbound_segment()
        if state is None:
            return self._event_state()
        if event_type.startswith("response"):
            if item_id:
                self._bind_item(state, item_id, translation=True)
            if response_id:
                self._bind_response(state, response_id)
        return state

    def _first_pending_original(self) -> _QwenSegmentState | None:
        self._retire_completed_segments()
        for state in self._segments:
            if not state.original_completed and not state.emitted:
                return state
        return None

    def _first_unbound_input(self) -> _QwenSegmentState | None:
        self._retire_completed_segments()
        for state in self._segments:
            if (
                not state.input_item_id
                and not state.original_completed
                and not state.emitted
            ):
                return state
        return None

    def _first_unbound_translation(self) -> _QwenSegmentState | None:
        self._retire_completed_segments()
        for state in self._segments:
            if (
                not state.translation_item_id
                and not state.translation_completed
                and not state.emitted
            ):
                return state
        return None

    def _first_unbound_segment(
        self, *, prefer_active: bool = False, require_no_response: bool = False
    ) -> _QwenSegmentState | None:
        self._retire_completed_segments()
        if prefer_active:
            for state in reversed(self._segments):
                if (
                    not state.response_completed
                    and not state.local_finished
                    and (not require_no_response or not state.response_id)
                ):
                    return state
        for state in self._segments:
            if (
                not state.response_completed
                and not state.emitted
                and (not require_no_response or not state.response_id)
            ):
                return state
        if require_no_response:
            return None
        return self._segments[-1] if self._segments else None

    def _bind_item(
        self, state: _QwenSegmentState, item_id: str, *, translation: bool
    ) -> None:
        if translation:
            state.translation_item_id = item_id
        else:
            state.input_item_id = item_id
        self._segments_by_item[item_id] = state

    def _bind_response(self, state: _QwenSegmentState, response_id: str) -> None:
        state.response_id = response_id
        self._segments_by_response[response_id] = state

    def _retire_completed_segments(self) -> None:
        while (
            self._segments
            and self._segments[0].response_completed
            and self._segments[0].emitted
        ):
            state = self._segments.popleft()
            for item_id in (state.input_item_id, state.translation_item_id):
                if item_id and self._segments_by_item.get(item_id) is state:
                    self._segments_by_item.pop(item_id, None)
            if state.response_id and self._segments_by_response.get(state.response_id) is state:
                self._segments_by_response.pop(state.response_id, None)

    def _extract_response_done(
        self, response: dict, state: _QwenSegmentState
    ) -> None:
        response_body = response.get("response") or {}
        output = response_body.get("output") or []
        if isinstance(output, dict):
            output = [output]
        for item in output:
            for content in item.get("content", []) or []:
                text = content.get("text") or content.get("transcript")
                if text:
                    state.translated = str(text).strip()

    def _emit_partial(self, state: _QwenSegmentState, *, final_side: str = "") -> None:
        if state.original or state.translated:
            self._on_event(
                state.original,
                state.translated,
                final_side == "both",
                state.segment_key,
                None,
                final_side,
            )

    def _maybe_emit_completed(self, state: _QwenSegmentState) -> None:
        # ASR and translation are independent streams. Wait for both final
        # events so history never stores a completed translation with a
        # placeholder original text while the ASR result is still in flight.
        if (
            state.original_completed
            and state.translation_completed
            and not state.emitted
        ):
            state.emitted = True
            if state.original or state.translated:
                self._on_event(
                    state.original,
                    state.translated,
                    True,
                    state.segment_key,
                    None,
                    "both",
                )

class AudioTranslationWorker(QThread):
    partial = Signal(str, str)
    completed = Signal(str, str)
    state_changed = Signal(str)
    source_changed = Signal(str)
    level_changed = Signal(int)
    speech_changed = Signal(bool)
    failed = Signal(str)

    def __init__(
        self, settings: AppSettings, stats: PerformanceStats | None = None
    ):
        super().__init__()
        self.settings = settings
        self.stats = stats
        self._stop_requested = False
        self._client: _GummyClient | None = None
        self._source = None
        self._send_buffer = bytearray()
        self._audio_tracking_lock = threading.RLock()
        self._current_audio_segment = bytearray()
        self._current_audio_segment_key = ""
        self._replay_audio_segments = deque()
        self._replay_work_queue = deque()
        self._translation_pair_lock = threading.RLock()
        self._pending_translation_pairs: dict[str, _PendingTranslationPair] = {}
        self._completed_result_keys: set[str] = set()
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
        client = self._client
        if client is not None:
            # The worker may currently be inside client.start(), before the
            # capture source has returned control.  Abort it on a daemon
            # thread so the UI stop action remains responsive.
            threading.Thread(
                target=self._abort_client_safely,
                args=(client,),
                daemon=True,
            ).start()

    def _emit_state(self, state: str, force: bool = False) -> None:
        if force or not self._stop_requested:
            self.state_changed.emit(state)

    def _sleep_retry(self) -> None:
        for _ in range(10):
            if self._stop_requested:
                return
            self.msleep(100)

    def _event(
        self,
        original: str,
        translated: str,
        sentence_end: bool,
        _request_id,
        _usage,
        _final_side: str = "",
    ) -> None:
        if self._stop_requested:
            return
        request_id = str(_request_id or "").strip()
        key = request_id or "__unkeyed__"
        with self._translation_pair_lock:
            # A provider may repeat a final event after response.done, or a
            # replayed segment may arrive after the original final event was
            # already accepted.  Stable provider/local segment keys make this
            # safe to discard without suppressing a different sentence.
            if key != "__unkeyed__" and key in self._completed_result_keys:
                return
            # The original transcription and translated text are independent
            # streams.  Keep the last non-empty value from each stream and
            # complete the pair only after a final marker has been observed.
            # This also handles providers that deliver the final source text
            # after the final translation event.
            if key == "__unkeyed__":
                candidates = [
                    (candidate_key, candidate)
                    for candidate_key, candidate in self._pending_translation_pairs.items()
                    if candidate_key != "__unkeyed__"
                    and not candidate.original
                    and not candidate.original_final
                    and not candidate.translated_final
                ]
                if len(candidates) == 1:
                    key = candidates[0][0]
            if key != "__unkeyed__":
                unkeyed = self._pending_translation_pairs.pop("__unkeyed__", None)
                pair = self._pending_translation_pairs.setdefault(
                    key, _PendingTranslationPair()
                )
                if unkeyed is not None:
                    pair.original = pair.original or unkeyed.original
                    pair.translated = pair.translated or unkeyed.translated
                    pair.original_final = pair.original_final or unkeyed.original_final
                    pair.translated_final = (
                        pair.translated_final or unkeyed.translated_final
                    )
            else:
                pair = self._pending_translation_pairs.setdefault(
                    key, _PendingTranslationPair()
                )
            if str(original).strip():
                pair.original = str(original).strip()
            if str(translated).strip():
                pair.translated = str(translated).strip()
            final_side = str(_final_side or "").strip().lower()
            if final_side == "original":
                pair.original_final = True
            elif final_side == "translation":
                pair.translated_final = True
            elif final_side == "both" or sentence_end:
                # Backward-compatible fallback for providers that expose one
                # sentence-end flag instead of identifying the side.
                pair.original_final = True
                pair.translated_final = True
            current_original = pair.original
            current_translated = pair.translated
            complete = bool(
                pair.original_final
                and pair.translated_final
                and current_original
                and current_translated
            )
            if complete:
                self._pending_translation_pairs.pop(key, None)
                if key != "__unkeyed__":
                    self._completed_result_keys.add(key)

        if complete:
            self._mark_audio_segment_completed(request_id)
            self.completed.emit(current_original, current_translated)
        elif current_original or current_translated:
            self.partial.emit(current_original, current_translated)

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
                    if not self._is_connection_error(message):
                        self._send_buffer.clear()
                        self._clear_audio_tracking()
                    else:
                        self._restore_audio_for_retry()
                    self._clear_translation_pairs()
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
                    if not self._is_connection_error(message):
                        self._send_buffer.clear()
                        self._clear_audio_tracking()
                    else:
                        self._restore_audio_for_retry()
                    self._clear_translation_pairs()
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

    @staticmethod
    def _is_connection_error(message: str) -> bool:
        lowered = str(message).lower()
        return any(
            marker in lowered
            for marker in (
                "websocket",
                "connection",
                "socket",
                "timed out",
                "timeout",
            )
        )

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
                bridge_ms=DEFAULT_VAD_BRIDGE_MS,
            )
            self.speech_changed.emit(False)
            self._emit_state(
                f"Listening for speech ({segmenter.vad_name}, local gate)..."
            )
            self._replay_pending_segments()
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
        message = str(message)
        current = self._api_error_message or ""
        # A socket-close callback often follows the more useful protocol
        # error.  Keep the first actionable message instead of replacing it
        # with the generic "connection closed" text.
        if not current or "connection closed" in current.lower():
            self._api_error_message = message

    def _reset_client(self) -> None:
        client = self._client
        self._client = None
        if client is not None:
            try:
                abort = getattr(client, "abort", None)
                if abort is not None:
                    abort()
                else:
                    client.stop()
            except Exception:
                pass

    @staticmethod
    def _stop_client_safely(client) -> None:
        try:
            client.stop()
        except Exception:
            pass

    @staticmethod
    def _abort_client_safely(client) -> None:
        try:
            abort = getattr(client, "abort", None)
            if abort is not None:
                abort()
            else:
                client.stop()
        except Exception:
            pass

    def _finish_client(self) -> None:
        if self._stop_requested:
            self._send_buffer.clear()
            self._clear_audio_tracking()
        else:
            self._flush_audio_buffer(force=True)
            self._remember_finished_audio_segment()
        client = self._client
        if client is not None:
            if self._stop_requested:
                self._client = None
                self._send_buffer.clear()
                self._clear_audio_tracking()
                threading.Thread(
                    target=self._stop_client_safely,
                    args=(client,),
                    daemon=True,
                ).start()
            elif hasattr(client, "finish_segment"):
                client.finish_segment()
                self._send_buffer.clear()
            else:
                self._client = None
                self._send_buffer.clear()
                self._clear_audio_tracking()
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
        with self._audio_tracking_lock:
            self._current_audio_segment.extend(data)
        self._send_buffer.extend(data)
        self._flush_audio_buffer()
        if not self._current_audio_segment_key:
            client = self._client
            active_key = getattr(client, "active_segment_key", None)
            if active_key is not None:
                self._current_audio_segment_key = str(active_key() or "")

    def _remember_finished_audio_segment(self) -> None:
        with self._audio_tracking_lock:
            if self._current_audio_segment:
                self._replay_audio_segments.append(
                    _ReplayAudioSegment(
                        bytes(self._current_audio_segment),
                        segment_key=self._current_audio_segment_key,
                    )
                )
                self._current_audio_segment.clear()
                self._current_audio_segment_key = ""

    def _mark_audio_segment_completed(self, segment_key: str = "") -> None:
        with self._audio_tracking_lock:
            segment_key = str(segment_key or "")
            if segment_key:
                for segment in list(self._replay_audio_segments):
                    if segment.segment_key == segment_key:
                        self._replay_audio_segments.remove(segment)
                        return
                if self._current_audio_segment_key == segment_key:
                    self._current_audio_segment.clear()
                    self._current_audio_segment_key = ""
                    return
            if self._replay_audio_segments:
                # Legacy providers do not expose a response ID.  Their
                # completion order is the only safe correlation available.
                self._replay_audio_segments.popleft()
            elif self._current_audio_segment:
                self._current_audio_segment.clear()
                self._current_audio_segment_key = ""

    def _restore_audio_for_retry(self) -> None:
        """Requeue only audio that has not produced a final result yet."""
        with self._audio_tracking_lock:
            segments = [
                _ReplayAudioSegment(segment.data)
                for segment in self._replay_audio_segments
            ]
            if self._current_audio_segment:
                segments.append(
                    _ReplayAudioSegment(bytes(self._current_audio_segment))
                )
            self._replay_audio_segments = deque(segments)
            self._replay_work_queue.clear()
            self._current_audio_segment.clear()
            self._current_audio_segment_key = ""
        self._send_buffer.clear()
        # Replay is intentionally not put into _send_buffer.  It must pass
        # through _replay_pending_segments so each local VAD segment is
        # replayed as its own bounded audio burst.

    def _replay_pending_segments(self) -> None:
        """Resend unfinished local segments immediately after reconnecting."""
        with self._audio_tracking_lock:
            self._replay_work_queue = deque(self._replay_audio_segments)

        while self._replay_work_queue and not self._stop_requested:
            segment = self._replay_work_queue[0]
            self._send_buffer = bytearray(segment.data)
            self._flush_audio_buffer(force=True)
            client = self._client
            if client is None:
                raise RuntimeError("Audio replay client was not created")
            if hasattr(client, "finish_segment"):
                client.finish_segment()
            else:
                client.stop()
                self._client = None
            self._send_buffer.clear()
            active_key = getattr(client, "active_segment_key", None)
            if active_key is not None:
                segment.segment_key = str(active_key() or "")
            self._replay_work_queue.popleft()

    def _clear_audio_tracking(self) -> None:
        with self._audio_tracking_lock:
            self._current_audio_segment.clear()
            self._current_audio_segment_key = ""
            self._replay_audio_segments.clear()
            self._replay_work_queue.clear()

    def _clear_translation_pairs(self) -> None:
        with self._translation_pair_lock:
            self._pending_translation_pairs.clear()
            self._completed_result_keys.clear()

    def _flush_audio_buffer(self, force: bool = False) -> None:
        packet_size = 16_000 * 2 // 10
        while self._send_buffer and (len(self._send_buffer) >= packet_size or force):
            if self._client is None:
                client_type = (
                    _GummyClient
                    if selected_audio_translation_model(self.settings) == "gummy-realtime-v1"
                    else _QwenLiveTranslateClient
                )
                self._client = client_type(
                    self.settings,
                    self._event,
                    self._handle_api_error,
                    self._emit_state,
                )
                if self.stats is not None:
                    self.stats.record_translation()
                self._client.start()
            packet = bytes(self._send_buffer[:packet_size])
            if not self._stop_requested or force:
                self._client.send(packet)
                # Remove audio only after the WebSocket accepted it. If the
                # transport closed, the retry path can send this packet again.
                del self._send_buffer[:packet_size]
