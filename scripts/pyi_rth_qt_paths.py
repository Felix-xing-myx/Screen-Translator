"""Make the bundled Qt and Shiboken DLL directories visible on Windows."""

from __future__ import annotations

import os
import sys
import ctypes
import glob


if sys.platform == "win32":
    bundle_root = getattr(sys, "_MEIPASS", "")
    if bundle_root:
        # Keep the returned handles alive for the whole process.  Windows
        # removes a directory from the DLL search path when its handle is
        # released, which can make Qt fail to load on machines without the
        # same system DLLs as the build machine.
        _dll_directory_handles = []
        dll_paths = [
            bundle_root,
            os.path.join(bundle_root, "PySide6"),
            os.path.join(bundle_root, "shiboken6"),
        ]
        for dll_path in dll_paths:
            if not os.path.isdir(dll_path):
                continue
            if hasattr(os, "add_dll_directory"):
                try:
                    _dll_directory_handles.append(os.add_dll_directory(dll_path))
                except OSError:
                    pass
            os.environ["PATH"] = dll_path + os.pathsep + os.environ.get(
                "PATH", ""
            )

        # PySide6's extension module depends on Shiboken and the Qt core DLL
        # before Python has a chance to import either package.  Preloading the
        # two core dependencies by absolute path avoids Windows resolving an
        # unrelated system copy (or reporting the generic QtCore DLL error).
        preload_paths = [
            *sorted(glob.glob(os.path.join(bundle_root, "icudt*.dll"))),
            os.path.join(bundle_root, "icuuc.dll"),
            os.path.join(bundle_root, "shiboken6", "shiboken6.abi3.dll"),
            os.path.join(bundle_root, "PySide6", "Qt6Core.dll"),
            os.path.join(bundle_root, "PySide6", "pyside6.abi3.dll"),
        ]
        for dll_path in preload_paths:
            if os.path.isfile(dll_path):
                try:
                    ctypes.WinDLL(dll_path)
                except OSError:
                    pass
