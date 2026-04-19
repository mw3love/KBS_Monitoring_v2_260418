"""
설정 다이얼로그 (7탭, 비모달)
저장 시 ConfigManager에 JSON 기록 + cmd_queue로 ApplyConfig / UpdateROIs 발행.
"""
import copy
import os
import subprocess
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QCheckBox,
    QComboBox, QScrollArea, QFrame, QFileDialog,
    QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QStackedWidget,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIntValidator, QDoubleValidator

from core.roi_manager import ROI, ROIManager
from ui.dual_slider import DualSlider
from ui.roi_editor import FullScreenROIEditor
from utils.config_manager import ConfigManager, DEFAULT_CONFIG

try:
    import sounddevice as sd
    _SD_OK = True
except ImportError:
    _SD_OK = False


# ── 공통 헬퍼 ──────────────────────────────────────────────────────────

def _int_edit(val: int, lo: int = 0, hi: int = 99999, w: int = 80) -> QLineEdit:
    e = QLineEdit(str(int(val)))
    e.setFixedWidth(w)
    e.setValidator(QIntValidator(lo, hi))
    return e


def _float_edit(val: float, w: int = 90) -> QLineEdit:
    e = QLineEdit(str(val))
    e.setFixedWidth(w)
    return e


def _make_scroll(inner: QWidget) -> QScrollArea:
    """inner를 QScrollArea로 감싸 반환. setWidget() 즉시 호출."""
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setWidget(inner)
    return sa


def _section(title: str) -> tuple["QFrame", "QVBoxLayout"]:
    """테두리 박스 섹션. (box_frame, inner_layout) 반환.
    호출부: box, sl = _section("제목"); sl.addLayout(...); vl.addWidget(box)
    """
    box = QFrame()
    box.setObjectName("settingsSection")
    outer_vl = QVBoxLayout(box)
    outer_vl.setContentsMargins(10, 4, 10, 6)
    outer_vl.setSpacing(0)

    lbl = QLabel(title)
    lbl.setObjectName("settingsSectionLabel")
    lbl.setContentsMargins(0, 0, 0, 0)
    lbl.setFixedHeight(16)
    outer_vl.addWidget(lbl)

    # 제목과 첫 행은 바로 붙이고 (spacing=0), 항목끼리는 여유(spacing=6)
    content_vl = QVBoxLayout()
    content_vl.setContentsMargins(0, 0, 0, 0)
    content_vl.setSpacing(6)
    outer_vl.addLayout(content_vl)

    return box, content_vl


def _row(label_text: str, widget: QWidget, hint: str = "") -> QHBoxLayout:
    """label(고정폭 220) + widget + hint 한 행"""
    h = QHBoxLayout()
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(8)
    lbl = QLabel(label_text)
    lbl.setFixedWidth(220)
    h.addWidget(lbl)
    h.addWidget(widget)
    if hint:
        d = QLabel(hint)
        d.setObjectName("settingsDesc")
        h.addWidget(d, 1)
    else:
        h.addStretch(1)
    return h


def _file_row(label_text: str, edit: QLineEdit,
              browse_cb, reset_cb=None, test_cb=None) -> QHBoxLayout:
    """파일 경로 편집 + 찾아보기 [초기화] [테스트] 버튼 행"""
    h = QHBoxLayout()
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(6)
    lbl = QLabel(label_text)
    lbl.setFixedWidth(130)
    h.addWidget(lbl)
    h.addWidget(edit, 1)
    btn_browse = QPushButton("찾아보기")
    btn_browse.clicked.connect(browse_cb)
    h.addWidget(btn_browse)
    if reset_cb:
        btn_reset = QPushButton("초기화")
        btn_reset.clicked.connect(reset_cb)
        h.addWidget(btn_reset)
    if test_cb:
        btn_test = QPushButton("테스트")
        btn_test.clicked.connect(test_cb)
        h.addWidget(btn_test)
    return h


# ──────────────────────────────────────────────────────────────────────
# 정파 감지영역 팝업 (ROI 선택)
# ──────────────────────────────────────────────────────────────────────

