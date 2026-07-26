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
~~~

## Module map

| Area | Modules | Responsibility |
| --- | --- | --- |
| Entry point | application.py, __main__.py | Create the Qt application and launch the main window |
| Configuration | config.py, models.py | Persist settings and define shared data objects |
| Capture adapters | screen_capture.py, audio_capture.py, windows_loopback.py | Connect to Windows screen and audio sources |
| Translation adapters | ocr.py, translator.py | Adapt Tesseract and remote translation providers |
| Workflows | capture.py, workers.py, vad.py, audio_translation.py | Coordinate capture, segmentation, retries, and background work |
| Input/system | hotkeys.py | Record and register global Windows hotkeys |
| UI | ui/ | Main window, settings, overlays, result windows, and shared widgets |
| Pure helpers | text_utils.py | Text normalization and comparison without Qt or network side effects |

The UI is the external seam for user actions. Provider and device modules are
adapters behind the workflow seam, which keeps API and Windows-specific details
out of most UI code. Tests should prefer crossing a small module interface
instead of reaching into implementation details.

## Configuration and generated data

User settings are stored at:

~~~text
%APPDATA%\ScreenTranslator\settings.json
~~~

Build output is generated under build\ and dist\. It is not source code and
is ignored by Git. The Tesseract runtime under vendor\tesseract is a checked
in release dependency used by the Windows build.
