"""Make the bundled Qt and Shiboken DLL directories visible on Windows."""

from __future__ import annotations

import os
import sys
import ctypes


if sys.platform == "win32":
    bundle_root = getattr(sys, "_MEIPASS", "")
    if bundle_root:
        # Keep the returned handles alive for the whole process.  Windows
        # removes a directory from the DLL search path when its handle is
        # released, which can make Qt fail to load on machines without the
        # same system DLLs as the build machine.
        _dll_directory_handles = []
        _preloaded_dlls = []
        dll_paths = [
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

        # Qt6Core imports unversioned ICU symbols.  The ICU DLL shipped in
        # recent PySide6 wheels exports version-suffixed symbols instead
        # (for example, *_78), so loading that private copy produces a
        # misleading entry-point-not-found error.  Preload the Windows
        # system ICU before Qt6Core; Windows 10/11 provide the ABI Qt needs.
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        system_icu = os.path.join(system_root, "System32", "icuuc.dll")
        if os.path.isfile(system_icu):
            try:
                _preloaded_dlls.append(ctypes.WinDLL(system_icu))
            except OSError:
                pass

        # PySide6's extension module depends on Shiboken and the Qt core DLL
        # before Python has a chance to import either package.  Preloading the
        # two core dependencies by absolute path avoids Windows resolving an
        # unrelated system copy (or reporting the generic QtCore DLL error).
        preload_paths = [
            os.path.join(bundle_root, "shiboken6", "shiboken6.abi3.dll"),
            os.path.join(bundle_root, "PySide6", "Qt6Core.dll"),
            os.path.join(bundle_root, "PySide6", "pyside6.abi3.dll"),
        ]
        for dll_path in preload_paths:
            if os.path.isfile(dll_path):
                try:
                    _preloaded_dlls.append(ctypes.WinDLL(dll_path))
                except OSError:
                    pass
