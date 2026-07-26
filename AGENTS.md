# Agent guide

## Project root

Always treat E:\translate as the project root. The Python source is under
src\screen_translator; it is not a standalone workspace.

## Environment

The project uses a local .venv managed from pyproject.toml.

Preferred commands:

~~~powershell
uv sync --extra dev
uv run --extra dev python -m screen_translator
uv run --extra dev python -m pytest -q
~~~

If uv is unavailable, use:

~~~powershell
.\scripts\bootstrap.ps1
.\.venv\Scripts\python.exe -m screen_translator
.\.venv\Scripts\python.exe -m pytest -q
~~~

Do not add a second dependency file or manually set PYTHONPATH for normal
development. The package is installed in editable mode from the project root.

## Important paths

- src\screen_translator: application implementation
- tests: automated tests
- scripts: environment, run, test, and build entry points
- packaging: Inno Setup installer definition and language files
- vendor\tesseract: bundled Windows OCR runtime
- docs: architecture and design documentation
- dist, build, .venv, and tmp: generated/local files; do not inspect as source

Read docs\architecture.md before making cross-module changes.
