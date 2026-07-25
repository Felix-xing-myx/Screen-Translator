"""Windows Application Loopback API binding."""

from __future__ import annotations

import ctypes
import sys
import uuid

if sys.platform != "win32":
    raise ImportError("Windows Application Loopback is only available on Windows")

HRESULT = ctypes.c_long
DWORD = ctypes.c_uint32
UINT32 = ctypes.c_uint32
UINT64 = ctypes.c_uint64
BYTE = ctypes.c_ubyte
WINFUNCTYPE = ctypes.WINFUNCTYPE


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [
        ("wFormatTag", ctypes.c_uint16),
        ("nChannels", ctypes.c_uint16),
        ("nSamplesPerSec", ctypes.c_uint32),
        ("nAvgBytesPerSec", ctypes.c_uint32),
        ("nBlockAlign", ctypes.c_uint16),
        ("wBitsPerSample", ctypes.c_uint16),
        ("cbSize", ctypes.c_uint16),
    ]


class BLOB(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint32), ("pBlobData", ctypes.c_void_p)]


class PROPVARIANT(ctypes.Structure):
    _fields_ = [
        ("vt", ctypes.c_uint16),
        ("wReserved1", ctypes.c_uint16),
        ("wReserved2", ctypes.c_uint16),
        ("wReserved3", ctypes.c_uint16),
        ("blob", BLOB),
    ]


class PROCESS_LOOPBACK_PARAMS(ctypes.Structure):
    _fields_ = [("TargetProcessId", DWORD), ("ProcessLoopbackMode", DWORD)]


class ACTIVATION_PARAMS(ctypes.Structure):
    _fields_ = [
        ("ActivationType", DWORD),
        ("ProcessLoopbackParams", PROCESS_LOOPBACK_PARAMS),
    ]


def guid(text: str) -> GUID:
    value = uuid.UUID(text)
    return GUID(
        value.time_low,
        value.time_mid,
        value.time_hi_version,
        (ctypes.c_ubyte * 8).from_buffer_copy(value.bytes[8:]),
    )


IID_IAUDIO_CLIENT = guid("1CB9AD4C-DBFA-4c32-B178-C2F568A703B2")
IID_IAUDIO_CAPTURE_CLIENT = guid("C8ADBD64-E71E-48a0-A4DE-185C395CEBF3")
S_OK = 0
E_FAIL = -2147467259
WAIT_TIMEOUT = 258
VT_BLOB = 65
WAVE_FORMAT_PCM = 1
SHAREMODE_SHARED = 0
STREAMFLAGS_LOOPBACK = 0x00020000
STREAMFLAGS_EVENTCALLBACK = 0x00040000
STREAMFLAGS_AUTOCONVERTPCM = 0x80000000
VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK = "VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK"

QI = WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
ADDREF = WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
RELEASE = WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
ACTIVATE_COMPLETED = WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.c_void_p)


class COM_VTABLE(ctypes.Structure):
    _fields_ = [
        ("QueryInterface", QI),
        ("AddRef", ADDREF),
        ("Release", RELEASE),
        ("ActivateCompleted", ACTIVATE_COMPLETED),
    ]


class COM_OBJECT(ctypes.Structure):
    _fields_ = [("lpVtbl", ctypes.POINTER(COM_VTABLE))]


