"""Unit tests for src.window_scanner: window enumeration and filtering.

All Win32/psutil calls are mocked so these tests exercise only the filtering
logic in this module and do not depend on whatever windows happen to be open
on the machine running the test suite.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import psutil
import pywintypes
import pytest

import window_scanner as ws


def make_enum_windows(hwnds):
    """Builds a fake win32gui.EnumWindows that invokes callback(hwnd, None)."""

    def fake_enum_windows(callback, extra):
        for hwnd in hwnds:
            callback(hwnd, extra)

    return fake_enum_windows


@pytest.fixture(autouse=True)
def no_cloaking(monkeypatch):
    """By default, no window is considered DWM-cloaked in these tests."""
    monkeypatch.setattr(ws, "_is_cloaked", lambda hwnd: False)


def _mock_process(name="app.exe", exe=r"C:\Apps\app.exe"):
    proc = MagicMock()
    proc.name.return_value = name
    proc.exe.return_value = exe
    return proc


class TestScanOpenWindows:
    def test_captures_a_normal_visible_window(self):
        with patch.object(ws.win32gui, "EnumWindows", side_effect=make_enum_windows([111])), \
             patch.object(ws.win32gui, "IsWindowVisible", return_value=True), \
             patch.object(ws.win32gui, "GetWindowText", return_value="My App"), \
             patch.object(ws.win32process, "GetWindowThreadProcessId", return_value=(1, 4242)), \
             patch.object(ws.psutil, "Process", return_value=_mock_process()):
            result = ws.scan_open_windows()

        assert result == [{
            "hwnd": 111,
            "title": "My App",
            "proc_name": "app.exe",
            "exe_path": r"C:\Apps\app.exe",
        }]

    def test_skips_invisible_windows(self):
        with patch.object(ws.win32gui, "EnumWindows", side_effect=make_enum_windows([1])), \
             patch.object(ws.win32gui, "IsWindowVisible", return_value=False):
            result = ws.scan_open_windows()

        assert result == []

    def test_skips_window_with_empty_title(self):
        with patch.object(ws.win32gui, "EnumWindows", side_effect=make_enum_windows([1])), \
             patch.object(ws.win32gui, "IsWindowVisible", return_value=True), \
             patch.object(ws.win32gui, "GetWindowText", return_value="   "):
            result = ws.scan_open_windows()

        assert result == []

    def test_skips_ignored_hwnd(self):
        with patch.object(ws.win32gui, "EnumWindows", side_effect=make_enum_windows([99])), \
             patch.object(ws.win32gui, "IsWindowVisible", return_value=True):
            result = ws.scan_open_windows(ignore_hwnd=99)

        assert result == []

    def test_skips_system_process(self):
        with patch.object(ws.win32gui, "EnumWindows", side_effect=make_enum_windows([1])), \
             patch.object(ws.win32gui, "IsWindowVisible", return_value=True), \
             patch.object(ws.win32gui, "GetWindowText", return_value="File Explorer"), \
             patch.object(ws.win32process, "GetWindowThreadProcessId", return_value=(1, 10)), \
             patch.object(ws.psutil, "Process", return_value=_mock_process(name="explorer.exe")):
            result = ws.scan_open_windows()

        assert result == []

    @pytest.mark.parametrize("exc", [
        psutil.NoSuchProcess(pid=123),
        psutil.AccessDenied(pid=123),
        psutil.ZombieProcess(pid=123),
    ])
    def test_skips_process_when_psutil_raises(self, exc):
        with patch.object(ws.win32gui, "EnumWindows", side_effect=make_enum_windows([1])), \
             patch.object(ws.win32gui, "IsWindowVisible", return_value=True), \
             patch.object(ws.win32gui, "GetWindowText", return_value="Ghost"), \
             patch.object(ws.win32process, "GetWindowThreadProcessId", return_value=(1, 123)), \
             patch.object(ws.psutil, "Process", side_effect=exc):
            result = ws.scan_open_windows()

        assert result == []

    def test_does_not_crash_when_window_vanishes_mid_enumeration(self):
        """GetWindowText can raise pywintypes.error if the window closes
        between EnumWindows handing us the handle and us querying it."""
        with patch.object(ws.win32gui, "EnumWindows", side_effect=make_enum_windows([1, 2])), \
             patch.object(ws.win32gui, "IsWindowVisible", return_value=True), \
             patch.object(ws.win32gui, "GetWindowText", side_effect=pywintypes.error(1400, "GetWindowText", "Invalid window handle")), \
             patch.object(ws.win32process, "GetWindowThreadProcessId", return_value=(1, 10)):
            result = ws.scan_open_windows()

        assert result == []

    def test_skips_cloaked_window(self, monkeypatch):
        monkeypatch.setattr(ws, "_is_cloaked", lambda hwnd: True)
        with patch.object(ws.win32gui, "EnumWindows", side_effect=make_enum_windows([1])), \
             patch.object(ws.win32gui, "IsWindowVisible", return_value=True):
            result = ws.scan_open_windows()

        assert result == []

    def test_multiple_windows_from_different_processes(self):
        procs = {4242: _mock_process(name="app.exe", exe=r"C:\Apps\app.exe"),
                 5000: _mock_process(name="other.exe", exe=r"C:\Apps\other.exe")}

        def fake_gwtpid(hwnd):
            return (1, 4242) if hwnd == 1 else (1, 5000)

        def fake_process(pid):
            return procs[pid]

        with patch.object(ws.win32gui, "EnumWindows", side_effect=make_enum_windows([1, 2])), \
             patch.object(ws.win32gui, "IsWindowVisible", return_value=True), \
             patch.object(ws.win32gui, "GetWindowText", side_effect=["App One", "App Two"]), \
             patch.object(ws.win32process, "GetWindowThreadProcessId", side_effect=fake_gwtpid), \
             patch.object(ws.psutil, "Process", side_effect=fake_process):
            result = ws.scan_open_windows()

        assert [w["title"] for w in result] == ["App One", "App Two"]
