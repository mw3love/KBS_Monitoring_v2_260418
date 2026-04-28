"""
설정 다이얼로그 (7탭, 비모달)
변경 즉시 ConfigManager에 JSON 기록 + cmd_queue로 ApplyConfig / UpdateROIs 발행.
체크박스·콤보박스는 변경 즉시, QLineEdit는 editingFinished 시점에 반영.
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
from PySide6.QtCore import Qt, Signal, QThread
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


class _TelegramTestWorker(QThread):
    """텔레그램 연결 테스트를 백그라운드에서 실행해 UI freeze를 방지한다."""
    result_ready = Signal(bool, str)  # (success, message)

    def __init__(self, token: str, chat_id: str):
        super().__init__()
        self._token = token
        self._chat_id = chat_id

    def run(self):
        try:
            import requests
            url = f"https://api.telegram.org/bot{self._token}/sendMessage"
            resp = requests.post(
                url,
                data={"chat_id": self._chat_id, "text": "[KBS On-Air Monitoring] 연결 테스트"},
                timeout=5,
            )
            if resp.ok:
                self.result_ready.emit(True, "")
            else:
                self.result_ready.emit(False, f"전송 실패: {resp.status_code}\n{resp.text[:200]}")
        except Exception as e:
            self.result_ready.emit(False, f"연결 오류:\n{e}")


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


def _sep() -> QFrame:
    """가로 구분선."""
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    return line


def _make_scroll(inner: QWidget) -> QScrollArea:
    """inner를 QScrollArea로 감싸 반환. setWidget() 즉시 호출."""
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setWidget(inner)
    return sa


def _section(title: str, enable_cb=None) -> tuple["QFrame", "QVBoxLayout"]:
    """테두리 박스 섹션. (box_frame, inner_layout) 반환.
    enable_cb: 제목 왼쪽에 놓을 활성화 체크박스 (QCheckBox 인스턴스 전달)
    """
    box = QFrame()
    box.setObjectName("settingsSection")
    outer_vl = QVBoxLayout(box)
    outer_vl.setContentsMargins(14, 10, 14, 12)
    outer_vl.setSpacing(0)

    if enable_cb is not None:
        header_hl = QHBoxLayout()
        header_hl.setContentsMargins(0, 0, 0, 0)
        header_hl.setSpacing(6)
        header_hl.addWidget(enable_cb)
        lbl = QLabel(title)
        lbl.setObjectName("settingsSectionLabel")
        header_hl.addWidget(lbl)
        header_hl.addStretch()
        outer_vl.addLayout(header_hl)
    else:
        lbl = QLabel(title)
        lbl.setObjectName("settingsSectionLabel")
        lbl.setContentsMargins(0, 0, 0, 0)
        outer_vl.addWidget(lbl)

    content_vl = QVBoxLayout()
    content_vl.setContentsMargins(0, 8, 0, 0)
    content_vl.setSpacing(8)
    outer_vl.addLayout(content_vl)

    return box, content_vl


def _row(label_text: str, widget: QWidget, hint: str = "") -> QHBoxLayout:
    """label(고정폭 220) + widget + hint 한 행"""
    h = QHBoxLayout()
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(10)
    lbl = QLabel(label_text)
    lbl.setObjectName("settingsRowLabel")
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


def _hsv_row(label_text: str, slider: "DualSlider",
             hint: str = "") -> "tuple[QHBoxLayout, QLineEdit, QLineEdit]":
    """HSV 슬라이더 행: label + slider + min_edit ~ max_edit + hint.
    (layout, min_edit, max_edit) 반환."""
    h = QHBoxLayout()
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(8)
    lbl = QLabel(label_text)
    lbl.setObjectName("settingsRowLabel")
    lbl.setFixedWidth(180)
    h.addWidget(lbl)
    h.addWidget(slider, 1)
    lo_val, hi_val = slider.get_range()
    min_edit = QLineEdit(str(lo_val))
    min_edit.setFixedWidth(44)
    min_edit.setAlignment(Qt.AlignCenter)
    min_edit.setObjectName("hsvValueEdit")
    sep = QLabel("~")
    sep.setFixedWidth(10)
    sep.setAlignment(Qt.AlignCenter)
    max_edit = QLineEdit(str(hi_val))
    max_edit.setFixedWidth(44)
    max_edit.setAlignment(Qt.AlignCenter)
    max_edit.setObjectName("hsvValueEdit")
    h.addWidget(min_edit)
    h.addWidget(sep)
    h.addWidget(max_edit)
    if hint:
        d = QLabel(hint)
        d.setObjectName("settingsDesc")
        h.addWidget(d, 1)
    else:
        h.addStretch(1)
    return h, min_edit, max_edit


def _file_row(label_text: str, edit: QLineEdit,
              browse_cb, test_cb=None, reset_cb=None) -> QHBoxLayout:
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
            cb.setToolTip("")
            vl.addWidget(cb)
            self._suppress_checks.append((roi.label, cb))

        if not all_rois:
            vl.addWidget(QLabel("(감지영역 없음)"))

        self._enter_combo.currentIndexChanged.connect(self._sync_trigger_checkbox)
        self._sync_trigger_checkbox()

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

    def _sync_trigger_checkbox(self):
        """진입 트리거로 선택된 ROI의 억제 체크박스를 자동 체크·비활성화."""
        trigger_label = self._enter_combo.currentData() or ""
        for label, cb in self._suppress_checks:
            if label == trigger_label:
                cb.setChecked(True)
                cb.setEnabled(False)
                cb.setToolTip("진입 트리거 항목은 자동으로 억제됩니다")
            else:
                cb.setEnabled(True)
                cb.setToolTip("")

    def get_result(self) -> dict:
        enter_label = self._enter_combo.currentData() or ""
        suppressed = [label for label, cb in self._suppress_checks if cb.isChecked()]
        # 진입 트리거가 억제 목록에 누락되지 않도록 보장
        if enter_label and enter_label not in suppressed:
            suppressed.append(enter_label)
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
    _applying = False  # 재진입 방지 플래그 (클래스 수준)

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
                 frozen_frame=None, parent=None, cmd_event=None):
        super().__init__(parent, Qt.Window)
        self._cfg = copy.deepcopy(cfg)
        self._cmd_queue = cmd_queue
        self._cmd_event = cmd_event
        self._alarm = alarm
        self._frozen_frame = frozen_frame
        self._cfg_mgr = ConfigManager()

        self._roi_mgr = ROIManager()
        self._load_rois_from_cfg()

        self.setWindowTitle("KBS On-Air Monitoring — 설정")
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


        self._switch_tab(0)

    def _switch_tab(self, idx: int):
        # 탭 전환 시 활성화된 편집 오버레이 자동 종료
        current = self._stack.currentIndex()
        if current == 1 and idx != 1:
            self._stop_edit_if_active("video")
        elif current == 2 and idx != 2:
            self._stop_edit_if_active("audio")

        for i, btn in enumerate(self._tab_btns):
            btn.setChecked(i == idx)
        self._stack.setCurrentIndex(idx)

    def _stop_edit_if_active(self, roi_type: str):
        """편집 오버레이가 활성 상태이면 종료하고 버튼 상태를 초기화한다."""
        from ui.main_window import MainWindow
        mw = self.parent()
        if isinstance(mw, MainWindow) and getattr(mw, "_roi_overlay", None) is not None:
            mw._stop_roi_overlay(done_callback=lambda: self._on_roi_editing_done(roi_type))

    # ─────────────────────────────────────────────────────────────────
    # 탭 1: 영상설정
    # ─────────────────────────────────────────────────────────────────

    def _build_tab_video(self) -> QScrollArea:
        inner = QWidget()
        vl = QVBoxLayout(inner)
        vl.setContentsMargins(16, 16, 16, 16)
        vl.setSpacing(12)

        # ── 캡처 포트 ──────────────────────────────────────────
        box1, sl1 = _section("캡처 포트")
        self._port_combo = QComboBox()
        for i in range(4):
            self._port_combo.addItem(str(i), i)
        self._port_combo.setCurrentIndex(self._cfg.get("port", 0))
        sl1.addLayout(_row("포트 번호 (0~3)", self._port_combo,
                           "캡처카드 포트 번호 (0~3)"))
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
        btn_vf_reset.clicked.connect(lambda: (self._video_file_edit.clear(), self._apply_now()))
        file_hl.addWidget(btn_vf_browse)
        file_hl.addWidget(btn_vf_reset)
        sl2.addLayout(file_hl)
        vl.addWidget(box2)

        # ── 자동 녹화 설정 ──────────────────────────────────────
        rec = self._cfg.get("recording", {})
        self._rec_enabled_cb = QCheckBox()
        self._rec_enabled_cb.setChecked(rec.get("enabled", True))
        box3, sl3 = _section("자동 녹화 설정", enable_cb=self._rec_enabled_cb)

        dir_widget = QWidget()
        dir_hl = QHBoxLayout(dir_widget)
        dir_hl.setContentsMargins(0, 0, 0, 0)
        dir_hl.setSpacing(4)
        self._rec_dir_edit = QLineEdit(rec.get("save_dir", "recordings"))
        dir_hl.addWidget(self._rec_dir_edit, 1)
        btn_dir_browse = QPushButton("찾아보기")
        btn_dir_browse.clicked.connect(self._browse_rec_dir)
        btn_dir_open = QPushButton("폴더 열기")
        btn_dir_open.clicked.connect(self._open_rec_dir)
        dir_hl.addWidget(btn_dir_browse)
        dir_hl.addWidget(btn_dir_open)
        sl3.addLayout(_row("저장 폴더", dir_widget))

        self._rec_pre_edit = _int_edit(rec.get("pre_seconds", 5), 1, 30)
        self._rec_post_edit = _int_edit(rec.get("post_seconds", 15), 1, 60)
        self._rec_keep_edit = _int_edit(rec.get("max_keep_days", 7), 1, 365)
        sl3.addLayout(_row("시작 전 버퍼 (초)", self._rec_pre_edit,
                           "1~30 / 기본값 5 — 알림 발생 전 구간 저장"))
        sl3.addLayout(_row("이후 녹화 시간 (초)", self._rec_post_edit,
                           "1~60 / 기본값 15 — 알림 발생 후 추가 녹화"))
        sl3.addLayout(_row("최대 보관 기간 (일)", self._rec_keep_edit,
                           "1~365 / 기본값 7 — 초과 파일 자동 삭제"))
        vl.addWidget(box3)

        # dim 처리용 위젯 목록 (자동 녹화 활성화 체크박스 연동)
        self._rec_sub_widgets = [
            self._rec_dir_edit, btn_dir_browse, btn_dir_open,
            self._rec_pre_edit, self._rec_post_edit, self._rec_keep_edit,
        ]

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
        sl4.addLayout(_row("출력 FPS", self._fps_combo,
                           "10fps 권장 (파일 크기 절약)"))
        vl.addWidget(box4)

        # dim 처리 목록에 녹화 품질 위젯 추가
        self._rec_sub_widgets += [self._res_combo, self._fps_combo]

        # 용량 추정 정보 바
        self._capacity_label = QLabel()
        self._capacity_label.setObjectName("capacityBar")
        self._capacity_label.setTextFormat(Qt.RichText)
        vl.addWidget(self._capacity_label)

        # 즉시 반영 연결 — 영상설정
        self._port_combo.currentIndexChanged.connect(self._apply_now)
        self._video_file_edit.editingFinished.connect(self._apply_now)
        self._rec_dir_edit.editingFinished.connect(self._apply_now)
        self._rec_pre_edit.editingFinished.connect(self._apply_now)
        self._rec_post_edit.editingFinished.connect(self._apply_now)
        self._rec_keep_edit.editingFinished.connect(self._apply_now)
        self._res_combo.currentIndexChanged.connect(self._apply_now)
        self._fps_combo.currentIndexChanged.connect(self._apply_now)

        # 용량 바 갱신 연결
        self._res_combo.currentIndexChanged.connect(self._update_capacity_label)
        self._fps_combo.currentIndexChanged.connect(self._update_capacity_label)
        self._rec_pre_edit.editingFinished.connect(self._update_capacity_label)
        self._rec_post_edit.editingFinished.connect(self._update_capacity_label)

        # 자동 녹화 체크박스: dim 처리 슬롯 연결
        self._rec_enabled_cb.stateChanged.connect(self._on_rec_enabled_changed)

        # 초기 상태 적용 (신호 연결 후)
        _rec_on = self._rec_enabled_cb.isChecked()
        for _w in self._rec_sub_widgets:
            _w.setEnabled(_rec_on)
        self._update_capacity_label()

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
        vl.setContentsMargins(16, 16, 16, 16)
        vl.setSpacing(12)

        kind_name = "비디오" if roi_type == "video" else "오디오 레벨미터"
        btn_edit = QPushButton(f"▶ {kind_name} 감지영역 편집")
        btn_edit.setObjectName("btnPrimary")
        btn_edit.setCheckable(True)
        btn_edit.clicked.connect(lambda checked: self._toggle_roi_editor(roi_type, checked, btn_edit))
        vl.addWidget(btn_edit)

        # 편집 버튼 참조 보관 (외부에서 상태 초기화용)
        if roi_type == "video":
            self._btn_edit_video = btn_edit
        else:
            self._btn_edit_audio = btn_edit

        # 단축키 안내
        shortcut_lbl = QLabel(
            "<b>편집 중 단축키</b><br>"
            "<table cellspacing='4'>"
            "<tr><td>↑↓←→</td><td>이동 10px</td></tr>"
            "<tr><td>Shift+↑↓←→</td><td>이동 1px</td></tr>"
            "<tr><td>Ctrl+↑↓←→</td><td>크기 10px</td></tr>"
            "<tr><td>Ctrl+Shift+↑↓←→</td><td>크기 1px</td></tr>"
            "<tr><td>Ctrl+D</td><td>선택 영역 복사</td></tr>"
            "<tr><td>Delete</td><td>선택 영역 삭제</td></tr>"
            "<tr><td>Ctrl+드래그(빈 곳)</td><td>범위 다중 선택</td></tr>"
            "<tr><td>Ctrl+클릭</td><td>선택 추가/제거</td></tr>"
            "<tr><td>Ctrl+드래그(선택 후)</td><td>복사하며 이동</td></tr>"
            "</table>"
        )
        shortcut_lbl.setObjectName("roiShortcutLabel")
        shortcut_lbl.setTextFormat(Qt.RichText)
        vl.addWidget(shortcut_lbl)

        # ROI 개수 카운터 라벨
        count_lbl = QLabel()
        count_lbl.setObjectName("roiCountLabel")
        count_lbl.setStyleSheet("color: #888; font-size: 11px;")
        if roi_type == "video":
            self._video_roi_count_lbl = count_lbl
        else:
            self._audio_roi_count_lbl = count_lbl
        vl.addWidget(count_lbl)

        # ROI 테이블
        table = QTableWidget()
        table.setObjectName("roiTable")
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["라벨", "매체명", "X", "Y", "W", "H"])
        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        table.setColumnWidth(0, 48)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        for _col in (2, 3, 4, 5):
            hdr.setSectionResizeMode(_col, QHeaderView.Fixed)
            table.setColumnWidth(_col, 60)
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

        # Del 키 → 선택 행 삭제
        orig_kpe = table.keyPressEvent
        def _kpe(event, _rt=roi_type, _tbl=table, _orig=orig_kpe):
            if event.key() == Qt.Key_Delete:
                self._roi_table_del(_rt, _tbl)
            else:
                _orig(event)
        table.keyPressEvent = _kpe

        # 테이블 셀 편집 완료 시 즉시 반영
        table.itemChanged.connect(
            lambda: self._on_roi_table_changed(roi_type, table)
        )

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
        # 개수 카운터 갱신
        count_lbl = (self._video_roi_count_lbl if roi_type == "video"
                     else self._audio_roi_count_lbl)
        n = len(rois)
        if n == 0:
            count_lbl.setText("감지영역  0개 (등록된 영역 없음)")
            count_lbl.setStyleSheet("color: #666; font-size: 11px;")
        else:
            count_lbl.setText(f"감지영역  {n}개 등록됨")
            count_lbl.setStyleSheet("color: #aaa; font-size: 11px;")

    def _toggle_roi_editor(self, roi_type: str, checked: bool, btn: QPushButton):
        """편집 버튼 토글: ON→오버레이 열기, OFF→오버레이 닫기."""
        from ui.main_window import MainWindow
        mw = self.parent()
        if not isinstance(mw, MainWindow):
            btn.setChecked(False)
            table = self._video_roi_table if roi_type == "video" else self._audio_roi_table
            self._sync_table_to_rois(roi_type, table)
            dlg = FullScreenROIEditor(self._roi_mgr, roi_type,
                                       self._frozen_frame, parent=self)
            dlg.editing_done.connect(lambda: self._on_roi_editing_done(roi_type))
            dlg.exec()
            return

        if checked:
            # 편집 시작 전 테이블의 매체명·좌표를 ROIManager에 먼저 반영
            table = self._video_roi_table if roi_type == "video" else self._audio_roi_table
            self._sync_table_to_rois(roi_type, table)
            btn.setText("■ 편집 종료 (클릭하여 완료)")
            mw.start_roi_overlay(
                roi_type,
                self._roi_mgr,
                rois_changed_cb=lambda: self._refresh_roi_table(roi_type),
                done_callback=lambda: self._on_roi_editing_done(roi_type),
            )
        else:
            mw._stop_roi_overlay(done_callback=lambda: self._on_roi_editing_done(roi_type))

    def _on_roi_editing_done(self, roi_type: str):
        """오버레이 종료 후 버튼 상태·텍스트 초기화 및 테이블·VideoWidget 갱신."""
        kind_name = "비디오" if roi_type == "video" else "오디오 레벨미터"
        btn = self._btn_edit_video if roi_type == "video" else self._btn_edit_audio
        btn.setChecked(False)
        btn.setText(f"▶ {kind_name} 감지영역 편집")
        self._refresh_roi_table(roi_type)
        self._apply_now()

    def _on_roi_table_changed(self, roi_type: str, table: QTableWidget):
        """테이블 셀 직접 편집 완료 시 ROIManager·오버레이·VideoWidget 즉시 갱신."""
        if SettingsDialog._applying:
            return
        self._sync_table_to_rois(roi_type, table)
        self._sync_overlay_canvas(roi_type)
        self._apply_now()

    def _roi_table_add(self, roi_type: str, table: QTableWidget):
        self._sync_table_to_rois(roi_type, table)
        rois = list(self._roi_mgr.video_rois if roi_type == "video"
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
        self._sync_overlay_canvas(roi_type)
        self._refresh_roi_table(roi_type)
        self._apply_now()

    def _roi_table_del(self, roi_type: str, table: QTableWidget):
        self._sync_table_to_rois(roi_type, table)
        rows = sorted(set(i.row() for i in table.selectedItems()), reverse=True)
        if not rows:
            # 선택 없으면 마지막 행 폴백
            if table.rowCount() == 0:
                return
            rows = [table.rowCount() - 1]
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
        self._sync_overlay_canvas(roi_type)
        self._refresh_roi_table(roi_type)
        self._apply_now()

    @staticmethod
    def _table_cell_text(table: QTableWidget, row: int, col: int) -> str:
        item = table.item(row, col)
        return item.text() if item else ""

    def _sync_table_to_rois(self, roi_type: str, table: QTableWidget):
        """테이블에서 편집된 매체명·좌표값을 ROI 매니저에 반영."""
        rois = (self._roi_mgr.video_rois if roi_type == "video"
                else self._roi_mgr.audio_rois)
        for row in range(min(table.rowCount(), len(rois))):
            roi = rois[row]
            roi.media_name = self._table_cell_text(table, row, 1)
            try: roi.x = int(self._table_cell_text(table, row, 2))
            except ValueError: pass
            try: roi.y = int(self._table_cell_text(table, row, 3))
            except ValueError: pass
            try: roi.w = max(1, int(self._table_cell_text(table, row, 4)))
            except ValueError: pass
            try: roi.h = max(1, int(self._table_cell_text(table, row, 5)))
            except ValueError: pass

    def _roi_table_move(self, roi_type: str, table: QTableWidget, direction: int):
        self._sync_table_to_rois(roi_type, table)
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
        self._sync_overlay_canvas(roi_type)
        self._refresh_roi_table(roi_type)
        table.selectRow(new_idx)
        self._apply_now()

    def _roi_table_clear(self, roi_type: str, table: QTableWidget):
        if roi_type == "video":
            self._roi_mgr.replace_video_rois([])
        else:
            self._roi_mgr.replace_audio_rois([])
        self._sync_overlay_canvas(roi_type)
        self._refresh_roi_table(roi_type)
        self._apply_now()

    def _sync_overlay_canvas(self, roi_type: str):
        """편집 오버레이가 활성화된 상태에서 테이블 버튼으로 ROI를 변경했을 때
        캔버스의 내부 복사본을 ROIManager와 동기화한다."""
        from ui.main_window import MainWindow
        mw = self.parent()
        if not isinstance(mw, MainWindow):
            return
        overlay = getattr(mw, "_roi_overlay", None)
        if overlay is None:
            return
        if getattr(mw, "_roi_overlay_type", "") != roi_type:
            return
        overlay._canvas.load_rois()
        overlay._canvas.update()

    # ─────────────────────────────────────────────────────────────────
    # 탭 4: 감도설정
    # ─────────────────────────────────────────────────────────────────

    def _build_tab_sensitivity(self) -> QScrollArea:
        inner = QWidget()
        vl = QVBoxLayout(inner)
        vl.setContentsMargins(16, 16, 16, 16)
        vl.setSpacing(12)
        det = self._cfg.get("detection", {})
        perf = self._cfg.get("performance", {})

        # ── 활성화 체크박스 (섹션 헤더 통합용) ──────────────
        self._black_enabled_cb = QCheckBox()
        self._still_enabled_cb = QCheckBox()
        self._audio_enabled_cb = QCheckBox()
        self._emb_enabled_cb = QCheckBox()
        self._black_enabled_cb.setChecked(perf.get("black_detection_enabled", True))
        self._still_enabled_cb.setChecked(perf.get("still_detection_enabled", True))
        self._audio_enabled_cb.setChecked(perf.get("audio_detection_enabled", True))
        self._emb_enabled_cb.setChecked(perf.get("embedded_detection_enabled", True))

        # ── 블랙 감지 ────────────────────────────────────
        box1, sl1 = _section("블랙 감지", enable_cb=self._black_enabled_cb)
        self._black_thresh = _int_edit(det.get("black_threshold", 5), 0, 255)
        self._black_ratio = _float_edit(det.get("black_dark_ratio", 98.0))
        self._black_suppress = _float_edit(det.get("black_motion_suppress_ratio", 0.2))
        self._black_dur = _int_edit(det.get("black_duration", 20), 1, 300)
        self._black_alarm_dur = _int_edit(det.get("black_alarm_duration", 60), 1, 300)
        sl1.addLayout(_row("밝기 임계값", self._black_thresh,
                           "0~255 / 이 값 이하면 어두운 픽셀로 판단 (기본값: 5)"))
        sl1.addLayout(_row("어두운 픽셀 비율(%)", self._black_ratio,
                           "50~100% / 이 비율 이상이면 블랙 판정 (기본값: 98%)"))
        sl1.addLayout(_row("움직임 감지 시 블랙 무시 기준", self._black_suppress,
                           "0~5.0 / 움직임 비율이 이 이상이면 블랙 억제"))
        sl1.addLayout(_row("알림 발생 기준(초)", self._black_dur,
                           "1~300 / 블랙이 이 시간(초) 이상 지속되면 알림"))
        sl1.addLayout(_row("알림음 지속(초)", self._black_alarm_dur,
                           "1~300 / 알림음이 최대 이 시간 동안 재생"))
        vl.addWidget(box1)
        self._black_section_widgets = (
            self._black_thresh, self._black_ratio, self._black_suppress,
            self._black_dur, self._black_alarm_dur,
        )
        self._toggle_section_widgets(self._black_section_widgets,
                                     self._black_enabled_cb.isChecked())

        # ── 스틸 감지 ────────────────────────────────────
        box2, sl2 = _section("스틸 감지", enable_cb=self._still_enabled_cb)
        self._still_thresh = _int_edit(det.get("still_threshold", 4), 0, 255)
        self._still_changed = _float_edit(det.get("still_changed_ratio", 10.0))
        self._still_reset = _int_edit(det.get("still_reset_frames", 3), 1, 10)
        self._still_dur = _int_edit(det.get("still_duration", 60), 1, 300)
        self._still_alarm_dur = _int_edit(det.get("still_alarm_duration", 60), 1, 300)
        sl2.addLayout(_row("픽셀 차이 임계값", self._still_thresh,
                           "0~255 / 프레임 차이 기준 (기본값: 4)"))
        sl2.addLayout(_row("블록 변화 비율(%)", self._still_changed,
                           "0~100% / 이 비율 미만이면 스틸로 판정 (기본값: 10%)"))
        sl2.addLayout(_row("연속 정상 프레임 수", self._still_reset,
                           "1~10 / 연속 정상 프레임 수 (글리치 방지)"))
        sl2.addLayout(_row("알림 발생 기준(초)", self._still_dur,
                           "1~300 / 정지화면이 이 시간(초) 이상 지속되면 알림"))
        sl2.addLayout(_row("알림음 지속(초)", self._still_alarm_dur,
                           "1~300 / 알림음이 최대 이 시간 동안 재생"))
        vl.addWidget(box2)
        self._still_section_widgets = (
            self._still_thresh, self._still_changed, self._still_reset,
            self._still_dur, self._still_alarm_dur,
        )
        self._toggle_section_widgets(self._still_section_widgets,
                                     self._still_enabled_cb.isChecked())

        # ── 오디오 레벨미터 감지 (HSV) ───────────────────
        box3, sl3 = _section("오디오 레벨미터 감지 (HSV)", enable_cb=self._audio_enabled_cb)

        preset_hl = QHBoxLayout()
        preset_hl.setContentsMargins(0, 0, 0, 4)
        preset_hl.setSpacing(6)
        btn_preset_std = QPushButton("표준 녹색")
        btn_preset_wide = QPushButton("넓은 범위")
        for _btn in (btn_preset_std, btn_preset_wide):
            _btn.setObjectName("btnSecondary")
            _btn.setFixedHeight(26)
            preset_hl.addWidget(_btn)
        preset_hl.addStretch()
        sl3.addLayout(preset_hl)

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
        _row_h, self._hsv_h_min, self._hsv_h_max = _hsv_row(
            "H 범위 (색조, 0~179)", self._hsv_h, "초록=40~95 / 기본값 유지 권장")
        _row_s, self._hsv_s_min, self._hsv_s_max = _hsv_row(
            "S 범위 (채도, 0~255)", self._hsv_s, "기본값 80~255")
        _row_v, self._hsv_v_min, self._hsv_v_max = _hsv_row(
            "V 범위 (명도, 0~255)", self._hsv_v, "기본값 60~255")
        sl3.addLayout(_row_h)
        sl3.addLayout(_row_s)
        sl3.addLayout(_row_v)
        sl3.addLayout(_row("감지 픽셀 비율(%)", self._audio_pixel_ratio,
                           "1~50% / 감지영역 내 해당 색상 픽셀이 이 값 이상이면 활성"))
        sl3.addLayout(_row("알림 발생 기준(초)", self._audio_level_dur,
                           "1~300 / 레벨 이상이 이 시간(초) 이상 지속되면 알림"))
        sl3.addLayout(_row("알림음 지속(초)", self._audio_level_alarm_dur,
                           "1~300 / 알림음이 최대 이 시간 동안 재생"))
        sl3.addLayout(_row("복구 대기(초)", self._audio_recovery,
                           "0~30 / 정상 복귀 후 이 시간이 지나야 알림 해제. 기본값 2"))
        vl.addWidget(box3)
        self._audio_section_widgets = (
            btn_preset_std, btn_preset_wide,
            self._hsv_h, self._hsv_s, self._hsv_v,
            self._hsv_h_min, self._hsv_h_max,
            self._hsv_s_min, self._hsv_s_max,
            self._hsv_v_min, self._hsv_v_max,
            self._audio_pixel_ratio, self._audio_level_dur,
            self._audio_level_alarm_dur, self._audio_recovery,
        )
        self._toggle_section_widgets(self._audio_section_widgets,
                                     self._audio_enabled_cb.isChecked())

        # ── 임베디드 오디오 감지 ──────────────────────────
        box4, sl4 = _section("임베디드 오디오 감지 (무음)", enable_cb=self._emb_enabled_cb)
        self._emb_thresh = _int_edit(det.get("embedded_silence_threshold", -50), -60, 0)
        self._emb_dur = _int_edit(det.get("embedded_silence_duration", 20), 1, 300)
        self._emb_alarm_dur = _int_edit(det.get("embedded_alarm_duration", 60), 1, 300)
        sl4.addLayout(_row("무음 임계값(dB)", self._emb_thresh,
                           "-60~0 / 이 값 이하일 때 무음 판정. 기본값 -50"))
        sl4.addLayout(_row("알림 발생 기준(초)", self._emb_dur,
                           "1~300 / 무음이 이 시간(초) 이상 지속되면 알림"))
        sl4.addLayout(_row("알림음 지속(초)", self._emb_alarm_dur,
                           "1~300 / 알림음이 최대 이 시간 동안 재생"))
        vl.addWidget(box4)
        self._emb_section_widgets = (
            self._emb_thresh, self._emb_dur, self._emb_alarm_dur,
        )
        self._toggle_section_widgets(self._emb_section_widgets,
                                     self._emb_enabled_cb.isChecked())

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
                           "짧을수록 반응 빠름, CPU 부담 증가"))

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

        perf_btn_hl = QHBoxLayout()
        perf_btn_hl.setContentsMargins(0, 0, 0, 0)
        btn_auto_perf = QPushButton("자동 성능 감지")
        btn_auto_perf.setObjectName("btnOutlineOrange")
        btn_auto_perf.clicked.connect(self._auto_detect_performance)
        perf_btn_hl.addWidget(btn_auto_perf)
        perf_btn_hl.addStretch()
        sl5.addLayout(perf_btn_hl)
        vl.addWidget(box5)

        # 즉시 반영 연결 — 감도설정
        for edit in (self._black_thresh, self._black_ratio, self._black_suppress,
                     self._black_dur, self._black_alarm_dur,
                     self._still_thresh, self._still_changed, self._still_reset,
                     self._still_dur, self._still_alarm_dur,
                     self._audio_pixel_ratio, self._audio_level_dur,
                     self._audio_level_alarm_dur, self._audio_recovery,
                     self._emb_thresh, self._emb_dur, self._emb_alarm_dur):
            edit.editingFinished.connect(self._apply_now)
        # 슬라이더 → 입력 필드 동기화
        def _sync_h(lo, hi): self._hsv_h_min.setText(str(lo)); self._hsv_h_max.setText(str(hi))
        def _sync_s(lo, hi): self._hsv_s_min.setText(str(lo)); self._hsv_s_max.setText(str(hi))
        def _sync_v(lo, hi): self._hsv_v_min.setText(str(lo)); self._hsv_v_max.setText(str(hi))
        self._hsv_h.range_changed.connect(_sync_h)
        self._hsv_s.range_changed.connect(_sync_s)
        self._hsv_v.range_changed.connect(_sync_v)
        self._hsv_h.range_changed.connect(self._apply_now)
        self._hsv_s.range_changed.connect(self._apply_now)
        self._hsv_v.range_changed.connect(self._apply_now)

        # 입력 필드 → 슬라이더 동기화
        def _edit_to_h():
            try: self._hsv_h.set_range(int(self._hsv_h_min.text()), int(self._hsv_h_max.text()))
            except ValueError: pass
        def _edit_to_s():
            try: self._hsv_s.set_range(int(self._hsv_s_min.text()), int(self._hsv_s_max.text()))
            except ValueError: pass
        def _edit_to_v():
            try: self._hsv_v.set_range(int(self._hsv_v_min.text()), int(self._hsv_v_max.text()))
            except ValueError: pass
        self._hsv_h_min.editingFinished.connect(_edit_to_h)
        self._hsv_h_max.editingFinished.connect(_edit_to_h)
        self._hsv_s_min.editingFinished.connect(_edit_to_s)
        self._hsv_s_max.editingFinished.connect(_edit_to_s)
        self._hsv_v_min.editingFinished.connect(_edit_to_v)
        self._hsv_v_max.editingFinished.connect(_edit_to_v)

        def _apply_hsv_preset(h_min, h_max, s_min, s_max, v_min, v_max):
            self._hsv_h.set_range(h_min, h_max)
            self._hsv_s.set_range(s_min, s_max)
            self._hsv_v.set_range(v_min, v_max)
            self._apply_now()

        btn_preset_std.clicked.connect(
            lambda: _apply_hsv_preset(40, 95, 80, 255, 60, 255))
        btn_preset_wide.clicked.connect(
            lambda: _apply_hsv_preset(30, 120, 50, 255, 40, 255))
        self._detect_interval_combo.currentIndexChanged.connect(self._apply_now)
        self._scale_combo.currentIndexChanged.connect(self._apply_now)

        self._black_enabled_cb.stateChanged.connect(self._on_black_enabled_changed)
        self._still_enabled_cb.stateChanged.connect(self._on_still_enabled_changed)
        self._audio_enabled_cb.stateChanged.connect(self._on_audio_enabled_changed)
        self._emb_enabled_cb.stateChanged.connect(self._on_emb_enabled_changed)

        vl.addStretch()
        btn_reset_sens = QPushButton("감도설정 전체 초기화")
        btn_reset_sens.setObjectName("btnDanger")
        btn_reset_sens.clicked.connect(self._reset_sensitivity_settings)
        vl.addWidget(btn_reset_sens)

        return _make_scroll(inner)

    @staticmethod
    def _toggle_section_widgets(widgets, enabled: bool):
        for w in widgets:
            w.setEnabled(enabled)

    def _on_black_enabled_changed(self, _state):
        self._toggle_section_widgets(self._black_section_widgets,
                                     self._black_enabled_cb.isChecked())
        self._apply_now()

    def _on_still_enabled_changed(self, _state):
        self._toggle_section_widgets(self._still_section_widgets,
                                     self._still_enabled_cb.isChecked())
        self._apply_now()

    def _on_audio_enabled_changed(self, _state):
        self._toggle_section_widgets(self._audio_section_widgets,
                                     self._audio_enabled_cb.isChecked())
        self._apply_now()

    def _on_emb_enabled_changed(self, _state):
        self._toggle_section_widgets(self._emb_section_widgets,
                                     self._emb_enabled_cb.isChecked())
        self._apply_now()

    # ─────────────────────────────────────────────────────────────────
    # 탭 5: 정파설정
    # ─────────────────────────────────────────────────────────────────

    def _build_tab_signoff(self) -> QScrollArea:
        inner = QWidget()
        vl = QVBoxLayout(inner)
        vl.setContentsMargins(16, 16, 16, 16)
        vl.setSpacing(12)
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

        # 자동 정파 활성화 체크박스 → 하위 섹션 활성/비활성 연동
        _so_sub_boxes = [w["_box"] for w in self._so_grp] + [box_sound]

        def _update_signoff_enabled(state=None):
            enabled = self._auto_prep_cb.isChecked()
            for _box in _so_sub_boxes:
                for child in _box.findChildren(QWidget):
                    if child.objectName() != "settingsSectionLabel":
                        child.setEnabled(enabled)

        self._auto_prep_cb.stateChanged.connect(_update_signoff_enabled)
        _update_signoff_enabled()

        # 즉시 반영 연결 — 정파설정
        self._auto_prep_cb.stateChanged.connect(self._apply_now)
        for edit in (self._so_prep_sound, self._so_enter_sound, self._so_release_sound):
            edit.editingFinished.connect(self._apply_now)
        for w in self._so_grp:
            w["name"].editingFinished.connect(self._apply_now)
            for key in ("start_h", "start_m", "end_h", "end_m",
                        "still_trigger_sec", "exit_trigger_sec"):
                w[key].editingFinished.connect(self._apply_now)
            w["end_next_day"].stateChanged.connect(self._apply_now)
            w["prep_minutes"].currentIndexChanged.connect(self._apply_now)
            w["exit_prep_minutes"].currentIndexChanged.connect(self._apply_now)
            for cb in w["weekdays"]:
                cb.stateChanged.connect(self._apply_now)

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

        widgets = {"_box": box}

        # 그룹명
        name_edit = QLineEdit(grp.get("name", f"{gid}TV"))
        sl.addLayout(_row(f"그룹{gid} 이름", name_edit))
        widgets["name"] = name_edit

        # 정파 시작/종료 시각
        start_h = _int_edit(int(grp.get("start_time", "03:00").split(":")[0]), 0, 23, 50)
        start_m = _int_edit(int(grp.get("start_time", "03:00").split(":")[1]), 0, 59, 50)
        end_h = _int_edit(int(grp.get("end_time", "05:00").split(":")[0]), 0, 23, 50)
        end_m = _int_edit(int(grp.get("end_time", "05:00").split(":")[1]), 0, 59, 50)
        end_next_cb = QCheckBox("익일")
        end_next_cb.setChecked(grp.get("end_next_day", False))
        time_widget = QWidget()
        time_hl = QHBoxLayout(time_widget)
        time_hl.setContentsMargins(0, 0, 0, 0)
        time_hl.setSpacing(4)
        time_hl.addWidget(start_h)
        time_hl.addWidget(QLabel(":"))
        time_hl.addWidget(start_m)
        time_hl.addWidget(QLabel("  종료:"))
        time_hl.addWidget(end_h)
        time_hl.addWidget(QLabel(":"))
        time_hl.addWidget(end_m)
        time_hl.addWidget(end_next_cb)
        time_hl.addStretch()
        sl.addLayout(_row("정파 시간 구간 (시작→종료):", time_widget,
                          "스틸 미감지 시 시작 시각에 자동 정파 진입 (fallback)"))
        widgets.update({"start_h": start_h, "start_m": start_m,
                        "end_h": end_h, "end_m": end_m, "end_next_day": end_next_cb})

        # 정파준비 활성화 (X분 전)
        prep_combo = QComboBox()
        prep_options = [(0, "사용 안 함"), (30, "30분 전"), (60, "1시간 전"),
                        (90, "1.5시간 전"), (120, "2시간 전"), (150, "2.5시간 전"),
                        (180, "3시간 전"), (210, "3.5시간 전"), (240, "4시간 전")]
        cur_prep = grp.get("prep_minutes", 150)
        for val, label in prep_options:
            prep_combo.addItem(label, val)
        for i in range(prep_combo.count()):
            if prep_combo.itemData(i) == cur_prep:
                prep_combo.setCurrentIndex(i)
                break

        prep_calc_lbl = QLabel()
        prep_calc_lbl.setObjectName("settingsDesc")

        def _update_prep_time(_, _pc=prep_combo, _sh=start_h, _sm=start_m, _lbl=prep_calc_lbl):
            minutes = _pc.currentData()
            try:
                sh = int(_sh.text()); sm = int(_sm.text())
            except ValueError:
                _lbl.setText("정파 시작 시각 기준 X분 전부터 ROI 스틸 감시 시작")
                return
            if not minutes:
                _lbl.setText("정파 시작 시각 기준 X분 전부터 ROI 스틸 감시 시작")
                return
            total = (sh * 60 + sm - minutes) % (24 * 60)
            _lbl.setText(f"→  {total // 60:02d}:{total % 60:02d}부터 준비 시작")

        prep_combo.currentIndexChanged.connect(_update_prep_time)
        start_h.textChanged.connect(_update_prep_time)
        start_m.textChanged.connect(_update_prep_time)
        _update_prep_time(None)

        prep_row_hl = QHBoxLayout()
        prep_row_hl.setContentsMargins(0, 0, 0, 0)
        prep_row_hl.setSpacing(10)
        prep_row_lbl = QLabel("정파준비 활성화")
        prep_row_lbl.setObjectName("settingsRowLabel")
        prep_row_lbl.setFixedWidth(220)
        prep_row_hl.addWidget(prep_row_lbl)
        prep_row_hl.addWidget(prep_combo)
        prep_row_hl.addWidget(prep_calc_lbl, 1)
        sl.addLayout(prep_row_hl)
        widgets["prep_minutes"] = prep_combo

        # 정파해제준비 활성화
        exit_prep_combo = QComboBox()
        exit_prep_options = [(0, "사용 안 함"), (30, "30분 전"), (60, "1시간 전"),
                             (120, "2시간 전"), (180, "3시간 전")]
        cur_exit_prep = grp.get("exit_prep_minutes", 30)
        for val, label in exit_prep_options:
            exit_prep_combo.addItem(label, val)
        for i in range(exit_prep_combo.count()):
            if exit_prep_combo.itemData(i) == cur_exit_prep:
                exit_prep_combo.setCurrentIndex(i)
                break

        exit_calc_lbl = QLabel()
        exit_calc_lbl.setObjectName("settingsDesc")

        def _update_exit_prep_time(_, _ec=exit_prep_combo, _eh=end_h, _em=end_m, _lbl=exit_calc_lbl):
            minutes = _ec.currentData()
            try:
                eh = int(_eh.text()); em = int(_em.text())
            except ValueError:
                _lbl.setText("정파 종료 X분 전에 해제준비 구간 시작 (사용 안 함 = 종료 시각에만 해제)")
                return
            if not minutes:
                _lbl.setText("정파 종료 X분 전에 해제준비 구간 시작 (사용 안 함 = 종료 시각에만 해제)")
                return
            total = (eh * 60 + em - minutes) % (24 * 60)
            _lbl.setText(f"→  {total // 60:02d}:{total % 60:02d}부터 해제준비 시작")

        exit_prep_combo.currentIndexChanged.connect(_update_exit_prep_time)
        end_h.textChanged.connect(_update_exit_prep_time)
        end_m.textChanged.connect(_update_exit_prep_time)
        _update_exit_prep_time(None)

        exit_row_hl = QHBoxLayout()
        exit_row_hl.setContentsMargins(0, 0, 0, 0)
        exit_row_hl.setSpacing(10)
        exit_row_lbl = QLabel("정파해제준비 활성화")
        exit_row_lbl.setObjectName("settingsRowLabel")
        exit_row_lbl.setFixedWidth(220)
        exit_row_hl.addWidget(exit_row_lbl)
        exit_row_hl.addWidget(exit_prep_combo)
        exit_row_hl.addWidget(exit_calc_lbl, 1)
        sl.addLayout(exit_row_hl)
        widgets["exit_prep_minutes"] = exit_prep_combo

        # 정파 진입 기준 시간 (ROI 스틸 유지 시간)
        still_trig = _int_edit(int(grp.get("still_trigger_sec", 60)), 5, 300)
        sl.addLayout(_row("정파 진입 기준 시간(초)", still_trig,
                          "ROI 스틸이 이 시간 이상 지속 시 정파 진입"))
        widgets["still_trigger_sec"] = still_trig

        # 조기 해제 트리거 시간
        exit_trig = _int_edit(grp.get("exit_trigger_sec", 5), 1, 300)
        sl.addLayout(_row("조기 해제 기준 시간(초)", exit_trig,
                          "화면이 바뀌면 이 시간 후 정파 종료"))
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
        def _toggle_all_days(checked=False, cbs=day_cbs):
            all_checked = all(cb.isChecked() for cb in cbs)
            for cb in cbs:
                cb.setChecked(not all_checked)
        btn_day_toggle = QPushButton("전체 선택")
        btn_day_toggle.setObjectName("btnNeutral")
        btn_day_toggle.clicked.connect(_toggle_all_days)

        def _update_toggle_label(cbs=day_cbs, btn=btn_day_toggle):
            btn.setText("전체 해제" if all(cb.isChecked() for cb in cbs) else "전체 선택")
        for cb in day_cbs:
            cb.stateChanged.connect(lambda _=0, fn=_update_toggle_label: fn())
        _update_toggle_label()
        day_hl.addWidget(btn_day_toggle)
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
        _enter_roi_init = dict(grp.get("enter_roi") or {"video_label": ""})
        _suppressed_init = list(grp.get("suppressed_labels", []))
        enter_v = _enter_roi_init.get("video_label", "") or ""
        sup_cnt = len(_suppressed_init)
        if enter_v:
            _roi_disp = f"{enter_v} · 억제 {sup_cnt}개" if sup_cnt else enter_v
            _roi_color = ""
        else:
            _roi_disp = "미설정"
            _roi_color = "color: #cc4444;"
        enter_lbl = QLabel(_roi_disp)
        if _roi_color:
            enter_lbl.setStyleSheet(_roi_color)
        roi_btn_hl.addWidget(enter_lbl)
        roi_btn_hl.addStretch()
        sl.addLayout(roi_btn_hl)
        widgets["enter_label_lbl"] = enter_lbl

        # 억제 라벨 내부 저장 (SignoffROIDialog 결과용)
        widgets["_enter_roi"] = _enter_roi_init
        widgets["_suppressed"] = _suppressed_init

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
            enter_v = result["enter_roi"].get("video_label", "") or ""
            sup_cnt = len(result["suppressed_labels"])
            lbl_widget = widgets["enter_label_lbl"]
            if enter_v:
                lbl_widget.setText(f"{enter_v} · 억제 {sup_cnt}개" if sup_cnt else enter_v)
                lbl_widget.setStyleSheet("")
            else:
                lbl_widget.setText("미설정")
                lbl_widget.setStyleSheet("color: #cc4444;")
            self._apply_now()

    # ─────────────────────────────────────────────────────────────────
    # 탭 6: 알림설정
    # ─────────────────────────────────────────────────────────────────

    def _build_tab_alert(self) -> QScrollArea:
        inner = QWidget()
        vl = QVBoxLayout(inner)
        vl.setContentsMargins(16, 16, 16, 16)
        vl.setSpacing(12)
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
            reset_cb=self._reset_alarm_sound,
            test_cb=lambda: self._test_sound(self._alarm_sound_edit.text()),
        ))
        vl.addWidget(box1)

        # 텔레그램
        box3, sl3 = _section("텔레그램 봇 설정")
        self._tg_enabled_cb = QCheckBox("텔레그램 알림 활성화")
        self._tg_enabled_cb.setChecked(tg.get("enabled", False))
        sl3.addWidget(self._tg_enabled_cb)

        # Bot Token (패스워드 모드 + 표시/숨김 토글)
        token_lbl = QLabel("Bot Token")
        token_lbl.setObjectName("settingsRowLabel")
        self._tg_token_edit = QLineEdit(tg.get("bot_token", ""))
        self._tg_token_edit.setPlaceholderText("BotFather에서 발급받은 토큰 (예: 123456789:AAFxxx...)")
        self._tg_token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._btn_tg_token_toggle = QPushButton("표시")
        self._btn_tg_token_toggle.setFixedWidth(48)
        self._btn_tg_token_toggle.clicked.connect(self._toggle_token_echo)
        token_edit_hl = QHBoxLayout()
        token_edit_hl.setContentsMargins(0, 0, 0, 0)
        token_edit_hl.setSpacing(6)
        token_edit_hl.addWidget(self._tg_token_edit, 1)
        token_edit_hl.addWidget(self._btn_tg_token_toggle)
        token_vl = QVBoxLayout()
        token_vl.setContentsMargins(0, 0, 0, 0)
        token_vl.setSpacing(3)
        token_vl.addWidget(token_lbl)
        token_vl.addLayout(token_edit_hl)
        sl3.addLayout(token_vl)

        # Chat ID
        chat_lbl = QLabel("Chat ID")
        chat_lbl.setObjectName("settingsRowLabel")
        self._tg_chat_edit = QLineEdit(tg.get("chat_id", ""))
        self._tg_chat_edit.setPlaceholderText("수신할 채팅/그룹/채널 ID (예: -1001234567890)")
        chat_vl = QVBoxLayout()
        chat_vl.setContentsMargins(0, 0, 0, 0)
        chat_vl.setSpacing(3)
        chat_vl.addWidget(chat_lbl)
        chat_vl.addWidget(self._tg_chat_edit)
        sl3.addLayout(chat_vl)

        tg_test_hl = QHBoxLayout()
        tg_test_hl.setContentsMargins(0, 0, 0, 0)
        self._btn_tg_test = QPushButton("연결 테스트")
        self._btn_tg_test.clicked.connect(self._test_telegram)
        tg_test_hl.addWidget(self._btn_tg_test)
        tg_test_hl.addStretch()
        sl3.addLayout(tg_test_hl)
        vl.addWidget(box3)

        # 텔레그램 알림 옵션
        self._tg_options_box, sl4 = _section("텔레그램 알림 옵션")
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
                   self._tg_audio_cb, self._tg_emb_cb):
            sl4.addWidget(cb)
        sl4.addWidget(self._tg_system_cb)
        system_hint = QLabel("Watchdog 감시, Detection 재시작/복구, 비정상 종료 시 텔레그램으로 시스템 상태 알림")
        system_hint.setObjectName("settingsDesc")
        system_hint.setWordWrap(True)
        system_hint.setContentsMargins(20, 0, 0, 0)
        sl4.addWidget(system_hint)

        self._tg_cooldown_edit = _int_edit(tg.get("cooldown", 60), 1, 3600)
        sl4.addLayout(_row("재전송 대기(초)", self._tg_cooldown_edit,
                           "동일 감지유형 연속 재전송 방지. 기본 60초"))
        vl.addWidget(self._tg_options_box)

        # 자동 재시작
        box5, sl5 = _section("자동 재시작")

        self._restart_enabled_cb = QCheckBox("예약 재시작 활성화")
        self._restart_enabled_cb.setChecked(sys_cfg.get("scheduled_restart_enabled", False))
        sl5.addWidget(self._restart_enabled_cb)

        self._restart_base_edit = QLineEdit(sys_cfg.get("scheduled_restart_base_time", "03:00"))
        self._restart_base_edit.setPlaceholderText("HH:MM")
        self._restart_base_edit.setFixedWidth(80)
        sl5.addLayout(_row("기준 시각", self._restart_base_edit,
                           "재시작 주기의 기준이 되는 시각 (예: 03:00)"))

        _INTERVAL_OPTIONS = [
            ("매일 (24시간)", 24),
            ("2일 (48시간)", 48),
            ("3일 (72시간)", 72),
            ("1주 (168시간)", 168),
            ("2주 (336시간)", 336),
            ("1달 (720시간)", 720),
        ]
        self._restart_interval_combo = QComboBox()
        for label, _ in _INTERVAL_OPTIONS:
            self._restart_interval_combo.addItem(label)
        cur_h = sys_cfg.get("scheduled_restart_interval_hours", 24)
        cur_idx = next((i for i, (_, h) in enumerate(_INTERVAL_OPTIONS) if h == cur_h), 0)
        self._restart_interval_combo.setCurrentIndex(cur_idx)
        self._restart_interval_values = [h for _, h in _INTERVAL_OPTIONS]
        sl5.addLayout(_row("재시작 주기", self._restart_interval_combo, ""))

        self._restart_exclude_edit = QLineEdit(sys_cfg.get("scheduled_restart_exclude", ""))
        self._restart_exclude_edit.setPlaceholderText("예: 10:00-11:30, 21:00-21:30")
        sl5.addLayout(_row("제외 시간대", self._restart_exclude_edit,
                           "재시작하지 않을 시간대. 쉼표로 여러 개 입력 가능"))

        vl.addWidget(box5)

        # 즉시 반영 연결 — 알림설정
        self._alarm_sound_edit.editingFinished.connect(self._apply_now)
        self._tg_enabled_cb.stateChanged.connect(self._apply_now)
        self._tg_enabled_cb.stateChanged.connect(self._toggle_telegram_widgets)
        self._tg_token_edit.editingFinished.connect(self._apply_now)
        self._tg_chat_edit.editingFinished.connect(self._apply_now)
        for cb in (self._tg_image_cb, self._tg_black_cb, self._tg_still_cb,
                   self._tg_audio_cb, self._tg_emb_cb, self._tg_system_cb):
            cb.stateChanged.connect(self._apply_now)
        self._tg_cooldown_edit.editingFinished.connect(self._apply_now)
        self._restart_enabled_cb.stateChanged.connect(self._apply_now)
        self._restart_enabled_cb.stateChanged.connect(self._toggle_restart_widgets)
        self._restart_base_edit.editingFinished.connect(self._validate_restart_time)
        self._restart_interval_combo.currentIndexChanged.connect(self._apply_now)
        self._restart_exclude_edit.editingFinished.connect(self._apply_now)

        # 초기 그레이아웃 상태 적용
        self._toggle_telegram_widgets(self._tg_enabled_cb.isChecked())
        self._toggle_restart_widgets(self._restart_enabled_cb.isChecked())

        vl.addStretch()
        return _make_scroll(inner)

    # ─────────────────────────────────────────────────────────────────
    # 탭 7: 저장/불러오기
    # ─────────────────────────────────────────────────────────────────

    def _build_tab_save(self) -> QWidget:
        inner = QWidget()
        vl = QVBoxLayout(inner)
        vl.setContentsMargins(16, 16, 16, 16)
        vl.setSpacing(12)

        for icon, title, desc, btn_text, obj_name, slot in [
            ("💾", "현재 설정 저장",
             "현재 설정을 JSON 파일로 내보냅니다.",
             "저장...", "btnOutlineOrange", self._export_config),
            ("📂", "설정 파일 불러오기",
             "저장된 JSON 파일을 불러와 적용합니다.",
             "불러오기...", "btnOutlineOrange", self._import_config),
            ("⚠", "기본값으로 초기화",
             "모든 설정을 초기 기본값으로 되돌립니다.",
             "초기화", "btnOutlineDanger", self._reset_all_settings),
        ]:
            card = QFrame()
            card.setObjectName("saveActionCard")
            card_h = QHBoxLayout(card)
            card_h.setContentsMargins(16, 14, 16, 14)
            card_h.setSpacing(14)

            lbl_icon = QLabel(icon)
            lbl_icon.setObjectName("saveCardIcon")
            lbl_icon.setFixedWidth(32)
            lbl_icon.setAlignment(Qt.AlignCenter)
            card_h.addWidget(lbl_icon)

            text_vl = QVBoxLayout()
            text_vl.setSpacing(2)
            lbl_title = QLabel(title)
            lbl_title.setObjectName("saveCardTitle")
            lbl_desc = QLabel(desc)
            lbl_desc.setObjectName("saveCardDesc")
            text_vl.addWidget(lbl_title)
            text_vl.addWidget(lbl_desc)
            card_h.addLayout(text_vl, 1)

            btn = QPushButton(btn_text)
            btn.setObjectName(obj_name)
            btn.setFixedHeight(34)
            btn.clicked.connect(slot)
            card_h.addWidget(btn)

            vl.addWidget(card)

        # About 카드
        about_card = QFrame()
        about_card.setObjectName("aboutCard")
        about_vl = QVBoxLayout(about_card)
        about_vl.setContentsMargins(16, 14, 16, 14)
        about_vl.setSpacing(4)

        lbl_ver = QLabel("KBS On-Air Monitoring v2.0.1")
        lbl_ver.setObjectName("aboutCardVersion")
        about_vl.addWidget(lbl_ver)

        lbl_meta = QLabel("날짜: 2026-04-28    제작: minwoo@kbs.co.kr")
        lbl_meta.setObjectName("aboutCardMeta")
        about_vl.addWidget(lbl_meta)

        vl.addStretch()
        vl.addWidget(about_card)
        return _make_scroll(inner)

    # ─────────────────────────────────────────────────────────────────
    # 설정 수집 / 저장
    # ─────────────────────────────────────────────────────────────────

    def _collect_config(self):
        """모든 위젯 값을 읽어 self._cfg 업데이트."""
        cfg = self._cfg

        # 영상설정
        cfg["port"] = self._port_combo.currentData()
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
            grp["still_trigger_sec"] = int(w["still_trigger_sec"].text() or 60)
            grp["exit_trigger_sec"] = int(w["exit_trigger_sec"].text() or 5)
            grp["weekdays"] = [d for d, cb in enumerate(w["weekdays"])
                               if cb.isChecked()]
            grp["enter_roi"] = w["_enter_roi"]
            grp["suppressed_labels"] = w["_suppressed"]

        # 알림설정
        alm = cfg.setdefault("alarm", {})
        alm["sound_file"] = self._alarm_sound_edit.text().strip()

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
        sys_cfg["scheduled_restart_enabled"] = self._restart_enabled_cb.isChecked()
        sys_cfg["scheduled_restart_base_time"] = self._restart_base_edit.text().strip() or "03:00"
        sys_cfg["scheduled_restart_interval_hours"] = self._restart_interval_values[
            self._restart_interval_combo.currentIndex()]
        sys_cfg["scheduled_restart_exclude"] = self._restart_exclude_edit.text().strip()

    def _apply_now(self):
        """위젯 값 수집 → 저장 → Detection 전파. 재진입 방지."""
        if SettingsDialog._applying:
            return
        SettingsDialog._applying = True
        try:
            self._collect_config()
            self._cfg_mgr.save(self._cfg)
            self._send_cmd_apply()
            self.config_saved.emit(copy.deepcopy(self._cfg))
        finally:
            SettingsDialog._applying = False

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
        if self._cmd_event is not None:
            self._cmd_event.set()

    # ─────────────────────────────────────────────────────────────────
    # 브라우저 / 테스트 / 리셋 슬롯
    # ─────────────────────────────────────────────────────────────────

    def _on_rec_enabled_changed(self):
        enabled = self._rec_enabled_cb.isChecked()
        for w in self._rec_sub_widgets:
            w.setEnabled(enabled)
        self._apply_now()

    def _update_capacity_label(self):
        res_data = self._res_combo.currentData() or (960, 540)
        w, h = res_data
        fps = self._fps_combo.currentData() or 10
        try:
            pre = int(self._rec_pre_edit.text() or 5)
            post = int(self._rec_post_edit.text() or 15)
        except ValueError:
            pre, post = 5, 15
        frame_bytes = w * h * 3 * 0.07
        pre_mb = (pre * fps + 5) * frame_bytes / 1024 / 1024
        rec_mb_lo = post * fps * frame_bytes / 1024 / 1024
        rec_mb_hi = rec_mb_lo * 1.5
        self._capacity_label.setText(
            f"출력: <b>{w}×{h}</b> | FPS: <b>{fps}</b> | "
            f"사전버퍼: 약 <b>{pre_mb:.1f} MB</b> | "
            f"녹화 파일: 약 <b>{rec_mb_lo:.0f}~{rec_mb_hi:.0f} MB</b> / {pre + post}초 | "
            f"코덱: <b>mp4v</b>"
        )

    def _browse_video_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "테스트용 영상 파일 선택", "",
            "동영상 파일 (*.mp4 *.avi *.mkv *.mov);;모든 파일 (*)")
        if path:
            self._video_file_edit.setText(path)
            self._apply_now()

    def _browse_rec_dir(self):
        path = QFileDialog.getExistingDirectory(self, "녹화 저장 폴더 선택",
                                                 self._rec_dir_edit.text())
        if path:
            self._rec_dir_edit.setText(path)
            self._apply_now()

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
            self._apply_now()

    def _reset_alarm_sound(self):
        self._alarm_sound_edit.setText("resources/sounds/alarm.wav")
        self._apply_now()

    def _test_sound(self, path: str):
        if self._alarm is not None:
            self._alarm.play_test_sound(path)

    def _toggle_token_echo(self):
        """Bot Token 표시/숨김 토글."""
        if self._tg_token_edit.echoMode() == QLineEdit.EchoMode.Password:
            self._tg_token_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self._btn_tg_token_toggle.setText("숨김")
        else:
            self._tg_token_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._btn_tg_token_toggle.setText("표시")

    def _toggle_telegram_widgets(self, enabled):
        """텔레그램 활성화 체크박스 ON/OFF에 따라 하위 위젯/섹션 활성/비활성."""
        on = bool(enabled)
        for w in (self._tg_token_edit, self._btn_tg_token_toggle,
                  self._tg_chat_edit, self._btn_tg_test):
            w.setEnabled(on)
        for child in self._tg_options_box.findChildren(QWidget):
            if child.objectName() != "settingsSectionLabel":
                child.setEnabled(on)

    def _toggle_restart_widgets(self, enabled):
        """예약 재시작 활성화 체크박스 ON/OFF에 따라 하위 위젯 활성/비활성."""
        on = bool(enabled)
        for w in (self._restart_base_edit, self._restart_interval_combo,
                  self._restart_exclude_edit):
            w.setEnabled(on)

    def _validate_restart_time(self):
        """기준 시각 HH:MM 형식 검증. 유효하면 즉시 반영, 아니면 빨간 테두리."""
        import re
        text = self._restart_base_edit.text().strip()
        if re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", text):
            self._restart_base_edit.setStyleSheet("")
            self._restart_base_edit.setToolTip("")
            self._apply_now()
        else:
            self._restart_base_edit.setStyleSheet("border: 1px solid #cc0000;")
            self._restart_base_edit.setToolTip("형식 오류: HH:MM (00:00 ~ 23:59)")

    def _test_telegram(self):
        token = self._tg_token_edit.text().strip()
        chat_id = self._tg_chat_edit.text().strip()
        if not token or not chat_id:
            QMessageBox.warning(self, "오류", "Bot Token과 Chat ID를 입력하세요.")
            return
        self._btn_tg_test.setEnabled(False)
        self._btn_tg_test.setText("테스트 중...")
        self._tg_worker = _TelegramTestWorker(token, chat_id)
        self._tg_worker.result_ready.connect(self._on_telegram_test_result)
        self._tg_worker.start()

    def _on_telegram_test_result(self, ok: bool, msg: str):
        self._btn_tg_test.setEnabled(True)
        self._btn_tg_test.setText("연결 테스트")
        if ok:
            QMessageBox.information(self, "성공", "텔레그램 연결 성공!")
        else:
            QMessageBox.warning(self, "실패", msg)

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
        d = DEFAULT_CONFIG
        rec = d.get("recording", {})
        self._port_combo.setCurrentIndex(d.get("port", 0))
        self._video_file_edit.clear()
        self._rec_enabled_cb.setChecked(rec.get("enabled", True))
        self._rec_dir_edit.setText(rec.get("save_dir", "recordings"))
        self._rec_pre_edit.setText(str(rec.get("pre_seconds", 5)))
        self._rec_post_edit.setText(str(rec.get("post_seconds", 15)))
        self._rec_keep_edit.setText(str(rec.get("max_keep_days", 7)))
        default_w = rec.get("output_width", 960)
        for i in range(self._res_combo.count()):
            if self._res_combo.itemData(i)[0] == default_w:
                self._res_combo.setCurrentIndex(i)
                break
        default_fps = rec.get("output_fps", 10)
        for i in range(self._fps_combo.count()):
            if self._fps_combo.itemData(i) == default_fps:
                self._fps_combo.setCurrentIndex(i)
                break
        self._apply_now()
        self._update_capacity_label()

    def _reset_sensitivity_settings(self):
        d = DEFAULT_CONFIG.get("detection", {})
        p = DEFAULT_CONFIG.get("performance", {})
        self._black_thresh.setText(str(d.get("black_threshold", 5)))
        self._black_ratio.setText(str(d.get("black_dark_ratio", 98.0)))
        self._black_suppress.setText(str(d.get("black_motion_suppress_ratio", 0.2)))
        self._black_dur.setText(str(d.get("black_duration", 20)))
        self._black_alarm_dur.setText(str(d.get("black_alarm_duration", 60)))

        self._still_thresh.setText(str(d.get("still_threshold", 4)))
        self._still_changed.setText(str(d.get("still_changed_ratio", 10.0)))
        self._still_reset.setText(str(d.get("still_reset_frames", 3)))
        self._still_dur.setText(str(d.get("still_duration", 60)))
        self._still_alarm_dur.setText(str(d.get("still_alarm_duration", 60)))

        self._hsv_h.set_range(d.get("audio_hsv_h_min", 40), d.get("audio_hsv_h_max", 95))
        self._hsv_s.set_range(d.get("audio_hsv_s_min", 80), d.get("audio_hsv_s_max", 255))
        self._hsv_v.set_range(d.get("audio_hsv_v_min", 60), d.get("audio_hsv_v_max", 255))
        self._audio_pixel_ratio.setText(str(d.get("audio_pixel_ratio", 5.0)))
        self._audio_level_dur.setText(str(d.get("audio_level_duration", 20)))
        self._audio_level_alarm_dur.setText(str(d.get("audio_level_alarm_duration", 60)))
        self._audio_recovery.setText(str(d.get("audio_level_recovery_seconds", 2.0)))

        self._emb_thresh.setText(str(d.get("embedded_silence_threshold", -50)))
        self._emb_dur.setText(str(d.get("embedded_silence_duration", 20)))
        self._emb_alarm_dur.setText(str(d.get("embedded_alarm_duration", 60)))

        for i in range(self._detect_interval_combo.count()):
            if self._detect_interval_combo.itemData(i) == p.get("detection_interval", 200):
                self._detect_interval_combo.setCurrentIndex(i)
                break
        for i in range(self._scale_combo.count()):
            if abs(self._scale_combo.itemData(i) - p.get("scale_factor", 1.0)) < 0.01:
                self._scale_combo.setCurrentIndex(i)
                break
        self._black_enabled_cb.setChecked(p.get("black_detection_enabled", True))
        self._still_enabled_cb.setChecked(p.get("still_detection_enabled", True))
        self._audio_enabled_cb.setChecked(p.get("audio_detection_enabled", True))
        self._emb_enabled_cb.setChecked(p.get("embedded_detection_enabled", True))
        self._toggle_section_widgets(self._black_section_widgets,
                                     self._black_enabled_cb.isChecked())
        self._toggle_section_widgets(self._still_section_widgets,
                                     self._still_enabled_cb.isChecked())
        self._toggle_section_widgets(self._audio_section_widgets,
                                     self._audio_enabled_cb.isChecked())
        self._toggle_section_widgets(self._emb_section_widgets,
                                     self._emb_enabled_cb.isChecked())
        self._apply_now()

    def _reset_signoff_settings(self):
        d = DEFAULT_CONFIG.get("signoff", {})
        self._auto_prep_cb.setChecked(d.get("auto_preparation", True))
        self._so_prep_sound.setText(d.get("prep_alarm_sound", ""))
        self._so_enter_sound.setText(d.get("enter_alarm_sound", ""))
        self._so_release_sound.setText(d.get("release_alarm_sound", ""))

        for idx, w in enumerate(self._so_grp):
            grp = d.get(f"group{idx + 1}", {})
            w["name"].setText(grp.get("name", f"{idx + 1}TV"))

            start_h, start_m = grp.get("start_time", "03:00").split(":")
            w["start_h"].setText(str(int(start_h)))
            w["start_m"].setText(str(int(start_m)))

            end_h, end_m = grp.get("end_time", "05:00").split(":")
            w["end_h"].setText(str(int(end_h)))
            w["end_m"].setText(str(int(end_m)))

            w["end_next_day"].setChecked(grp.get("end_next_day", False))

            prep_val = grp.get("prep_minutes", 150)
            for i in range(w["prep_minutes"].count()):
                if w["prep_minutes"].itemData(i) == prep_val:
                    w["prep_minutes"].setCurrentIndex(i)
                    break

            exit_prep_val = grp.get("exit_prep_minutes", 30)
            for i in range(w["exit_prep_minutes"].count()):
                if w["exit_prep_minutes"].itemData(i) == exit_prep_val:
                    w["exit_prep_minutes"].setCurrentIndex(i)
                    break

            w["still_trigger_sec"].setText(str(grp.get("still_trigger_sec", 60)))
            w["exit_trigger_sec"].setText(str(grp.get("exit_trigger_sec", 5)))

            default_days = set(grp.get("weekdays", list(range(7))))
            for d_idx, cb in enumerate(w["weekdays"]):
                cb.setChecked(d_idx in default_days)

            w["_enter_roi"] = dict(grp.get("enter_roi") or {"video_label": ""})
            w["_suppressed"] = list(grp.get("suppressed_labels", []))
            enter_v = w["_enter_roi"].get("video_label", "") or ""
            sup_cnt = len(w["_suppressed"])
            lbl_widget = w["enter_label_lbl"]
            if enter_v:
                lbl_widget.setText(f"{enter_v} · 억제 {sup_cnt}개" if sup_cnt else enter_v)
                lbl_widget.setStyleSheet("")
            else:
                lbl_widget.setText("미설정")
                lbl_widget.setStyleSheet("color: #cc4444;")

        self._apply_now()

    def _export_config(self):
        self._collect_config()
        import os
        default_path = os.path.join(
            os.path.abspath(self._cfg_mgr.CONFIG_DIR), "kbs_config_backup.json")
        path, _ = QFileDialog.getSaveFileName(
            self, "설정 저장", default_path,
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
                raw = json.load(f)
            merged = self._cfg_mgr._merge_defaults(raw)
            self._cfg_mgr.save(merged)
            self._cfg = merged
            self._load_rois_from_cfg()
            self._send_cmd_apply()
            self.config_saved.emit(copy.deepcopy(self._cfg))
            QMessageBox.information(self, "완료",
                                    "설정을 불러와 적용했습니다.\n"
                                    "(위젯 표시는 다이얼로그를 닫고 다시 열면 갱신됩니다.)")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"불러오기 실패:\n{e}")

    def closeEvent(self, event):
        """다이얼로그 닫힐 때 텔레그램 테스트 워커 안전 정리."""
        worker = getattr(self, "_tg_worker", None)
        if worker is not None and worker.isRunning():
            worker.result_ready.disconnect()
            worker.wait(3000)
        super().closeEvent(event)

    def _reload_all_tabs(self):
        """현재 self._cfg 값으로 모든 탭 위젯을 다시 채운다.
        중간 _apply_now 호출이 self._cfg를 덮어쓰지 않도록 _applying 플래그로 차단."""
        SettingsDialog._applying = True
        try:
            self._reset_video_settings()
            self._reset_sensitivity_settings()
            self._reset_signoff_settings()
            alm = self._cfg.get("alarm", {})
            tg = self._cfg.get("telegram", {})
            self._alarm_sound_edit.setText(alm.get("sound_file", "resources/sounds/alarm.wav"))
            self._tg_enabled_cb.setChecked(tg.get("enabled", False))
            self._tg_token_edit.setText(tg.get("bot_token", ""))
            self._tg_chat_edit.setText(tg.get("chat_id", ""))
            self._toggle_telegram_widgets(self._tg_enabled_cb.isChecked())
            # ROI 탭: 테이블·오버레이 갱신 (ROIManager는 호출 전 이미 갱신됨)
            self._refresh_roi_table("video")
            self._refresh_roi_table("audio")
            self._sync_overlay_canvas("video")
            self._sync_overlay_canvas("audio")
        finally:
            SettingsDialog._applying = False

    def _reset_all_settings(self):
        reply = QMessageBox.question(
            self, "기본값으로 초기화",
            "모든 설정이 초기 기본값으로 돌아갑니다.\n계속하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self._cfg = copy.deepcopy(DEFAULT_CONFIG)
        # ROIManager를 먼저 비워야 _send_cmd_apply / config_saved emit 시
        # Detection·VideoWidget 모두 빈 ROI 리스트를 받는다.
        self._load_rois_from_cfg()
        self._cfg_mgr.save(self._cfg)
        self._send_cmd_apply()
        self.config_saved.emit(copy.deepcopy(self._cfg))
        self._reload_all_tabs()