def method(pointer, index: int, result, *args):
    address = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_void_p))[0]
    vtable = ctypes.cast(address, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    return WINFUNCTYPE(result, ctypes.c_void_p, *args)(vtable[index])(pointer, *args)


class ApplicationLoopbackSource:
    """Streaming process-tree capture using ActivateAudioInterfaceAsync."""
    def __init__(self, process_id: int, include_children: bool = True):
        if process_id <= 0:
            raise ValueError("A valid process id is required")
        self.process_id = int(process_id)
        self.include_children = bool(include_children)
        self.sample_rate = 48_000
        self.channels = 2
        self._closed = False
        self._setup()


    def _setup(self) -> None:
        import threading

        self._ole32 = ctypes.WinDLL("ole32.dll")
        self._kernel32 = ctypes.WinDLL("kernel32.dll")
        self._ole32.CoInitializeEx(None, 0)
        self._com_initialized = True
        self._activation_event = self._kernel32.CreateEventW(None, True, False, None)
        self._activation_error = E_FAIL
        self._audio_client = ctypes.c_void_p()

        @QI
        def query_interface(this, _riid, out):
            out[0] = ctypes.cast(this, ctypes.c_void_p).value
            return S_OK

        @ADDREF
        def add_ref(_this):
            return 1

        @RELEASE
        def release(_this):
            return 1

        @ACTIVATE_COMPLETED
        def activate_completed(_this, operation):
            try:
                result = HRESULT()
                interface = ctypes.c_void_p()
                get_result = method(
                    ctypes.c_void_p(operation), 3, HRESULT,
                    ctypes.POINTER(HRESULT), ctypes.POINTER(ctypes.c_void_p),
                )
                hr = get_result(ctypes.byref(result), ctypes.byref(interface))
                self._activation_error = int(hr)
                if result.value >= 0:
                    self._activation_error = int(result.value)
                    self._audio_client = interface
            finally:
                self._kernel32.SetEvent(self._activation_event)
            return S_OK

        self._callbacks = (query_interface, add_ref, release, activate_completed)
        self._vtable = COM_VTABLE(query_interface, add_ref, release, activate_completed)
        self._callback_object = COM_OBJECT(ctypes.pointer(self._vtable))
        self._params = ACTIVATION_PARAMS(
            1, PROCESS_LOOPBACK_PARAMS(self.process_id, 0 if self.include_children else 1)
        )
        prop = PROPVARIANT()
        prop.vt = VT_BLOB
        prop.blob.cbSize = ctypes.sizeof(self._params)
        prop.blob.pBlobData = ctypes.cast(ctypes.pointer(self._params), ctypes.c_void_p)

        mmdevapi = ctypes.WinDLL("mmdevapi.dll")
        activate = mmdevapi.ActivateAudioInterfaceAsync
        activate.argtypes = [
            ctypes.c_wchar_p, ctypes.POINTER(GUID), ctypes.POINTER(PROPVARIANT),
            ctypes.POINTER(COM_OBJECT), ctypes.POINTER(ctypes.c_void_p),
        ]
        activate.restype = HRESULT
        operation = ctypes.c_void_p()
        hr = activate(
            VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK,
            ctypes.byref(IID_IAUDIO_CLIENT), ctypes.byref(prop),
            ctypes.byref(self._callback_object), ctypes.byref(operation),
        )
        if hr < 0:
            raise RuntimeError(f"ActivateAudioInterfaceAsync failed: 0x{hr & 0xffffffff:08X}")
        self._kernel32.WaitForSingleObject(self._activation_event, 10_000)
        if self._activation_error < 0 or not self._audio_client:
            raise RuntimeError("Windows process loopback activation failed")

        self._capture_event = self._kernel32.CreateEventW(None, False, False, None)
        wave = WAVEFORMATEX(WAVE_FORMAT_PCM, 2, self.sample_rate, self.sample_rate * 4, 4, 16, 0)
        flags = STREAMFLAGS_LOOPBACK | STREAMFLAGS_EVENTCALLBACK | STREAMFLAGS_AUTOCONVERTPCM
        hr = method(
            self._audio_client, 3, HRESULT, ctypes.c_uint32, ctypes.c_uint32,
            ctypes.POINTER(WAVEFORMATEX), ctypes.c_void_p,
        )(SHAREMODE_SHARED, flags, 0, ctypes.byref(wave), None)
        if hr < 0:
            raise RuntimeError(f"IAudioClient.Initialize failed: 0x{hr & 0xffffffff:08X}")
        if method(self._audio_client, 13, HRESULT, ctypes.c_void_p)(self._capture_event) < 0:
            raise RuntimeError("IAudioClient.SetEventHandle failed")
        buffer_frames = UINT32()
        method(self._audio_client, 4, HRESULT, ctypes.POINTER(UINT32))(ctypes.byref(buffer_frames))
        capture_client = ctypes.c_void_p()
        hr = method(
            self._audio_client, 14, HRESULT, ctypes.POINTER(GUID),
            ctypes.POINTER(ctypes.c_void_p),
        )(ctypes.byref(IID_IAUDIO_CAPTURE_CLIENT), ctypes.byref(capture_client))
        if hr < 0 or not capture_client:
            raise RuntimeError("IAudioClient.GetService failed")
        self._capture_client = capture_client
        self._block_align = 4
        if method(self._audio_client, 10, HRESULT)() < 0:
            raise RuntimeError("IAudioClient.Start failed")

    def read(self, timeout: float = 0.2) -> bytes:
        if self._closed:
            return b""
        result = self._kernel32.WaitForSingleObject(
            self._capture_event, max(1, int(timeout * 1000))
        )
        if result == WAIT_TIMEOUT:
            return b""
        if self._closed:
            return b""
        chunks: list[bytes] = []
        while True:
            frames = UINT32()
            hr = method(
                self._capture_client, 5, HRESULT, ctypes.POINTER(UINT32)
            )(ctypes.byref(frames))
            if hr < 0 or frames.value == 0:
                break
            data = ctypes.POINTER(BYTE)()
            flags = DWORD()
            device_position, qpc_position = UINT64(), UINT64()
            hr = method(
                self._capture_client, 3, HRESULT,
                ctypes.POINTER(ctypes.POINTER(BYTE)), ctypes.POINTER(UINT32),
                ctypes.POINTER(DWORD), ctypes.POINTER(UINT64), ctypes.POINTER(UINT64),
            )(
                ctypes.byref(data), ctypes.byref(frames), ctypes.byref(flags),
                ctypes.byref(device_position), ctypes.byref(qpc_position),
            )
            if hr < 0:
                break
            size = int(frames.value) * self._block_align
            chunks.append(
                b"\0" * size if flags.value & 0x2 else ctypes.string_at(data, size)
            )
            method(self._capture_client, 4, HRESULT, UINT32)(frames.value)
        return b"".join(chunks)

    def interrupt(self) -> None:
        self._closed = True
        event = getattr(self, "_capture_event", None)
        if event:
            try:
                self._kernel32.SetEvent(event)
            except Exception:
                pass

    def close(self) -> None:
        if getattr(self, "_closed", True):
            return
        self._closed = True
        try:
            method(self._audio_client, 11, HRESULT)()
        except Exception:
            pass
        for pointer in (
            getattr(self, "_capture_client", None),
            getattr(self, "_audio_client", None),
        ):
            if pointer:
                try:
                    method(pointer, 2, ctypes.c_ulong)()
                except Exception:
                    pass
        for name in ("_capture_event", "_activation_event"):
            handle = getattr(self, name, None)
            if handle:
                self._kernel32.CloseHandle(handle)
        if getattr(self, "_com_initialized", False):
            self._ole32.CoUninitialize()
