import unittest
from collections import deque
import json
import threading
from unittest.mock import patch

from screen_translator.config import AppSettings
from screen_translator.audio_translation import (
    AudioTranslationWorker,
    _QwenLiveTranslateClient,
    _QwenSegmentState,
    _ReplayAudioSegment,
    _RawQwenRealtimeConversation,
)


class _FakeConversation:
    def __init__(self):
        self.commit_count = 0
        self.finish_count = 0
        self.audio = []

    def commit(self):
        self.commit_count += 1

    def finish(self, timeout=20):
        self.finish_count += 1

    def append_audio(self, _audio):
        self.audio.append(_audio)

    def close(self):
        pass


class _FakeRawConversation:
    instances = []

    def __init__(self, *, on_open, on_close, on_event, on_error, **kwargs):
        self.on_open = on_open
        self.on_close = on_close
        self.on_event = on_event
        self.on_error = on_error
        self.constructor_kwargs = kwargs
        self.update_session_kwargs = None
        self.events = []
        self.closed = False
        self.__class__.instances.append(self)

    def connect(self):
        self.on_open()

    def update_session(self, session):
        self.update_session_kwargs = session
        self.on_event({"type": "session.updated"})

    def append_audio(self, _audio):
        self.events.append("input_audio_buffer.append")

    def finish(self, timeout=20):
        self.events.append("session.finish")

    def close(self):
        self.closed = True


class _FakeReplayClient:
    def __init__(self):
        self.finish_count = 0

    def finish_segment(self):
        self.finish_count += 1


class _FakeWebSocketApp:
    instances = []

    def __init__(self, _url, *, header, on_open, on_message, on_error, on_close):
        self.header = header
        self.on_open = on_open
        self.on_message = on_message
        self.on_error = on_error
        self.on_close = on_close
        self.sock = self
        self.connected = False
        self.sent = []
        self.__class__.instances.append(self)

    def run_forever(self):
        self.connected = True
        self.on_open(self)

    def send(self, payload):
        self.sent.append(json.loads(payload))
        if self.sent[-1]["type"] == "session.finish":
            self.on_message(self, json.dumps({"type": "session.finished"}))

    def close(self):
        self.connected = False


def _client_for_stop_test(segment_has_audio: bool):
    client = _QwenLiveTranslateClient.__new__(_QwenLiveTranslateClient)
    client._conversation = _FakeConversation()
    client._closed = False
    client._segments = deque([_QwenSegmentState()]) if segment_has_audio else deque()
    client._segments_by_item = {}
    client._segments_by_response = {}
    client._state_lock = threading.RLock()
    client._connected = threading.Event()
    client._connected.set()
    client._session_ready = threading.Event()
    client._segment_counter = 0
    client._session_error = ""
    client._closing = False
    client._on_error = lambda _message: None
    return client