class SignoffROIDialog(QDialog):
    """정파 그룹의 진입 트리거 ROI / 억제 대상 ROI 선택 팝업."""

    def __init__(self, group_cfg: dict, roi_mgr: ROIManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("정파 감지영역 선택")
        self.setMinimumSize(400, 320)
        self._group_cfg = group_cfg
        self._roi_mgr = roi_mgr
        self._setup_ui()

    def _setup_ui(self):
        vl = QVBoxLayout(self)
        vl.setSpacing(10)

        # 진입 트리거 ROI (단일 선택)
        lbl_enter = QLabel("진입 트리거 (단일 비디오 ROI)")
        lbl_enter.setObjectName("settingsSectionLabel")
        vl.addWidget(lbl_enter)
        vl.addWidget(QLabel("선택한 ROI가 스틸 상태 지속 시 SIGNOFF 조기 진입"))
        self._enter_combo = QComboBox()
        self._enter_combo.addItem("없음", "")
        for roi in self._roi_mgr.video_rois:
            display = f"{roi.label} [{roi.media_name}]" if roi.media_name else roi.label
            self._enter_combo.addItem(display, roi.label)
        cur_enter = (self._group_cfg.get("enter_roi") or {}).get("video_label", "")
        for i in range(self._enter_combo.count()):
            if self._enter_combo.itemData(i) == cur_enter:
                self._enter_combo.setCurrentIndex(i)
                break
        vl.addWidget(self._enter_combo)

        vl.addWidget(_sep())

        # 억제 대상 ROI (다중 체크박스)
        lbl_suppress = QLabel("알림 억제 대상 (SIGNOFF 중 억제)")
        lbl_suppress.setObjectName("settingsSectionLabel")
        vl.addWidget(lbl_suppress)
        suppressed = set(self._group_cfg.get("suppressed_labels", []))
        self._suppress_checks: list[tuple[str, QCheckBox]] = []
        all_rois = self._roi_mgr.video_rois + self._roi_mgr.audio_rois
        for roi in all_rois:
            cb = QCheckBox(f"{roi.label} [{roi.media_name}]" if roi.media_name else roi.label)
            cb.setChecked(roi.label in suppressed)
            vl.addWidget(cb)
            self._suppress_checks.append((roi.label, cb))

        if not all_rois:
            vl.addWidget(QLabel("(감지영역 없음)"))

        vl.addStretch()
        btn_row = QHBoxLayout()
        btn_ok = QPushButton("확인")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("취소")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        vl.addLayout(btn_row)

    def get_result(self) -> dict:
        enter_label = self._enter_combo.currentData() or ""
        suppressed = [label for label, cb in self._suppress_checks if cb.isChecked()]
        return {
            "enter_roi": {"video_label": enter_label},
            "suppressed_labels": suppressed,
        }


# ──────────────────────────────────────────────────────────────────────
# 메인 설정 다이얼로그
# ──────────────────────────────────────────────────────────────────────

class SettingsDialog(QDialog):
    """
    KBS Monitoring v2 설정 다이얼로그 (7탭, 비모달).
    show()로 열어 비모달로 사용. 저장 시 config_saved 시그널 발행.
    """
    config_saved = Signal(dict)

    _TAB_LABELS = [
        "영상설정",
        "비디오\n영역 설정",
        "오디오 레벨미터\n영역 설정",
        "감도설정",
        "정파설정",
        "알림설정",
        "저장/불러오기",
    ]

    def __init__(self, cfg: dict, cmd_queue, alarm,
                 frozen_frame=None, parent=None):
        super().__init__(parent, Qt.Window)
        self._cfg = copy.deepcopy(cfg)
        self._cmd_queue = cmd_queue
        self._alarm = alarm
        self._frozen_frame = frozen_frame
        self._cfg_mgr = ConfigManager()

        self._roi_mgr = ROIManager()
        self._load_rois_from_cfg()

        self.setWindowTitle("KBS Monitoring v2 — 설정")
        self.setMinimumSize(880, 640)
        self.resize(980, 720)
        self._setup_ui()

    # ── ROI 로드/저장 ─────────────────────────────────────────────────

    def _load_rois_from_cfg(self):
        rois_cfg = self._cfg.get("rois", {})
        video_rois = [ROI(**{**r, "roi_type": "video"})
                      for r in rois_cfg.get("video", [])]
        audio_rois = [ROI(**{**r, "roi_type": "audio"})
                      for r in rois_cfg.get("audio", [])]
        self._roi_mgr.replace_video_rois(video_rois)
        self._roi_mgr.replace_audio_rois(audio_rois)

    def _save_rois_to_cfg(self):
        self._cfg["rois"] = {
            "video": [{"label": r.label, "media_name": r.media_name,
                        "x": r.x, "y": r.y, "w": r.w, "h": r.h}
                       for r in self._roi_mgr.video_rois],
            "audio": [{"label": r.label, "media_name": r.media_name,
                        "x": r.x, "y": r.y, "w": r.w, "h": r.h}
                       for r in self._roi_mgr.audio_rois],
        }

    # ── UI 구성 ──────────────────────────────────────────────────────

    def _setup_ui(self):
        main_vl = QVBoxLayout(self)
        main_vl.setContentsMargins(0, 0, 0, 8)
        main_vl.setSpacing(0)

        # 탭 버튼 바
        tab_bar = QWidget()
        tab_bar.setObjectName("settingsTabBar")
        tab_bar_hl = QHBoxLayout(tab_bar)
        tab_bar_hl.setContentsMargins(8, 6, 8, 0)
        tab_bar_hl.setSpacing(2)
        self._tab_btns: list[QPushButton] = []
        for i, label in enumerate(self._TAB_LABELS):
            btn = QPushButton(label)
            btn.setObjectName("settingsTabBtn")
            btn.setCheckable(True)
            btn.setMinimumHeight(44)
            btn.clicked.connect(lambda _checked, idx=i: self._switch_tab(idx))
            tab_bar_hl.addWidget(btn)
            self._tab_btns.append(btn)
        main_vl.addWidget(tab_bar)

        # 탭 내용 스택
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_tab_video())
        self._page_video_area = self._build_tab_roi_area("video")
        self._stack.addWidget(self._page_video_area)
        self._page_audio_area = self._build_tab_roi_area("audio")
        self._stack.addWidget(self._page_audio_area)
        self._stack.addWidget(self._build_tab_sensitivity())
        self._stack.addWidget(self._build_tab_signoff())
        self._stack.addWidget(self._build_tab_alert())
        self._stack.addWidget(self._build_tab_save())
        main_vl.addWidget(self._stack, 1)

        # 하단 버튼
        bottom_hl = QHBoxLayout()
        bottom_hl.setContentsMargins(12, 4, 12, 4)
        bottom_hl.addStretch()
        btn_save = QPushButton("저장")
        btn_save.setObjectName("btnPrimary")
        btn_save.setFixedSize(100, 32)
        btn_save.clicked.connect(self._on_save)
        btn_close = QPushButton("닫기")
        btn_close.setFixedSize(80, 32)
        btn_close.clicked.connect(self.close)
        bottom_hl.addWidget(btn_save)
        bottom_hl.addWidget(btn_close)
        main_vl.addLayout(bottom_hl)

        self._switch_tab(0)

    def _switch_tab(self, idx: int):
        for i, btn in enumerate(self._tab_btns):
            btn.setChecked(i == idx)
        self._stack.setCurrentIndex(idx)

    # ─────────────────────────────────────────────────────────────────
    # 탭 1: 영상설정
    # ─────────────────────────────────────────────────────────────────

    def _build_tab_video(self) -> QScrollArea:
        inner = QWidget()
        vl = QVBoxLayout(inner)
        vl.setContentsMargins(12, 12, 12, 12)
        vl.setSpacing(10)

        # ── 캡처 포트 ──────────────────────────────────────────
        box1, sl1 = _section("캡처 포트")
        self._port_edit = _int_edit(self._cfg.get("port", 0), 0, 9)
        sl1.addLayout(_row("포트 번호 (0~9)", self._port_edit,
                           "OpenCV VideoCapture 인덱스"))
        vl.addWidget(box1)

        # ── 파일 입력 (테스트용) ────────────────────────────────
        box2, sl2 = _section("파일 입력 (테스트용)")
        desc = QLabel(
            "MP4 등 영상 파일을 불러와 포트 대신 소스로 사용합니다.\n"
            "파일을 선택하면 파일 재생으로 전환되며, 초기화하면 포트로 복귀합니다.")
        desc.setObjectName("settingsDesc")
        sl2.addWidget(desc)
        file_hl = QHBoxLayout()
        file_hl.setContentsMargins(0, 0, 0, 0)
        self._video_file_edit = QLineEdit(self._cfg.get("video_file", ""))
        self._video_file_edit.setPlaceholderText("(파일 선택 안 함 — 포트 사용)")
        file_hl.addWidget(self._video_file_edit, 1)
        btn_vf_browse = QPushButton("찾아보기")
        btn_vf_browse.clicked.connect(self._browse_video_file)
        btn_vf_reset = QPushButton("초기화")
        btn_vf_reset.clicked.connect(self._video_file_edit.clear)
        file_hl.addWidget(btn_vf_browse)
        file_hl.addWidget(btn_vf_reset)
        sl2.addLayout(file_hl)
        vl.addWidget(box2)

        # ── 자동 녹화 설정 ──────────────────────────────────────
        box3, sl3 = _section("자동 녹화 설정")
        rec = self._cfg.get("recording", {})
        self._rec_enabled_cb = QCheckBox("알림 발생 시 자동 녹화 활성화")
        self._rec_enabled_cb.setChecked(rec.get("enabled", True))
        sl3.addWidget(self._rec_enabled_cb)

        dir_hl = QHBoxLayout()
        dir_hl.setContentsMargins(0, 0, 0, 0)
        dir_hl.addWidget(QLabel("저장 폴더:"))
        self._rec_dir_edit = QLineEdit(rec.get("save_dir", "recordings"))
        dir_hl.addWidget(self._rec_dir_edit, 1)
        btn_dir_browse = QPushButton("찾아보기")
        btn_dir_browse.clicked.connect(self._browse_rec_dir)
        btn_dir_open = QPushButton("폴더 열기")
        btn_dir_open.clicked.connect(self._open_rec_dir)
        dir_hl.addWidget(btn_dir_browse)
        dir_hl.addWidget(btn_dir_open)
        sl3.addLayout(dir_hl)

        self._rec_pre_edit = _int_edit(rec.get("pre_seconds", 5), 1, 30)
        self._rec_post_edit = _int_edit(rec.get("post_seconds", 15), 1, 60)
        self._rec_keep_edit = _int_edit(rec.get("max_keep_days", 7), 1, 365)
        sl3.addLayout(_row("시작 전 버퍼 (초)", self._rec_pre_edit, "1~30 / 기본값 5"))
        sl3.addLayout(_row("이후 녹화 시간 (초)", self._rec_post_edit, "1~60 / 기본값 15"))
        sl3.addLayout(_row("최대 보관 기간 (일)", self._rec_keep_edit, "1~365"))
        vl.addWidget(box3)

        # ── 녹화 품질 설정 ──────────────────────────────────────
        box4, sl4 = _section("녹화 품질 설정")
        self._res_combo = QComboBox()
        for label, wv, hv in [("960×540 (기본값)", 960, 540),
                               ("1280×720", 1280, 720),
                               ("1920×1080", 1920, 1080)]:
            self._res_combo.addItem(label, (wv, hv))
        cur_w = rec.get("output_width", 960)
        for i in range(self._res_combo.count()):
            if self._res_combo.itemData(i)[0] == cur_w:
                self._res_combo.setCurrentIndex(i)
                break
        sl4.addLayout(_row("출력 해상도", self._res_combo,
                           "저해상도일수록 파일 크기 절약"))

        self._fps_combo = QComboBox()
        for fps_val in [10, 15, 25, 30]:
            self._fps_combo.addItem(f"{fps_val} fps", fps_val)
        cur_fps = rec.get("output_fps", 10)
        for i in range(self._fps_combo.count()):
            if self._fps_combo.itemData(i) == cur_fps:
                self._fps_combo.setCurrentIndex(i)
                break
        sl4.addLayout(_row("출력 FPS", self._fps_combo))
        vl.addWidget(box4)

        vl.addStretch()
        btn_reset_v = QPushButton("영상설정 전체 초기화")
        btn_reset_v.setObjectName("btnDanger")
        btn_reset_v.clicked.connect(self._reset_video_settings)
        vl.addWidget(btn_reset_v)

        return _make_scroll(inner)

    # ─────────────────────────────────────────────────────────────────
    # 탭 2/3: ROI 영역 설정
    # ─────────────────────────────────────────────────────────────────

    def _build_tab_roi_area(self, roi_type: str) -> QWidget:
        """roi_type: 'video' | 'audio'"""
        outer = QWidget()
        vl = QVBoxLayout(outer)
        vl.setContentsMargins(12, 12, 12, 12)
        vl.setSpacing(8)

        kind_name = "비디오" if roi_type == "video" else "오디오 레벨미터"
        btn_edit = QPushButton(f"▶ {kind_name} 감지영역 편집 (전체화면)")
        btn_edit.setObjectName("btnPrimary")
        btn_edit.clicked.connect(lambda: self._open_roi_editor(roi_type))
        vl.addWidget(btn_edit)

        # ROI 테이블
        table = QTableWidget()
        table.setObjectName("roiTable")
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["라벨", "매체명", "X", "Y", "W", "H"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setEditTriggers(QAbstractItemView.DoubleClicked)
        table.verticalHeader().setVisible(False)
        vl.addWidget(table)

        # 테이블 버튼
        table_btn_hl = QHBoxLayout()
        table_btn_hl.setContentsMargins(0, 0, 0, 0)
        btn_add = QPushButton("추가")
        btn_add.clicked.connect(lambda: self._roi_table_add(roi_type, table))
        btn_del = QPushButton("삭제")
        btn_del.clicked.connect(lambda: self._roi_table_del(roi_type, table))
        btn_up = QPushButton("▲ 위로")
        btn_up.clicked.connect(lambda: self._roi_table_move(roi_type, table, -1))
        btn_down = QPushButton("▼ 아래로")
        btn_down.clicked.connect(lambda: self._roi_table_move(roi_type, table, 1))
        btn_clear = QPushButton("전체 지우기")
        btn_clear.setObjectName("btnDanger")
        btn_clear.clicked.connect(lambda: self._roi_table_clear(roi_type, table))
        for btn in (btn_add, btn_del, btn_up, btn_down):
            table_btn_hl.addWidget(btn)
        table_btn_hl.addStretch()
        table_btn_hl.addWidget(btn_clear)
        vl.addLayout(table_btn_hl)

        # 저장소에 테이블 참조 보관
        if roi_type == "video":
            self._video_roi_table = table
        else:
            self._audio_roi_table = table
        self._refresh_roi_table(roi_type)

        return outer

    def _refresh_roi_table(self, roi_type: str):
        table = self._video_roi_table if roi_type == "video" \
                else self._audio_roi_table
        rois = self._roi_mgr.video_rois if roi_type == "video" \
               else self._roi_mgr.audio_rois
        table.blockSignals(True)
        table.setRowCount(len(rois))
        for i, roi in enumerate(rois):
            for col, val in enumerate([roi.label, roi.media_name,
                                        roi.x, roi.y, roi.w, roi.h]):
                item = QTableWidgetItem(str(val))
                if col == 0:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                table.setItem(i, col, item)
        table.blockSignals(False)

    def _open_roi_editor(self, roi_type: str):
        dlg = FullScreenROIEditor(self._roi_mgr, roi_type,
                                   self._frozen_frame, parent=self)
        dlg.editing_done.connect(lambda: self._on_roi_editing_done(roi_type))
        dlg.exec()

    def _on_roi_editing_done(self, roi_type: str):
        self._refresh_roi_table(roi_type)

    def _roi_table_add(self, roi_type: str, table: QTableWidget):
        rois = (self._roi_mgr.video_rois if roi_type == "video"
                else self._roi_mgr.audio_rois)
        prefix = "V" if roi_type == "video" else "A"
        if rois:
            last = rois[-1]
            new_roi = ROI(label="", media_name=last.media_name,
                          x=min(last.x + 10, 1900), y=min(last.y + 10, 1060),
                          w=last.w, h=last.h, roi_type=roi_type)
        else:
            new_roi = ROI(label="", media_name="", x=10, y=10,
                          w=100, h=80, roi_type=roi_type)
        rois.append(new_roi)
        for i, r in enumerate(rois):
            r.label = f"{prefix}{i + 1}"
        if roi_type == "video":
            self._roi_mgr.replace_video_rois(rois)
        else:
            self._roi_mgr.replace_audio_rois(rois)
        self._refresh_roi_table(roi_type)

    def _roi_table_del(self, roi_type: str, table: QTableWidget):
        rows = sorted(set(i.row() for i in table.selectedItems()), reverse=True)
        if not rows:
            return
        rois = list(self._roi_mgr.video_rois if roi_type == "video"
                    else self._roi_mgr.audio_rois)
        for r in rows:
            if 0 <= r < len(rois):
                rois.pop(r)
        prefix = "V" if roi_type == "video" else "A"
        for i, roi in enumerate(rois):
            roi.label = f"{prefix}{i + 1}"
        if roi_type == "video":
            self._roi_mgr.replace_video_rois(rois)
        else:
            self._roi_mgr.replace_audio_rois(rois)
        self._refresh_roi_table(roi_type)

    def _roi_table_move(self, roi_type: str, table: QTableWidget, direction: int):
        rows = sorted(set(i.row() for i in table.selectedItems()))
        if not rows:
            return
        idx = rows[0]
        rois = list(self._roi_mgr.video_rois if roi_type == "video"
                    else self._roi_mgr.audio_rois)
        new_idx = idx + direction
        if not (0 <= new_idx < len(rois)):
            return
        rois[idx], rois[new_idx] = rois[new_idx], rois[idx]
        prefix = "V" if roi_type == "video" else "A"
        for i, roi in enumerate(rois):
            roi.label = f"{prefix}{i + 1}"
        if roi_type == "video":
            self._roi_mgr.replace_video_rois(rois)
        else:
            self._roi_mgr.replace_audio_rois(rois)
        self._refresh_roi_table(roi_type)
        table.selectRow(new_idx)

    def _roi_table_clear(self, roi_type: str, table: QTableWidget):
        if QMessageBox.question(
            self, "확인", f"{'비디오' if roi_type == 'video' else '오디오'} "
                          f"감지영역을 모두 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No
        ) != QMessageBox.Yes:
            return
        if roi_type == "video":
            self._roi_mgr.replace_video_rois([])
        else:
            self._roi_mgr.replace_audio_rois([])
        self._refresh_roi_table(roi_type)

    # ─────────────────────────────────────────────────────────────────
    # 탭 4: 감도설정
    # ─────────────────────────────────────────────────────────────────

    def _build_tab_sensitivity(self) -> QScrollArea:
        inner = QWidget()
        vl = QVBoxLayout(inner)
        vl.setContentsMargins(12, 12, 12, 12)
        vl.setSpacing(10)
        det = self._cfg.get("detection", {})
        perf = self._cfg.get("performance", {})

        # ── 블랙 감지 ────────────────────────────────────
        box1, sl1 = _section("블랙 감지")
        self._black_thresh = _int_edit(det.get("black_threshold", 10), 0, 255)
        self._black_ratio = _float_edit(det.get("black_dark_ratio", 95.0))
        self._black_suppress = _float_edit(det.get("black_motion_suppress_ratio", 0.2))
        self._black_dur = _int_edit(det.get("black_duration", 20), 1, 300)
        self._black_alarm_dur = _int_edit(det.get("black_alarm_duration", 60), 1, 300)
        sl1.addLayout(_row("밝기 임계값", self._black_thresh,
                           "0~255 / 이 값 이하면 어두운 픽셀로 판단"))
        sl1.addLayout(_row("어두운 픽셀 비율(%)", self._black_ratio,
                           "50~100% / 이 비율 이상이면 블랙 판정"))
        sl1.addLayout(_row("모션 억제 비율", self._black_suppress,
                           "0~5.0 / 움직임 비율이 이 이상이면 블랙 억제"))
        sl1.addLayout(_row("알람 발생까지 지속 시간(초)", self._black_dur,
                           "1~300 / 기본값 20"))
        sl1.addLayout(_row("알람 소리 지속 시간(초)", self._black_alarm_dur,
                           "1~300 / 기본값 60"))
        vl.addWidget(box1)

        # ── 스틸 감지 ────────────────────────────────────
        box2, sl2 = _section("스틸 감지")
        self._still_thresh = _int_edit(det.get("still_threshold", 8), 0, 255)
        self._still_changed = _float_edit(det.get("still_changed_ratio", 2.0))
        self._still_reset = _int_edit(det.get("still_reset_frames", 3), 1, 10)
        self._still_dur = _int_edit(det.get("still_duration", 60), 1, 300)
        self._still_alarm_dur = _int_edit(det.get("still_alarm_duration", 60), 1, 300)
        sl2.addLayout(_row("픽셀 차이 임계값", self._still_thresh,
                           "0~255 / 프레임 차이 기준"))
        sl2.addLayout(_row("블록 변화 비율(%)", self._still_changed,
                           "0~100% / 이 비율 미만이면 스틸로 판정"))
        sl2.addLayout(_row("히스테리시스 프레임 수", self._still_reset,
                           "1~10 / 연속 정상 프레임 수 (글리치 방지)"))
        sl2.addLayout(_row("알람 발생까지 지속 시간(초)", self._still_dur,
                           "1~300 / 기본값 60"))
        sl2.addLayout(_row("알람 소리 지속 시간(초)", self._still_alarm_dur,
                           "1~300 / 기본값 60"))
        vl.addWidget(box2)

        # ── 오디오 레벨미터 감지 (HSV) ───────────────────
        box3, sl3 = _section("오디오 레벨미터 감지 (HSV)")
        self._hsv_h = DualSlider(0, 179, "hue")
        self._hsv_h.set_range(det.get("audio_hsv_h_min", 40),
                               det.get("audio_hsv_h_max", 95))
        self._hsv_s = DualSlider(0, 255, "saturation")
        self._hsv_s.set_range(det.get("audio_hsv_s_min", 80),
                               det.get("audio_hsv_s_max", 255))
        self._hsv_v = DualSlider(0, 255, "value")
        self._hsv_v.set_range(det.get("audio_hsv_v_min", 60),
                               det.get("audio_hsv_v_max", 255))
        self._audio_pixel_ratio = _float_edit(det.get("audio_pixel_ratio", 5.0))
        self._audio_level_dur = _int_edit(det.get("audio_level_duration", 20), 1, 300)
        self._audio_level_alarm_dur = _int_edit(
            det.get("audio_level_alarm_duration", 60), 1, 300)
        self._audio_recovery = _float_edit(det.get("audio_level_recovery_seconds", 2.0))
        sl3.addLayout(_row("H 범위 (색조, 0~179)", self._hsv_h,
                           "OpenCV HSV. 기본값 40~95 (초록 계열)"))
        sl3.addLayout(_row("S 범위 (채도, 0~255)", self._hsv_s, "기본값 80~255"))
        sl3.addLayout(_row("V 범위 (명도, 0~255)", self._hsv_v, "기본값 60~255"))
        sl3.addLayout(_row("감지 픽셀 비율(%)", self._audio_pixel_ratio,
                           "1~50% / ROI 내 HSV 범위 픽셀이 이 값 이상이면 활성"))
        sl3.addLayout(_row("알람 발생까지 지속 시간(초)", self._audio_level_dur,
                           "1~300 / 기본값 20"))
        sl3.addLayout(_row("알람 소리 지속 시간(초)", self._audio_level_alarm_dur,
                           "1~300 / 기본값 60"))
        sl3.addLayout(_row("복구 딜레이(초)", self._audio_recovery,
                           "0~30 / 0=즉시복구. 기본값 2"))
        vl.addWidget(box3)

        # ── 임베디드 오디오 감지 ──────────────────────────
        box4, sl4 = _section("임베디드 오디오 감지 (무음)")
        self._emb_thresh = _int_edit(det.get("embedded_silence_threshold", -50), -60, 0)
        self._emb_dur = _int_edit(det.get("embedded_silence_duration", 20), 1, 300)
        self._emb_alarm_dur = _int_edit(det.get("embedded_alarm_duration", 60), 1, 300)
        sl4.addLayout(_row("무음 임계값(dB)", self._emb_thresh,
                           "-60~0 / 이 값 이하일 때 무음 판정. 기본값 -50"))
        sl4.addLayout(_row("알람 발생까지 지속 시간(초)", self._emb_dur,
                           "1~300 / 기본값 20"))
        sl4.addLayout(_row("알람 소리 지속 시간(초)", self._emb_alarm_dur,
                           "1~300 / 기본값 60"))
        vl.addWidget(box4)

        # ── 성능 설정 ─────────────────────────────────────
        box5, sl5 = _section("성능 설정")
        self._detect_interval_combo = QComboBox()
        for ms in [100, 200, 500, 1000]:
            self._detect_interval_combo.addItem(f"{ms} ms", ms)
        cur_interval = perf.get("detection_interval", 200)
        for i in range(self._detect_interval_combo.count()):
            if self._detect_interval_combo.itemData(i) == cur_interval:
                self._detect_interval_combo.setCurrentIndex(i)
                break
        sl5.addLayout(_row("감지 주기", self._detect_interval_combo,
                           "100/200/500/1000 ms 이산값"))

        self._scale_combo = QComboBox()
        for label, val in [("원본 (1.0×)", 1.0), ("0.5× 해상도", 0.5),
                            ("0.25× 해상도", 0.25)]:
            self._scale_combo.addItem(label, val)
        cur_scale = perf.get("scale_factor", 1.0)
        for i in range(self._scale_combo.count()):
            if abs(self._scale_combo.itemData(i) - cur_scale) < 0.01:
                self._scale_combo.setCurrentIndex(i)
                break
        sl5.addLayout(_row("감지 해상도 스케일", self._scale_combo,
                           "50% 시 CPU 부담 약 50% 절감"))

        self._black_enabled_cb = QCheckBox("블랙 감지 활성화")
        self._still_enabled_cb = QCheckBox("스틸 감지 활성화")
        self._audio_enabled_cb = QCheckBox("오디오 레벨미터 감지 활성화")
        self._emb_enabled_cb = QCheckBox("임베디드 오디오 감지 활성화")
        self._black_enabled_cb.setChecked(perf.get("black_detection_enabled", True))
        self._still_enabled_cb.setChecked(perf.get("still_detection_enabled", True))
        self._audio_enabled_cb.setChecked(perf.get("audio_detection_enabled", True))
        self._emb_enabled_cb.setChecked(perf.get("embedded_detection_enabled", True))
        for cb in (self._black_enabled_cb, self._still_enabled_cb,
                   self._audio_enabled_cb, self._emb_enabled_cb):
            sl5.addWidget(cb)

        perf_btn_hl = QHBoxLayout()
        perf_btn_hl.setContentsMargins(0, 0, 0, 0)
        btn_auto_perf = QPushButton("자동 성능 감지")
        btn_auto_perf.setObjectName("btnPrimary")
        btn_auto_perf.clicked.connect(self._auto_detect_performance)
        perf_btn_hl.addWidget(btn_auto_perf)
        perf_btn_hl.addStretch()
        sl5.addLayout(perf_btn_hl)
        vl.addWidget(box5)

        vl.addStretch()
        return _make_scroll(inner)

    # ─────────────────────────────────────────────────────────────────
    # 탭 5: 정파설정
    # ─────────────────────────────────────────────────────────────────

    def _build_tab_signoff(self) -> QScrollArea:
        inner = QWidget()
        vl = QVBoxLayout(inner)
        vl.setContentsMargins(12, 12, 12, 12)
        vl.setSpacing(10)
        so = self._cfg.get("signoff", {})

        self._auto_prep_cb = QCheckBox("자동 정파 활성화")
        self._auto_prep_cb.setChecked(so.get("auto_preparation", True))
        vl.addWidget(self._auto_prep_cb)

        # Group 1, 2
        self._so_grp: list[dict] = []
        for gid in (1, 2):
            grp = so.get(f"group{gid}", {})
            widgets = self._build_signoff_group_section(vl, gid, grp)
            self._so_grp.append(widgets)

        # 정파 알림음
        box_sound, sl_sound = _section("정파 알림음")
        self._so_prep_sound = QLineEdit(so.get("prep_alarm_sound", ""))
        self._so_enter_sound = QLineEdit(so.get("enter_alarm_sound", ""))
        self._so_release_sound = QLineEdit(so.get("release_alarm_sound", ""))
        sl_sound.addLayout(_file_row(
            "정파준비 시작:",   self._so_prep_sound,
            lambda: self._browse_sound(self._so_prep_sound),
            test_cb=lambda: self._test_sound(self._so_prep_sound.text()),
        ))
        sl_sound.addLayout(_file_row(
            "정파모드 진입:",   self._so_enter_sound,
            lambda: self._browse_sound(self._so_enter_sound),
            test_cb=lambda: self._test_sound(self._so_enter_sound.text()),
        ))
        sl_sound.addLayout(_file_row(
            "정파 해제:",       self._so_release_sound,
            lambda: self._browse_sound(self._so_release_sound),
            test_cb=lambda: self._test_sound(self._so_release_sound.text()),
        ))
        vl.addWidget(box_sound)

        vl.addStretch()
        btn_reset_so = QPushButton("정파설정 전체 초기화")
        btn_reset_so.setObjectName("btnDanger")
        btn_reset_so.clicked.connect(self._reset_signoff_settings)
        vl.addWidget(btn_reset_so)

        return _make_scroll(inner)

    def _build_signoff_group_section(self, parent_vl: QVBoxLayout,
                                     gid: int, grp: dict) -> dict:
        box, sl = _section(f"그룹 {gid}")
        parent_vl.addWidget(box)

        widgets = {}

        # 그룹명
        name_edit = QLineEdit(grp.get("name", f"{gid}TV"))
        sl.addLayout(_row(f"그룹{gid} 이름", name_edit))
        widgets["name"] = name_edit

        # 정파 시작/종료 시각
        time_hl = QHBoxLayout()
        time_hl.setContentsMargins(0, 0, 0, 0)
        time_hl.addWidget(QLabel("정파모드 시작 HH:MM:"))
        start_h = _int_edit(int(grp.get("start_time", "03:00").split(":")[0]), 0, 23, 50)
        start_m = _int_edit(int(grp.get("start_time", "03:00").split(":")[1]), 0, 59, 50)
        time_hl.addWidget(start_h)
        time_hl.addWidget(QLabel(":"))
        time_hl.addWidget(start_m)
        time_hl.addWidget(QLabel("  종료:"))
        end_h = _int_edit(int(grp.get("end_time", "05:00").split(":")[0]), 0, 23, 50)
        end_m = _int_edit(int(grp.get("end_time", "05:00").split(":")[1]), 0, 59, 50)
        time_hl.addWidget(end_h)
        time_hl.addWidget(QLabel(":"))
        time_hl.addWidget(end_m)
        end_next_cb = QCheckBox("익일")
        end_next_cb.setChecked(grp.get("end_next_day", False))
        time_hl.addWidget(end_next_cb)
        time_hl.addStretch()
        sl.addLayout(time_hl)
        widgets.update({"start_h": start_h, "start_m": start_m,
                        "end_h": end_h, "end_m": end_m, "end_next_day": end_next_cb})

        # 정파준비 활성화 (X분 전)
        prep_combo = QComboBox()
        prep_options = [(30, "30분 전"), (60, "1시간 전"), (90, "1.5시간 전"),
                        (120, "2시간 전"), (150, "2.5시간 전"), (180, "3시간 전")]
        cur_prep = grp.get("prep_minutes", 150)
        for val, label in prep_options:
            prep_combo.addItem(label, val)
        for i in range(prep_combo.count()):
            if prep_combo.itemData(i) == cur_prep:
                prep_combo.setCurrentIndex(i)
                break
        sl.addLayout(_row("정파준비 활성화", prep_combo,
                          "정파 시작 X분 전에 PREPARATION 전환"))
        widgets["prep_minutes"] = prep_combo

        # 정파해제준비 활성화
        exit_prep_combo = QComboBox()
        exit_prep_options = [(30, "30분 전"), (60, "1시간 전"),
                             (120, "2시간 전"), (180, "3시간 전")]
        cur_exit_prep = grp.get("exit_prep_minutes", 30)
        for val, label in exit_prep_options:
            exit_prep_combo.addItem(label, val)
        for i in range(exit_prep_combo.count()):
            if exit_prep_combo.itemData(i) == cur_exit_prep:
                exit_prep_combo.setCurrentIndex(i)
                break
        sl.addLayout(_row("정파해제준비 활성화", exit_prep_combo,
                          "정파 종료 X분 전에 해제준비 구간 시작"))
        widgets["exit_prep_minutes"] = exit_prep_combo

        # 조기 해제 트리거 시간
        exit_trig = _int_edit(grp.get("exit_trigger_sec", 5), 1, 300)
        sl.addLayout(_row("조기 해제 기준 시간(초)", exit_trig,
                          "비-스틸이 이 시간 이상 지속 시 SIGNOFF → IDLE"))
        widgets["exit_trigger_sec"] = exit_trig

        # 요일 선택
        day_hl = QHBoxLayout()
        day_hl.setContentsMargins(0, 0, 0, 0)
        day_hl.addWidget(QLabel("적용 요일:"))
        day_names = ["월", "화", "수", "목", "금", "토", "일"]
        cur_days = set(grp.get("weekdays", list(range(7))))
        day_cbs = []
        for d_idx, d_name in enumerate(day_names):
            cb = QCheckBox(d_name)
            cb.setChecked(d_idx in cur_days)
            day_hl.addWidget(cb)
            day_cbs.append(cb)
        day_hl.addStretch()
        sl.addLayout(day_hl)
        widgets["weekdays"] = day_cbs

        # 감지영역 선택 버튼
        roi_btn_hl = QHBoxLayout()
        roi_btn_hl.setContentsMargins(0, 0, 0, 0)
        roi_btn_hl.addWidget(QLabel("정파 감지영역:"))
        btn_roi = QPushButton("감지영역 선택...")
        btn_roi.clicked.connect(lambda: self._open_signoff_roi_dialog(gid - 1))
        roi_btn_hl.addWidget(btn_roi)
        enter_lbl = QLabel(
            (grp.get("enter_roi") or {}).get("video_label", "없음") or "없음")
        roi_btn_hl.addWidget(enter_lbl)
        roi_btn_hl.addStretch()
        sl.addLayout(roi_btn_hl)
        widgets["enter_label_lbl"] = enter_lbl

        # 억제 라벨 내부 저장 (SignoffROIDialog 결과용)
        widgets["_enter_roi"] = dict(grp.get("enter_roi") or {"video_label": ""})
        widgets["_suppressed"] = list(grp.get("suppressed_labels", []))

        return widgets

    def _open_signoff_roi_dialog(self, grp_idx: int):
        widgets = self._so_grp[grp_idx]
        grp_cfg = {
            "enter_roi": widgets["_enter_roi"],
            "suppressed_labels": widgets["_suppressed"],
        }
        dlg = SignoffROIDialog(grp_cfg, self._roi_mgr, parent=self)
        if dlg.exec() == QDialog.Accepted:
            result = dlg.get_result()
            widgets["_enter_roi"] = result["enter_roi"]
            widgets["_suppressed"] = result["suppressed_labels"]
            enter_label = result["enter_roi"].get("video_label", "") or "없음"
            widgets["enter_label_lbl"].setText(enter_label)

    # ─────────────────────────────────────────────────────────────────
    # 탭 6: 알림설정
    # ─────────────────────────────────────────────────────────────────

    def _build_tab_alert(self) -> QScrollArea:
        inner = QWidget()
        vl = QVBoxLayout(inner)
        vl.setContentsMargins(12, 12, 12, 12)
        vl.setSpacing(10)
        alm = self._cfg.get("alarm", {})
        tg = self._cfg.get("telegram", {})
        sys_cfg = self._cfg.get("system", {})
        emb = self._cfg.get("embedded", {})

        # 알림음 파일
        box1, sl1 = _section("알림음 공통 설정")
        self._alarm_sound_edit = QLineEdit(alm.get("sound_file", ""))
        sl1.addLayout(_file_row(
            "알림음 파일:",
            self._alarm_sound_edit,
            lambda: self._browse_sound(self._alarm_sound_edit),
            reset_cb=lambda: self._alarm_sound_edit.setText(
                "resources/sounds/alarm.wav"),
            test_cb=lambda: self._test_sound(self._alarm_sound_edit.text()),
        ))
        vl.addWidget(box1)

        # 임베디드 오디오 입력 장치
        box2, sl2 = _section("임베디드 오디오 입력 장치")
        self._audio_dev_combo = QComboBox()
        self._audio_dev_combo.addItem("시스템 기본 입력", "")
        if _SD_OK:
            try:
                devs = sd.query_devices()
                for dev in devs:
                    if dev.get("max_input_channels", 0) > 0:
                        name = dev["name"]
                        self._audio_dev_combo.addItem(name, name)
            except Exception:
                pass
        cur_dev = emb.get("audio_input_device", "")
        for i in range(self._audio_dev_combo.count()):
            if self._audio_dev_combo.itemData(i) == cur_dev:
                self._audio_dev_combo.setCurrentIndex(i)
                break
        sl2.addLayout(_row("입력 장치", self._audio_dev_combo,
                           "이름 기반 저장 — 재부팅 후에도 유지"))
        vl.addWidget(box2)

        # 텔레그램
        box3, sl3 = _section("텔레그램 봇 설정")
        self._tg_enabled_cb = QCheckBox("텔레그램 알림 활성화")
        self._tg_enabled_cb.setChecked(tg.get("enabled", False))
        sl3.addWidget(self._tg_enabled_cb)

        self._tg_token_edit = QLineEdit(tg.get("bot_token", ""))
        self._tg_token_edit.setPlaceholderText("BotFather에서 발급받은 토큰")
        self._tg_chat_edit = QLineEdit(tg.get("chat_id", ""))
        self._tg_chat_edit.setPlaceholderText("수신할 채팅/그룹/채널 ID")
        sl3.addLayout(_row("Bot Token", self._tg_token_edit))
        sl3.addLayout(_row("Chat ID", self._tg_chat_edit))

        tg_test_hl = QHBoxLayout()
        tg_test_hl.setContentsMargins(0, 0, 0, 0)
        btn_tg_test = QPushButton("연결 테스트")
        btn_tg_test.clicked.connect(self._test_telegram)
        tg_test_hl.addWidget(btn_tg_test)
        tg_test_hl.addStretch()
        sl3.addLayout(tg_test_hl)
        vl.addWidget(box3)

        # 텔레그램 알림 옵션
        box4, sl4 = _section("텔레그램 알림 옵션")
        self._tg_image_cb = QCheckBox("알림 발생 시 스냅샷 이미지 첨부")
        self._tg_black_cb = QCheckBox("블랙 감지 알림")
        self._tg_still_cb = QCheckBox("스틸 감지 알림")
        self._tg_audio_cb = QCheckBox("오디오 레벨미터 감지 알림")
        self._tg_emb_cb = QCheckBox("임베디드 오디오 감지 알림")
        self._tg_system_cb = QCheckBox("시스템 이벤트 알림 (재spawn, 비정상종료 등)")
        self._tg_image_cb.setChecked(tg.get("send_image", True))
        self._tg_black_cb.setChecked(tg.get("notify_black", True))
        self._tg_still_cb.setChecked(tg.get("notify_still", True))
        self._tg_audio_cb.setChecked(tg.get("notify_audio_level", True))
        self._tg_emb_cb.setChecked(tg.get("notify_embedded", True))
        self._tg_system_cb.setChecked(tg.get("notify_system", True))
        for cb in (self._tg_image_cb, self._tg_black_cb, self._tg_still_cb,
                   self._tg_audio_cb, self._tg_emb_cb, self._tg_system_cb):
            sl4.addWidget(cb)

        self._tg_cooldown_edit = _int_edit(tg.get("cooldown", 60), 1, 3600)
        sl4.addLayout(_row("재전송 대기(초)", self._tg_cooldown_edit,
                           "동일 감지유형 연속 재전송 방지. 기본 60초"))
        vl.addWidget(box4)

        # 자동 재시작
        box5, sl5 = _section("자동 재시작")
        self._restart1_cb = QCheckBox("재시작 시각 1 활성화")
        self._restart1_cb.setChecked(bool(sys_cfg.get("scheduled_restart_time", "")))
        self._restart1_edit = QLineEdit(sys_cfg.get("scheduled_restart_time", ""))
        self._restart1_edit.setPlaceholderText("HH:MM")
        self._restart1_edit.setFixedWidth(80)
        restart1_hl = QHBoxLayout()
        restart1_hl.setContentsMargins(0, 0, 0, 0)
        restart1_hl.addWidget(self._restart1_cb)
        restart1_hl.addWidget(self._restart1_edit)
        restart1_hl.addStretch()
        sl5.addLayout(restart1_hl)

        self._restart2_cb = QCheckBox("재시작 시각 2 활성화")
        self._restart2_cb.setChecked(bool(sys_cfg.get("scheduled_restart_time_2", "")))
        self._restart2_edit = QLineEdit(sys_cfg.get("scheduled_restart_time_2", ""))
        self._restart2_edit.setPlaceholderText("HH:MM")
        self._restart2_edit.setFixedWidth(80)
        restart2_hl = QHBoxLayout()
        restart2_hl.setContentsMargins(0, 0, 0, 0)
        restart2_hl.addWidget(self._restart2_cb)
        restart2_hl.addWidget(self._restart2_edit)
        restart2_hl.addStretch()
        sl5.addLayout(restart2_hl)
        vl.addWidget(box5)

        vl.addStretch()
        return _make_scroll(inner)

    # ─────────────────────────────────────────────────────────────────
    # 탭 7: 저장/불러오기
    # ─────────────────────────────────────────────────────────────────

    def _build_tab_save(self) -> QWidget:
        inner = QWidget()
        vl = QVBoxLayout(inner)
        vl.setContentsMargins(12, 12, 12, 12)
        vl.setSpacing(10)

        # 저장
        box1, sl1 = _section("설정 파일 저장")
        btn_export = QPushButton("현재 설정 저장...")
        btn_export.setObjectName("btnOutlineOrange")
        btn_export.setMinimumHeight(48)
        btn_export.clicked.connect(self._export_config)
        sl1.addWidget(btn_export)
        vl.addWidget(box1)

        # 불러오기
        box2, sl2 = _section("설정 파일 불러오기")
        btn_import = QPushButton("설정 파일 불러오기...")
        btn_import.setObjectName("btnOutlineOrange")
        btn_import.setMinimumHeight(48)
        btn_import.clicked.connect(self._import_config)
        sl2.addWidget(btn_import)
        vl.addWidget(box2)

        # 초기화
        box3, sl3 = _section("기본값으로 초기화")
        btn_reset_all = QPushButton("기본값으로 초기화")
        btn_reset_all.setObjectName("btnOutlineDanger")
        btn_reset_all.setMinimumHeight(48)
        btn_reset_all.clicked.connect(self._reset_all_settings)
        sl3.addWidget(btn_reset_all)
        vl.addWidget(box3)

        # About
        box4, sl4 = _section("About")
        from utils.config_manager import DEFAULT_CONFIG
        about_lbl = QLabel(
            "버전:     KBS Monitoring v2.0.0\n"
            "날짜:     2026-04-18\n"
            "제작:     KBS 기술본부"
        )
        about_lbl.setObjectName("settingsAbout")
        sl4.addWidget(about_lbl)
        vl.addWidget(box4)

        vl.addStretch()
        return _make_scroll(inner)

    # ─────────────────────────────────────────────────────────────────
    # 설정 수집 / 저장
    # ─────────────────────────────────────────────────────────────────

    def _collect_config(self):
        """모든 위젯 값을 읽어 self._cfg 업데이트."""
        cfg = self._cfg

        # 영상설정
        try:
            cfg["port"] = int(self._port_edit.text() or 0)
        except ValueError:
            cfg["port"] = 0
        cfg["video_file"] = self._video_file_edit.text().strip()

        rec = cfg.setdefault("recording", {})
        rec["enabled"] = self._rec_enabled_cb.isChecked()
        rec["save_dir"] = self._rec_dir_edit.text().strip() or "recordings"
        rec["pre_seconds"] = int(self._rec_pre_edit.text() or 5)
        rec["post_seconds"] = int(self._rec_post_edit.text() or 15)
        rec["max_keep_days"] = int(self._rec_keep_edit.text() or 7)
        wv, hv = self._res_combo.currentData()
        rec["output_width"] = wv
        rec["output_height"] = hv
        rec["output_fps"] = self._fps_combo.currentData()

        # ROI
        self._save_rois_to_cfg()

        # 감도설정
        det = cfg.setdefault("detection", {})
        det["black_threshold"] = int(self._black_thresh.text() or 10)
        det["black_dark_ratio"] = float(self._black_ratio.text() or 95.0)
        det["black_motion_suppress_ratio"] = float(self._black_suppress.text() or 0.2)
        det["black_duration"] = int(self._black_dur.text() or 20)
        det["black_alarm_duration"] = int(self._black_alarm_dur.text() or 60)

        det["still_threshold"] = int(self._still_thresh.text() or 8)
        det["still_changed_ratio"] = float(self._still_changed.text() or 2.0)
        det["still_reset_frames"] = int(self._still_reset.text() or 3)
        det["still_duration"] = int(self._still_dur.text() or 60)
        det["still_alarm_duration"] = int(self._still_alarm_dur.text() or 60)

        h_lo, h_hi = self._hsv_h.get_range()
        s_lo, s_hi = self._hsv_s.get_range()
        v_lo, v_hi = self._hsv_v.get_range()
        det["audio_hsv_h_min"] = h_lo
        det["audio_hsv_h_max"] = h_hi
        det["audio_hsv_s_min"] = s_lo
        det["audio_hsv_s_max"] = s_hi
        det["audio_hsv_v_min"] = v_lo
        det["audio_hsv_v_max"] = v_hi
        det["audio_pixel_ratio"] = float(self._audio_pixel_ratio.text() or 5.0)
        det["audio_level_duration"] = int(self._audio_level_dur.text() or 20)
        det["audio_level_alarm_duration"] = int(self._audio_level_alarm_dur.text() or 60)
        det["audio_level_recovery_seconds"] = float(self._audio_recovery.text() or 2.0)

        det["embedded_silence_threshold"] = int(self._emb_thresh.text() or -50)
        det["embedded_silence_duration"] = int(self._emb_dur.text() or 20)
        det["embedded_alarm_duration"] = int(self._emb_alarm_dur.text() or 60)

        perf = cfg.setdefault("performance", {})
        perf["detection_interval"] = self._detect_interval_combo.currentData()
        perf["scale_factor"] = self._scale_combo.currentData()
        perf["black_detection_enabled"] = self._black_enabled_cb.isChecked()
        perf["still_detection_enabled"] = self._still_enabled_cb.isChecked()
        perf["audio_detection_enabled"] = self._audio_enabled_cb.isChecked()
        perf["embedded_detection_enabled"] = self._emb_enabled_cb.isChecked()

        # 정파설정
        so = cfg.setdefault("signoff", {})
        so["auto_preparation"] = self._auto_prep_cb.isChecked()
        so["prep_alarm_sound"] = self._so_prep_sound.text().strip()
        so["enter_alarm_sound"] = self._so_enter_sound.text().strip()
        so["release_alarm_sound"] = self._so_release_sound.text().strip()
        for idx, gid in enumerate((1, 2)):
            w = self._so_grp[idx]
            grp = so.setdefault(f"group{gid}", {})
            grp["name"] = w["name"].text().strip()
            sh = w["start_h"].text().zfill(2)
            sm = w["start_m"].text().zfill(2)
            eh = w["end_h"].text().zfill(2)
            em = w["end_m"].text().zfill(2)
            grp["start_time"] = f"{sh}:{sm}"
            grp["end_time"] = f"{eh}:{em}"
            grp["end_next_day"] = w["end_next_day"].isChecked()
            grp["prep_minutes"] = w["prep_minutes"].currentData()
            grp["exit_prep_minutes"] = w["exit_prep_minutes"].currentData()
            grp["exit_trigger_sec"] = int(w["exit_trigger_sec"].text() or 5)
            grp["weekdays"] = [d for d, cb in enumerate(w["weekdays"])
                               if cb.isChecked()]
            grp["enter_roi"] = w["_enter_roi"]
            grp["suppressed_labels"] = w["_suppressed"]

        # 알림설정
        alm = cfg.setdefault("alarm", {})
        alm["sound_file"] = self._alarm_sound_edit.text().strip()

        emb = cfg.setdefault("embedded", {})
        emb["audio_input_device"] = self._audio_dev_combo.currentData() or ""

        tg = cfg.setdefault("telegram", {})
        tg["enabled"] = self._tg_enabled_cb.isChecked()
        tg["bot_token"] = self._tg_token_edit.text().strip()
        tg["chat_id"] = self._tg_chat_edit.text().strip()
        tg["send_image"] = self._tg_image_cb.isChecked()
        tg["notify_black"] = self._tg_black_cb.isChecked()
        tg["notify_still"] = self._tg_still_cb.isChecked()
        tg["notify_audio_level"] = self._tg_audio_cb.isChecked()
        tg["notify_embedded"] = self._tg_emb_cb.isChecked()
        tg["notify_system"] = self._tg_system_cb.isChecked()
        tg["cooldown"] = int(self._tg_cooldown_edit.text() or 60)

        sys_cfg = cfg.setdefault("system", {})
        sys_cfg["scheduled_restart_time"] = (
            self._restart1_edit.text().strip()
            if self._restart1_cb.isChecked() else "")
        sys_cfg["scheduled_restart_time_2"] = (
            self._restart2_edit.text().strip()
            if self._restart2_cb.isChecked() else "")

    def _on_save(self):
        self._collect_config()
        self._cfg_mgr.save(self._cfg)
        self._send_cmd_apply()
        self.config_saved.emit(copy.deepcopy(self._cfg))
        QMessageBox.information(self, "저장 완료", "설정이 저장되었습니다.")

    def _send_cmd_apply(self):
        if self._cmd_queue is None:
            return
        try:
            from ipc.messages import ApplyConfig, UpdateROIs
            self._put_cmd(ApplyConfig(config=self._cfg, reason="settings_save"))
            roi_list = (
                [{"label": r.label, "media_name": r.media_name,
                  "x": r.x, "y": r.y, "w": r.w, "h": r.h, "roi_type": "video"}
                 for r in self._roi_mgr.video_rois] +
                [{"label": r.label, "media_name": r.media_name,
                  "x": r.x, "y": r.y, "w": r.w, "h": r.h, "roi_type": "audio"}
                 for r in self._roi_mgr.audio_rois]
            )
            self._put_cmd(UpdateROIs(rois=roi_list))
        except Exception:
            pass

    def _put_cmd(self, msg):
        try:
            self._cmd_queue.put_nowait(msg)
        except Exception:
            try:
                self._cmd_queue.get_nowait()
                self._cmd_queue.put_nowait(msg)
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────────
    # 브라우저 / 테스트 / 리셋 슬롯
    # ─────────────────────────────────────────────────────────────────

    def _browse_video_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "테스트용 영상 파일 선택", "",
            "동영상 파일 (*.mp4 *.avi *.mkv *.mov);;모든 파일 (*)")
        if path:
            self._video_file_edit.setText(path)

    def _browse_rec_dir(self):
        path = QFileDialog.getExistingDirectory(self, "녹화 저장 폴더 선택",
                                                 self._rec_dir_edit.text())
        if path:
            self._rec_dir_edit.setText(path)

    def _open_rec_dir(self):
        path = os.path.abspath(self._rec_dir_edit.text() or "recordings")
        os.makedirs(path, exist_ok=True)
        try:
            subprocess.Popen(f'explorer "{path}"')
        except Exception:
            pass

    def _browse_sound(self, edit: QLineEdit):
        path, _ = QFileDialog.getOpenFileName(
            self, "사운드 파일 선택", edit.text(),
            "WAV 파일 (*.wav);;모든 파일 (*)")
        if path:
            edit.setText(path)

    def _test_sound(self, path: str):
        if self._alarm is not None:
            self._alarm.play_test_sound(path)

    def _test_telegram(self):
        token = self._tg_token_edit.text().strip()
        chat_id = self._tg_chat_edit.text().strip()
        if not token or not chat_id:
            QMessageBox.warning(self, "오류", "Bot Token과 Chat ID를 입력하세요.")
            return
        try:
            import requests
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            resp = requests.post(url, data={"chat_id": chat_id,
                                             "text": "[KBS Monitoring v2] 연결 테스트"},
                                  timeout=5)
            if resp.ok:
                QMessageBox.information(self, "성공", "텔레그램 연결 성공!")
            else:
                QMessageBox.warning(self, "실패",
                                    f"전송 실패: {resp.status_code}\n{resp.text[:200]}")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"연결 오류:\n{e}")

    def _auto_detect_performance(self):
        """현재 CPU/RAM 측정 후 scale_factor / detection_interval 자동 추천."""
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=1.0)
            ram = psutil.virtual_memory().percent
        except ImportError:
            QMessageBox.warning(self, "오류", "psutil이 설치되어 있지 않습니다.")
            return

        if cpu < 40 and ram < 60:
            interval, scale, msg = 200, 1.0, "성능 여유 충분 — 기본값 (200ms / 원본)"
        elif cpu < 65:
            interval, scale, msg = 500, 1.0, "CPU 중간 — 감지 주기 500ms 권장"
        else:
            interval, scale, msg = 500, 0.5, "CPU 부하 높음 — 500ms + 0.5× 해상도 권장"

        for i in range(self._detect_interval_combo.count()):
            if self._detect_interval_combo.itemData(i) == interval:
                self._detect_interval_combo.setCurrentIndex(i)
                break
        for i in range(self._scale_combo.count()):
            if abs(self._scale_combo.itemData(i) - scale) < 0.01:
                self._scale_combo.setCurrentIndex(i)
                break
        QMessageBox.information(
            self, "자동 성능 감지 결과",
            f"CPU: {cpu:.1f}%  RAM: {ram:.1f}%\n\n{msg}")

    def _reset_video_settings(self):
        if QMessageBox.question(
            self, "확인", "영상설정을 기본값으로 초기화하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No
        ) != QMessageBox.Yes:
            return
        d = DEFAULT_CONFIG
        self._port_edit.setText(str(d.get("port", 0)))
        self._video_file_edit.clear()
        rec = d.get("recording", {})
        self._rec_enabled_cb.setChecked(rec.get("enabled", True))
        self._rec_dir_edit.setText(rec.get("save_dir", "recordings"))
        self._rec_pre_edit.setText(str(rec.get("pre_seconds", 5)))
        self._rec_post_edit.setText(str(rec.get("post_seconds", 15)))
        self._rec_keep_edit.setText(str(rec.get("max_keep_days", 7)))

    def _reset_signoff_settings(self):
        if QMessageBox.question(
            self, "확인", "정파설정을 기본값으로 초기화하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No
        ) != QMessageBox.Yes:
            return
        d = DEFAULT_CONFIG.get("signoff", {})
        self._auto_prep_cb.setChecked(d.get("auto_preparation", True))
        self._so_prep_sound.clear()
        self._so_enter_sound.clear()
        self._so_release_sound.clear()

    def _export_config(self):
        self._collect_config()
        path, _ = QFileDialog.getSaveFileName(
            self, "설정 저장", "kbs_config_backup.json",
            "JSON 파일 (*.json)")
        if not path:
            return
        try:
            import json
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._cfg, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "저장 완료", f"저장됨:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"저장 실패:\n{e}")

    def _import_config(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "설정 불러오기", "",
            "JSON 파일 (*.json);;모든 파일 (*)")
        if not path:
            return
        try:
            import json
            with open(path, "r", encoding="utf-8") as f:
                new_cfg = json.load(f)
            self._cfg_mgr.save(new_cfg)
            self._cfg = new_cfg
            self._load_rois_from_cfg()
            self._on_save()
            QMessageBox.information(self, "완료",
                                    "설정을 불러왔습니다. 적용하려면 프로그램을 재시작하세요.")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"불러오기 실패:\n{e}")

    def _reset_all_settings(self):
        if QMessageBox.question(
            self, "확인",
            "모든 설정을 기본값으로 초기화하시겠습니까?\n현재 설정이 모두 사라집니다.",
            QMessageBox.Yes | QMessageBox.No
        ) != QMessageBox.Yes:
            return
        self._cfg = copy.deepcopy(DEFAULT_CONFIG)
        self._cfg_mgr.save(self._cfg)
        self._send_cmd_apply()
        self.config_saved.emit(copy.deepcopy(self._cfg))
        QMessageBox.information(self, "완료",
                                "기본값으로 초기화했습니다. 재시작 후 완전 적용됩니다.")
        self.close()
