"""Modern PySide6 Desktop GUI for MToolLite (MTool-inspired dark workspace)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPoint, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from .detector import GameInfo, detect_engine
from .dictionary import get_untranslated, load_json_dict, merge_extracted, save_json_dict
from .extractor_2k3 import extract_2k3_texts
from .extractor_mvmz import extract_mvmz_texts
from .extractor_rgss import extract_rgss_texts, mount_rgss, unmount_rgss
from .extractor_wolf import extract_wolf_texts, mount_wolf, unmount_wolf
from .injector_mvmz import mount_mvmz, unmount_mvmz
from .modifier_mvmz import mount_cheat_mvmz, unmount_cheat_mvmz
from .translator import DEFAULT_SYSTEM_PROMPT, TranslatorConfig, test_translation_connection, translate_batch

_HISTORY_FILE = Path.home() / ".mtoollite_history.json"
_SETTINGS_FILE = Path.home() / ".mtoollite_settings.json"

_AI_PRESETS: dict[str, tuple[str, str]] = {
    "DeepSeek (deepseek-chat)": ("https://api.deepseek.com/v1", "deepseek-chat"),
    "OpenAI (gpt-4o-mini)": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "Ollama 本地 (qwen2.5:14b)": ("http://127.0.0.1:11434/v1", "qwen2.5:14b"),
    "自定义 AI 接口": ("", ""),
}

_MT_PRESETS: dict[str, tuple[str, str]] = {
    "Google 翻译 (官方 GTX)": ("google_free", "https://translate.googleapis.com/translate_a/single"),
    "Google 翻译 (自定义镜像)": ("google_free", "https://translate.googleapis.com/translate_a/single"),
    "百度翻译 API": ("baidu", "https://fanyi-api.baidu.com/api/trans/vip/translate"),
}

_MODERN_QSS = """
QMainWindow, QStackedWidget, QWidget#PageRoot {
    background-color: #0b0f19;
    color: #e2e8f0;
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 13px;
}
QLabel, QCheckBox {
    background-color: transparent;
    color: #e2e8f0;
}

/* Sidebar */
QFrame#Sidebar {
    background-color: #111827;
    border-right: 1px solid #1f2937;
}
QLabel#BrandTitle {
    color: #f8fafc;
    font-size: 18px;
    font-weight: 700;
}
QLabel#BrandBadge {
    background-color: rgba(56, 189, 248, 0.14);
    color: #38bdf8;
    border: 1px solid rgba(56, 189, 248, 0.35);
    border-radius: 9px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}
QPushButton#NavBtn {
    background-color: transparent;
    color: #94a3b8;
    border: none;
    border-radius: 8px;
    padding: 11px 14px;
    text-align: left;
    font-size: 13px;
    font-weight: 500;
}
QPushButton#NavBtn:hover {
    background-color: #1f2937;
    color: #f1f5f9;
}
QPushButton#NavBtn:checked {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #2563eb);
    color: #ffffff;
    font-weight: 700;
}

/* Top Header */
QFrame#TopBar {
    background-color: #0e1422;
    border-bottom: 1px solid #1f2937;
}
QLabel#PageTitle {
    font-size: 17px;
    font-weight: 700;
    color: #f8fafc;
}
QLabel#GameStatusPill {
    background-color: #1e293b;
    color: #94a3b8;
    border: 1px solid #334155;
    border-radius: 13px;
    padding: 4px 12px;
    font-size: 12px;
}

/* Cards */
QFrame#Card {
    background-color: #151c2c;
    border: 1px solid #232d42;
    border-radius: 12px;
}
QFrame#DropZone {
    background-color: #131b2e;
    border: 2px dashed #334155;
    border-radius: 14px;
}
QFrame#DropZone:hover {
    border-color: #38bdf8;
    background-color: #16223b;
}
QLabel#CardTitle {
    font-size: 14px;
    font-weight: 700;
    color: #f1f5f9;
}
QLabel#MutedText {
    color: #94a3b8;
    font-size: 12px;
}
QLabel#EngineBadge {
    background-color: rgba(14, 165, 233, 0.16);
    color: #38bdf8;
    border: 1px solid rgba(56, 189, 248, 0.4);
    border-radius: 10px;
    padding: 3px 10px;
    font-weight: 700;
    font-size: 12px;
}
QLabel#MetricPill {
    background-color: #0b1120;
    border: 1px solid #232d42;
    border-radius: 8px;
    padding: 6px 12px;
    color: #cbd5e1;
    font-weight: 600;
}

/* Inputs */
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {
    background-color: #0b1120;
    border: 1px solid #2d3a52;
    border-radius: 8px;
    padding: 6px 10px;
    color: #f8fafc;
    min-height: 22px;
    selection-background-color: #0284c7;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {
    border: 1px solid #38bdf8;
}
QComboBox {
    padding-right: 26px;
}
QComboBox QAbstractItemView {
    background-color: #151c2c;
    color: #f8fafc;
    border: 1px solid #334155;
    selection-background-color: #0284c7;
}

/* Buttons */
QPushButton {
    background-color: #1e293b;
    color: #e2e8f0;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 7px 14px;
    min-height: 22px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #293548;
    border-color: #475569;
}
QPushButton:disabled {
    background-color: #151c2c;
    color: #475569;
    border-color: #1e293b;
}
QPushButton#PrimaryBtn {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #2563eb);
    border: none;
    color: #ffffff;
    font-weight: 700;
}
QPushButton#PrimaryBtn:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0369a1, stop:1 #1d4ed8);
}
QPushButton#SuccessBtn {
    background-color: #059669;
    border: none;
    color: #ffffff;
    font-weight: 700;
}
QPushButton#SuccessBtn:hover {
    background-color: #047857;
}
QPushButton#DangerBtn {
    background-color: rgba(220, 38, 38, 0.14);
    border: 1px solid rgba(239, 68, 68, 0.45);
    color: #fca5a5;
}
QPushButton#DangerBtn:hover {
    background-color: #b91c1c;
    color: #ffffff;
}

/* History List */
QListWidget#HistoryList {
    background-color: #0b1120;
    border: 1px solid #232d42;
    border-radius: 8px;
    padding: 4px;
    outline: none;
}
QListWidget#HistoryList::item {
    padding: 9px 12px;
    border-radius: 6px;
    margin: 2px 0;
    color: #cbd5e1;
}
QListWidget#HistoryList::item:hover {
    background-color: #1e293b;
}
QListWidget#HistoryList::item:selected {
    background-color: rgba(14, 165, 233, 0.2);
    color: #38bdf8;
}

/* Table */
QTableView {
    background-color: #0b1120;
    alternate-background-color: #101829;
    gridline-color: #1e293b;
    border: 1px solid #232d42;
    border-radius: 10px;
    selection-background-color: rgba(2, 132, 199, 0.38);
    selection-color: #ffffff;
    outline: none;
}
QHeaderView::section {
    background-color: #151c2c;
    color: #94a3b8;
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid #232d42;
    border-right: 1px solid #1e293b;
    font-weight: 700;
}

/* Progress Bar */
QProgressBar {
    background-color: #0b1120;
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #38bdf8, stop:1 #3b82f6);
    border-radius: 4px;
}