class QwenLiveTranslateClientTests(unittest.TestCase):
    def test_raw_server_vad_transport_never_sends_manual_commit(self) -> None:
        import websocket

        _FakeWebSocketApp.instances.clear()
        with patch.object(websocket, "WebSocketApp", _FakeWebSocketApp):
            conversation = _RawQwenRealtimeConversation(
                model="qwen3.5-livetranslate-flash-realtime",
                api_key="test-key",
                workspace="test-workspace",
                on_open=lambda: None,
                on_close=lambda *_args: None,
                on_event=lambda _event: None,
                on_error=lambda _message: None,
            )
            conversation.connect()
            conversation.update_session({"turn_detection": {"type": "server_vad"}})
            conversation.append_audio(b"pcm")
            conversation.finish()
            conversation.close()

        events = _FakeWebSocketApp.instances[0].sent
        self.assertEqual(
            [event["type"] for event in events],
            [
                "session.update",
                "input_audio_buffer.append",
                "session.finish",
            ],
        )

    def test_start_waits_for_session_update_and_enables_server_vad(self) -> None:
        _FakeRawConversation.instances.clear()
        settings = AppSettings(dashscope_api_key="test-key")

        with patch(
            "screen_translator.audio_translation._RawQwenRealtimeConversation",
            _FakeRawConversation,
        ):
            client = _QwenLiveTranslateClient(
                settings,
                lambda *_args: None,
                lambda _message: None,
                lambda _state: None,
            )
            client.start()

        update = _FakeRawConversation.instances[0].update_session_kwargs
        self.assertEqual(update["turn_detection"]["type"], "server_vad")
        self.assertTrue(update["turn_detection"]["create_response"])
        self.assertEqual(
            update["turn_detection"]["silence_duration_ms"],
            settings.audio_vad_post_roll_ms + 320,
        )
        self.assertNotIn("input_audio_buffer.commit", update)
        self.assertNotIn("input_audio_buffer.commit", _FakeRawConversation.instances[0].events)
        self.assertTrue(client._session_ready.is_set())

    def test_session_updated_marks_translation_session_ready(self) -> None:
        client = _client_for_stop_test(segment_has_audio=False)

        client._handle_event({"type": "session.updated"})

        self.assertTrue(client._session_ready.is_set())

    def test_stop_does_not_commit_empty_audio_buffer(self) -> None:
        client = _client_for_stop_test(segment_has_audio=False)

        client.stop()

        self.assertEqual(client._conversation.commit_count, 0)
        self.assertEqual(client._conversation.finish_count, 1)

    def test_stop_ends_session_without_manual_commit(self) -> None:
        client = _client_for_stop_test(segment_has_audio=True)

        client.stop()
        client.stop()

        self.assertEqual(client._conversation.commit_count, 0)
        self.assertEqual(client._conversation.finish_count, 1)

    def test_finish_segment_keeps_qwen_session_open_without_manual_commit(self) -> None:
        client = _client_for_stop_test(segment_has_audio=True)
        state = client._segments[0]
        state.original = "source"
        state.translated = "target"
        client._on_event = lambda *_args: None
        client.finish_segment()

        self.assertFalse(client._closed)
        self.assertTrue(state.local_finished)
        self.assertEqual(client._conversation.commit_count, 0)
        self.assertEqual(client._segments[0].original, "source")
        self.assertEqual(client._segments[0].translated, "target")

    def test_finish_segment_without_audio_does_not_commit(self) -> None:
        client = _client_for_stop_test(segment_has_audio=True)
        client.finish_segment()

        self.assertEqual(client._conversation.commit_count, 0)
        self.assertTrue(client._segments[0].local_finished)

    def test_finish_empty_segment_does_not_commit(self) -> None:
        client = _client_for_stop_test(segment_has_audio=False)

        client.finish_segment()

        self.assertEqual(client._conversation.commit_count, 0)

    def test_send_does_not_write_after_socket_is_closed(self) -> None:
        client = _client_for_stop_test(segment_has_audio=False)

        client.send(b"pcm")
        self.assertEqual(len(client._conversation.audio), 1)

        client._connected.clear()
        with self.assertRaises(ConnectionError):
            client.send(b"pcm-after-close")
        self.assertEqual(len(client._conversation.audio), 1)

    def test_history_completion_waits_for_late_original(self) -> None:
        client = _client_for_stop_test(segment_has_audio=True)
        events = []
        client._on_event = lambda *args: events.append(args)

        client._handle_event({"type": "response.text.done", "text": "译文"})
        self.assertFalse(any(event[2] for event in events))

        client._handle_event(
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "transcript": "original",
            }
        )
        self.assertTrue(any(event[2] for event in events))

    def test_response_ids_keep_overlapping_segments_separate(self) -> None:
        client = _client_for_stop_test(segment_has_audio=True)
        client._segments.append(_QwenSegmentState())
        events = []
        client._on_event = lambda *args: events.append(args)

        client._handle_event(
            {"type": "response.created", "response": {"id": "resp-1"}}
        )
        client._handle_event(
            {"type": "response.created", "response": {"id": "resp-2"}}
        )
        client._handle_event(
            {
                "type": "response.text.done",
                "response_id": "resp-2",
                "item_id": "translation-2",
                "text": "t2",
            }
        )
        client._handle_event(
            {
                "type": "response.text.done",
                "response_id": "resp-1",
                "item_id": "translation-1",
                "text": "t1",
            }
        )
        client._handle_event(
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "item_id": "input-1",
                "transcript": "o1",
            }
        )
        client._handle_event(
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "item_id": "input-2",
                "transcript": "o2",
            }
        )

        completed = {(event[0], event[1]) for event in events if event[2]}
        self.assertEqual(completed, {("o1", "t1"), ("o2", "t2")})

    def test_late_original_after_response_done_stays_with_earlier_segment(self) -> None:
        client = _client_for_stop_test(segment_has_audio=True)
        client._segments.append(_QwenSegmentState())
        events = []
        client._on_event = lambda *args: events.append(args)

        client._handle_event(
            {"type": "response.created", "response": {"id": "resp-1"}}
        )
        client._handle_event(
            {"type": "response.created", "response": {"id": "resp-2"}}
        )
        client._handle_event(
            {
                "type": "response.done",
                "response_id": "resp-1",
                "response": {
                    "id": "resp-1",
                    "output": [
                        {
                            "content": [
                                {"type": "text", "text": "t1"},
                            ],
                        },
                    ],
                },
            }
        )
        client._handle_event(
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "item_id": "input-1",
                "transcript": "o1",
            }
        )

        completed = [(event[0], event[1]) for event in events if event[2]]
        self.assertEqual(completed, [("o1", "t1")])
        self.assertEqual(client._segments[0].original, "o1")
        self.assertEqual(client._segments[1].original, "")

    def test_input_items_do_not_reuse_previous_response_state(self) -> None:
        client = _client_for_stop_test(segment_has_audio=True)
        client._segments.append(_QwenSegmentState())
        events = []
        client._on_event = lambda *args: events.append(args)

        client._handle_event(
            {"type": "response.created", "response": {"id": "resp-1"}}
        )
        client._handle_event(
            {
                "type": "conversation.item.created",
                "item": {"id": "input-1", "role": "user"},
            }
        )
        client._handle_event(
            {"type": "response.created", "response": {"id": "resp-2"}}
        )
        client._handle_event(
            {
                "type": "conversation.item.created",
                "item": {"id": "input-2", "role": "user"},
            }
        )
        client._handle_event(
            {
                "type": "response.text.done",
                "response_id": "resp-1",
                "item_id": "translation-1",
                "text": "t1",
            }
        )
        client._handle_event(
            {
                "type": "response.text.done",
                "response_id": "resp-2",
                "item_id": "translation-2",
                "text": "t2",
            }
        )
        client._handle_event(
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "item_id": "input-1",
                "transcript": "o1",
            }
        )
        client._handle_event(
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "item_id": "input-2",
                "transcript": "o2",
            }
        )

        completed = {(event[0], event[1]) for event in events if event[2]}
        self.assertEqual(completed, {("o1", "t1"), ("o2", "t2")})

    def test_manual_commit_event_sequence_pairs_one_history_entry(self) -> None:
        client = _client_for_stop_test(segment_has_audio=True)
        events = []
        client._on_event = lambda *args: events.append(args)

        client._handle_event({"type": "input_audio_buffer.committed"})
        client._handle_event(
            {
                "type": "conversation.item.created",
                "item": {"id": "input-1", "role": "user"},
            }
        )
        client._handle_event(
            {"type": "response.created", "response": {"id": "resp-1"}}
        )
        client._handle_event(
            {
                "type": "conversation.item.created",
                "previous_item_id": "input-1",
                "item": {"id": "translation-1", "role": "assistant"},
            }
        )
        client._handle_event(
            {
                "type": "response.text.done",
                "response_id": "resp-1",
                "item_id": "translation-1",
                "text": "t1",
            }
        )
        client._handle_event(
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "item_id": "input-1",
                "transcript": "o1",
            }
        )
        client._handle_event(
            {
                "type": "response.done",
                "response": {"id": "resp-1", "output": []},
            }
        )

        completed = [(event[0], event[1]) for event in events if event[2]]
        self.assertEqual(completed, [("o1", "t1")])

    def test_server_vad_event_sequence_pairs_one_history_entry(self) -> None:
        client = _client_for_stop_test(segment_has_audio=True)
        events = []
        client._on_event = lambda *args: events.append(args)

        client._handle_event({"type": "input_audio_buffer.speech_stopped"})
        client._handle_event(
            {
                "type": "conversation.item.created",
                "item": {"id": "input-1", "role": "user"},
            }
        )
        client._handle_event(
            {"type": "response.created", "response": {"id": "resp-1"}}
        )
        client._handle_event(
            {
                "type": "response.output_item.added",
                "response_id": "resp-1",
                "item": {"id": "translation-1", "role": "assistant"},
            }
        )
        client._handle_event(
            {
                "type": "conversation.item.created",
                "previous_item_id": "input-1",
                "item": {"id": "translation-1", "role": "assistant"},
            }
        )
        client._handle_event(
            {
                "type": "response.text.text",
                "response_id": "resp-1",
                "item_id": "translation-1",
                "text": "t",
            }
        )
        client._handle_event(
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "item_id": "input-1",
                "transcript": "o",
            }
        )
        client._handle_event(
            {
                "type": "response.text.done",
                "response_id": "resp-1",
                "item_id": "translation-1",
                "text": "t",
            }
        )
        client._handle_event(
            {
                "type": "response.done",
                "response_id": "resp-1",
                "response": {"id": "resp-1", "output": []},
            }
        )

        completed = [(event[0], event[1]) for event in events if event[2]]
        self.assertEqual(completed, [("o", "t")])

    def test_reconnect_replays_each_unfinished_segment_separately(self) -> None:
        worker = AudioTranslationWorker.__new__(AudioTranslationWorker)
        worker._stop_requested = False
        worker._audio_tracking_lock = threading.RLock()
        worker._current_audio_segment = bytearray()
        worker._replay_audio_segments = deque(
            [_ReplayAudioSegment(b"segment-1"), _ReplayAudioSegment(b"segment-2")]
        )
        worker._replay_work_queue = deque()
        worker._send_buffer = bytearray()
        worker._client = _FakeReplayClient()
        sent_buffers = []
        worker._flush_audio_buffer = lambda force=False: sent_buffers.append(
            (bytes(worker._send_buffer), force)
        )

        worker._replay_pending_segments()

        self.assertEqual(
            sent_buffers,
            [(b"segment-1", True), (b"segment-2", True)],
        )
        self.assertEqual(worker._client.finish_count, 2)
        self.assertEqual(bytes(worker._send_buffer), b"")
        self.assertEqual(list(worker._replay_work_queue), [])


