# Architecture

Screen Translator is a Windows desktop application with a src-layout Python
package. The package is installed editable during development, so imports and
runtime behaviour use the same source tree that tests inspect.

## Runtime flow

~~~text
application.py
  -> MainWindow
     -> screenshot workflow: capture -> OCR -> translator -> results
     -> monitor workflow: capture regions -> workers -> OCR -> translator -> results
     -> audio workflow: audio_capture -> VAD -> audio_translation -> audio_results
                                             -> voice_relay -> virtual audio output
~~~

## Module map

| Area | Modules | Responsibility |
| --- | --- | --- |
| Entry point | application.py, __main__.py | Create the Qt application and launch the main window |
| Configuration | config.py, models.py | Persist settings and define shared data objects |
| Capture adapters | screen_capture.py, audio_capture.py, windows_loopback.py | Connect to Windows screen, audio sources, and playback devices |
| Translation adapters | ocr.py, translator.py | Adapt Tesseract and remote translation providers |
| Workflows | capture.py, workers.py, vad.py, audio_translation.py, voice_relay.py | Coordinate capture, segmentation, retries, background work, and sentence-level translated speech output |
| Input/system | hotkeys.py | Record and register global Windows hotkeys |
| UI | ui/ | Main window, settings, overlays, result windows, and shared widgets |
| Pure helpers | text_utils.py | Text normalization and comparison without Qt or network side effects |

The UI is the external seam for user actions. Provider and device modules are
adapters behind the workflow seam, which keeps API and Windows-specific details
out of most UI code. Tests should prefer crossing a small module interface
instead of reaching into implementation details.

The Qwen LiveTranslate adapter uses an explicit WebSocket transport. In server
VAD mode it sends only `input_audio_buffer.append` events and waits for the
service to produce the translation; `input_audio_buffer.commit` is reserved for
Manual mode and is not part of the long-running audio workflow. Each local
audio segment also has a stable correlation key so streamed source recognition
and translated output cannot be paired solely by arrival order.

The local speech gate also applies a short bridge window after the configured
end-of-speech silence threshold. This keeps brief unvoiced dips inside one
fast utterance, and the server-VAD silence duration is extended by the same
window so the local and remote turn boundaries do not disagree. On Python
3.14, where the native WebRTC VAD wheel may be unavailable, the energy
fallback uses a lower calibrated RMS floor so quiet syllables are not rejected
before the bridge window can preserve them.

## Voice relay workflow

`voice_relay.py` is a deep module with a deliberately small interface:
`start()`, `enqueue(translated_text)`, and `stop()`. It accepts only completed
translations, bounds the pending queue, renders speech through Windows SAPI to a
temporary WAV, and plays that WAV through the selected Windows output device.
The temporary file is deleted immediately after playback data is read; no audio
recording is retained by the application.

For a virtual microphone workflow, Screen Translator writes to a virtual cable's
playback endpoint (for VB-CABLE, `CABLE Input`), while the game selects its
recording endpoint (for VB-CABLE, `CABLE Output`) as the microphone. The relay
forces microphone capture while active, preventing it from re-translating system
or process loopback audio.

## Configuration and generated data

User settings are stored at:

~~~text
%APPDATA%\ScreenTranslator\settings.json
~~~

Build output is generated under build\ and dist\. It is not source code and
is ignored by Git. The Tesseract runtime under vendor\tesseract is a checked
in release dependency used by the Windows build.