/* Scrollbar */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #334155;
    border-radius: 4px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover {
    background: #475569;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""


class DropZoneWidget(QFrame):
    """MTool-style hero drag-and-drop card accepting game folders or .exe files."""

    path_dropped = Signal(str)
    browse_dir_clicked = Signal()
    browse_exe_clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(145)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        icon = QLabel("⬇")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 26px; color: #38bdf8;")

        title = QLabel("拖入游戏主程序 (.exe) 或游戏根目录")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 15px; font-weight: 700; color: #f8fafc;")

        sub = QLabel("自动识别 RPG Maker MV / MZ / XP / VX / VXAce / 2000 / 2003")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setObjectName("MutedText")

        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_row.setSpacing(10)
        b_dir = QPushButton("浏览文件夹")
        b_dir.clicked.connect(self.browse_dir_clicked.emit)
        b_exe = QPushButton("选择 .exe")
        b_exe.clicked.connect(self.browse_exe_clicked.emit)
        btn_row.addWidget(b_dir)
        btn_row.addWidget(b_exe)

        layout.addWidget(icon)
        layout.addWidget(title)
        layout.addWidget(sub)
        layout.addLayout(btn_row)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet(
                "QFrame#DropZone { border: 2px dashed #38bdf8; background-color: #172554; border-radius: 14px; }"
            )

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self.setStyleSheet("")

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self.setStyleSheet("")
        urls = event.mimeData().urls()
        if urls:
            local_path = urls[0].toLocalFile()
            if local_path:
                self.path_dropped.emit(local_path)


FILTERED_TAG = "__FILTERED__"

# Language detection regexes
_RE_CHINESE = re.compile(r"[\u4e00-\u9fff]")
_RE_JAPANESE_KANA = re.compile(r"[\u3040-\u30ff]")
_RE_KOREAN = re.compile(r"[\uac00-\ud7af]")
_RE_LATIN = re.compile(r"[A-Za-z]")


def detect_language_match(text: str, lang_type: str) -> bool:
    """Check if the text predominantly matches the specified language type."""
    if not text:
        return False
    if lang_type == "chinese":
        # Contains CJK ideographs but no Japanese kana
        return bool(_RE_CHINESE.search(text)) and not bool(_RE_JAPANESE_KANA.search(text))
    if lang_type == "japanese":
        # Kana or CJK with kana
        return bool(_RE_JAPANESE_KANA.search(text))
    if lang_type == "english":
        # Contains English letters and no CJK / Kana / Hangul
        return bool(_RE_LATIN.search(text)) and not bool(
            _RE_CHINESE.search(text) or _RE_JAPANESE_KANA.search(text) or _RE_KOREAN.search(text)
        )
    if lang_type == "korean":
        return bool(_RE_KOREAN.search(text))
    return False


class DictTableModel(QAbstractTableModel):
    """High-performance virtualized table model for 10,000+ translation entries."""

    def __init__(self) -> None:
        super().__init__()
        self._data: dict[str, str] = {}
        self._visible_keys: list[str] = []
        self._search = ""
        self._filter_mode = "all"

    def set_dict(self, data: dict[str, str]) -> None:
        self._data = data
        self._rebuild_filter()

    def get_dict(self) -> dict[str, str]:
        return self._data

    def set_filter(self, search: str, mode: str) -> None:
        self._search = search.strip().lower()
        self._filter_mode = mode
        self._rebuild_filter()

    def _rebuild_filter(self) -> None:
        self.beginResetModel()
        keys: list[str] = []
        for k, v in self._data.items():
            is_filtered = (v == FILTERED_TAG)
            if self._filter_mode == "filtered":
                if not is_filtered:
                    continue
            elif is_filtered:
                # Normal views hide filtered entries
                continue
            elif self._filter_mode == "untranslated" and v.strip():
                continue
            elif self._filter_mode == "translated" and not v.strip():
                continue
            elif self._filter_mode == "coded" and ("\\" not in k and "%" not in k):
                continue

            if self._search and self._search not in k.lower() and self._search not in v.lower():
                continue
            keys.append(k)
        self._visible_keys = keys
        self.endResetModel()

    def stats(self) -> tuple[int, int, int]:
        """Returns (translated_count, untranslated_count, filtered_count)."""
        filtered = 0
        done = 0
        todo = 0
        for v in self._data.values():
            if v == FILTERED_TAG:
                filtered += 1
            elif v.strip():
                done += 1
            else:
                todo += 1
        return done, todo, filtered

    def get_key_at(self, row: int) -> str | None:
        if 0 <= row < len(self._visible_keys):
            return self._visible_keys[row]
        return None

    def revert_to_untranslated(self, keys: list[str]) -> int:
        count = 0
        for k in keys:
            if k in self._data and self._data[k] != "":
                self._data[k] = ""
                count += 1
        if count > 0:
            self._rebuild_filter()
        return count

    def mark_filtered(self, keys: list[str]) -> int:
        count = 0
        for k in keys:
            if k in self._data and self._data[k] != FILTERED_TAG:
                self._data[k] = FILTERED_TAG
                count += 1
        if count > 0:
            self._rebuild_filter()
        return count

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._visible_keys)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else 2

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return "原文 (Source)" if section == 0 else "译文 (Translation - 双击行内精修)"
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        key = self._visible_keys[index.row()]
        val = self._data.get(key, "")
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            if index.column() == 0:
                return key
            return "[已过滤/跳过翻译]" if val == FILTERED_TAG else val
        if role == Qt.ItemDataRole.ForegroundRole and index.column() == 1:
            if val == FILTERED_TAG:
                return QColor("#eab308")  # Amber for filtered
            if not val.strip():
                return QColor("#475569")  # Slate for untranslated
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        base = super().flags(index)
        if index.column() == 1 and self._data.get(self._visible_keys[index.row()]) != FILTERED_TAG:
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def setData(self, index: QModelIndex, value, role: int = Qt.ItemDataRole.EditRole) -> bool:  # noqa: N802
        if index.isValid() and index.column() == 1 and role == Qt.ItemDataRole.EditRole:
            key = self._visible_keys[index.row()]
            self._data[key] = str(value)
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole])
            return True
        return False


class ExtractWorker(QThread):
    finished_ok = Signal(list)
    failed = Signal(str)

    def __init__(self, info: GameInfo) -> None:
        super().__init__()
        self.info = info

    def run(self) -> None:
        try:
            if self.info.is_mvmz:
                texts = extract_mvmz_texts(self.info)
            elif self.info.engine in ("RPG Maker XP", "RPG Maker VX", "RPG Maker VX Ace"):
                texts = extract_rgss_texts(self.info)
            elif self.info.engine == "RPG Maker 2000/2003":
                texts = extract_2k3_texts(self.info)
            elif self.info.engine == "Wolf RPG":
                texts = extract_wolf_texts(self.info)
            else:
                raise ValueError(f"暂不支持提取该引擎: {self.info.engine}")
            self.finished_ok.emit(texts)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class TranslateWorker(QThread):
    batch_done = Signal(dict, int, int, int, int)  # dict, done_lines, total_lines, batch_idx, total_batches
    log_msg = Signal(str)
    finished_all = Signal()
    failed = Signal(str)

    def __init__(
        self,
        dict_path: Path,
        config: TranslatorConfig,
        glossary: dict[str, str],
    ) -> None:
        super().__init__()
        self.dict_path = dict_path
        self.config = config
        self.glossary = glossary
        self._stop_flag = False

    def stop(self) -> None:
        self._stop_flag = True

    def run(self) -> None:
        try:
            data = load_json_dict(self.dict_path)
            pending = get_untranslated(data)
            total = len(pending)
            if total == 0:
                self.log_msg.emit("没有待翻译的词条。")
                self.finished_all.emit()
                return

            done = 0
            bs = max(1, self.config.batch_size)
            batches = [pending[i : i + bs] for i in range(0, total, bs)]
            total_batches = len(batches)
            done_batches = 0
            lock = threading.Lock()
            max_w = max(1, self.config.max_workers)

            pool = ThreadPoolExecutor(max_workers=max_w)
            in_flight = set()
            next_idx = 0

            def _submit_next() -> None:
                nonlocal next_idx
                while len(in_flight) < max_w and next_idx < total_batches and not self._stop_flag:
                    b = batches[next_idx]
                    next_idx += 1
                    fut = pool.submit(
                        translate_batch,
                        b,
                        self.config,
                        self.glossary,
                        None,
                        self.log_msg.emit,
                    )
                    in_flight.add(fut)

            _submit_next()
            while in_flight:
                if self._stop_flag:
                    for f in in_flight:
                        f.cancel()
                    pool.shutdown(wait=False, cancel_futures=True)
                    self.log_msg.emit("已立即停止调度新批次（已完成的译文已保存）。")
                    break

                finished_set, in_flight = wait(in_flight, timeout=0.25, return_when=FIRST_COMPLETED)
                for fut in finished_set:
                    if self._stop_flag:
                        continue
                    res = fut.result()
                    with lock:
                        for src, dst in res.items():
                            if dst:
                                data[src] = dst
                                done += 1
                        done_batches += 1
                        save_json_dict(self.dict_path, data)
                        self.batch_done.emit(dict(data), done, total, done_batches, total_batches)
                _submit_next()

            if not self._stop_flag:
                pool.shutdown(wait=False)
            self.finished_all.emit()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class TestConnWorker(QThread):
    result_ready = Signal(bool, str, int)

    def __init__(self, config: TranslatorConfig) -> None:
        super().__init__()
        self.config = config

    def run(self) -> None:
        ok, msg, ms = test_translation_connection(self.config)
        self.result_ready.emit(ok, msg, ms)


