"""
시스템 로그 위젯
v1 ui/log_widget.py에서 임포트 경로 수정 (변경 없음).
로그 타입별 색상: error=빨간, still=보라, audio=초록, embedded=파란
"""
import datetime
import os
import subprocess
import sys
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLabel, QPushButton, QStyle,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextOption


class LogWidget(QWidget):
    """시스템 로그를 표시하는 위젯"""

    MAX_LOG_ITEMS = 500
    LOG_DIR = "logs"

    # log_type → (배경색 or None, 글자색)
    _COLORS = {
        "error":    ("#cc0000", "#ffffff"),
        "still":    ("#7B2FBE", "#ffffff"),
        "audio":    ("#006600", "#ffffff"),
        "embedded": ("#004488", "#ffffff"),
        "info":     (None,      "#cccccc"),
        "debug":    (None,      "#555555"),
    }

    log_cleared = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_date: str = ""
        self._item_count: int = 0
        self._show_debug: bool = False
        self._auto_scroll: bool = True
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header_widget = QWidget()
        header_widget.setObjectName("logHeaderArea")
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(8, 4, 8, 4)

        self._header = QLabel("SYSTEM LOG")
        self._header.setObjectName("logHeader")
        self._header.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        header_layout.addWidget(self._header)

        header_layout.addStretch()

        self._btn_debug = QPushButton("DEBUG")
        self._btn_debug.setObjectName("btnLogDebug")
        self._btn_debug.setFixedSize(60, 26)
        self._btn_debug.setToolTip("내부 디버그 로그 표시/숨김")
        self._btn_debug.setCheckable(True)
        self._btn_debug.setChecked(False)
        self._btn_debug.toggled.connect(self._on_debug_toggled)
        header_layout.addWidget(self._btn_debug)

        self._btn_open_folder = QPushButton()
        self._btn_open_folder.setObjectName("btnLogFolder")
        self._btn_open_folder.setIcon(
            self.style().standardIcon(QStyle.SP_DirOpenIcon)
        )
        self._btn_open_folder.setFixedSize(32, 26)
        self._btn_open_folder.setToolTip("Log 폴더 열기")
        self._btn_open_folder.clicked.connect(self._open_log_folder)
        header_layout.addWidget(self._btn_open_folder)

        self._btn_clear = QPushButton("Log 초기화")
        self._btn_clear.setObjectName("btnLogClear")
        self._btn_clear.setFixedSize(80, 26)
        self._btn_clear.setToolTip("화면 로그 초기화 (파일 변경 없음)")
        self._btn_clear.clicked.connect(self.clear_logs)
        header_layout.addWidget(self._btn_clear)

        layout.addWidget(header_widget)

        self._text = QTextEdit()
        self._text.setObjectName("logList")
        self._text.setReadOnly(True)
        self._text.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        self._text.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._text.setFocusPolicy(Qt.NoFocus)
        self._text.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)
        layout.addWidget(self._text)

    def _on_debug_toggled(self, checked: bool):
        self._show_debug = checked

    def _on_scroll_changed(self, value: int):
        sb = self._text.verticalScrollBar()
        self._auto_scroll = (value >= sb.maximum() - 4)

    def add_log(self, message: str, log_type: str = "info"):
        """로그 항목 추가.
        log_type: "debug" | "info" | "error" | "still" | "audio" | "embedded"
        """
        if log_type == "debug" and not self._show_debug:
            return
        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")

        if date_str != self._last_date:
            self._add_date_separator(date_str)
            self._last_date = date_str

        bg, fg = self._COLORS.get(log_type, self._COLORS["info"])
        self._insert_line(f"{time_str}  {message}", bg, fg)
        self._item_count += 1

        if self._item_count > self.MAX_LOG_ITEMS:
            self._trim_oldest()

    def _insert_line(self, text: str, bg_hex, fg_hex, align=Qt.AlignLeft):
        doc = self._text.document()
        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.End)

        char_fmt = QTextCharFormat()
        char_fmt.setForeground(QColor(fg_hex))
        if bg_hex:
            char_fmt.setBackground(QColor(bg_hex))

        block_fmt = QTextBlockFormat()
        if bg_hex:
            block_fmt.setBackground(QColor(bg_hex))
        block_fmt.setAlignment(align)

        # 문서가 비어있으면 첫 블록 재사용, 아니면 새 블록 삽입
        if doc.isEmpty():
            cursor.setBlockFormat(block_fmt)
            cursor.setBlockCharFormat(char_fmt)
            cursor.insertText(text, char_fmt)
        else:
            cursor.insertBlock(block_fmt, char_fmt)
            cursor.insertText(text, char_fmt)

        self._text.setTextCursor(cursor)
        if self._auto_scroll:
            self._text.ensureCursorVisible()

    def _trim_oldest(self):
        doc = self._text.document()
        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.Start)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        # 다음 줄바꿈 문자까지 포함해서 삭제
        cursor.movePosition(QTextCursor.NextCharacter, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        self._item_count -= 1

    def _add_date_separator(self, date_str: str):
        self._insert_line(f"──── {date_str} ────", None, "#6060a0", Qt.AlignCenter)
        self._item_count += 1

    def add_error(self, message: str):
        self.add_log(message, log_type="error")

    def add_info(self, message: str):
        self.add_log(message, log_type="info")

    def clear_logs(self):
        self._text.document().clear()
        self._last_date = ""
        self._item_count = 0
        self._auto_scroll = True
        self.log_cleared.emit()

    def _open_log_folder(self):
        log_path = os.path.abspath(self.LOG_DIR)
        os.makedirs(log_path, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(log_path)
            else:
                subprocess.Popen(["xdg-open", log_path])
        except Exception:
            pass
