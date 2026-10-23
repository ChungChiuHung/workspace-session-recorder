"""Unit tests for src.browser_inspector: UIA-based browser URL extraction.

The real ``uiautomation``/``comtypes`` objects are replaced with mocks so
these tests do not require an actual browser window to inspect.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import browser_inspector as bi


class TestLooksLikeUrl:
    @pytest.mark.parametrize("value, expected", [
        ("https://example.com", True),
        ("http://example.com/path?x=1", True),
        ("not a url", False),
        ("", False),
        ("example.com", False),  # no scheme
    ])
    def test_cases(self, value, expected):
        assert bi._looks_like_url(value) is expected


class TestExtractBrowserUrl:
    def test_returns_none_for_non_browser_process(self):
        assert bi.extract_browser_url(hwnd=1, proc_name="notepad.exe") is None

    def test_returns_none_when_uia_unavailable(self, monkeypatch):
        monkeypatch.setattr(bi, "HAS_UIA", False)
        assert bi.extract_browser_url(hwnd=1, proc_name="chrome.exe") is None

    def test_returns_none_when_control_from_handle_fails(self, monkeypatch):
        monkeypatch.setattr(bi, "HAS_UIA", True)
        fake_auto = MagicMock()
        fake_auto.ControlFromHandle.return_value = None
        monkeypatch.setattr(bi, "auto", fake_auto)

        assert bi.extract_browser_url(hwnd=1, proc_name="chrome.exe") is None

    def test_extracts_and_normalizes_url(self, monkeypatch):
        monkeypatch.setattr(bi, "HAS_UIA", True)

        fake_value_pattern = MagicMock()
        fake_value_pattern.Value = "example.com/path"

        fake_edit = MagicMock()
        fake_edit.Exists.return_value = True
        fake_edit.GetValuePattern.return_value = fake_value_pattern

        fake_window = MagicMock()
        fake_window.EditControl.return_value = fake_edit

        fake_auto = MagicMock()
        fake_auto.ControlFromHandle.return_value = fake_window
        monkeypatch.setattr(bi, "auto", fake_auto)

        url = bi.extract_browser_url(hwnd=123, proc_name="chrome.exe")

        assert url == "https://example.com/path"
        fake_window.EditControl.assert_called_once_with(searchDepth=bi._EDIT_SEARCH_DEPTH)
        fake_edit.Exists.assert_called_once_with(maxSearchSeconds=bi._EDIT_SEARCH_TIMEOUT_SECONDS)

    def test_returns_none_when_edit_control_missing(self, monkeypatch):
        monkeypatch.setattr(bi, "HAS_UIA", True)

        fake_edit = MagicMock()
        fake_edit.Exists.return_value = False

        fake_window = MagicMock()
        fake_window.EditControl.return_value = fake_edit

        fake_auto = MagicMock()
        fake_auto.ControlFromHandle.return_value = fake_window
        monkeypatch.setattr(bi, "auto", fake_auto)

        assert bi.extract_browser_url(hwnd=1, proc_name="msedge.exe") is None

    def test_swallows_com_errors_and_returns_none(self, monkeypatch):
        monkeypatch.setattr(bi, "HAS_UIA", True)

        fake_comtypes = MagicMock()
        fake_comtypes.COMError = RuntimeError  # usable as an exception class
        monkeypatch.setattr(bi, "comtypes", fake_comtypes)

        fake_auto = MagicMock()
        fake_auto.ControlFromHandle.side_effect = RuntimeError("UIA server died")
        monkeypatch.setattr(bi, "auto", fake_auto)

        assert bi.extract_browser_url(hwnd=1, proc_name="brave.exe") is None

    def test_proc_name_is_case_insensitive(self, monkeypatch):
        monkeypatch.setattr(bi, "HAS_UIA", True)
        fake_auto = MagicMock()
        fake_auto.ControlFromHandle.return_value = None
        monkeypatch.setattr(bi, "auto", fake_auto)

        bi.extract_browser_url(hwnd=1, proc_name="CHROME.EXE")
        fake_auto.ControlFromHandle.assert_called_once()


class TestUiaThreadSession:
    def test_initializes_and_uninitializes_when_uia_available(self, monkeypatch):
        monkeypatch.setattr(bi, "HAS_UIA", True)
        fake_auto = MagicMock()
        monkeypatch.setattr(bi, "auto", fake_auto)

        with bi.uia_thread_session():
            fake_auto.InitializeUIAutomationInCurrentThread.assert_called_once()
            fake_auto.UninitializeUIAutomationInCurrentThread.assert_not_called()

        fake_auto.UninitializeUIAutomationInCurrentThread.assert_called_once()

    def test_uninitializes_even_if_body_raises(self, monkeypatch):
        monkeypatch.setattr(bi, "HAS_UIA", True)
        fake_auto = MagicMock()
        monkeypatch.setattr(bi, "auto", fake_auto)

        with pytest.raises(ValueError):
            with bi.uia_thread_session():
                raise ValueError("boom")

        fake_auto.UninitializeUIAutomationInCurrentThread.assert_called_once()

    def test_is_noop_when_uia_unavailable(self, monkeypatch):
        monkeypatch.setattr(bi, "HAS_UIA", False)
        fake_auto = MagicMock()
        monkeypatch.setattr(bi, "auto", fake_auto)

        with bi.uia_thread_session():
            pass

        fake_auto.InitializeUIAutomationInCurrentThread.assert_not_called()
        fake_auto.UninitializeUIAutomationInCurrentThread.assert_not_called()
