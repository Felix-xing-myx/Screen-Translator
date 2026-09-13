"""Make the bundled Qt and Shiboken DLL directories visible on Windows."""

from __future__ import annotations

import os
import sys
import ctypes


if sys.platform == "win32":
    bundle_root = getattr(sys, "_MEIPASS", "")
    if bundle_root:
        dll_paths = [
            os.path.join(bundle_root, "PySide6"),
            os.path.join(bundle_root, "shiboken6"),
        ]
        for dll_path in dll_paths:
            if not os.path.isdir(dll_path):
                continue
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(dll_path)
            os.environ["PATH"] = dll_path + os.pathsep + os.environ.get(
                "PATH", ""
            )

        # PySide6's extension module depends on Shiboken and the Qt core DLL
        # before Python has a chance to import either package.  Preloading the
        # two core dependencies by absolute path avoids Windows resolving an
        # unrelated system copy (or reporting the generic QtCore DLL error).
        for dll_path in (
            os.path.join(bundle_root, "shiboken6", "shiboken6.abi3.dll"),
            os.path.join(bundle_root, "PySide6", "Qt6Core.dll"),
            os.path.join(bundle_root, "PySide6", "pyside6.abi3.dll"),
        ):
            if os.path.isfile(dll_path):
                try:
                    ctypes.WinDLL(dll_path)
                except OSError:
                    pass
