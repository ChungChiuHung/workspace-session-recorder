"""Active-tab URL extraction for Chromium-based browsers via UI Automation.

Chromium-based browsers (Chrome, Edge, Brave, Opera, Vivaldi, ...) expose
their address bar as a standard UIA ``Edit`` control, which lets us read the
current tab's URL without any browser-specific extension. Non-Chromium
browsers such as Firefox use a different accessibility tree shape and are
intentionally not supported here; callers should treat a ``None`` return as
"fall back to tracking the application by its executable path" rather than
as an error.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Iterator, Optional
from urllib.parse import urlparse

try:
    import uiautomation as auto
    import comtypes

    HAS_UIA = True
except ImportError:  # pragma: no cover - exercised only without optional deps
    auto = None  # type: ignore[assignment]
    comtypes = None  # type: ignore[assignment]
    HAS_UIA = False

logger = logging.getLogger(__name__)

if not HAS_UIA:  # pragma: no cover - environment dependent
    logger.warning(
        "uiautomation/comtypes not available; browser URL extraction is disabled "
        "and all browser windows will be recorded as plain applications."
    )

# Chromium-family processes known to expose their address bar as a plain
# UIA Edit control. Firefox (Gecko) and other non-Chromium browsers are
# deliberately excluded: they use a different accessibility tree and would
# require a separate extraction strategy.
KNOWN_BROWSERS = frozenset({
    "chrome.exe",
    "msedge.exe",
    "brave.exe",
    "opera.exe",
    "opera_gx.exe",
    "vivaldi.exe",
    "chromium.exe",
})

# How deep into the window's UI tree to search for the address bar edit
# control. Chromium's omnibox is typically only a few levels deep; capping
# this keeps the UI Automation walk fast even when a window has many tabs
# or toolbar buttons.
_EDIT_SEARCH_DEPTH = 10

# Upper bound (in seconds) on how long to wait for the address bar control to
# be found. Keeping this small is what prevents a single unresponsive or
# slow-to-enumerate browser window from stalling the whole scan.
_EDIT_SEARCH_TIMEOUT_SECONDS = 0.5


@contextlib.contextmanager
def uia_thread_session() -> Iterator[None]:
    """Initializes UI Automation's COM apartment for the current thread.

    ``uiautomation`` requires ``InitializeUIAutomationInCurrentThread()`` to
    be called on any thread other than the one it was first imported on
    before Controls/Patterns can be used, and the matching uninitialize call
    when that thread is done. Wrap any background-thread work that calls
    :func:`extract_browser_url` in this context manager, e.g.::

        with uia_thread_session():
            url = extract_browser_url(hwnd, proc_name)

    This is a no-op when ``uiautomation`` is unavailable.
    """
    if not HAS_UIA:
        yield
        return

    auto.InitializeUIAutomationInCurrentThread()
    try:
        yield
    finally:
        auto.UninitializeUIAutomationInCurrentThread()


def _looks_like_url(value: str) -> bool:
    """Heuristically checks that a string resembles a usable URL."""
    parsed = urlparse(value)
    return bool(parsed.scheme) and bool(parsed.netloc)


def extract_browser_url(hwnd: int, proc_name: str) -> Optional[str]:
    """Attempts to read the address bar value of a Chromium browser window.

    Args:
        hwnd: Window handle of the candidate browser window.
        proc_name: Lowercase or mixed-case executable name owning the window
            (e.g. ``"chrome.exe"``). Compared case-insensitively against
            :data:`KNOWN_BROWSERS`.

    Returns:
        The current address bar URL if it could be read from a known
        Chromium-based browser, otherwise ``None``. A ``None`` result is the
        normal/expected outcome for non-browser windows, non-Chromium
        browsers (e.g. Firefox), and any transient UI Automation failure
        (closed window, unresponsive process, missing control) -- callers
        should treat it as "no URL available", not as an error.
    """
    if not HAS_UIA or proc_name.lower() not in KNOWN_BROWSERS:
        return None

    try:
        window = auto.ControlFromHandle(hwnd)
        if not window:
            return None

        # Search the window's hierarchy for the address bar edit box.
        edit_control = window.EditControl(searchDepth=_EDIT_SEARCH_DEPTH)
        if edit_control and edit_control.Exists(maxSearchSeconds=_EDIT_SEARCH_TIMEOUT_SECONDS):
            value_pattern = edit_control.GetValuePattern()
            url = value_pattern.Value if value_pattern else None
            if url:
                url = url.strip()
            if not url:
                return None

            if not (url.startswith("http://") or url.startswith("https://")):
                url = "https://" + url

            return url if _looks_like_url(url) else None
    except (comtypes.COMError, OSError) as exc:
        logger.debug("UI Automation failed for hwnd=%s (%s): %s", hwnd, proc_name, exc)
    except Exception as exc:  # noqa: BLE001 - UIA can raise a variety of errors
        logger.debug("Unexpected error extracting URL for hwnd=%s: %s", hwnd, exc)

    return None
