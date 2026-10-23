"""Unit tests for src.exporter: batch file generation and escaping rules."""

from __future__ import annotations

import logging

import pytest

from exporter import generate_batch_file


def _item(target: str, name: str = "Item") -> dict:
    return {"include": True, "type": "Application", "name": name, "target": target}


def _read_raw(path) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _read_text(path) -> str:
    return _read_raw(path).decode("utf-8-sig")


class TestGenerateBatchFile:
    def test_writes_start_command_per_item(self, tmp_path):
        bat_path = tmp_path / "out.bat"
        items = [_item(r"C:\Apps\notepad.exe"), _item("https://example.com", name="Site")]

        generate_batch_file(str(bat_path), items)
        content = _read_text(bat_path)

        assert '@echo off' in content
        assert 'start "" "C:\\Apps\\notepad.exe"' in content
        assert 'start "" "https://example.com"' in content

    def test_percent_sign_is_doubled_to_prevent_env_expansion(self, tmp_path):
        bat_path = tmp_path / "out.bat"
        items = [_item(r"C:\Some%TEMP%Folder\file.txt")]

        generate_batch_file(str(bat_path), items)
        content = _read_text(bat_path)

        assert "%%TEMP%%" in content
        assert "%TEMP%" not in content.replace("%%TEMP%%", "")

    def test_double_quote_is_stripped(self, tmp_path):
        bat_path = tmp_path / "out.bat"
        items = [_item('C:\\Apps\\evil".exe')]

        generate_batch_file(str(bat_path), items)
        content = _read_text(bat_path)

        assert '"' not in content.split("evil")[1].split("exe")[0]
        assert 'evil.exe' in content

    def test_empty_target_is_skipped_without_crashing(self, tmp_path, caplog):
        bat_path = tmp_path / "out.bat"
        items = [_item(""), _item(r"C:\Apps\keep.exe")]

        with caplog.at_level(logging.WARNING):
            generate_batch_file(str(bat_path), items)
        content = _read_text(bat_path)

        assert 'start "" ""' not in content
        assert "keep.exe" in content
        assert any("empty target" in rec.message.lower() for rec in caplog.records)

    def test_output_has_utf8_bom(self, tmp_path):
        bat_path = tmp_path / "out.bat"
        generate_batch_file(str(bat_path), [_item(r"C:\Apps\a.exe")])

        raw = _read_raw(bat_path)
        assert raw.startswith(b"\xef\xbb\xbf")

    def test_unicode_paths_round_trip(self, tmp_path):
        bat_path = tmp_path / "out.bat"
        unicode_target = r"C:\Users\ユーザー\デスクトップ\app.exe"
        generate_batch_file(str(bat_path), [_item(unicode_target)])

        content = _read_text(bat_path)
        assert unicode_target in content

    def test_returns_true_on_success(self, tmp_path):
        bat_path = tmp_path / "out.bat"
        assert generate_batch_file(str(bat_path), [_item(r"C:\Apps\a.exe")]) is True

    def test_raises_oserror_for_invalid_path(self):
        with pytest.raises(OSError):
            generate_batch_file(r"Z:\definitely\not\a\real\drive\out.bat", [_item("a")])

    def test_no_selected_items_still_produces_valid_script(self, tmp_path):
        bat_path = tmp_path / "out.bat"
        generate_batch_file(str(bat_path), [])
        content = _read_text(bat_path)

        assert "@echo off" in content
        assert "start" not in content
