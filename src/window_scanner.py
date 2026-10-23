"""Enumeration of visible top-level windows and their owning processes.

This module wraps the Win32 ``EnumWindows`` API together with ``psutil`` to
build a snapshot of the applications a user currently has open, so that a
workspace session can later be restored. It is designed to be safe to call
from a background thread, since both UI Automation lookups (done elsewhere)
and process inspection can be slow enough to freeze a Tkinter GUI if run on
the main thread.
"""

from __future__ import annotations

import ctypes
import logging
from typing import Callable, List, Optional, TypedDict

import psutil
import pywintypes
import win32gui
import win32process

logger = logging.getLogger(__name__)

# Common background / shell processes that should never be treated as a
# restorable "application" window.
IGNORED_PROCESS_NAMES = frozenset({
    "explorer.exe",
    "python.exe",
    "pythonw.exe",
    "cmd.exe",
    "powershell.exe",
    "searchhost.exe",
    "taskmgr.exe",
    "applicationframehost.exe",
})

# DWM attribute id used to detect "cloaked" windows. On Windows 10/11, windows
# that live on another virtual desktop (or certain hidden UWP host windows)
# still report IsWindowVisible() == True but are not actually shown on
# screen. Filtering these out avoids false positives in the scan results.
_DWMWA_CLOAKED = 14

try:
    _dwmapi = ctypes.windll.dwmapi
except (AttributeError, OSError):  # pragma: no cover - non-Windows / no DWM
    _dwmapi = None


class WindowInfo(TypedDict):
    """Shape of each entry returned by :func:`scan_open_windows`."""

    hwnd: int
    title: str
    proc_name: str
    exe_path: str


def _is_cloaked(hwnd: int) -> bool:
    """Returns True if the window is DWM-cloaked (not actually on screen).

    Cloaked windows commonly appear for UWP host windows and for windows
    parked on an inactive virtual desktop; both would otherwise show up as
    false positives in the recorded session.
    """
    if _dwmapi is None:
        return False

    cloaked = ctypes.c_int(0)
    try:
        result = _dwmapi.DwmGetWindowAttribute(
            ctypes.c_void_p(hwnd),
            ctypes.c_uint(_DWMWA_CLOAKED),
            ctypes.byref(cloaked),
            ctypes.sizeof(cloaked),
        )
    except OSError:
        return False

    return result == 0 and cloaked.value != 0


def _resolve_process(pid: int) -> Optional[psutil.Process]:
    """Safely resolves a psutil.Process, returning None if inaccessible."""
    try:
        return psutil.Process(pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, ValueError):
        return None


def scan_open_windows(ignore_hwnd: Optional[int] = None) -> List[WindowInfo]:
    """Scans for all visible top-level windows and their owning processes.

    This performs a synchronous Win32 ``EnumWindows`` pass. It is relatively
    fast on its own, but callers that also want browser tab URLs (via
    ``browser_inspector``) should run the combined scan on a background
    thread, since UI Automation lookups per window are considerably slower
    and would otherwise freeze the UI.

    Args:
        ignore_hwnd: Optional window handle to exclude from the results
            (typically the recorder's own GUI window).

    Returns:
        A list of :class:`WindowInfo` dictionaries, one per captured window.
        Windows belonging to ignored/system processes, windows without a
        title, and DWM-cloaked (not actually visible) windows are skipped.
        Any window that disappears mid-enumeration or whose owning process
        cannot be inspected is silently skipped rather than raising.
    """
    captured_windows: List[WindowInfo] = []

    def enum_windows_callback(hwnd: int, _: object) -> bool:
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True

            if ignore_hwnd is not None and hwnd == ignore_hwnd:
                return True

            if _is_cloaked(hwnd):
                return True

            title = win32gui.GetWindowText(hwnd).strip()
        except pywintypes.error as exc:
            # The window can legitimately be destroyed between EnumWindows
            # handing us the handle and us querying it (e.g. tooltips,
            # transient notification windows). Skip rather than crash.
            logger.debug("Window %s vanished during enumeration: %s", hwnd, exc)
            return True

        if not title:
            return True

        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
        except pywintypes.error as exc:
            logger.debug("Could not resolve PID for hwnd %s: %s", hwnd, exc)
            return True

        proc = _resolve_process(pid)
        if proc is None:
            return True

        try:
            exe_path = proc.exe()
            proc_name = proc.name().lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as exc:
            logger.debug("Process %s became inaccessible: %s", pid, exc)
            return True

        if proc_name in IGNORED_PROCESS_NAMES:
            return True

        captured_windows.append({
            "hwnd": hwnd,
            "title": title,
            "proc_name": proc_name,
            "exe_path": exe_path,
        })
        return True

    callback: Callable[[int, object], bool] = enum_windows_callback
    win32gui.EnumWindows(callback, None)
    return captured_windows
