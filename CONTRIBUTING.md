# Development

## First setup

From the project root:

~~~powershell
.\scripts\bootstrap.ps1
~~~

This creates or synchronizes .venv, installs the package in editable mode,
and installs development tools from pyproject.toml.

## Daily commands

~~~powershell
.\scripts\run.ps1
.\scripts\test.ps1
uv run --extra dev ruff check src tests
~~~

The same commands can be run directly with uv run --extra dev.

## Release build

~~~powershell
.\scripts\build.ps1
~~~

The PyInstaller output is placed in dist\ScreenTranslator. The Inno Setup
script in packaging\ScreenTranslator.iss consumes that directory to produce
the Windows installer.

Keep source changes under src, tests under tests, and generated files out
of Git. Add new dependencies to pyproject.toml; do not create another
requirements file.
