"""One recharge window per Windows session: a named mutex, and raising the existing window."""
from __future__ import annotations

import ctypes
from ctypes import wintypes

MUTEX_NAME = "Local\\CodexCdkRecharge.Window"
_ERROR_ALREADY_EXISTS = 183
_SW_RESTORE = 9
_HWND_TOPMOST, _HWND_NOTOPMOST = -1, -2
_SWP_NOSIZE, _SWP_NOMOVE, _SWP_SHOWWINDOW = 0x0001, 0x0002, 0x0040


def _kernel32():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    k.CreateMutexW.restype = wintypes.HANDLE
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    return k


def acquire(name: str = MUTEX_NAME):
    """Return a handle when this process is the only window; None when another one runs."""
    k = _kernel32()
    handle = k.CreateMutexW(None, False, name)
    if not handle:
        return None
    if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
        k.CloseHandle(handle)
        return None
    return handle


def release(handle) -> None:
    if handle:
        _kernel32().CloseHandle(handle)


def raise_existing(title: str) -> bool:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wintypes.UINT]
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return False
    flags = _SWP_NOSIZE | _SWP_NOMOVE | _SWP_SHOWWINDOW
    user32.ShowWindow(hwnd, _SW_RESTORE)
    # Topmost on/off brings it forward even when Windows refuses SetForegroundWindow.
    user32.SetWindowPos(hwnd, wintypes.HWND(_HWND_TOPMOST), 0, 0, 0, 0, flags)
    user32.SetWindowPos(hwnd, wintypes.HWND(_HWND_NOTOPMOST), 0, 0, 0, 0, flags)
    user32.SetForegroundWindow(hwnd)
    return True