class MainWindow(QMainWindow):
    _PAGE_TITLES = ("游戏工作台", "翻译与词库工作台", "引擎与接口设置", "运行日志")

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MToolLite - RPG 游戏本地化与辅助工具")
        self.resize(1200, 790)

        self.current_game: GameInfo | None = None
        self.current_dict_path: Path | None = None
        self._extract_worker: ExtractWorker | None = None
        self._translate_worker: TranslateWorker | None = None
        self._test_worker: TestConnWorker | None = None
        self._tr_start_time: float = 0.0
        self._tr_done_in_run: int = 0
        self._tr_total_in_run: int = 0
        self._tr_batch_info: tuple[int, int] = (0, 0)
        self._anim_step: int = 0
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(400)
        self._anim_timer.timeout.connect(self._on_anim_tick)
        self._history: list[dict[str, str]] = self._load_history()
        self._ai_profiles: dict[str, dict[str, str]] = {
            k: {"base_url": v[0], "model": v[1], "api_key": ""} for k, v in _AI_PRESETS.items()
        }

        root = QWidget()
        root.setObjectName("PageRoot")
        self.setCentralWidget(root)
        main_layout = QHBoxLayout(root)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ---- Left Sidebar ----
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(215)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(14, 18, 14, 16)
        sb_layout.setSpacing(6)

        brand_row = QHBoxLayout()
        brand_lbl = QLabel("MToolLite")
        brand_lbl.setObjectName("BrandTitle")
        ver_lbl = QLabel("v0.1")
        ver_lbl.setObjectName("BrandBadge")
        brand_row.addWidget(brand_lbl)
        brand_row.addWidget(ver_lbl)
        brand_row.addStretch(1)
        sb_layout.addLayout(brand_row)

        sub_brand = QLabel("RPG 本地化 & 辅助工作台")
        sub_brand.setObjectName("MutedText")
        sb_layout.addWidget(sub_brand)
        sb_layout.addSpacing(14)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        nav_labels = ("🎮  游戏工作台", "🌐  翻译与词库", "⚙  引擎设置", "📋  运行日志")
        for idx, text in enumerate(nav_labels):
            btn = QPushButton(text)
            btn.setObjectName("NavBtn")
            btn.setCheckable(True)
            if idx == 0:
                btn.setChecked(True)
            self._nav_group.addButton(btn, idx)
            sb_layout.addWidget(btn)

        sb_layout.addStretch(1)
        tip = QLabel("快捷键提示\n游戏内按 F9 呼出修改器")
        tip.setStyleSheet(
            "background-color: #0b1120; border: 1px solid #1f2937; border-radius: 8px; "
            "padding: 10px; color: #64748b; font-size: 11px;"
        )
        sb_layout.addWidget(tip)
        main_layout.addWidget(sidebar)

        # ---- Right Content Area ----
        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(0)

        top_bar = QFrame()
        top_bar.setObjectName("TopBar")
        top_bar.setFixedHeight(56)
        tb_layout = QHBoxLayout(top_bar)
        tb_layout.setContentsMargins(22, 0, 22, 0)
        self.lbl_page_title = QLabel(self._PAGE_TITLES[0])
        self.lbl_page_title.setObjectName("PageTitle")
        self.lbl_status_pill = QLabel("● 未加载游戏")
        self.lbl_status_pill.setObjectName("GameStatusPill")
        tb_layout.addWidget(self.lbl_page_title)
        tb_layout.addStretch(1)
        tb_layout.addWidget(self.lbl_status_pill)
        right_col.addWidget(top_bar)

        self.pages = QStackedWidget()
        right_col.addWidget(self.pages, 1)
        main_layout.addLayout(right_col, 1)

        self._build_home_page()
        self._build_translator_page()
        self._build_settings_page()
        self._build_log_page()

        self._nav_group.idClicked.connect(self._switch_page)
        self._load_settings()
        self._refresh_history_list()
        self.log("MToolLite 已就绪。拖入游戏文件夹或 .exe 即可开始。")

    def _switch_page(self, idx: int) -> None:
        self.pages.setCurrentIndex(idx)
        self.lbl_page_title.setText(self._PAGE_TITLES[idx])
        btn = self._nav_group.button(idx)
        if btn:
            btn.setChecked(True)

    # ---- Page 1: Home / Launcher ----
    def _build_home_page(self) -> None:
        page = QWidget()
        page.setObjectName("PageRoot")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)

        self.drop_zone = DropZoneWidget()
        self.drop_zone.path_dropped.connect(self.load_game)
        self.drop_zone.browse_dir_clicked.connect(self._browse_game_dir)
        self.drop_zone.browse_exe_clicked.connect(self._browse_game_exe)
        layout.addWidget(self.drop_zone)

        mid_row = QHBoxLayout()
        mid_row.setSpacing(14)

        info_card = QFrame()
        info_card.setObjectName("Card")
        ic_layout = QVBoxLayout(info_card)
        ic_layout.setContentsMargins(16, 14, 16, 14)
        ic_layout.setSpacing(8)

        hdr = QHBoxLayout()
        ic_title = QLabel("当前游戏信息")
        ic_title.setObjectName("CardTitle")
        self.lbl_engine = QLabel("未识别")
        self.lbl_engine.setObjectName("EngineBadge")
        hdr.addWidget(ic_title)
        hdr.addStretch(1)
        hdr.addWidget(self.lbl_engine)
        ic_layout.addLayout(hdr)

        self.lbl_root = QLabel("根目录: -")
        self.lbl_root.setObjectName("MutedText")
        self.lbl_root.setWordWrap(True)
        self.lbl_data = QLabel("数据目录: -")
        self.lbl_data.setObjectName("MutedText")
        self.lbl_data.setWordWrap(True)
        self.lbl_exe = QLabel("主程序: -")
        self.lbl_exe.setObjectName("MutedText")
        self.lbl_exe.setWordWrap(True)
        ic_layout.addWidget(self.lbl_root)
        ic_layout.addWidget(self.lbl_data)
        ic_layout.addWidget(self.lbl_exe)
        ic_layout.addStretch(1)
        mid_row.addWidget(info_card, 5)

        act_card = QFrame()
        act_card.setObjectName("Card")
        ac_layout = QVBoxLayout(act_card)
        ac_layout.setContentsMargins(16, 14, 16, 14)
        ac_layout.setSpacing(10)

        ac_title = QLabel("快捷操作面板")
        ac_title.setObjectName("CardTitle")
        ac_layout.addWidget(ac_title)

        self.chk_capture = QCheckBox("游玩时捕获遗漏文本 (生成 untranslated_capture.json)")
        ac_layout.addWidget(self.chk_capture)

        grid = QGridLayout()
        grid.setSpacing(8)
        self.btn_extract = QPushButton("1. 提取游戏文本")
        self.btn_extract.setObjectName("PrimaryBtn")
        self.btn_extract.clicked.connect(self._on_extract)

        self.btn_mount_tr = QPushButton("2. 挂载翻译补丁")
        self.btn_mount_tr.setObjectName("PrimaryBtn")
        self.btn_mount_tr.clicked.connect(self._on_mount_translator)

        self.btn_mount_cheat = QPushButton("3. 挂载 F9 修改器")
        self.btn_mount_cheat.setObjectName("PrimaryBtn")
        self.btn_mount_cheat.clicked.connect(self._on_mount_cheat)

        self.btn_launch = QPushButton("▶ 启动游戏")
        self.btn_launch.setObjectName("SuccessBtn")
        self.btn_launch.clicked.connect(self._on_launch_game)

        self.btn_unmount = QPushButton("↺ 卸载并还原原版")
        self.btn_unmount.setObjectName("DangerBtn")
        self.btn_unmount.clicked.connect(self._on_unmount_all)

        grid.addWidget(self.btn_extract, 0, 0)
        grid.addWidget(self.btn_mount_tr, 0, 1)
        grid.addWidget(self.btn_mount_cheat, 1, 0)
        grid.addWidget(self.btn_launch, 1, 1)
        grid.addWidget(self.btn_unmount, 2, 0, 1, 2)
        ac_layout.addLayout(grid)

        # In-card Mount Status Indicator Pill
        self.lbl_mount_status = QLabel("挂载状态: 未挂载任何插件")
        self.lbl_mount_status.setStyleSheet(
            "background-color: #0b1120; border: 1px solid #1f2937; border-radius: 8px; "
            "padding: 7px 10px; color: #64748b; font-size: 12px; font-weight: 500;"
        )
        ac_layout.addWidget(self.lbl_mount_status)
        mid_row.addWidget(act_card, 6)

        layout.addLayout(mid_row)

        hist_card = QFrame()
        hist_card.setObjectName("Card")
        hc_layout = QVBoxLayout(hist_card)
        hc_layout.setContentsMargins(16, 12, 16, 12)
        hc_layout.setSpacing(8)
        hc_title = QLabel("最近游玩 / 历史游戏（双击快速加载）")
        hc_title.setObjectName("CardTitle")
        hc_layout.addWidget(hc_title)

        self.history_list = QListWidget()
        self.history_list.setObjectName("HistoryList")
        self.history_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.history_list.customContextMenuRequested.connect(self._show_history_context_menu)
        self.history_list.itemDoubleClicked.connect(self._on_history_double_click)
        hc_layout.addWidget(self.history_list)
        layout.addWidget(hist_card, 1)

        self.pages.addWidget(page)

    # ---- Page 2: Translator & Dictionary ----
    def _build_translator_page(self) -> None:
        page = QWidget()
        page.setObjectName("PageRoot")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # Clean Mode & Engine Selector Card
        cfg_card = QFrame()
        cfg_card.setObjectName("Card")
        cfg_layout = QVBoxLayout(cfg_card)
        cfg_layout.setContentsMargins(16, 14, 16, 14)
        cfg_layout.setSpacing(10)

        row1 = QHBoxLayout()
        row1.setSpacing(10)

        self.cmb_tr_mode = QComboBox()
        self.cmb_tr_mode.setMinimumWidth(130)
        self.cmb_tr_mode.addItems(["AI 翻译", "机器翻译"])
        self.cmb_tr_mode.currentTextChanged.connect(self._on_mode_changed)

        self.cmb_tr_engine = QComboBox()
        self.cmb_tr_engine.setMinimumWidth(240)
        self.cmb_tr_engine.currentTextChanged.connect(self._on_engine_changed)

        self.btn_test_quick = QPushButton("🔌 测试连接")
        self.btn_test_quick.clicked.connect(lambda: self._run_connection_test(None))

        btn_go_settings = QPushButton("⚙ 接口详细设置")
        btn_go_settings.clicked.connect(lambda: self._switch_page(2))

        row1.addWidget(QLabel("翻译方式:"))
        row1.addWidget(self.cmb_tr_mode)
        row1.addWidget(QLabel("翻译引擎 / 模型:"))
        row1.addWidget(self.cmb_tr_engine, 1)
        row1.addWidget(self.btn_test_quick)
        row1.addWidget(btn_go_settings)
        cfg_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        self.inp_glossary = QLineEdit()
        self.inp_glossary.setPlaceholderText("可选：选择专有名词术语表 glossary.json")
        btn_glossary = QPushButton("选择词库")
        btn_glossary.clicked.connect(self._browse_glossary)
        row2.addWidget(QLabel("术语词库:"))
        row2.addWidget(self.inp_glossary, 1)
        row2.addWidget(btn_glossary)
        cfg_layout.addLayout(row2)
        layout.addWidget(cfg_card)

        # Stats & Progress Card
        stat_card = QFrame()
        stat_card.setObjectName("Card")
        sc_layout = QVBoxLayout(stat_card)
        sc_layout.setContentsMargins(16, 12, 16, 12)
        sc_layout.setSpacing(10)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.lbl_metric_total = QLabel("总词条: 0")
        self.lbl_metric_total.setObjectName("MetricPill")
        self.lbl_metric_done = QLabel("已翻译: 0")
        self.lbl_metric_done.setObjectName("MetricPill")
        self.lbl_metric_todo = QLabel("待翻译: 0")
        self.lbl_metric_todo.setObjectName("MetricPill")
        self.lbl_metric_filtered = QLabel("已过滤: 0")
        self.lbl_metric_filtered.setObjectName("MetricPill")

        btn_load_dict = QPushButton("打开字典")
        btn_load_dict.clicked.connect(self._browse_dict)
        btn_save_dict = QPushButton("保存修改")
        btn_save_dict.clicked.connect(self._save_current_dict)
        btn_merge_cap = QPushButton("合并漏词")
        btn_merge_cap.clicked.connect(self._merge_captured)

        # Quick Filter Language Tool
        self.cmb_filter_lang = QComboBox()
        self.cmb_filter_lang.setMinimumWidth(110)
        self.cmb_filter_lang.addItem("过滤: 中文", "chinese")
        self.cmb_filter_lang.addItem("过滤: 日文假名", "japanese")
        self.cmb_filter_lang.addItem("过滤: 纯英文", "english")
        self.cmb_filter_lang.addItem("过滤: 韩文", "korean")

        btn_run_filter = QPushButton("⚡ 一键过滤")
        btn_run_filter.clicked.connect(self._on_auto_filter_clicked)

        self.btn_start_tr = QPushButton("▶ 开始批量翻译")
        self.btn_start_tr.setObjectName("PrimaryBtn")
        self.btn_start_tr.clicked.connect(self._on_start_translate)
        self.btn_stop_tr = QPushButton("⏸ 暂停")
        self.btn_stop_tr.setEnabled(False)
        self.btn_stop_tr.clicked.connect(self._on_stop_translate)

        for w in (self.lbl_metric_total, self.lbl_metric_done, self.lbl_metric_todo, self.lbl_metric_filtered):
            bar.addWidget(w)
        bar.addSpacing(6)
        bar.addWidget(self.cmb_filter_lang)
        bar.addWidget(btn_run_filter)
        bar.addStretch(1)
        for b in (btn_load_dict, btn_save_dict, btn_merge_cap, self.btn_start_tr, self.btn_stop_tr):
            bar.addWidget(b)
        sc_layout.addLayout(bar)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setValue(0)
        sc_layout.addWidget(self.progress)

        self.lbl_tr_runtime = QLabel("状态: 空闲")
        self.lbl_tr_runtime.setObjectName("MutedText")
        sc_layout.addWidget(self.lbl_tr_runtime)
        layout.addWidget(stat_card)

        # Filter + Table
        flt_row = QHBoxLayout()
        flt_row.setSpacing(10)
        self.inp_search = QLineEdit()
        self.inp_search.setPlaceholderText("🔍 搜索原文或译文关键词...")
        self.inp_search.textChanged.connect(self._apply_table_filter)
        self.cmb_filter = QComboBox()
        self.cmb_filter.setMinimumWidth(150)
        self.cmb_filter.addItem("全部词条 (不含已过滤)", "all")
        self.cmb_filter.addItem("仅未翻译", "untranslated")
        self.cmb_filter.addItem("已翻译", "translated")
        self.cmb_filter.addItem("含控制符", "coded")
        self.cmb_filter.addItem("🚫 被过滤的内容", "filtered")
        self.cmb_filter.currentIndexChanged.connect(self._apply_table_filter)
        flt_row.addWidget(self.inp_search, 1)
        flt_row.addWidget(self.cmb_filter)
        layout.addLayout(flt_row)

        self.table_model = DictTableModel()
        self.table = QTableView()
        self.table.setModel(self.table_model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

        self.pages.addWidget(page)

    # ---- Page 3: Engine Settings ----
    def _make_stepper(self, spin: QSpinBox) -> QHBoxLayout:
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spin.setFixedWidth(56)
        btn_dec = QPushButton("−")
        btn_dec.setFixedSize(30, 32)
        btn_dec.setStyleSheet("padding: 0px; font-size: 15px; font-weight: bold;")
        btn_dec.clicked.connect(spin.stepDown)
        btn_inc = QPushButton("+")
        btn_inc.setFixedSize(30, 32)
        btn_inc.setStyleSheet("padding: 0px; font-size: 15px; font-weight: bold;")
        btn_inc.clicked.connect(spin.stepUp)
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(btn_dec)
        row.addWidget(spin)
        row.addWidget(btn_inc)
        return row

    def _build_settings_page(self) -> None:
        page = QWidget()
        page.setObjectName("PageRoot")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 16, 22, 16)
        layout.setSpacing(14)

        top_nav = QHBoxLayout()
        btn_back = QPushButton("← 返回翻译工作台")
        btn_back.clicked.connect(lambda: self._switch_page(1))
        top_nav.addWidget(btn_back)
        top_nav.addStretch(1)
        layout.addLayout(top_nav)

        # Card 1: AI Settings
        ai_card = QFrame()
        ai_card.setObjectName("Card")
        ai_layout = QVBoxLayout(ai_card)
        ai_layout.setContentsMargins(18, 16, 18, 16)
        ai_layout.setSpacing(12)

        ai_hdr = QHBoxLayout()
        ai_title = QLabel("AI 大模型翻译配置 (OpenAI 兼容接口)")
        ai_title.setObjectName("CardTitle")
        self.lbl_ai_test_status = QLabel("")
        self.lbl_ai_test_status.setObjectName("MutedText")
        self.btn_test_ai = QPushButton("🔌 测试 AI 连接")
        self.btn_test_ai.clicked.connect(lambda: self._run_connection_test("ai"))
        ai_hdr.addWidget(ai_title)
        ai_hdr.addStretch(1)
        ai_hdr.addWidget(self.lbl_ai_test_status)
        ai_hdr.addWidget(self.btn_test_ai)
        ai_layout.addLayout(ai_hdr)

        ai_form = QFormLayout()
        ai_form.setSpacing(10)
        self.cmb_ai_preset = QComboBox()
        self.cmb_ai_preset.addItems(list(_AI_PRESETS.keys()))
        self.cmb_ai_preset.currentTextChanged.connect(self._on_ai_preset_changed_in_settings)

        self.inp_base_url = QLineEdit("https://api.deepseek.com/v1")
        self.inp_model = QLineEdit("deepseek-chat")

        key_row = QHBoxLayout()
        self.inp_api_key = QLineEdit(os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY", ""))
        self.inp_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_api_key.setPlaceholderText("输入 API Key（本地接口可留空）")
        btn_eye = QPushButton("显示")
        btn_eye.setCheckable(True)
        btn_eye.setMinimumWidth(64)
        btn_eye.toggled.connect(
            lambda checked: (
                self.inp_api_key.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password),
                btn_eye.setText("隐藏" if checked else "显示"),
            )
        )
        key_row.addWidget(self.inp_api_key, 1)
        key_row.addWidget(btn_eye)

        param_row = QHBoxLayout()
        self.spin_batch = QSpinBox()
        self.spin_batch.setRange(1, 200)
        self.spin_batch.setValue(50)
        self.spin_workers = QSpinBox()
        self.spin_workers.setRange(1, 16)
        self.spin_workers.setValue(4)
        self.cmb_thinking = QComboBox()
        self.cmb_thinking.addItem("关闭思考 (最快)", "off")
        self.cmb_thinking.addItem("低思考 (low)", "low")
        self.cmb_thinking.addItem("默认 (由模型决定)", "default")
        self.cmb_thinking.setMinimumWidth(150)
        param_row.addWidget(QLabel("每批条数:"))
        param_row.addLayout(self._make_stepper(self.spin_batch))
        param_row.addSpacing(12)
        param_row.addWidget(QLabel("并发线程:"))
        param_row.addLayout(self._make_stepper(self.spin_workers))
        param_row.addSpacing(12)
        param_row.addWidget(QLabel("思考模式:"))
        param_row.addWidget(self.cmb_thinking)
        param_row.addStretch(1)

        ai_form.addRow("当前 AI 配置槽:", self.cmb_ai_preset)
        ai_form.addRow("API Base URL:", self.inp_base_url)
        ai_form.addRow("模型名称 (Model):", self.inp_model)
        ai_form.addRow("API Key:", key_row)
        ai_form.addRow("并发参数:", param_row)

        prompt_box = QVBoxLayout()
        prompt_hdr = QHBoxLayout()
        prompt_hdr.addWidget(QLabel("自定义翻译风格/角色提示词 (System Prompt，格式与占位符规则会自动附加):"))
        prompt_hdr.addStretch(1)
        btn_reset_prompt = QPushButton("恢复默认")
        btn_reset_prompt.clicked.connect(
            lambda: self.inp_custom_prompt.setPlainText(
                DEFAULT_SYSTEM_PROMPT.format(target_lang="Simplified Chinese")
            )
        )
        prompt_hdr.addWidget(btn_reset_prompt)
        self.inp_custom_prompt = QPlainTextEdit()
        self.inp_custom_prompt.setMaximumHeight(82)
        self.inp_custom_prompt.setPlainText(DEFAULT_SYSTEM_PROMPT.format(target_lang="Simplified Chinese"))
        prompt_box.addLayout(prompt_hdr)
        prompt_box.addWidget(self.inp_custom_prompt)

        ai_layout.addLayout(ai_form)
        ai_layout.addLayout(prompt_box)
        layout.addWidget(ai_card)

        # Card 2: Machine Translation Settings
        mt_card = QFrame()
        mt_card.setObjectName("Card")
        mt_layout = QVBoxLayout(mt_card)
        mt_layout.setContentsMargins(18, 16, 18, 16)
        mt_layout.setSpacing(12)

        mt_hdr = QHBoxLayout()
        mt_title = QLabel("机器翻译接口配置")
        mt_title.setObjectName("CardTitle")
        self.lbl_mt_test_status = QLabel("")
        self.lbl_mt_test_status.setObjectName("MutedText")
        self.btn_test_mt = QPushButton("🔌 测试机器翻译连接")
        self.btn_test_mt.clicked.connect(lambda: self._run_connection_test("mt"))
        mt_hdr.addWidget(mt_title)
        mt_hdr.addStretch(1)
        mt_hdr.addWidget(self.lbl_mt_test_status)
        mt_hdr.addWidget(self.btn_test_mt)
        mt_layout.addLayout(mt_hdr)

        mt_form = QFormLayout()
        mt_form.setSpacing(10)
        self.cmb_mt_provider = QComboBox()
        self.cmb_mt_provider.addItems(list(_MT_PRESETS.keys()))
        self.cmb_mt_provider.currentTextChanged.connect(self._on_mt_preset_changed)
        self.inp_mt_endpoint = QLineEdit("https://translate.googleapis.com/translate_a/single")
        self.inp_mt_app_id = QLineEdit()
        self.inp_mt_app_id.setPlaceholderText("仅百度翻译等需要 AppID 的接口填写")
        self.inp_mt_secret = QLineEdit()
        self.inp_mt_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_mt_secret.setPlaceholderText("仅需要 Secret Key 的接口填写")

        mt_form.addRow("机器翻译路径:", self.cmb_mt_provider)
        mt_form.addRow("接口地址 (Endpoint):", self.inp_mt_endpoint)
        mt_form.addRow("App ID:", self.inp_mt_app_id)
        mt_form.addRow("Secret Key:", self.inp_mt_secret)
        mt_layout.addLayout(mt_form)
        layout.addWidget(mt_card)

        save_row = QHBoxLayout()
        save_row.addStretch(1)
        btn_save_cfg = QPushButton("💾 保存设置到本地")
        btn_save_cfg.setObjectName("PrimaryBtn")
        btn_save_cfg.clicked.connect(self._save_settings_clicked)
        save_row.addWidget(btn_save_cfg)
        layout.addLayout(save_row)
        layout.addStretch(1)

        self.pages.addWidget(page)

    # ---- Page 4: Log ----
    def _build_log_page(self) -> None:
        page = QWidget()
        page.setObjectName("PageRoot")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        top = QHBoxLayout()
        top.addStretch(1)
        btn_clear = QPushButton("清空日志")
        btn_clear.clicked.connect(lambda: self.log_view.clear())
        top.addWidget(btn_clear)
        layout.addLayout(top)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 12px;")
        layout.addWidget(self.log_view, 1)
        self.pages.addWidget(page)

    # ---- Settings & Mode Switching ----
    def _commit_active_ai_profile(self, profile_name: str | None = None) -> None:
        key = profile_name or self.cmb_ai_preset.currentText()
        if key in self._ai_profiles:
            self._ai_profiles[key] = {
                "base_url": self.inp_base_url.text().strip(),
                "model": self.inp_model.text().strip(),
                "api_key": self.inp_api_key.text().strip(),
            }

    def _apply_ai_profile(self, profile_name: str) -> None:
        prof = self._ai_profiles.get(profile_name)
        if prof is not None:
            self.inp_base_url.setText(prof.get("base_url", ""))
            self.inp_model.setText(prof.get("model", ""))
            self.inp_api_key.setText(prof.get("api_key", ""))

    def _on_mode_changed(self, mode_text: str) -> None:
        self.cmb_tr_engine.blockSignals(True)
        self.cmb_tr_engine.clear()
        if mode_text == "AI 翻译":
            self.cmb_tr_engine.addItems(list(_AI_PRESETS.keys()))
            self.cmb_tr_engine.setCurrentText(self.cmb_ai_preset.currentText())
        else:
            self.cmb_tr_engine.addItems(list(_MT_PRESETS.keys()))
            self.cmb_tr_engine.setCurrentText(self.cmb_mt_provider.currentText())
        self.cmb_tr_engine.blockSignals(False)
        self._save_settings()

    def _on_engine_changed(self, engine_text: str) -> None:
        if not engine_text:
            return
        if self.cmb_tr_mode.currentText() == "AI 翻译":
            if engine_text != self.cmb_ai_preset.currentText():
                self._commit_active_ai_profile(self.cmb_ai_preset.currentText())
                self.cmb_ai_preset.blockSignals(True)
                self.cmb_ai_preset.setCurrentText(engine_text)
                self.cmb_ai_preset.blockSignals(False)
                self._apply_ai_profile(engine_text)
        else:
            if engine_text in _MT_PRESETS and engine_text != self.cmb_mt_provider.currentText():
                self.cmb_mt_provider.setCurrentText(engine_text)
        self._save_settings()

    def _on_ai_preset_changed_in_settings(self, preset_name: str) -> None:
        if not preset_name:
            return
        # Save edits from previous profile before switching
        prev = self.cmb_tr_engine.currentText() if self.cmb_tr_mode.currentText() == "AI 翻译" else None
        if prev and prev in self._ai_profiles and prev != preset_name:
            self._commit_active_ai_profile(prev)
        self._apply_ai_profile(preset_name)
        if self.cmb_tr_mode.currentText() == "AI 翻译":
            self.cmb_tr_engine.blockSignals(True)
            self.cmb_tr_engine.setCurrentText(preset_name)
            self.cmb_tr_engine.blockSignals(False)
        self._save_settings()

    def _on_mt_preset_changed(self, name: str) -> None:
        _, endpoint = _MT_PRESETS.get(name, ("google_free", ""))
        if endpoint:
            self.inp_mt_endpoint.setText(endpoint)

    def _build_current_config(self, force_mode: str | None = None) -> TranslatorConfig:
        mode = force_mode or ("ai" if self.cmb_tr_mode.currentText() == "AI 翻译" else "mt")
        mt_key = self.cmb_mt_provider.currentText() if force_mode == "mt" else (
            self.cmb_tr_engine.currentText() if mode == "mt" else self.cmb_mt_provider.currentText()
        )
        mt_provider, _ = _MT_PRESETS.get(mt_key, ("google_free", ""))
        return TranslatorConfig(
            api_key=self.inp_api_key.text().strip(),
            base_url=self.inp_base_url.text().strip(),
            model=self.inp_model.text().strip(),
            custom_prompt=self.inp_custom_prompt.toPlainText().strip(),
            thinking_mode=self.cmb_thinking.currentData() or "off",
            batch_size=self.spin_batch.value(),
            max_workers=self.spin_workers.value(),
            mode=mode,
            mt_provider=mt_provider,
            mt_endpoint=self.inp_mt_endpoint.text().strip(),
            mt_app_id=self.inp_mt_app_id.text().strip(),
            mt_secret_key=self.inp_mt_secret.text().strip(),
        )

    def _run_connection_test(self, force_mode: str | None) -> None:
        cfg = self._build_current_config(force_mode)
        self.btn_test_ai.setEnabled(False)
        self.btn_test_mt.setEnabled(False)
        self.btn_test_quick.setEnabled(False)
        target_lbl = self.lbl_ai_test_status if cfg.mode == "ai" else self.lbl_mt_test_status
        target_lbl.setText("⏳ 正在测试连接...")
        target_lbl.setStyleSheet("color: #38bdf8;")

        self._test_worker = TestConnWorker(cfg)
        self._test_worker.result_ready.connect(lambda ok, msg, ms: self._on_test_done(cfg.mode, ok, msg, ms))
        self._test_worker.start()

    def _on_test_done(self, mode: str, ok: bool, msg: str, ms: int) -> None:
        self.btn_test_ai.setEnabled(True)
        self.btn_test_mt.setEnabled(True)
        self.btn_test_quick.setEnabled(True)
        lbl = self.lbl_ai_test_status if mode == "ai" else self.lbl_mt_test_status
        if ok:
            text = f"✅ 连接正常 ({ms} ms) | 示例译文: {msg}"
            lbl.setText(text)
            lbl.setStyleSheet("color: #34d399; font-weight: 600;")
            self.log(f"[{mode.upper()}] {text}")
            if self.pages.currentIndex() == 1:
                QMessageBox.information(self, "连接测试成功", text)
        else:
            text = f"❌ 连接失败 ({ms} ms): {msg}"
            lbl.setText(text)
            lbl.setStyleSheet("color: #f87171; font-weight: 600;")
            self.log(f"[{mode.upper()}] {text}")
            if self.pages.currentIndex() == 1:
                QMessageBox.warning(self, "连接测试失败", text)

    def _load_settings(self) -> None:
        cfg: dict = {}
        try:
            if _SETTINGS_FILE.is_file():
                loaded = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    cfg = loaded
        except Exception:
            cfg = {}

        saved_profiles = cfg.get("ai_profiles")
        if isinstance(saved_profiles, dict):
            for k, v in saved_profiles.items():
                if k in self._ai_profiles and isinstance(v, dict):
                    self._ai_profiles[k].update({str(sk): str(sv) for sk, sv in v.items()})

        # Backward compatibility with flat base_url/model/api_key
        active_preset = cfg.get("ai_preset", "DeepSeek (deepseek-chat)")
        if active_preset not in _AI_PRESETS:
            active_preset = "自定义 AI 接口"
        if cfg.get("base_url") or cfg.get("model"):
            self._ai_profiles[active_preset] = {
                "base_url": str(cfg.get("base_url", self._ai_profiles[active_preset]["base_url"])),
                "model": str(cfg.get("model", self._ai_profiles[active_preset]["model"])),
                "api_key": str(cfg.get("api_key", self._ai_profiles[active_preset]["api_key"])),
            }

        self.cmb_ai_preset.blockSignals(True)
        self.cmb_ai_preset.setCurrentText(active_preset)
        self.cmb_ai_preset.blockSignals(False)
        self._apply_ai_profile(active_preset)

        if cfg.get("custom_prompt"):
            self.inp_custom_prompt.setPlainText(cfg["custom_prompt"])
        if "batch_size" in cfg:
            self.spin_batch.setValue(int(cfg["batch_size"]))
        if "workers" in cfg:
            self.spin_workers.setValue(int(cfg["workers"]))
        if cfg.get("thinking_mode"):
            idx = self.cmb_thinking.findData(cfg["thinking_mode"])
            if idx >= 0:
                self.cmb_thinking.setCurrentIndex(idx)
        if cfg.get("mt_provider"):
            self.cmb_mt_provider.blockSignals(True)
            self.cmb_mt_provider.setCurrentText(cfg["mt_provider"])
            self.cmb_mt_provider.blockSignals(False)
        if cfg.get("mt_endpoint"):
            self.inp_mt_endpoint.setText(cfg["mt_endpoint"])
        if cfg.get("mt_app_id"):
            self.inp_mt_app_id.setText(cfg["mt_app_id"])
        if cfg.get("mt_secret"):
            self.inp_mt_secret.setText(cfg["mt_secret"])

        # Restore translator page mode & engine dropdown without triggering overwrites
        saved_mode = cfg.get("tr_mode", "AI 翻译")
        self.cmb_tr_mode.blockSignals(True)
        self.cmb_tr_mode.setCurrentText(saved_mode)
        self.cmb_tr_mode.blockSignals(False)

        self.cmb_tr_engine.blockSignals(True)
        self.cmb_tr_engine.clear()
        if saved_mode == "AI 翻译":
            self.cmb_tr_engine.addItems(list(_AI_PRESETS.keys()))
            self.cmb_tr_engine.setCurrentText(active_preset)
        else:
            self.cmb_tr_engine.addItems(list(_MT_PRESETS.keys()))
            self.cmb_tr_engine.setCurrentText(self.cmb_mt_provider.currentText())
        self.cmb_tr_engine.blockSignals(False)

    def _save_settings(self) -> None:
        self._commit_active_ai_profile()
        payload = {
            "tr_mode": self.cmb_tr_mode.currentText(),
            "ai_preset": self.cmb_ai_preset.currentText(),
            "ai_profiles": self._ai_profiles,
            "base_url": self.inp_base_url.text().strip(),
            "model": self.inp_model.text().strip(),
            "api_key": self.inp_api_key.text().strip(),
            "custom_prompt": self.inp_custom_prompt.toPlainText().strip(),
            "batch_size": self.spin_batch.value(),
            "workers": self.spin_workers.value(),
            "thinking_mode": self.cmb_thinking.currentData() or "off",
            "mt_provider": self.cmb_mt_provider.currentText(),
            "mt_endpoint": self.inp_mt_endpoint.text().strip(),
            "mt_app_id": self.inp_mt_app_id.text().strip(),
            "mt_secret": self.inp_mt_secret.text().strip(),
        }
        try:
            _SETTINGS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _save_settings_clicked(self) -> None:
        self._save_settings()
        self.log("设置已保存到本地。")
        QMessageBox.information(self, "保存成功", f"配置已保存至:\n{_SETTINGS_FILE}")

    # ---- History & Game Loading ----
    def log(self, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{ts}] {text}")

    def _load_history(self) -> list[dict[str, str]]:
        try:
            if _HISTORY_FILE.is_file():
                data = json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data[:12]
        except Exception:
            pass
        return []

    def _persist_history(self) -> None:
        try:
            _HISTORY_FILE.write_text(json.dumps(self._history, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        self._refresh_history_list()

    def _save_history(self, info: GameInfo) -> None:
        entry = {"name": info.root_dir.name, "engine": info.engine, "path": str(info.root_dir)}
        self._history = [h for h in self._history if h.get("path") != entry["path"]]
        self._history.insert(0, entry)
        self._history = self._history[:12]
        self._persist_history()

    def _refresh_history_list(self) -> None:
        self.history_list.clear()
        for h in self._history:
            item = QListWidgetItem(f"[{h.get('engine', '?')}]  {h.get('name', '')}   —   {h.get('path', '')}")
            item.setData(Qt.ItemDataRole.UserRole, h.get("path", ""))
            self.history_list.addItem(item)

    def _show_history_context_menu(self, pos: QPoint) -> None:
        item = self.history_list.itemAt(pos)
        menu = QMenu(self.history_list)
        menu.setStyleSheet(
            "QMenu { background-color: #1e293b; color: #f1f5f9; border: 1px solid #334155; padding: 4px; border-radius: 6px; }\n"
            "QMenu::item { padding: 6px 20px; border-radius: 4px; }\n"
            "QMenu::item:selected { background-color: #0284c7; color: #ffffff; }\n"
            "QMenu::separator { height: 1px; background: #334155; margin: 4px 8px; }"
        )

        if item:
            path_str = item.data(Qt.ItemDataRole.UserRole)
            act_load = QAction("▶ 加载此游戏", self)
            act_load.triggered.connect(lambda: self.load_game(path_str))
            menu.addAction(act_load)

            if path_str and Path(path_str).exists():
                act_open = QAction("📂 打开所在文件夹", self)
                act_open.triggered.connect(lambda: self._open_path_in_explorer(path_str))
                menu.addAction(act_open)

            act_remove = QAction("🗑️ 从历史列表中移除", self)
            act_remove.triggered.connect(lambda: self._remove_history_entry(path_str))
            menu.addAction(act_remove)
            menu.addSeparator()

        act_clean_invalid = QAction("🧹 清理所有不存在/失效游戏", self)
        act_clean_invalid.triggered.connect(self._clean_invalid_history)
        menu.addAction(act_clean_invalid)

        act_clear_all = QAction("❌ 清空全部历史记录", self)
        act_clear_all.triggered.connect(self._clear_all_history)
        menu.addAction(act_clear_all)

        menu.exec(self.history_list.viewport().mapToGlobal(pos))

    def _remove_history_entry(self, path: str) -> None:
        self._history = [h for h in self._history if h.get("path") != path]
        self._persist_history()
        self.log(f"已从历史记录移除: {path}")

    def _clean_invalid_history(self, notify: bool = True) -> int:
        before = len(self._history)
        self._history = [h for h in self._history if Path(h.get("path", "")).exists()]
        removed = before - len(self._history)
        self._persist_history()
        self.log(f"已清理 {removed} 条失效历史记录。")
        if notify and self.isVisible():
            QMessageBox.information(self, "清理完成", f"已清理 {removed} 条不存在的游戏路径。")
        return removed

    def _clear_all_history(self) -> None:
        if not self._history:
            return
        res = QMessageBox.question(
            self,
            "清空确认",
            "确定要清空所有历史游玩记录吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if res == QMessageBox.StandardButton.Yes:
            self._history.clear()
            self._persist_history()
            self.log("已清空所有历史游戏记录。")

    def _open_path_in_explorer(self, path_str: str) -> None:
        try:
            p = Path(path_str)
            target = p.parent if p.is_file() else p
            if target.is_dir():
                os.startfile(str(target))
        except Exception as exc:
            QMessageBox.warning(self, "打开文件夹失败", str(exc))

    def _on_history_double_click(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.load_game(path)

    def _browse_game_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择游戏根目录")
        if path:
            self.load_game(path)

    def _browse_game_exe(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择游戏主程序", filter="Executable (*.exe);;All (*.*)")
        if path:
            self.load_game(path)

    def load_game(self, path: str) -> None:
        try:
            info = detect_engine(path)
        except Exception as exc:  # noqa: BLE001
            err_msg = str(exc)
            if "does not exist" in err_msg or not Path(path).exists() or isinstance(exc, FileNotFoundError):
                res = QMessageBox.question(
                    self,
                    "路径不存在",
                    f"游戏路径不存在：\n{path}\n\n是否直接从历史记录中移除该项？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if res == QMessageBox.StandardButton.Yes:
                    self._remove_history_entry(path)
                return
            QMessageBox.warning(self, "识别失败", err_msg)
            return

        self.current_game = info
        self.lbl_engine.setText(info.engine)
        self.lbl_root.setText(f"根目录: {info.root_dir}")
        self.lbl_data.setText(f"数据目录: {info.data_dir or '-'}")
        self.lbl_exe.setText(f"主程序: {info.exe_path.name if info.exe_path else '-'}")
        self.lbl_status_pill.setText(f"● {info.root_dir.name}  |  {info.engine}")
        self.lbl_status_pill.setStyleSheet(
            "background-color: rgba(16, 185, 129, 0.14); color: #34d399; "
            "border: 1px solid rgba(52, 211, 153, 0.35); border-radius: 13px; padding: 4px 12px; font-size: 12px;"
        )
        self._save_history(info)
        self.log(f"已加载游戏: {info.root_dir.name} ({info.engine})")

        default_dict = info.root_dir / "ManualTransFile.json"
        if default_dict.is_file():
            self._load_dict_file(default_dict)
        self._refresh_mount_status()

    def _refresh_mount_status(self, flash_msg: str | None = None) -> None:
        if not self.current_game:
            self.btn_mount_tr.setText("2. 挂载翻译补丁")
            self.btn_mount_cheat.setText("3. 挂载 F9 修改器")
            self.lbl_mount_status.setText("挂载状态: 未加载游戏")
            return

        mounted_items: list[str] = []
        tr_on = False
        cheat_on = False

        if self.current_game.is_mvmz and self.current_game.js_dir:
            plugins_js = self.current_game.js_dir / "plugins.js"
            if plugins_js.is_file():
                txt = plugins_js.read_text(encoding="utf-8-sig", errors="ignore")
                if "MToolLite_Translator" in txt:
                    tr_on = True
                    mounted_items.append("翻译补丁")
                if "MToolLite_Cheat" in txt:
                    cheat_on = True
                    mounted_items.append("F9 修改器")
        elif self.current_game.engine in ("RPG Maker XP", "RPG Maker VX", "RPG Maker VX Ace"):
            data_dir = self.current_game.data_dir or (self.current_game.root_dir / "Data")
            if data_dir.is_dir() and any(data_dir.glob("*.mtoollite.bak")):
                tr_on = True
                mounted_items.append("RGSS 翻译补丁")
        elif self.current_game.engine == "Wolf RPG":
            data_dir = self.current_game.data_dir or (self.current_game.root_dir / "Data")
            if data_dir.is_dir() and any(data_dir.rglob("*.mtoollite.bak")):
                tr_on = True
                mounted_items.append("Wolf RPG 翻译补丁")

        self.btn_mount_tr.setText("2. 翻译补丁 (已挂载 ✓)" if tr_on else "2. 挂载翻译补丁")
        self.btn_mount_cheat.setText("3. F9 修改器 (已挂载 ✓)" if cheat_on else "3. 挂载 F9 修改器")

        if mounted_items:
            prefix = f"✅ {flash_msg} | " if flash_msg else "✅ 已挂载: "
            self.lbl_mount_status.setText(prefix + " + ".join(mounted_items))
            self.lbl_mount_status.setStyleSheet(
                "background-color: rgba(16, 185, 129, 0.14); border: 1px solid rgba(52, 211, 153, 0.4); "
                "border-radius: 8px; padding: 7px 10px; color: #34d399; font-size: 12px; font-weight: 600;"
            )
        else:
            msg = f"↺ {flash_msg}" if flash_msg else "⚪ 当前未挂载任何补丁"
            self.lbl_mount_status.setText(msg)
            self.lbl_mount_status.setStyleSheet(
                "background-color: #0b1120; border: 1px solid #1f2937; border-radius: 8px; "
                "padding: 7px 10px; color: #94a3b8; font-size: 12px; font-weight: 500;"
            )

    def _load_dict_file(self, path: Path) -> None:
        data = load_json_dict(path)
        self.current_dict_path = path
        self.table_model.set_dict(data)
        self._refresh_stats()
        self.log(f"已加载字典: {path} ({len(data)} 条)")

    def _refresh_stats(self) -> None:
        done, todo, filtered = self.table_model.stats()
        total = done + todo + filtered
        self.lbl_metric_total.setText(f"总词条: {total}")
        self.lbl_metric_done.setText(f"已翻译: {done}")
        self.lbl_metric_todo.setText(f"待翻译: {todo}")
        self.lbl_metric_filtered.setText(f"已过滤: {filtered}")
        active_total = done + todo
        self.progress.setMaximum(max(1, active_total))
        self.progress.setValue(done)

    def _get_selected_keys(self) -> list[str]:
        selection = self.table.selectionModel()
        if not selection or not selection.hasSelection():
            return []
        rows = {idx.row() for idx in selection.selectedRows()}
        keys = []
        for r in sorted(rows):
            k = self.table_model.get_key_at(r)
            if k is not None:
                keys.append(k)
        return keys

    def _on_table_context_menu(self, pos) -> None:
        keys = self._get_selected_keys()
        if not keys:
            # Fallback to item at pos if selection was empty
            idx = self.table.indexAt(pos)
            if idx.isValid():
                k = self.table_model.get_key_at(idx.row())
                if k:
                    keys = [k]
        if not keys:
            return

        menu = QMenu(self.table)
        menu.setStyleSheet(
            "QMenu { background-color: #1e293b; color: #f1f5f9; border: 1px solid #334155; padding: 4px; border-radius: 6px; }"
            "QMenu::item { padding: 6px 20px; border-radius: 4px; }"
            "QMenu::item:selected { background-color: #0284c7; color: #ffffff; }"
        )

        n = len(keys)
        act_revert = QAction(f"↺ 退回未翻译列表 ({n} 条)", self)
        act_revert.triggered.connect(lambda: self._on_revert_selected(keys))
        act_filter = QAction(f"🚫 标记为过滤 ({n} 条)", self)
        act_filter.triggered.connect(lambda: self._on_filter_selected(keys))

        menu.addAction(act_revert)
        menu.addAction(act_filter)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _on_revert_selected(self, keys: list[str]) -> None:
        n = self.table_model.revert_to_untranslated(keys)
        self._refresh_stats()
        if self.current_dict_path:
            save_json_dict(self.current_dict_path, self.table_model.get_dict())
        self.log(f"已将 {n} 条词条退回未翻译列表。")

    def _on_filter_selected(self, keys: list[str]) -> None:
        n = self.table_model.mark_filtered(keys)
        self._refresh_stats()
        if self.current_dict_path:
            save_json_dict(self.current_dict_path, self.table_model.get_dict())
        self.log(f"已手动将 {n} 条词条加入过滤列表。")

    def _on_auto_filter_clicked(self) -> None:
        data = self.table_model.get_dict()
        if not data:
            QMessageBox.information(self, "提示", "请先提取或加载字典。")
            return

        lang_type = self.cmb_filter_lang.currentData() or "chinese"
        lang_name = self.cmb_filter_lang.currentText()

        # Find matching untranslated keys
        matches = [k for k, v in data.items() if not v.strip() and detect_language_match(k, lang_type)]
        if not matches:
            QMessageBox.information(self, "提示", f"在待翻译词条中未发现匹配「{lang_name}」的文本。")
            return

        reply = QMessageBox.question(
            self,
            "确认一键过滤",
            f"检测到 {len(matches)} 条匹配「{lang_name}」的待翻译词条。\n\n"
            "过滤后它们将从待翻译列表中排除，不会消耗 API。\n"
            "（若误滤，可随时在「🚫 被过滤的内容」中右键多选退回未翻译列表）\n\n是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply == QMessageBox.StandardButton.Yes:
            n = self.table_model.mark_filtered(matches)
            self._refresh_stats()
            if self.current_dict_path:
                save_json_dict(self.current_dict_path, self.table_model.get_dict())
            self.log(f"一键过滤完成：已将 {n} 条「{lang_name}」文本移至过滤列表。")
            self.cmb_filter.setCurrentIndex(self.cmb_filter.findData("filtered"))

    def _apply_table_filter(self) -> None:
        mode = self.cmb_filter.currentData()
        self.table_model.set_filter(self.inp_search.text(), mode)

    def _on_extract(self) -> None:
        if not self.current_game:
            QMessageBox.information(self, "提示", "请先选择或拖入游戏。")
            return
        self.btn_extract.setEnabled(False)
        self.log("正在提取文本...")
        self._extract_worker = ExtractWorker(self.current_game)
        self._extract_worker.finished_ok.connect(self._on_extract_done)
        self._extract_worker.failed.connect(self._on_extract_fail)
        self._extract_worker.start()

    def _on_extract_done(self, texts: list[str]) -> None:
        self.btn_extract.setEnabled(True)
        assert self.current_game is not None
        out_path = self.current_dict_path or (self.current_game.root_dir / "ManualTransFile.json")
        existing = load_json_dict(out_path)
        merged, added = merge_extracted(existing, texts)
        save_json_dict(out_path, merged)
        self._load_dict_file(out_path)
        self.log(f"提取完成: 共 {len(texts)} 条去重文本（新增 {added} 条）-> {out_path}")
        if self.current_game.engine == "Wolf RPG" and len(texts) == 0:
            data_dir = self.current_game.data_dir or (self.current_game.root_dir / "Data")
            wolf_packs = list(self.current_game.root_dir.glob("*.wolf")) + (list(data_dir.glob("*.wolf")) if data_dir.exists() else [])
            if wolf_packs:
                self.log("⚠️ 提示: 检测到游戏使用了 .wolf 归档封包。若尚未解包，建议使用解包工具（如 wolfdec）将 .wolf 解包至 Data/ 目录后再点击提取。Wolf 引擎会自动优先读取 Data/ 散文件并支持补丁挂载。")
        self._switch_page(1)

    def _on_extract_fail(self, err: str) -> None:
        self.btn_extract.setEnabled(True)
        self.log(f"提取失败: {err}")
        QMessageBox.critical(self, "提取失败", err)

    def _browse_dict(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "打开 ManualTransFile.json", filter="JSON (*.json)")
        if path:
            self._load_dict_file(Path(path))

    def _browse_glossary(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择词库 JSON", filter="JSON (*.json)")
        if path:
            self.inp_glossary.setText(path)

    def _save_current_dict(self) -> None:
        if not self.current_dict_path:
            path, _ = QFileDialog.getSaveFileName(self, "保存字典", "ManualTransFile.json", "JSON (*.json)")
            if not path:
                return
            self.current_dict_path = Path(path)
        save_json_dict(self.current_dict_path, self.table_model.get_dict())
        self._refresh_stats()
        self.log(f"已保存字典: {self.current_dict_path}")

    def _merge_captured(self) -> None:
        if not self.current_game:
            return
        cap_path = self.current_game.root_dir / "untranslated_capture.json"
        if not cap_path.is_file():
            QMessageBox.information(self, "提示", f"未找到捕获文件:\n{cap_path}")
            return
        cap = load_json_dict(cap_path)
        merged, added = merge_extracted(self.table_model.get_dict(), list(cap.keys()))
        if self.current_dict_path:
            save_json_dict(self.current_dict_path, merged)
        self.table_model.set_dict(merged)
        self._refresh_stats()
        self.log(f"已合并捕获遗漏文本: 新增 {added} 条")

    def _on_start_translate(self) -> None:
        if not self.current_dict_path:
            QMessageBox.information(self, "提示", "请先提取或打开一个字典文件。")
            return
        cfg = self._build_current_config()
        is_local = "127.0.0.1" in cfg.base_url or "localhost" in cfg.base_url
        if cfg.mode == "ai" and not cfg.api_key and not is_local:
            QMessageBox.warning(self, "缺少 API Key", "请前往「引擎设置」填写大模型 API Key。")
            self._switch_page(2)
            return

        self._save_settings()
        save_json_dict(self.current_dict_path, self.table_model.get_dict())
        glossary = load_json_dict(self.inp_glossary.text().strip()) if self.inp_glossary.text().strip() else {}

        self.btn_start_tr.setEnabled(False)
        self.btn_stop_tr.setEnabled(True)
        self._tr_start_time = time.perf_counter()
        self._tr_done_in_run = 0
        self._tr_total_in_run = 0
        self._tr_batch_info = (0, 0)
        self._anim_step = 0
        self._anim_timer.start()
        self._on_anim_tick()
        self.log(f"开始批量翻译 ({self.cmb_tr_mode.currentText()} / {self.cmb_tr_engine.currentText()})...")
        self._translate_worker = TranslateWorker(self.current_dict_path, cfg, glossary)
        self._translate_worker.batch_done.connect(self._on_tr_batch)
        self._translate_worker.log_msg.connect(self.log)
        self._translate_worker.finished_all.connect(self._on_tr_finished)
        self._translate_worker.failed.connect(self._on_tr_failed)
        self._translate_worker.start()

    def _on_anim_tick(self) -> None:
        dots = ("·", "··", "···", "····")[self._anim_step % 4]
        spin_char = ("◐", "◓", "◑", "◒")[self._anim_step % 4]
        self._anim_step += 1
        self.btn_start_tr.setText(f"{spin_char} 翻译中{dots}")

        elapsed = max(0, int(time.perf_counter() - self._tr_start_time))
        mm, ss = divmod(elapsed, 60)
        b_done, b_total = self._tr_batch_info
        if self._tr_done_in_run > 0 and elapsed > 0:
            speed = self._tr_done_in_run / elapsed
            rem_lines = max(0, self._tr_total_in_run - self._tr_done_in_run)
            eta_s = int(rem_lines / speed) if speed > 0 else 0
            em, es = divmod(eta_s, 60)
            self.lbl_tr_runtime.setText(
                f"● 正在翻译 | 批次 {b_done}/{b_total} | 速率 {speed:.1f} 条/秒 | 已耗时 {mm:02d}:{ss:02d} | 预计剩余 {em:02d}:{es:02d}"
            )
        else:
            self.lbl_tr_runtime.setText(
                f"● 正在等待接口首批响应 ({self.cmb_tr_engine.currentText()}) | 已耗时 {mm:02d}:{ss:02d}"
            )
        self.lbl_tr_runtime.setStyleSheet("color: #38bdf8; font-weight: 600;")

    def _on_stop_translate(self) -> None:
        if self._translate_worker:
            self._translate_worker.stop()
            self.btn_stop_tr.setEnabled(False)
            self.btn_stop_tr.setText("停止中...")
            self.lbl_tr_runtime.setText("⏹ 正在安全停止（未开始批次已取消）...")
            self.lbl_tr_runtime.setStyleSheet("color: #fbbf24; font-weight: 600;")

    def _on_tr_batch(self, updated_dict: dict[str, str], done: int, total: int, b_done: int, b_total: int) -> None:
        self._tr_done_in_run = done
        self._tr_total_in_run = total
        self._tr_batch_info = (b_done, b_total)
        self.table_model.set_dict(updated_dict)
        self._refresh_stats()
        self.log(f"本轮进度: {done}/{total} (批次 {b_done}/{b_total})")

    def _on_tr_finished(self) -> None:
        self._anim_timer.stop()
        self.btn_start_tr.setEnabled(True)
        self.btn_start_tr.setText("▶ 开始批量翻译")
        self.btn_stop_tr.setEnabled(False)
        self.btn_stop_tr.setText("⏸ 暂停")
        self.lbl_tr_runtime.setText("✅ 状态: 空闲 / 本轮翻译已结束")
        self.lbl_tr_runtime.setStyleSheet("color: #34d399; font-weight: 600;")
        self.log("翻译任务结束。")

    def _on_tr_failed(self, err: str) -> None:
        self._anim_timer.stop()
        self.btn_start_tr.setEnabled(True)
        self.btn_start_tr.setText("▶ 开始批量翻译")
        self.btn_stop_tr.setEnabled(False)
        self.btn_stop_tr.setText("⏸ 暂停")
        self.lbl_tr_runtime.setText(f"❌ 出错: {err[:80]}")
        self.lbl_tr_runtime.setStyleSheet("color: #f87171; font-weight: 600;")
        self.log(f"翻译出错: {err}")
        QMessageBox.critical(self, "翻译出错", err)

    def _on_mount_translator(self) -> None:
        if not self.current_game:
            QMessageBox.information(self, "提示", "请先选择或拖入游戏。")
            return
        try:
            if self.current_game.is_mvmz:
                mount_mvmz(
                    self.current_game,
                    dict_path=self.current_dict_path,
                    capture_untranslated=self.chk_capture.isChecked(),
                )
                self.log("已无损挂载 MV/MZ 翻译插件。")
                self._refresh_mount_status("翻译补丁挂载成功")
            elif self.current_game.engine in ("RPG Maker XP", "RPG Maker VX", "RPG Maker VX Ace"):
                if not self.current_dict_path:
                    QMessageBox.warning(self, "提示", "请先提取或加载字典。")
                    return
                written = mount_rgss(self.current_game, self.current_dict_path)
                self.log(f"已应用 RGSS 翻译补丁（共 {len(written)} 个数据文件，原文件已备份）。")
                self._refresh_mount_status(f"RGSS 补丁挂载成功 ({len(written)} 个文件)")
            elif self.current_game.engine == "Wolf RPG":
                if not self.current_dict_path:
                    QMessageBox.warning(self, "提示", "请先提取或加载字典。")
                    return
                written = mount_wolf(self.current_game, self.current_dict_path)
                self.log(f"已应用 Wolf RPG 翻译补丁（共 {len(written)} 个数据文件，原文件已备份）。")
                self._refresh_mount_status(f"Wolf 补丁挂载成功 ({len(written)} 个文件)")
            else:
                QMessageBox.information(self, "提示", f"暂不支持挂载该引擎: {self.current_game.engine}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "挂载失败", str(exc))

    def _on_mount_cheat(self) -> None:
        if not self.current_game:
            QMessageBox.information(self, "提示", "请先选择或拖入游戏。")
            return
        if not self.current_game.is_mvmz:
            QMessageBox.information(self, "提示", "F9 悬浮修改器目前支持 RPG Maker MV / MZ。")
            return
        try:
            mount_cheat_mvmz(self.current_game)
            self.log("已挂载 F9 内置修改器。")
            self._refresh_mount_status("F9 修改器挂载成功")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "挂载失败", str(exc))

    def _on_launch_game(self) -> None:
        if not self.current_game or not self.current_game.exe_path:
            QMessageBox.information(self, "提示", "未找到游戏主程序 .exe。")
            return
        subprocess.Popen([str(self.current_game.exe_path)], cwd=str(self.current_game.root_dir))
        self.log(f"已启动游戏: {self.current_game.exe_path.name}")

    def _on_unmount_all(self) -> None:
        if not self.current_game:
            QMessageBox.information(self, "提示", "请先选择或拖入游戏。")
            return
        try:
            if self.current_game.is_mvmz:
                unmount_cheat_mvmz(self.current_game)
                unmount_mvmz(self.current_game)
                self.log("已卸载 MV/MZ 插件并还原 plugins.js。")
                self._refresh_mount_status("已卸载并还原原版")
            elif self.current_game.engine in ("RPG Maker XP", "RPG Maker VX", "RPG Maker VX Ace"):
                n = unmount_rgss(self.current_game)
                self.log(f"已还原 {n} 个 RGSS 数据文件。")
                self._refresh_mount_status(f"已还原 {n} 个数据文件")
            elif self.current_game.engine == "Wolf RPG":
                n = unmount_wolf(self.current_game)
                self.log(f"已还原 {n} 个 Wolf RPG 数据文件。")
                self._refresh_mount_status(f"已还原 {n} 个数据文件")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "卸载失败", str(exc))


def launch_gui() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(_MODERN_QSS)
    win = MainWindow()
    win.show()
    return app.exec()
