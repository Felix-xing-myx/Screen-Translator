"""Command-line entry point used by both Python and PyInstaller."""

from screen_translator.application import main


if __name__ == "__main__":
    raise SystemExit(main())

