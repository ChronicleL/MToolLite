"""Headless smoke tests for PySide6 GUI."""

from __future__ import annotations

import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402
from rpgm_tool.gui import MainWindow  # noqa: E402


class TestGui(unittest.TestCase):
    def test_window_init_and_table_filter(self) -> None:
        app = QApplication.instance() or QApplication([])
        win = MainWindow()
        win.table_model.set_dict(
            {
                "こんにちは": "你好",
                r"\C[1]勇者\C[0]": "",
                "剣": "剑",
            }
        )
        self.assertEqual(win.table_model.stats(), (2, 1, 0))
        self.assertEqual(win.table_model.rowCount(), 3)

        win.table_model.set_filter("", "untranslated")
        self.assertEqual(win.table_model.rowCount(), 1)

        win.table_model.set_filter("剣", "all")
        self.assertEqual(win.table_model.rowCount(), 1)

        # Verify language filter and right-click revert/filter
        win.table_model.set_dict(
            {
                "你好世界": "",
                "こんにちは": "",
                "Hello World": "",
            }
        )
        done, todo, filt = win.table_model.stats()
        self.assertEqual((done, todo, filt), (0, 3, 0))

        # Mark Chinese filtered
        win.table_model.mark_filtered(["你好世界"])
        done, todo, filt = win.table_model.stats()
        self.assertEqual((done, todo, filt), (0, 2, 1))

        # Check dropdown filter view
        win.table_model.set_filter("", "filtered")
        self.assertEqual(win.table_model.rowCount(), 1)
        self.assertEqual(win.table_model.get_key_at(0), "你好世界")

        # Revert back to untranslated
        win.table_model.revert_to_untranslated(["你好世界"])
        done, todo, filt = win.table_model.stats()
        self.assertEqual((done, todo, filt), (0, 3, 0))

        # Verify mode switching between AI and Machine Translation
        win.cmb_tr_mode.setCurrentText("机器翻译")
        self.assertEqual(win._build_current_config().mode, "mt")
        win.cmb_tr_mode.setCurrentText("AI 翻译")
        self.assertEqual(win._build_current_config().mode, "ai")

        # Verify history removal & clean invalid
        win._history = [
            {"name": "ValidGame", "engine": "RPG Maker MV", "path": str(Path(__file__).parent)},
            {"name": "InvalidGame", "engine": "Wolf RPG", "path": "D:/FakeNonExistentPath/Game.exe"},
        ]
        win._refresh_history_list()
        self.assertEqual(win.history_list.count(), 2)

        # Remove single entry
        win._remove_history_entry("D:/FakeNonExistentPath/Game.exe")
        self.assertEqual(win.history_list.count(), 1)

        # Add invalid entry back and test clean_invalid
        win._history.append({"name": "Invalid2", "engine": "Wolf RPG", "path": "Z:/NoSuchPath/Game.exe"})
        win._refresh_history_list()
        self.assertEqual(win.history_list.count(), 2)
        win._clean_invalid_history()
        self.assertEqual(win.history_list.count(), 1)
        self.assertEqual(win._history[0]["name"], "ValidGame")

        win.close()
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