class AudioTranslationWorkerEventTests(unittest.TestCase):
    def _worker(self) -> AudioTranslationWorker:
        worker = AudioTranslationWorker(AppSettings())
        worker._replay_audio_segments = deque(
            [_ReplayAudioSegment(b"audio")]
        )
        return worker

    def test_history_pair_waits_for_late_original(self) -> None:
        worker = self._worker()
        partial = []
        completed = []
        worker.partial.connect(lambda original, translated: partial.append((original, translated)))
        worker.completed.connect(
            lambda original, translated: completed.append((original, translated))
        )

        worker._event("", "translation", True, "response-1", None)
        self.assertEqual(completed, [])
        worker._event("original", "", False, "response-1", None)

        self.assertEqual(completed, [("original", "translation")])
        self.assertTrue(partial)
        self.assertEqual(list(worker._replay_audio_segments), [])

    def test_final_translation_waits_for_final_original_side(self) -> None:
        worker = self._worker()
        completed = []
        worker.completed.connect(
            lambda original, translated: completed.append((original, translated))
        )

        worker._event(
            "",
            "partial translation",
            False,
            "segment-1",
            None,
            "translation",
        )
        self.assertEqual(completed, [])
        worker._event(
            "original",
            "final translation",
            False,
            "segment-1",
            None,
            "original",
        )

        self.assertEqual(completed, [("original", "final translation")])

    def test_duplicate_final_event_for_same_segment_is_ignored(self) -> None:
        worker = self._worker()
        completed = []
        worker.completed.connect(
            lambda original, translated: completed.append((original, translated))
        )

        worker._event(
            "original",
            "translation",
            False,
            "segment-1",
            None,
            "both",
        )
        worker._event(
            "original",
            "translation",
            False,
            "segment-1",
            None,
            "both",
        )

        self.assertEqual(completed, [("original", "translation")])

    def test_qwen_segment_key_survives_original_before_response_binding(self) -> None:
        client = _client_for_stop_test(segment_has_audio=True)
        client._segments[0].segment_key = "segment-1"
        events = []
        client._on_event = lambda *args: events.append(args)

        client._handle_event(
            {
                "type": "conversation.item.input_audio_transcription.text",
                "item_id": "input-1",
                "text": "orig",
                "stash": "inal",
            }
        )
        client._handle_event(
            {"type": "response.created", "response": {"id": "resp-1"}}
        )
        client._handle_event(
            {
                "type": "response.text.done",
                "response_id": "resp-1",
                "text": "译文",
            }
        )
        client._handle_event(
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "item_id": "input-1",
                "transcript": "original",
            }
        )

        completed = [(event[0], event[1]) for event in events if event[2]]
        self.assertEqual(completed, [("original", "译文")])

    def test_incomplete_final_event_never_creates_history_pair(self) -> None:
        worker = self._worker()
        completed = []
        worker.completed.connect(
            lambda original, translated: completed.append((original, translated))
        )

        worker._event("", "translation", True, "response-1", None)

        self.assertEqual(completed, [])
        self.assertEqual(len(worker._replay_audio_segments), 1)
