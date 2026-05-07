"""
상단 바 위젯
v1 ui/top_bar.py에서 임포트 경로 수정.
L/R 레벨미터: MainWindow에서 SharedStateBuffer 폴링 후 update_audio_levels() 호출.
볼륨 슬라이더: debounce QTimer 100ms 적용 (cmd_queue 폭주 방지).
"""
import datetime
import math
import subprocess

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import GPUtil
    GPUTIL_AVAILABLE = True
except ImportError:
    GPUTIL_AVAILABLE = False

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QSlider, QFrame,
)
from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import QFont, QColor, QPainter, QPixmap, QIcon, QPen



def _fmt_dhms(secs: float) -> str:
    s = int(abs(secs))
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    if d > 0:
        return f"[{d}D] {h:02d}:{m:02d}:{s:02d}"
    return f"{h:02d}:{m:02d}:{s:02d}"


def _fmt_elapsed(secs: float) -> str:
    s = int(abs(secs))
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    if h > 0:
        return f"{h}h {m}m {s:02d}s"
    return f"{m}m {s:02d}s"


def _refresh_property(widget: QWidget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


class LevelMeterBar(QWidget):
    """L 또는 R 오디오 레벨 미터 (세로 10칸 디지털 세그먼트)"""

    NUM_SEGMENTS = 10
    SEGMENT_GAP = 1

    def __init__(self, channel: str = "L", parent=None):
        super().__init__(parent)
        self._channel = channel
        self._level_db = -60.0
        self._bg_color = QColor("#111122")
        self._seg_off_color = QColor("#1e1e1e")
        self.setFixedWidth(20)
        self.setMinimumHeight(44)

    def set_level(self, db: float):
        self._level_db = max(-60.0, min(0.0, db))
        self.update()

    def set_theme(self, is_dark: bool):
        if is_dark:
            self._bg_color = QColor("#111122")
            self._seg_off_color = QColor("#1e1e1e")
        else:
            self._bg_color = QColor("#e0e0e8")
            self._seg_off_color = QColor("#cccccc")
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        w = self.width()
        h = self.height()
        label_h = 13
        bar_area_h = h - label_h
        n = self.NUM_SEGMENTS
        gap = self.SEGMENT_GAP
        seg_h = max(2, (bar_area_h - gap * (n - 1)) // n)

        painter.fillRect(0, 0, w, h, self._bg_color)
        ratio = (self._level_db + 60.0) / 60.0
        lit_count = round(ratio * n)

        for i in range(n):
            y_top = i * (seg_h + gap)
            from_bottom = n - 1 - i
            if from_bottom < lit_count:
                if i <= 1:
                    color = QColor("#ff3333")
                elif i <= 3:
                    color = QColor("#e8a730")
                else:
                    color = QColor("#2f9e44")
                painter.fillRect(2, y_top, w - 4, seg_h, color)
            else:
                painter.fillRect(2, y_top, w - 4, seg_h, self._seg_off_color)

        painter.setPen(QColor("#aaaacc"))
        painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
        painter.drawText(0, h - label_h, w, label_h, Qt.AlignCenter, self._channel)
        painter.end()


class SysMonitorWidget(QWidget):
    """CPU / RAM / GPU 실시간 성능 수치 표시"""

    _NVIDIASMI_PATHS = [
        "nvidia-smi",
        r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
        r"C:\Windows\System32\nvidia-smi.exe",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._gpu_method = None
        self._nvidiasmi_path = ""
        self._setup_ui()
        self._init_backends()
        self._start_timer()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(6)

        title = QLabel("시스템 성능".upper())
        title.setObjectName("lblSectionTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        stats_widget = QWidget()
        hbox = QHBoxLayout(stats_widget)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(14)

        _small_style = "font-size: 10px; font-weight: bold;"
        self._lbl_cpu = QLabel("CPU\n--%")
        self._lbl_cpu.setAlignment(Qt.AlignCenter)
        self._lbl_cpu.setStyleSheet(_small_style)
        self._lbl_ram = QLabel("RAM\n--%")
        self._lbl_ram.setAlignment(Qt.AlignCenter)
        self._lbl_ram.setStyleSheet(_small_style)
        self._lbl_gpu = QLabel("GPU\nN/A")
        self._lbl_gpu.setAlignment(Qt.AlignCenter)
        self._lbl_gpu.setStyleSheet(_small_style)

        hbox.addWidget(self._lbl_cpu)
        hbox.addWidget(self._lbl_ram)
        hbox.addWidget(self._lbl_gpu)
        layout.addWidget(stats_widget)

    def _init_backends(self):
        if PSUTIL_AVAILABLE:
            psutil.cpu_percent(interval=None)
        self._detect_gpu()
        QTimer.singleShot(500, self._update_stats)

    def _detect_gpu(self):
        if GPUTIL_AVAILABLE:
            try:
                if GPUtil.getGPUs():
                    self._gpu_method = "gputil"
                    return
            except Exception:
                pass
        for path in self._NVIDIASMI_PATHS:
            try:
                result = subprocess.run(
                    [path, "--query-gpu=utilization.gpu",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=3,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                if result.returncode == 0 and result.stdout.strip():
                    self._gpu_method = "nvidiasmi"
                    self._nvidiasmi_path = path
                    return
            except Exception:
                continue
        self._gpu_method = None

    def _start_timer(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_stats)
        self._timer.start(2000)

    def _update_stats(self):
        if PSUTIL_AVAILABLE:
            self._lbl_cpu.setText(f"CPU\n{psutil.cpu_percent():.0f}%")
            self._lbl_ram.setText(f"RAM\n{psutil.virtual_memory().percent:.0f}%")
        else:
            self._lbl_cpu.setText("CPU\nN/A")
            self._lbl_ram.setText("RAM\nN/A")

        if self._gpu_method == "gputil" and GPUTIL_AVAILABLE:
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    self._lbl_gpu.setText(f"GPU\n{gpus[0].load * 100:.0f}%")
            except Exception:
                pass
        elif self._gpu_method == "nvidiasmi":
            try:
                result = subprocess.run(
                    [self._nvidiasmi_path, "--query-gpu=utilization.gpu",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=2,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                if result.returncode == 0:
                    self._lbl_gpu.setText(f"GPU\n{result.stdout.strip()}%")
            except Exception:
                pass


class TopBar(QWidget):
    """상단 제어 바"""

    settings_requested      = Signal()
    roi_visibility_changed  = Signal(bool)
    detection_toggled       = Signal(bool)
    sound_toggled           = Signal(bool)
    volume_changed          = Signal(int)    # debounce 100ms 적용
    embed_mute_toggled      = Signal(bool)   # True=뮤트, False=해제
    alarm_acknowledged      = Signal()
    dark_mode_toggled       = Signal(bool)
    fullscreen_toggled      = Signal()
    signoff_manual_release  = Signal(int)    # group_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._roi_visible = True
        self._sound_enabled = True
        self._dark_mode = True
        # debounce: 슬라이더 valueChanged → 100ms 후 volume_changed 발행
        self._volume_debounce = QTimer(self)
        self._volume_debounce.setSingleShot(True)
        self._volume_debounce.setInterval(100)
        self._volume_debounce.timeout.connect(self._emit_volume)
        self._pending_volume = 80
        self._setup_ui()
        self._start_clock()

    def _setup_ui(self):
        self.setObjectName("topBar")
        self.setFixedHeight(68)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignTop)

        self._sys_monitor = SysMonitorWidget()
        layout.addWidget(self._sys_monitor, alignment=Qt.AlignTop)

        layout.addWidget(self._make_separator())

        # 현재시간 영역
        time_container = QWidget()
        time_vbox = QVBoxLayout(time_container)
        time_vbox.setContentsMargins(4, 0, 4, 0)
        time_vbox.setSpacing(4)

        lbl_time_title = QLabel("현재시간".upper())
        lbl_time_title.setObjectName("lblSectionTitle")
        lbl_time_title.setAlignment(Qt.AlignCenter)
        time_vbox.addWidget(lbl_time_title)

        self._lbl_time = QLabel("00:00:00")
        self._lbl_time.setObjectName("lblTime")
        self._lbl_time.setAlignment(Qt.AlignCenter)
        self._lbl_time.setFont(QFont("JetBrains Mono", 18))
        time_vbox.addWidget(self._lbl_time)

        layout.addWidget(time_container, alignment=Qt.AlignTop)
        layout.addWidget(self._make_separator())

        # Embedded Audio 영역
        embed_container = QWidget()
        embed_container.setMaximumWidth(205)
        embed_vbox = QVBoxLayout(embed_container)
        embed_vbox.setContentsMargins(4, 0, 4, 0)
        embed_vbox.setSpacing(2)

        lbl_embed_title = QLabel("Embedded Audio".upper())
        lbl_embed_title.setObjectName("lblSectionTitle")
        lbl_embed_title.setAlignment(Qt.AlignCenter)
        embed_vbox.addWidget(lbl_embed_title)

        embed_content = QWidget()
        embed_hbox = QHBoxLayout(embed_content)
        embed_hbox.setContentsMargins(0, 0, 0, 0)
        embed_hbox.setSpacing(4)

        self._btn_embed_mute = QPushButton()
        self._btn_embed_mute.setObjectName("btnEmbedMute")
        self._btn_embed_mute.setCheckable(True)
        self._btn_embed_mute.setFixedSize(28, 24)
        self._btn_embed_mute.setIcon(self._make_volume_icon(False))
        self._btn_embed_mute.setIconSize(QSize(18, 18))
        self._btn_embed_mute.setToolTip("임베디드 오디오 음소거")
        self._btn_embed_mute.clicked.connect(self._on_embed_mute_clicked)
        embed_hbox.addWidget(self._btn_embed_mute, 0, Qt.AlignVCenter)

        self._slider_volume = QSlider(Qt.Horizontal)
        self._slider_volume.setObjectName("sliderVolume")
        self._slider_volume.setRange(0, 100)
        self._slider_volume.setValue(80)
        self._slider_volume.setFixedWidth(58)
        self._slider_volume.setToolTip("임베디드 오디오 볼륨")
        self._slider_volume.valueChanged.connect(self._on_volume_changed_raw)
        embed_hbox.addWidget(self._slider_volume, 0, Qt.AlignVCenter)

        self._lbl_volume_val = QLabel("80%")
        self._lbl_volume_val.setObjectName("lblVolumeVal")
        self._lbl_volume_val.setFixedWidth(30)
        self._lbl_volume_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        embed_hbox.addWidget(self._lbl_volume_val, 0, Qt.AlignVCenter)

        self._meter_l = LevelMeterBar("L")
        self._meter_r = LevelMeterBar("R")
        embed_hbox.addWidget(self._meter_l)
        embed_hbox.addWidget(self._meter_r)

        embed_vbox.addWidget(embed_content)
        layout.addWidget(embed_container, alignment=Qt.AlignTop)
        layout.addWidget(self._make_separator())

        layout.addWidget(self._create_summary_widget(), alignment=Qt.AlignTop)
        layout.addWidget(self._make_separator())

        self._btn_detection = QPushButton("감지 ON\n감시중")
        self._btn_detection.setObjectName("btnDetection")
        self._btn_detection.setCheckable(True)
        self._btn_detection.setChecked(True)
        self._btn_detection.setFixedSize(90, 46)
        self._btn_detection.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self._btn_detection.clicked.connect(self._on_detection_clicked)
        layout.addWidget(self._btn_detection)

        self._btn_roi = QPushButton("영역 표시\nON")
        self._btn_roi.setObjectName("btnRoi")
        self._btn_roi.setCheckable(True)
        self._btn_roi.setChecked(True)
        self._btn_roi.setFixedSize(90, 46)
        self._btn_roi.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self._btn_roi.clicked.connect(self._on_roi_clicked)
        layout.addWidget(self._btn_roi)

        self._btn_mute = QPushButton("알림음\n켜짐")
        self._btn_mute.setObjectName("btnMuteText")
        self._btn_mute.setCheckable(True)
        self._btn_mute.setFixedSize(80, 46)
        self._btn_mute.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self._btn_mute.setToolTip("알림음 음소거")
        self._btn_mute.clicked.connect(self._on_mute_clicked)
        layout.addWidget(self._btn_mute)

        layout.addWidget(self._make_separator())

        self._btn_ack = QPushButton("알림 확인\nACK")
        self._btn_ack.setObjectName("btnAlarmAck")
        self._btn_ack.setFixedSize(90, 46)
        self._btn_ack.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self._btn_ack.setToolTip("알림확인 — 소리 및 깜빡임 해제")
        self._btn_ack.clicked.connect(self.alarm_acknowledged)
        layout.addWidget(self._btn_ack)

        layout.addWidget(self._make_separator())

        self._btn_signoff: dict = {}
        for gid in (1, 2):
            btn = QPushButton(f"Group{gid} 정파\n--:--:--")
            btn.setObjectName("btnSignoff")
            btn.setCheckable(False)
            btn.setProperty("signoff_state", "IDLE")
            btn.setFixedSize(160, 46)
            btn.setFont(QFont("Segoe UI", 9, QFont.Bold))
            btn.clicked.connect(lambda _, g=gid: self.signoff_manual_release.emit(g))
            layout.addWidget(btn, alignment=Qt.AlignVCenter)
            self._btn_signoff[gid] = btn

        layout.addStretch()

        self._btn_settings = QPushButton()
        self._btn_settings.setObjectName("btnSettings")
        self._btn_settings.setFixedSize(36, 36)
        self._btn_settings.setIcon(self._make_gear_icon())
        self._btn_settings.setIconSize(QSize(22, 22))
        self._btn_settings.setToolTip("설정")
        self._btn_settings.clicked.connect(self.settings_requested)
        layout.addWidget(self._btn_settings)

        self._btn_dark = QPushButton()
        self._btn_dark.setObjectName("btnDark")
        self._btn_dark.setCheckable(True)
        self._btn_dark.setChecked(True)
        self._btn_dark.setFixedSize(36, 36)
        self._btn_dark.setIcon(self._make_darkmode_icon(True))
        self._btn_dark.setIconSize(QSize(22, 22))
        self._btn_dark.setToolTip("주간/야간 모드 전환")
        self._btn_dark.clicked.connect(self._on_dark_mode_clicked)
        layout.addWidget(self._btn_dark)

        self._btn_fullscreen = QPushButton()
        self._btn_fullscreen.setObjectName("btnFullscreen")
        self._btn_fullscreen.setCheckable(True)
        self._btn_fullscreen.setFixedSize(36, 36)
        self._btn_fullscreen.setIcon(self._make_fullscreen_icon(False))
        self._btn_fullscreen.setIconSize(QSize(22, 22))
        self._btn_fullscreen.setToolTip("F11 — 전체화면 전환")
        self._btn_fullscreen.clicked.connect(self.fullscreen_toggled)
        layout.addWidget(self._btn_fullscreen)

    def _create_summary_widget(self) -> QWidget:
        container = QWidget()
        container.setObjectName("summaryContainer")
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(6, 0, 6, 0)
        vbox.setSpacing(5)

        title = QLabel("감지 현황".upper())
        title.setObjectName("lblSectionTitle")
        title.setAlignment(Qt.AlignCenter)
        vbox.addWidget(title)

        badges_widget = QWidget()
        hbox = QHBoxLayout(badges_widget)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(6)
        hbox.setAlignment(Qt.AlignHCenter)

        self._det_badges: dict = {}
        self._det_val_labels: dict = {}

        for key, display in [("V", "V"), ("A", "A"), ("EA", "EA")]:
            badge = QFrame()
            badge.setObjectName("detBadge")
            badge_layout = QVBoxLayout(badge)
            badge_layout.setContentsMargins(8, 3, 8, 3)
            badge_layout.setSpacing(0)

            lbl_key = QLabel(display)
            lbl_key.setObjectName("detBadgeKey")
            lbl_key.setAlignment(Qt.AlignCenter)
            lbl_key.setFont(QFont("Segoe UI", 8))

            init_val = "-" if key == "EA" else "0"
            lbl_val = QLabel(init_val)
            lbl_val.setObjectName("detBadgeVal")
            lbl_val.setAlignment(Qt.AlignCenter)
            lbl_val.setFont(QFont("JetBrains Mono", 11, QFont.Bold))

            badge_layout.addWidget(lbl_key)
            badge_layout.addWidget(lbl_val)

            hbox.addWidget(badge)
            self._det_badges[key] = badge
            self._det_val_labels[key] = lbl_val

        # 기존 코드와의 호환성 유지
        self._lbl_v  = self._det_val_labels["V"]
        self._lbl_a  = self._det_val_labels["A"]
        self._lbl_ea = self._det_val_labels["EA"]

        vbox.addWidget(badges_widget)
        return container

    def update_health(self, detect_stale: bool):
        """감지 루프 stale 여부 → 감지 ON 버튼 테두리로 표현."""
        state = "stale" if detect_stale else "ok"
        self._btn_detection.setProperty("health_state", state)
        _refresh_property(self._btn_detection)
        tip = "감지 중단 — 루프 응답 없음" if detect_stale else ""
        self._btn_detection.setToolTip(tip)

    def show_detection_crashed(self, reason: str, stale_sec: float = 0.0):
        """Detection 비정상 종료 — 재spawn 진행 중임을 버튼 테두리로 표현."""
        if reason == "heartbeat_stale":
            tip = f"재시작 중 (HB {stale_sec:.0f}초 무응답)"
        else:
            tip = "재시작 중"
        self._btn_detection.setProperty("health_state", "crashed")
        _refresh_property(self._btn_detection)
        self._btn_detection.setToolTip(tip)

    def _make_separator(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setObjectName("topBarSeparator")
        line.setFixedHeight(44)
        return line

    def _start_clock(self):
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_time)
        self._clock_timer.start(1000)
        self._update_time()

    def _update_time(self):
        self._lbl_time.setText(datetime.datetime.now().strftime("%H:%M:%S"))

    def _make_fullscreen_icon(self, is_fullscreen: bool) -> QIcon:
        size = 22
        px = QPixmap(size, size)
        px.fill(Qt.transparent)
        painter = QPainter(px)
        painter.setRenderHint(QPainter.Antialiasing)
        fg = QColor("#dddddd") if self._dark_mode else QColor("#404040")
        pen = QPen(fg)
        pen.setWidth(2)
        pen.setCapStyle(Qt.SquareCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        m, a = 4, 5
        if not is_fullscreen:
            for sx, sy, dx, dy in [
                (m, m, m + a, m), (m, m, m, m + a),
                (size - m, m, size - m - a, m), (size - m, m, size - m, m + a),
                (m, size - m, m + a, size - m), (m, size - m, m, size - m - a),
                (size - m, size - m, size - m - a, size - m),
                (size - m, size - m, size - m, size - m - a),
            ]:
                painter.drawLine(sx, sy, dx, dy)
        else:
            c = size // 2
            for sx, sy, dx, dy in [
                (m + a, m + a, m, m + a), (m, m + a, m + a, m + a),
                (size - m - a, m + a, size - m, m + a),
                (size - m, m + a, size - m - a, m + a),
                (m + a, size - m - a, m, size - m - a),
                (m, size - m - a, m + a, size - m - a),
                (size - m - a, size - m - a, size - m, size - m - a),
                (size - m, size - m - a, size - m - a, size - m - a),
            ]:
                painter.drawLine(sx, sy, dx, dy)
        painter.end()
        return QIcon(px)

    def _make_darkmode_icon(self, is_dark: bool) -> QIcon:
        size = 22
        px = QPixmap(size, size)
        px.fill(Qt.transparent)
        painter = QPainter(px)
        painter.setRenderHint(QPainter.Antialiasing)
        fg = QColor("#dddddd") if self._dark_mode else QColor("#404040")
        if is_dark:
            painter.setBrush(fg)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(3, 3, 16, 16)
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.drawEllipse(8, 1, 14, 14)
        else:
            painter.setPen(Qt.NoPen)
            painter.setBrush(fg)
            painter.drawEllipse(8, 8, 6, 6)
            pen = painter.pen()
            pen.setColor(fg)
            pen.setWidth(2)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            cx, cy, r1, r2 = 11, 11, 6, 9
            for i in range(8):
                a = math.radians(i * 45)
                x1 = cx + r1 * math.cos(a)
                y1 = cy + r1 * math.sin(a)
                x2 = cx + r2 * math.cos(a)
                y2 = cy + r2 * math.sin(a)
                painter.drawLine(int(x1 + 0.5), int(y1 + 0.5),
                                 int(x2 + 0.5), int(y2 + 0.5))
        painter.end()
        return QIcon(px)

    def _make_gear_icon(self) -> QIcon:
        from PySide6.QtGui import QPainterPath
        size = 22
        px = QPixmap(size, size)
        px.fill(Qt.transparent)
        painter = QPainter(px)
        painter.setRenderHint(QPainter.Antialiasing)
        fg = QColor("#dddddd") if self._dark_mode else QColor("#404040")
        cx, cy = size / 2.0, size / 2.0
        n_teeth = 8
        r_out = 10.0
        r_in = 7.2
        r_hole = 3.5
        import math as _math
        path = QPainterPath()
        for i in range(n_teeth):
            step = 2 * _math.pi / n_teeth
            a = i * step - _math.pi / 2
            tooth_half = step * 0.3
            pts = [
                (cx + r_in  * _math.cos(a - tooth_half * 1.3),
                 cy + r_in  * _math.sin(a - tooth_half * 1.3)),
                (cx + r_out * _math.cos(a - tooth_half),
                 cy + r_out * _math.sin(a - tooth_half)),
                (cx + r_out * _math.cos(a + tooth_half),
                 cy + r_out * _math.sin(a + tooth_half)),
                (cx + r_in  * _math.cos(a + tooth_half * 1.3),
                 cy + r_in  * _math.sin(a + tooth_half * 1.3)),
            ]
            if i == 0:
                path.moveTo(*pts[0])
            else:
                path.lineTo(*pts[0])
            for pt in pts[1:]:
                path.lineTo(*pt)
        path.closeSubpath()
        painter.setPen(Qt.NoPen)
        painter.setBrush(fg)
        painter.drawPath(path)
        painter.setCompositionMode(QPainter.CompositionMode_Clear)
        painter.drawEllipse(cx - r_hole, cy - r_hole, r_hole * 2, r_hole * 2)
        painter.end()
        return QIcon(px)

    def _make_volume_icon(self, muted: bool) -> QIcon:
        size = 18
        px = QPixmap(size, size)
        px.fill(Qt.transparent)
        painter = QPainter(px)
        painter.setRenderHint(QPainter.Antialiasing)
        fg = QColor("#dddddd") if self._dark_mode else QColor("#404040")
        painter.setBrush(fg)
        painter.setPen(Qt.NoPen)
        # 스피커 몸체
        body_pts = [
            (2, 6), (6, 6), (11, 2), (11, 16), (6, 12), (2, 12),
        ]
        from PySide6.QtGui import QPainterPath
        body = QPainterPath()
        body.moveTo(*body_pts[0])
        for pt in body_pts[1:]:
            body.lineTo(*pt)
        body.closeSubpath()
        painter.drawPath(body)
        if muted:
            pen = QPen(QColor("#e03131"))
            pen.setWidth(2)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawLine(13, 5, 17, 13)
            painter.drawLine(17, 5, 13, 13)
        else:
            pen = QPen(fg)
            pen.setWidth(2)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawArc(11, 4, 6, 10, -60 * 16, 120 * 16)
        painter.end()
        return QIcon(px)

    # ── 이벤트 핸들러 ──────────────────────────────────────────────

    def _on_volume_changed_raw(self, value: int):
        """슬라이더 변경 시 debounce 타이머 재시작."""
        self._pending_volume = value
        self._lbl_volume_val.setText(f"{value}%")
        self._volume_debounce.start()

    def _emit_volume(self):
        self.volume_changed.emit(self._pending_volume)

    def _on_embed_mute_clicked(self, checked: bool):
        self._btn_embed_mute.setIcon(self._make_volume_icon(checked))
        self.embed_mute_toggled.emit(checked)

    def _on_mute_clicked(self, checked: bool):
        self._btn_mute.setText("알림음\nMUTE" if checked else "알림음\n켜짐")
        self.sound_toggled.emit(not checked)

    def _on_detection_clicked(self, checked: bool):
        self._btn_detection.setText("감지 ON\n감시중" if checked else "감지 OFF\n중지됨")
        self.detection_toggled.emit(checked)

    def _on_roi_clicked(self, checked: bool):
        self._roi_visible = checked
        self._btn_roi.setText("영역 표시\nON" if checked else "영역 표시\nOFF")
        self.roi_visibility_changed.emit(checked)

    def _on_dark_mode_clicked(self, checked: bool):
        self._dark_mode = checked
        self._btn_dark.setIcon(self._make_darkmode_icon(checked))
        self._btn_embed_mute.setIcon(
            self._make_volume_icon(self._btn_embed_mute.isChecked()))
        self._btn_fullscreen.setIcon(
            self._make_fullscreen_icon(self._btn_fullscreen.isChecked()))
        self._btn_settings.setIcon(self._make_gear_icon())
        self._meter_l.set_theme(checked)
        self._meter_r.set_theme(checked)
        self.dark_mode_toggled.emit(checked)

    # ── 외부 호출 메서드 ───────────────────────────────────────────

    def update_audio_levels(self, l_db: float, r_db: float):
        self._meter_l.set_level(l_db)
        self._meter_r.set_level(r_db)

    def update_summary(self, video_count: int, audio_count: int,
                       embedded_enabled: bool, embedded_alerting: bool = False,
                       video_alerting: bool = False, audio_alerting: bool = False):
        self._det_val_labels["V"].setText(str(video_count))
        self._det_val_labels["A"].setText(str(audio_count))
        self._det_val_labels["EA"].setText("1" if embedded_enabled else "-")

        v_badge = self._det_badges["V"]
        v_badge.setProperty("alert", "true" if video_alerting else "false")
        _refresh_property(v_badge)

        a_badge = self._det_badges["A"]
        a_badge.setProperty("alert", "true" if audio_alerting else "false")
        _refresh_property(a_badge)

        ea_badge = self._det_badges["EA"]
        if embedded_alerting:
            ea_badge.setProperty("ea_state", "alert")
        elif not embedded_enabled:
            ea_badge.setProperty("ea_state", "disabled")
        else:
            ea_badge.setProperty("ea_state", "ok")
        _refresh_property(ea_badge)

    def set_detection_state(self, enabled: bool):
        self._btn_detection.blockSignals(True)
        self._btn_detection.setChecked(enabled)
        self._btn_detection.setText("감지 ON\n감시중" if enabled else "감지 OFF\n중지됨")
        self._btn_detection.blockSignals(False)

    def set_roi_visible_state(self, visible: bool):
        self._roi_visible = visible
        self._btn_roi.blockSignals(True)
        self._btn_roi.setChecked(visible)
        self._btn_roi.setText("영역 표시\nON" if visible else "영역 표시\nOFF")
        self._btn_roi.blockSignals(False)

    def set_volume_display(self, value: int):
        v = max(0, min(100, value))
        self._slider_volume.blockSignals(True)
        self._slider_volume.setValue(v)
        self._lbl_volume_val.setText(f"{v}%")
        self._slider_volume.blockSignals(False)

    def set_mute_state(self, enabled: bool):
        """enabled=True: 소리 켜짐(뮤트 아님), False: 뮤트"""
        self._btn_mute.blockSignals(True)
        muted = not enabled
        self._btn_mute.setChecked(muted)
        self._btn_mute.setText("알림음\nMUTE" if muted else "알림음\n켜짐")
        self._btn_mute.blockSignals(False)

    def set_signoff_buttons_enabled(self, enabled: bool):
        for gid in (1, 2):
            btn = self._btn_signoff.get(gid)
            if btn:
                btn.setEnabled(enabled)
                if not enabled:
                    btn.setText(btn.text().split('\n')[0])

    def set_fullscreen_button_state(self, is_fullscreen: bool):
        self._btn_fullscreen.blockSignals(True)
        self._btn_fullscreen.setChecked(is_fullscreen)
        self._btn_fullscreen.setIcon(self._make_fullscreen_icon(is_fullscreen))
        self._btn_fullscreen.blockSignals(False)

    def set_alarm_blink_state(self, active: bool):
        self._btn_ack.setProperty("alarm_active", "true" if active else "false")
        _refresh_property(self._btn_ack)

    def update_signoff_state(self, group_id: int, state: str,
                              group_name: str, seconds: float = 0.0,
                              clock_enabled: bool = True):
        btn = self._btn_signoff.get(group_id)
        if btn is None:
            return

        name = group_name or f"Group{group_id}"

        if not clock_enabled:
            btn.setText(f"{name} 정파")
            resolved = state if state in ("IDLE", "PREPARATION", "SIGNOFF") else "IDLE"
            btn.setProperty("signoff_state", resolved)
        elif state == "IDLE":
            btn.setText(f"{name} 정파\n준비 {_fmt_dhms(seconds)}")
            btn.setProperty("signoff_state", "IDLE")
        elif state == "PREPARATION":
            btn.setText(f"{name} 정파\n정파 {_fmt_dhms(seconds)}")
            btn.setProperty("signoff_state", "PREPARATION")
        elif state == "SIGNOFF":
            btn.setText(f"{name} 정파\n해제 {_fmt_dhms(seconds)}")
            btn.setProperty("signoff_state", "SIGNOFF")
        else:
            btn.setText(f"{name} 정파")
            btn.setProperty("signoff_state", "IDLE")

        btn.style().unpolish(btn)
        btn.style().polish(btn)
        btn.update()
