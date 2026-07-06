"""
시스템 로그 위젯 (v2)
QListWidget + QStyledItemDelegate 기반으로 컬럼 레이아웃, 타입 필터, pulse 애니메이션 구현
컬럼 레이아웃: 타임스탬프(68px) | 타입 배지(72px) | 메시지(1fr) | 소스(auto)
"""
import datetime
import os
import subprocess
import sys
from dataclasses import dataclass

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem,
    QLabel, QPushButton, QStyle, QLineEdit,
    QStyledItemDelegate, QAbstractItemView,
)
from PySide6.QtCore import Qt, Signal, QTimer, QRect, QSize
from PySide6.QtGui import (
    QColor, QPainter, QFont, QPen, QBrush, QFontMetrics,
)


@dataclass
class LogItemData:
    timestamp: str = ""
    log_type: str = "info"
    source: str = ""
    message: str = ""
    is_separator: bool = False
    is_newest: bool = False
    pulse_alpha: float = 0.0


class LogRowDelegate(QStyledItemDelegate):
    """로그 행 커스텀 렌더러 — 컬럼 레이아웃 + 배지 + pulse 오버레이"""

    TS_W    = 68   # 타임스탬프 컬럼 폭
    BADGE_W = 72   # 타입 배지 컬럼 폭
    SRC_MAX = 68   # 소스 컬럼 최대 폭
    ROW_H   = 22   # 일반 행 높이
    SEP_H   = 18   # 날짜 구분선 높이
    PAD     = 6    # 좌측 패딩

    # (행 배경색 hex 또는 None, 텍스트/배지 글자색)
    # black = 블랙 감지(영상 이상), error = 시스템 장애 (스트림/크래시/녹화/텔레그램)
    _TYPE_COLORS_DARK: dict[str, tuple] = {
        "black":    ("#cc0000", "#ffffff"),
        "still":    ("#7B2FBE", "#ffffff"),
        "audio":    ("#1f7a1f", "#ffffff"),
        "embedded": ("#1e5a9e", "#ffffff"),
        "error":    ("#e8730a", "#ffffff"),
        "recovery": ("#1aa68a", "#ffffff"),
        # 정파 3상태 — 전용 앰버 단일색(배지 준비/정파/해제로 상태 구분)
        "sign_prep":  ("#C89B3C", "#ffffff"),
        "sign_enter": ("#C89B3C", "#ffffff"),
        "sign_rel":   ("#C89B3C", "#ffffff"),
        "info":     (None,      "#b8b9bd"),
        "debug":    (None,      "#555565"),
    }

    # 라이트 모드: 배지 배경색은 동일(컬러 구분 유지), 메시지 fg는 어두운 톤으로
    _TYPE_COLORS_LIGHT: dict[str, tuple] = {
        # (row_bg_hex, message_fg_hex, badge_fg_hex)
        "black":    ("#cc0000", "#1a1a1a", "#ffffff"),
        "still":    ("#7B2FBE", "#1a1a1a", "#ffffff"),
        "audio":    ("#1f7a1f", "#1a1a1a", "#ffffff"),
        "embedded": ("#1e5a9e", "#1a1a1a", "#ffffff"),
        "error":    ("#e8730a", "#1a1a1a", "#ffffff"),
        "recovery": ("#1aa68a", "#1a1a1a", "#ffffff"),
        "sign_prep":  ("#C89B3C", "#1a1a1a", "#ffffff"),
        "sign_enter": ("#C89B3C", "#1a1a1a", "#ffffff"),
        "sign_rel":   ("#C89B3C", "#1a1a1a", "#ffffff"),
        "info":     (None,      "#3a3a3a", "#3a3a3a"),
        "debug":    (None,      "#888888", "#888888"),
    }

    # 테마별 보조 색상 (타임스탬프 / 소스 / separator)
    _AUX_COLORS_DARK = {
        "ts":      "#7d7e84",
        "src":     "#555565",
        "sep_ln":  "#3a3b42",
        "sep_txt": "#6060a0",
    }
    _AUX_COLORS_LIGHT = {
        "ts":      "#666666",
        "src":     "#666666",
        "sep_ln":  "#cccccc",
        "sep_txt": "#888888",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dark: bool = True

    def set_dark(self, dark: bool):
        self._dark = dark

    def _type_color(self, log_type: str) -> tuple:
        """현재 테마에 맞는 (row_bg, message_fg, badge_fg) 반환."""
        if self._dark:
            bg, fg = self._TYPE_COLORS_DARK.get(log_type, self._TYPE_COLORS_DARK["info"])
            return bg, fg, fg
        return self._TYPE_COLORS_LIGHT.get(log_type, self._TYPE_COLORS_LIGHT["info"])

    def _aux(self, key: str) -> str:
        return (self._AUX_COLORS_DARK if self._dark else self._AUX_COLORS_LIGHT)[key]

    _BADGE_LABELS: dict[str, str] = {
        "black":    "BLACK",
        "still":    "STILL",
        "audio":    "AUDIO",
        "embedded": "EMBED",
        "error":    "ERROR",
        "recovery": "복구",
        "sign_prep":  "준비",
        "sign_enter": "정파",
        "sign_rel":   "해제",
        "info":     "INFO ",
        "debug":    "DEBUG",
    }

    def sizeHint(self, option, index) -> QSize:
        data: LogItemData = index.data(Qt.UserRole)
        if data and data.is_separator:
            return QSize(0, self.SEP_H)
        return QSize(0, self.ROW_H)

    def paint(self, painter: QPainter, option, index):
        data: LogItemData = index.data(Qt.UserRole)
        if not data:
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect: QRect = option.rect

        if data.is_separator:
            self._paint_separator(painter, rect, data.timestamp, option)
            painter.restore()
            return

        # ── 행 배경 ──
        bg_hex, fg_hex, badge_fg_hex = self._type_color(data.log_type)
        if bg_hex:
            row_bg = QColor(bg_hex)
            # 복구·정파준비·정파해제는 옅은 톤(구별되되 경보만큼 강하지 않게).
            # 정파돌입(sign_enter)은 '정파 중' 상태 강조를 위해 진하게.
            if data.log_type in ("recovery", "sign_prep", "sign_rel"):
                row_bg.setAlphaF(0.10 if self._dark else 0.08)
            elif data.log_type == "sign_enter":
                row_bg.setAlphaF(0.24 if self._dark else 0.18)
            else:
                row_bg.setAlphaF(0.18 if self._dark else 0.14)
            painter.fillRect(rect, row_bg)

        # ── pulse 하이라이트 ──
        if data.is_newest and data.pulse_alpha > 0:
            # 라이트 모드는 흰색 펄스가 안보이므로 오렌지 톤 사용
            pulse_c = QColor(255, 255, 255) if self._dark else QColor("#D97757")
            pulse_c.setAlphaF(data.pulse_alpha)
            painter.fillRect(rect, pulse_c)

        # ── 폰트 설정 ──
        mono = QFont("JetBrains Mono")
        mono.setPixelSize(12)
        if not QFontMetrics(mono).inFont('A'):
            mono = QFont("Consolas")
            mono.setPixelSize(12)
        painter.setFont(mono)
        fm = QFontMetrics(mono)

        # ── 1) 타임스탬프 컬럼 ──
        ts_rect = QRect(rect.left() + self.PAD, rect.top(), self.TS_W, rect.height())
        painter.setPen(QColor(self._aux("ts")))
        painter.drawText(ts_rect, Qt.AlignVCenter | Qt.AlignLeft, data.timestamp)

        # ── 2) 타입 배지 컬럼 ──
        badge_label = self._BADGE_LABELS.get(data.log_type, data.log_type[:5].upper())
        badge_x = rect.left() + self.PAD + self.TS_W
        badge_rect = QRect(badge_x + 2, rect.top() + 3, self.BADGE_W - 8, rect.height() - 6)

        if bg_hex:
            badge_bg = QColor(bg_hex)
            painter.setBrush(QBrush(badge_bg))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(badge_rect, 3, 3)
            painter.setPen(QColor(badge_fg_hex))
        else:
            painter.setPen(QColor(badge_fg_hex))

        bold_mono = QFont(mono)
        bold_mono.setBold(True)
        painter.setFont(bold_mono)
        painter.drawText(badge_rect, Qt.AlignCenter, badge_label)
        painter.setFont(mono)

        # ── 3) 소스 컬럼 (우측) ──
        src_text = f"[{data.source}]" if data.source else ""
        src_w = 0
        if src_text:
            src_w = min(fm.horizontalAdvance(src_text) + 10, self.SRC_MAX)
            src_rect = QRect(rect.right() - src_w - self.PAD,
                             rect.top(), src_w, rect.height())
            painter.setPen(QColor(self._aux("src")))
            src_font = QFont("Pretendard")
            src_font.setPixelSize(10)
            painter.setFont(src_font)
            painter.drawText(src_rect, Qt.AlignVCenter | Qt.AlignRight, src_text)
            painter.setFont(mono)

        # ── 4) 메시지 컬럼 ──
        msg_x = badge_x + self.BADGE_W
        msg_w = rect.right() - msg_x - src_w - self.PAD * 2
        msg_rect = QRect(msg_x, rect.top(), msg_w, rect.height())
        painter.setPen(QColor(fg_hex))
        msg_elided = fm.elidedText(data.message, Qt.ElideRight, max(msg_w, 0))
        painter.drawText(msg_rect, Qt.AlignVCenter | Qt.AlignLeft, msg_elided)

        painter.restore()

    def _paint_separator(self, painter: QPainter, rect: QRect, date_str: str, _option):
        # 텍스트 양 옆에 선을 그려 배경색 의존 없이 구현
        sep_font = QFont("Pretendard")
        sep_font.setPixelSize(10)
        painter.setFont(sep_font)
        fm = QFontMetrics(sep_font)
        text_w = fm.horizontalAdvance(date_str)
        text_x = (rect.width() - text_w) // 2 + rect.left()
        mid_y = rect.center().y()
        gap = 8

        painter.setPen(QPen(QColor(self._aux("sep_ln")), 1))
        if text_x - gap > rect.left() + 8:
            painter.drawLine(rect.left() + 8, mid_y, text_x - gap, mid_y)
        painter.drawLine(text_x + text_w + gap, mid_y, rect.right() - 8, mid_y)

        painter.setPen(QColor(self._aux("sep_txt")))
        painter.drawText(
            QRect(text_x, rect.top(), text_w, rect.height()),
            Qt.AlignVCenter | Qt.AlignLeft,
            date_str,
        )


class LogWidget(QWidget):
    """시스템 로그 위젯 — QListWidget + 컬럼 레이아웃 + 타입 필터"""

    MAX_LOG_ITEMS = 500
    LOG_DIR = "logs"

    # (표시 텍스트, 필터 키, 활성 색상)
    # 필터 키는 그룹명. 그룹↔log_type 매핑은 _GROUP_TYPES 참조.
    _FILTER_DEFS: list[tuple] = [
        ("ALL",   "ALL",   "#D97757"),
        ("VIDEO", "VIDEO", "#cc0000"),
        ("AUDIO", "AUDIO", "#2ea82e"),
        ("ERROR", "ERROR", "#e8730a"),
        ("INFO",  "INFO",  "#7d7e84"),
    ]

    # 필터 그룹 → 포함 log_type 집합
    _GROUP_TYPES: dict[str, set] = {
        "VIDEO": {"black", "still"},
        "AUDIO": {"audio", "embedded"},
        "ERROR": {"error"},
        "INFO":  {"info", "recovery", "sign_prep", "sign_enter", "sign_rel"},
    }

    log_cleared = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_date: str = ""
        self._total_count: int = 0
        self._show_debug: bool = False
        self._auto_scroll: bool = True
        self._active_type_filters: set = {"ALL"}
        self._keyword: str = ""
        self._filter_buttons: dict[str, QPushButton] = {}
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 헤더 행 ──
        header_widget = QWidget()
        header_widget.setObjectName("logHeaderArea")
        header_row = QHBoxLayout(header_widget)
        header_row.setContentsMargins(8, 4, 8, 4)
        header_row.setSpacing(4)

        header_label = QLabel("SYSTEM LOG")
        header_label.setObjectName("logHeader")
        header_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        header_row.addWidget(header_label)

        header_row.addStretch()

        self._count_badge = QLabel("0")
        self._count_badge.setObjectName("logCountBadge")
        self._count_badge.setAlignment(Qt.AlignCenter)
        self._count_badge.setMinimumWidth(28)
        header_row.addWidget(self._count_badge)

        self._btn_search = QPushButton("🔍")
        self._btn_search.setObjectName("btnLogSearch")
        self._btn_search.setFixedSize(28, 24)
        self._btn_search.setToolTip("키워드 검색 (토글)")
        self._btn_search.setCheckable(True)
        self._btn_search.toggled.connect(self._toggle_search_bar)
        header_row.addWidget(self._btn_search)

        self._btn_debug = QPushButton("DEBUG")
        self._btn_debug.setObjectName("btnLogDebug")
        self._btn_debug.setFixedSize(56, 24)
        self._btn_debug.setToolTip("내부 디버그 로그 표시/숨김")
        self._btn_debug.setCheckable(True)
        self._btn_debug.setChecked(False)
        self._btn_debug.toggled.connect(self._on_debug_toggled)
        header_row.addWidget(self._btn_debug)

        self._btn_open_folder = QPushButton()
        self._btn_open_folder.setObjectName("btnLogFolder")
        self._btn_open_folder.setIcon(self.style().standardIcon(QStyle.SP_DirOpenIcon))
        self._btn_open_folder.setFixedSize(28, 24)
        self._btn_open_folder.setToolTip("Log 폴더 열기")
        self._btn_open_folder.clicked.connect(self._open_log_folder)
        header_row.addWidget(self._btn_open_folder)

        self._btn_clear = QPushButton("초기화")
        self._btn_clear.setObjectName("btnLogClear")
        self._btn_clear.setFixedSize(56, 24)
        self._btn_clear.setToolTip("화면 로그 초기화 (파일 변경 없음)")
        self._btn_clear.clicked.connect(self.clear_logs)
        header_row.addWidget(self._btn_clear)

        main_layout.addWidget(header_widget)

        # ── 타입 필터 + 스크롤 재개 버튼 행 ──
        filter_widget = QWidget()
        filter_widget.setObjectName("logFilterArea")
        filter_row = QHBoxLayout(filter_widget)
        filter_row.setContentsMargins(6, 3, 6, 3)
        filter_row.setSpacing(4)

        for label, type_key, active_color in self._FILTER_DEFS:
            btn = QPushButton(label)
            btn.setObjectName("btnLogFilter")
            btn.setCheckable(True)
            btn.setChecked(type_key == "ALL")
            btn.setFixedHeight(20)
            btn.setProperty("filterKey", type_key)
            btn.setProperty("activeColor", active_color)
            self._apply_filter_btn_style(btn, checked=(type_key == "ALL"),
                                         active_color=active_color)
            btn.toggled.connect(
                lambda checked, t=type_key, c=active_color:
                self._on_type_filter_changed(t, checked, c)
            )
            filter_row.addWidget(btn)
            self._filter_buttons[type_key] = btn

        filter_row.addStretch()

        self._btn_scroll_resume = QPushButton("↓ 자동 스크롤 재개")
        self._btn_scroll_resume.setObjectName("btnScrollResume")
        self._btn_scroll_resume.setFixedHeight(20)
        self._btn_scroll_resume.setVisible(False)
        self._btn_scroll_resume.clicked.connect(self._resume_auto_scroll)
        filter_row.addWidget(self._btn_scroll_resume)

        main_layout.addWidget(filter_widget)

        # ── 검색창 행 (기본 숨김) ──
        self._search_widget = QWidget()
        self._search_widget.setObjectName("logSearchArea")
        search_row = QHBoxLayout(self._search_widget)
        search_row.setContentsMargins(6, 2, 6, 2)
        search_row.setSpacing(4)

        self._search_input = QLineEdit()
        self._search_input.setObjectName("logSearchInput")
        self._search_input.setPlaceholderText("메시지/소스 검색...")
        self._search_input.setFixedHeight(24)
        self._search_input.textChanged.connect(self._on_keyword_changed)
        search_row.addWidget(self._search_input)

        btn_search_close = QPushButton("✕")
        btn_search_close.setObjectName("btnLogSearchClose")
        btn_search_close.setFixedSize(24, 24)
        btn_search_close.clicked.connect(lambda: self._btn_search.setChecked(False))
        search_row.addWidget(btn_search_close)

        self._search_widget.setVisible(False)
        main_layout.addWidget(self._search_widget)

        # ── 로그 리스트 ──
        self._list = QListWidget()
        self._list.setObjectName("logList")
        self._list.setItemDelegate(LogRowDelegate(self._list))
        self._list.setFocusPolicy(Qt.NoFocus)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.setSpacing(0)
        self._list.setUniformItemSizes(False)
        self._list.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)
        main_layout.addWidget(self._list)

    # ── 필터 버튼 스타일 헬퍼 ─────────────────────────────────────

    def _apply_filter_btn_style(self, btn: QPushButton, checked: bool,
                                active_color: str):
        if checked:
            btn.setStyleSheet(
                f"color: {active_color}; border-color: {active_color};"
            )
        else:
            btn.setStyleSheet("")

    # ── 필터/검색 슬롯 ────────────────────────────────────────────

    def _on_type_filter_changed(self, type_key: str, checked: bool, active_color: str):
        btn = self._filter_buttons[type_key]
        self._apply_filter_btn_style(btn, checked, active_color)

        if type_key == "ALL":
            if checked:
                self._active_type_filters = {"ALL"}
                for k, b in self._filter_buttons.items():
                    if k != "ALL":
                        b.blockSignals(True)
                        b.setChecked(False)
                        self._apply_filter_btn_style(b, False, b.property("activeColor"))
                        b.blockSignals(False)
            else:
                # ALL 단독 해제 금지 — 강제 재체크
                btn.blockSignals(True)
                btn.setChecked(True)
                self._apply_filter_btn_style(btn, True, active_color)
                btn.blockSignals(False)
                self._active_type_filters = {"ALL"}
        else:
            all_btn = self._filter_buttons["ALL"]
            if checked:
                self._active_type_filters.discard("ALL")
                self._active_type_filters.add(type_key)
                if all_btn.isChecked():
                    all_btn.blockSignals(True)
                    all_btn.setChecked(False)
                    self._apply_filter_btn_style(all_btn, False,
                                                 all_btn.property("activeColor"))
                    all_btn.blockSignals(False)
            else:
                self._active_type_filters.discard(type_key)
                if not (self._active_type_filters - {"ALL"}):
                    # 선택된 타입이 없으면 ALL로 복귀
                    self._active_type_filters = {"ALL"}
                    all_btn.blockSignals(True)
                    all_btn.setChecked(True)
                    self._apply_filter_btn_style(all_btn, True,
                                                 all_btn.property("activeColor"))
                    all_btn.blockSignals(False)

        self._apply_all_filters()

    def _on_debug_toggled(self, checked: bool):
        self._show_debug = checked
        self._apply_all_filters()

    def _on_keyword_changed(self, text: str):
        self._keyword = text.lower()
        self._apply_all_filters()

    def _toggle_search_bar(self, checked: bool):
        self._search_widget.setVisible(checked)
        if checked:
            self._search_input.setFocus()
        else:
            self._search_input.clear()

    def _item_visible(self, data: LogItemData) -> bool:
        if data.is_separator:
            return True
        if data.log_type == "debug" and not self._show_debug:
            return False
        if self._active_type_filters and "ALL" not in self._active_type_filters:
            allowed_types: set = set()
            for group in self._active_type_filters:
                allowed_types |= self._GROUP_TYPES.get(group, set())
            if data.log_type not in allowed_types:
                return False
        if self._keyword:
            haystack = f"{data.source} {data.message}".lower()
            if self._keyword not in haystack:
                return False
        return True

    def _apply_all_filters(self):
        for i in range(self._list.count()):
            item = self._list.item(i)
            data: LogItemData = item.data(Qt.UserRole)
            if data:
                item.setHidden(not self._item_visible(data))
        self._update_count_badge()

    # ── 스크롤 슬롯 ──────────────────────────────────────────────

    def _on_scroll_changed(self, value: int):
        sb = self._list.verticalScrollBar()
        at_bottom = (value >= sb.maximum() - 4)
        if self._auto_scroll and not at_bottom:
            self._auto_scroll = False
            self._btn_scroll_resume.setVisible(True)
        elif not self._auto_scroll and at_bottom:
            self._auto_scroll = True
            self._btn_scroll_resume.setVisible(False)

    def _resume_auto_scroll(self):
        self._auto_scroll = True
        self._btn_scroll_resume.setVisible(False)
        self._list.scrollToBottom()

    # ── 공개 API ─────────────────────────────────────────────────

    def add_log(self, message: str, log_type: str = "info", source: str = ""):
        """로그 항목 추가.
        log_type: "debug" | "info" | "black" | "still" | "audio" | "embedded" | "error"
          - black: 블랙 감지 (영상 이상) — VIDEO 그룹
          - still: 스틸 감지 — VIDEO 그룹
          - audio: 오디오레벨 이상 — AUDIO 그룹
          - embedded: 임베디드 오디오 이상 — AUDIO 그룹
          - error: 시스템 장애 (스트림/크래시/녹화/텔레그램) — SYSTEM 그룹
        source: 소스 태그 (예: "시스템", "알람", "복구")
        """
        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")

        if date_str != self._last_date:
            self._add_date_separator(date_str)
            self._last_date = date_str

        data = LogItemData(
            timestamp=time_str,
            log_type=log_type,
            source=source,
            message=message,
            is_separator=False,
            is_newest=True,
            pulse_alpha=0.25,
        )
        self._insert_item(data)

        # 마지막으로 삽입된 항목에 pulse 시작
        last_idx = self._list.count() - 1
        if last_idx >= 0:
            self._trigger_pulse(self._list.item(last_idx))

        if self._total_count > self.MAX_LOG_ITEMS:
            self._trim_oldest()

        self._update_count_badge()

    def add_error(self, message: str, source: str = ""):
        self.add_log(message, log_type="error", source=source)

    def add_info(self, message: str, source: str = ""):
        self.add_log(message, log_type="info", source=source)

    def set_theme(self, dark: bool):
        """테마 변경 시 delegate에 전달하고 리스트 다시 그리기."""
        delegate = self._list.itemDelegate()
        if isinstance(delegate, LogRowDelegate):
            delegate.set_dark(dark)
        self._list.viewport().update()

    def clear_logs(self):
        self._list.clear()
        self._last_date = ""
        self._total_count = 0
        self._auto_scroll = True
        self._btn_scroll_resume.setVisible(False)
        self._update_count_badge()
        self.log_cleared.emit()

    # ── 내부 헬퍼 ────────────────────────────────────────────────

    def _add_date_separator(self, date_str: str):
        data = LogItemData(
            timestamp=date_str,
            log_type="separator",
            is_separator=True,
        )
        self._insert_item(data)

    def _insert_item(self, data: LogItemData):
        item = QListWidgetItem()
        item.setData(Qt.UserRole, data)
        if not data.is_separator:
            # 메시지가 잘려도 호버 시 전문 확인 가능하도록 툴팁 부착
            tip = data.message
            if data.source:
                tip = f"[{data.source}] {tip}"
            item.setToolTip(tip)
        h = LogRowDelegate.SEP_H if data.is_separator else LogRowDelegate.ROW_H
        item.setSizeHint(QSize(0, h))
        self._list.addItem(item)
        item.setHidden(not self._item_visible(data))
        self._total_count += 1
        if self._auto_scroll and not item.isHidden():
            self._list.scrollToBottom()

    def _trim_oldest(self):
        """최대 항목 초과 시 가장 오래된 항목 제거. 날짜 구분선 처리 포함."""
        if self._list.count() == 0:
            return
        self._list.takeItem(0)
        self._total_count -= 1

        # 첫 항목이 날짜 구분선이고, 다음 항목도 구분선이거나 리스트에 구분선만 남으면 제거
        if self._list.count() > 0:
            first = self._list.item(0)
            if first:
                d: LogItemData = first.data(Qt.UserRole)
                if d and d.is_separator:
                    remove = False
                    if self._list.count() == 1:
                        remove = True
                    elif self._list.count() > 1:
                        nxt: LogItemData = self._list.item(1).data(Qt.UserRole)
                        if nxt and nxt.is_separator:
                            remove = True
                    if remove:
                        self._list.takeItem(0)
                        self._total_count -= 1

    def _update_count_badge(self):
        count = 0
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.isHidden():
                continue
            data: LogItemData = item.data(Qt.UserRole)
            if data and not data.is_separator:
                count += 1
        self._count_badge.setText(str(count))

    def _trigger_pulse(self, item: QListWidgetItem):
        """신규 항목 pulse 애니메이션 — 200ms × 7스텝으로 alpha 감소."""
        total_steps = 7
        for step in range(1, total_steps + 1):
            QTimer.singleShot(
                step * 200,
                lambda s=step, it=item: self._pulse_step(it, s, total_steps)
            )

    def _pulse_step(self, item: QListWidgetItem, step: int, total: int):
        data: LogItemData = item.data(Qt.UserRole)
        if data is None:
            return
        data.pulse_alpha = max(0.0, 0.25 * (1.0 - step / total))
        if step >= total:
            data.is_newest = False
            data.pulse_alpha = 0.0
        item.setData(Qt.UserRole, data)
        self._list.update()

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
