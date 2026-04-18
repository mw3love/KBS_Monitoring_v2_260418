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
    QListWidget, QListWidgetItem, QLabel, QPushButton, QStyle,
    QStyledItemDelegate,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont


class _LogItemDelegate(QStyledItemDelegate):
    """로그 타입에 따라 배경색+흰 텍스트를 렌더링."""
    LOG_TYPE_ROLE = Qt.UserRole + 1

    _COLORS = {
        "error":    ("#cc0000", "#ffffff"),
        "still":    ("#7B2FBE", "#ffffff"),
        "audio":    ("#006600", "#ffffff"),
        "embedded": ("#004488", "#ffffff"),
    }

    def paint(self, painter, option, index):
        log_type = index.data(self.LOG_TYPE_ROLE)
        colors = self._COLORS.get(log_type)
        if colors:
            bg_color, fg_color = colors
            painter.save()
            painter.fillRect(option.rect, QColor(bg_color))
            painter.setFont(option.font)
            painter.setPen(QColor(fg_color))
            text_rect = option.rect.adjusted(6, 0, -6, 0)
            painter.drawText(
                text_rect,
                Qt.AlignLeft | Qt.AlignVCenter,
                index.data(Qt.DisplayRole) or "",
            )
            painter.restore()
        else:
            super().paint(painter, option, index)


class LogWidget(QWidget):
    """시스템 로그를 표시하는 위젯"""

    MAX_LOG_ITEMS = 500
    LOG_DIR = "logs"

    log_cleared = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_date: str = ""
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

        self._list = QListWidget()
        self._list.setObjectName("logList")
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._list.setSelectionMode(QListWidget.NoSelection)
        self._list.setFocusPolicy(Qt.NoFocus)
        self._list.setItemDelegate(_LogItemDelegate(self._list))
        layout.addWidget(self._list)

    def add_log(self, message: str, log_type: str = "info"):
        """로그 항목 추가.
        log_type: "info" | "error" | "still" | "audio" | "embedded"
        """
        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")

        if date_str != self._last_date:
            self._add_date_separator(date_str)
            self._last_date = date_str

        text = f"{time_str}  {message}"
        item = QListWidgetItem(text)
        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        if log_type in ("error", "still", "audio", "embedded"):
            item.setData(_LogItemDelegate.LOG_TYPE_ROLE, log_type)

        self._list.addItem(item)

        while self._list.count() > self.MAX_LOG_ITEMS:
            self._list.takeItem(0)

        self._list.scrollToBottom()

    def _add_date_separator(self, date_str: str):
        item = QListWidgetItem(f"──── {date_str} ────")
        item.setTextAlignment(Qt.AlignCenter)
        item.setForeground(QColor("#6060a0"))
        item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
        self._list.addItem(item)

    def add_error(self, message: str):
        self.add_log(message, log_type="error")

    def add_info(self, message: str):
        self.add_log(message, log_type="info")

    def clear_logs(self):
        self._list.clear()
        self._last_date = ""
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
