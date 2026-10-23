"""Generation of Windows batch (.bat) scripts that restore a recorded session.

The exported script simply calls ``start`` once per recorded item (an
application executable path or a browser URL). Because the values being
embedded come from arbitrary file system paths and URLs, this module takes
care to escape characters that ``cmd.exe`` treats specially so that the
generated script behaves exactly as expected rather than being silently
corrupted or, worse, executing something unintended.
"""

from __future__ import annotations

import logging
from typing import Iterable, List, TypedDict

logger = logging.getLogger(__name__)

# Batch files saved as UTF-8 with a BOM are auto-detected by cmd.exe
# (Windows 10 version 1903+) and run under code page 65001, which is what
# lets launch targets containing non-ASCII / unicode characters resolve
# correctly. Plain "utf-8" (no BOM) would instead be interpreted using the
# legacy OEM code page and could mangle such paths.
_BATCH_ENCODING = "utf-8-sig"


class SessionItem(TypedDict):
    """Shape of each recorded item passed in to :func:`generate_batch_file`."""

    include: bool
    type: str
    name: str
    target: str


def _escape_for_batch(value: str) -> str:
    """Escapes a string for safe embedding inside a quoted batch command.

    Two transformations matter here:

    * ``%`` is cmd.exe's variable-expansion marker and is expanded *even
      inside double quotes*. Left unescaped, a path or URL containing a
      literal ``%`` (e.g. ``100%`` in a title, or ``%2520``-style encoded
      query strings) could be silently rewritten -- or, if it happens to
      match a real environment variable name, replaced with unrelated data.
      Doubling it to ``%%`` makes cmd.exe treat it as a literal percent sign.
    * ``"`` would terminate the surrounding quoted argument early, breaking
      the command. Double quotes are not valid in Windows file paths, and
      are stripped here for URLs/titles as a defensive measure.
    """
    return value.replace("%", "%%").replace('"', "")


def _build_batch_lines(selected_items: Iterable[SessionItem]) -> List[str]:
    """Builds the list of batch-file lines for the given session items."""
    lines = [
        "@echo off",
        "echo Restoring saved workspace session...",
        "echo -----------------------------------",
        "",
    ]

    for item in selected_items:
        target = item.get("target")
        if not target:
            logger.warning("Skipping item with empty target: %r", item.get("name"))
            continue
        lines.append(f'start "" "{_escape_for_batch(target)}"')

    lines.append("")
    lines.append("echo All applications launched successfully!")
    lines.append("timeout /t 3")
    return lines


def generate_batch_file(file_path: str, selected_items: Iterable[SessionItem]) -> bool:
    """Writes a formatted batch file to launch specified applications and URLs.

    Args:
        file_path: Destination path for the generated ``.bat`` file.
        selected_items: Session items to include, each exposing at least a
            ``"target"`` key (executable path or URL). Items with an empty
            target are skipped with a logged warning rather than producing
            a broken ``start`` command.

    Returns:
        True on success.

    Raises:
        OSError: If the file cannot be written (e.g. invalid path,
            insufficient permissions, destination directory missing).
    """
    lines = _build_batch_lines(selected_items)

    with open(file_path, "w", encoding=_BATCH_ENCODING, newline="\r\n") as f:
        f.write("\n".join(lines))

    return True
