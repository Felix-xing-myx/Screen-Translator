"""Backward-compatible development entry point.

The application implementation now lives in ``src/screen_translator``.
This file keeps the existing ``python main.py`` command working during the
migration.
"""

from pathlib import Path
import sys


SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from screen_translator.application import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
