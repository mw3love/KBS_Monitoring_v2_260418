"""
메인 윈도우 (v2)
3분할 레이아웃: TopBar + VideoWidget(~75%) + LogWidget(~25%)
UIBridge(result_queue → Signal) + SharedFramePoller(SharedMemory → VideoWidget)
L/R 레벨미터: QTimer 33ms로 SharedStateBuffer 직접 폴링
"""
import os
import logging

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QSplitter, QApplication,
)
from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut

from core.roi_manager import ROI
from ui.top_bar import TopBar
from ui.video_widget import VideoWidget, SharedFramePoller
from ui.log_widget import LogWidget
from ui.ui_bridge import UIBridge
from ui.alarm import AlarmSystem
from utils.logger import AppLogger
from utils.config_manager import ConfigManager

_log = logging.getLogger(__name__)

VERSION = "2.0.0"


class MainWindow(QMainWindow):
    """KBS Monitoring v2 메인 윈도우"""

    def __init__(self, result_queue, cmd_queue, shutdown_event,
                 shared_frame=None, shared_state=None, cmd_event=None):
        super().__init__()
        self._result_queue  = result_queue
        self._cmd_queue     = cmd_queue
        self._shutdown_event = shutdown_event
        self._shared_frame  = shared_frame
        self._shared_state  = shared_state
        self._cmd_event     = cmd_event

        self.setWindowTitle(f"KBS Monitoring v{VERSION}")
        self.setMinimumSize(1280, 720)
        self.resize(1600, 900)

        # 설정 로드
        self._cfg_mgr = ConfigManager()
        self._cfg = self._cfg_mgr.load()

        # 로거
        self._logger = AppLogger(suffix="_ui")

        # 알람 시스템 (UI 프로세스 전용)
        self._alarm = AlarmSystem(parent=self)
        alarm_cfg = self._cfg.get("alarm", {})
        self._alarm.set_sound_enabled(alarm_cfg.get("sound_enabled", True))
        self._alarm.set_volume(alarm_cfg.get("volume", 80) / 100.0)

        # UI 런타임 상태 (재spawn 시 재주입용)
        self._detection_enabled = self._cfg.get("ui_state", {}).get("detection_enabled", True)
        self._signoff_states = {1: "IDLE", 2: "IDLE"}

        # Detection 준비 여부
        self._detection_ready = False

        # ROI 인라인 오버레이 상태
        self._roi_overlay = None
        self._roi_overlay_type: str = ""

        self._setup_ui()
        self._connect_signals()
        self._start_timers()
        self._restore_ui_state()

        self._logger.info(f"SYSTEM - KBS Monitoring v{VERSION} 시작")

    # ── UI 구성 ────────────────────────────────────────────────────

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._top_bar = TopBar()
        main_layout.addWidget(self._top_bar)

        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setObjectName("mainSplitter")
        main_layout.addWidget(self._splitter, stretch=1)

        self._video_widget = VideoWidget()
        self._video_widget.setObjectName("videoArea")
        self._splitter.addWidget(self._video_widget)

        self._log_widget = LogWidget()
        self._log_widget.setObjectName("logArea")
        self._splitter.addWidget(self._log_widget)

        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([1200, 400])

        self._apply_theme(dark=True)

    # ── 신호 연결 ──────────────────────────────────────────────────

    def _connect_signals(self):
        # TopBar → cmd_queue
        self._top_bar.detection_toggled.connect(self._on_detection_toggled)
        self._top_bar.volume_changed.connect(self._on_volume_changed)
        self._top_bar.alarm_acknowledged.connect(self._alarm.acknowledge_all)
        self._top_bar.sound_toggled.connect(self._alarm.set_sound_enabled)
        self._top_bar.roi_visibility_changed.connect(self._video_widget.set_show_rois)
        self._top_bar.dark_mode_toggled.connect(self._apply_theme)
        self._top_bar.fullscreen_toggled.connect(self._toggle_fullscreen)
        self._top_bar.signoff_manual_release.connect(self._on_signoff_button_clicked)
        self._top_bar.settings_requested.connect(self._open_settings)

        # AlarmSystem → VideoWidget/TopBar
        self._alarm.visual_blink.connect(self._video_widget.set_blink_state)
        self._alarm.visual_blink.connect(self._top_bar.set_alarm_blink_state)

        # F11 단축키
        sc = QShortcut(QKeySequence("F11"), self)
        sc.activated.connect(self._toggle_fullscreen)

    def _start_timers(self):
        # UIBridge: result_queue 폴링
        self._bridge = UIBridge(self._result_queue, parent=self)
        self._bridge.log_entry_received.connect(self._on_log_entry)
        self._bridge.alarm_trigger_received.connect(self._on_alarm_trigger)
        self._bridge.alarm_resolve_received.connect(self._on_alarm_resolve)
        self._bridge.detection_ready_received.connect(self._on_detection_ready)
        self._bridge.detection_crashed_received.connect(self._on_detection_crashed)
        self._bridge.signoff_state_received.connect(self._on_signoff_state_changed)
        self._bridge.stream_error_received.connect(self._on_stream_error)
        self._bridge.diag_snapshot_received.connect(self._on_diag_snapshot)
        self._bridge.start_polling()

        # SharedFramePoller: VideoWidget에 프레임 공급
        self._frame_poller = SharedFramePoller(
            self._shared_frame, self._video_widget, parent=self
        )
        self._frame_poller.start()

        # L/R 레벨미터: SharedStateBuffer 직접 폴링 (33ms)
        self._level_timer = QTimer(self)
        self._level_timer.setInterval(33)
        self._level_timer.timeout.connect(self._poll_levels)
        if self._shared_state:
            self._level_timer.start()

        # 정파 버튼 시간 갱신 (1초 주기)
        self._summary_timer = QTimer(self)
        self._summary_timer.setInterval(1000)
        self._summary_timer.timeout.connect(self._update_signoff_display)
        self._summary_timer.start()

    def _restore_ui_state(self):
        ui_state = self._cfg.get("ui_state", {})
        vol = self._cfg.get("alarm", {}).get("volume", 80)
        self._top_bar.set_volume_display(vol)
        self._top_bar.set_mute_state(
            self._cfg.get("alarm", {}).get("sound_enabled", True))
        self._top_bar.set_detection_state(self._detection_enabled)
        roi_visible = ui_state.get("roi_visible", True)
        self._top_bar.set_roi_visible_state(roi_visible)
        self._video_widget.set_show_rois(roi_visible)

        signoff_cfg = self._cfg.get("signoff", {})
        auto_prep = signoff_cfg.get("auto_preparation", True)
        self._top_bar.set_signoff_buttons_enabled(auto_prep)

        self._apply_rois_to_video_widget(self._cfg)

        if ui_state.get("fullscreen", False):
            QTimer.singleShot(200, self._toggle_fullscreen)

    # ── 슬롯: TopBar → cmd_queue ───────────────────────────────────

    def _on_detection_toggled(self, enabled: bool):
        self._detection_enabled = enabled
        from ipc.messages import SetDetectionEnabled, ClearAlarms
        self._send_cmd(SetDetectionEnabled(enabled=enabled))
        if not enabled:
            self._send_cmd(ClearAlarms())
            self._alarm.resolve_all()
            self._top_bar.update_health(False)

    def _on_volume_changed(self, value: int):
        from ipc.messages import SetVolume
        self._send_cmd(SetVolume(volume=value))

    def _on_signoff_button_clicked(self, group_id: int):
        from ipc.messages import SetSignoffState
        current = self._signoff_states.get(group_id, "IDLE")
        _cycle = {"IDLE": "PREPARATION", "PREPARATION": "SIGNOFF", "SIGNOFF": "IDLE"}
        # 정파 시간대 밖이면 PREPARATION → IDLE
        next_state = _cycle.get(current, "IDLE")
        self._send_cmd(SetSignoffState(group_id=group_id, new_state=next_state))

    # ── 슬롯: UIBridge ────────────────────────────────────────────

    def _on_log_entry(self, msg):
        level_map = {"debug": "debug", "error": "error", "still": "still",
                     "audio": "audio", "embedded": "embedded"}
        log_type = level_map.get(msg.level, "info")
        self._log_widget.add_log(f"[{msg.source}] {msg.message}", log_type)
        if msg.level == "error":
            self._logger.error(f"[{msg.source}] {msg.message}")
        else:
            self._logger.info(f"[{msg.source}] {msg.message}")

    def _on_alarm_trigger(self, msg):
        self._alarm.trigger(msg.detection_type, msg.label)
        self._video_widget.set_alert_state(msg.label, True)
        self._log_widget.add_log(
            f"[알람] {msg.label} {msg.detection_type} 감지",
            log_type=self._detect_type_to_log_type(msg.detection_type),
        )

    def _on_alarm_resolve(self, msg):
        self._alarm.resolve(msg.detection_type, msg.label)
        self._video_widget.set_alert_state(msg.label, False)
        self._log_widget.add_log(
            f"[복구] {msg.label} {msg.detection_type} "
            f"({msg.duration_sec:.0f}초)"
        )

    def _on_detection_crashed(self, msg):
        reason_kr = "heartbeat 무응답" if msg.reason == "heartbeat_stale" else "프로세스 종료"
        log_msg = f"[시스템] Detection 비정상 종료 (PID={msg.dead_pid}, 원인={reason_kr})"
        if msg.stale_sec > 0:
            log_msg += f", stale={msg.stale_sec:.0f}초"
        log_msg += " → 재spawn 중"
        self._logger.error(log_msg)
        self._log_widget.add_error(log_msg)
        self._top_bar.show_detection_crashed(msg.reason, msg.stale_sec)

    def _on_detection_ready(self, msg):
        self._detection_ready = True
        self._log_widget.add_log(
            f"[시스템] Detection 준비 완료 "
            f"(PID={msg.pid}, ROI={msg.roi_count})"
        )
        self._top_bar.update_health(False)
        # 런타임 상태 재주입 (재spawn 복원)
        self._reinject_runtime_state()

    def _on_signoff_state_changed(self, msg):
        self._signoff_states[msg.group_id] = msg.new_state
        self._log_widget.add_log(
            f"[정파] 그룹{msg.group_id}: {msg.prev_state} → {msg.new_state}"
        )

    def _on_stream_error(self, msg):
        self._log_widget.add_error(
            f"[{msg.source}] {msg.message} (재연결 {msg.retry_count}회)"
        )

    def _on_diag_snapshot(self, msg):
        if msg.section == "SYSTEM-HB":
            detection_enabled = msg.payload.get("detection_enabled", True)
            stale = msg.payload.get("loop_count", 1) == 0 and detection_enabled
            self._top_bar.update_health(stale)

    # ── 런타임 상태 재주입 ────────────────────────────────────────

    def _reinject_runtime_state(self):
        from ipc.messages import (
            ApplyConfig, SetDetectionEnabled, SetVolume, SetMute,
            SetSignoffState, UpdateROIs,
        )
        self._send_cmd(ApplyConfig(config=self._cfg, reason="restore"))
        self._send_cmd(SetDetectionEnabled(enabled=self._detection_enabled))
        vol = self._cfg.get("alarm", {}).get("volume", 80)
        self._send_cmd(SetVolume(volume=vol))
        muted = not self._cfg.get("alarm", {}).get("sound_enabled", True)
        from ipc.messages import SetMute
        self._send_cmd(SetMute(muted=muted))
        for gid, state in self._signoff_states.items():
            self._send_cmd(SetSignoffState(group_id=gid, new_state=state))
        rois = self._cfg.get("rois", {})
        roi_list = (
            [dict(r, roi_type="video") for r in rois.get("video", [])] +
            [dict(r, roi_type="audio") for r in rois.get("audio", [])]
        )
        self._send_cmd(UpdateROIs(rois=roi_list))

    # ── 레벨미터 폴링 ─────────────────────────────────────────────

    def _poll_levels(self):
        if self._shared_state is None:
            return
        try:
            l_db, r_db = self._shared_state.get_levels()
            self._top_bar.update_audio_levels(l_db, r_db)
        except Exception:
            pass

    # ── 정파 버튼 갱신 (1초) ──────────────────────────────────────

    def _update_signoff_display(self):
        signoff_cfg = self._cfg.get("signoff", {})
        for gid in (1, 2):
            state = self._signoff_states.get(gid, "IDLE")
            grp_data = signoff_cfg.get(f"group{gid}", {})
            group_name = grp_data.get("name", f"Group{gid}")
            auto_prep = signoff_cfg.get("auto_preparation", True)
            self._top_bar.update_signoff_state(
                gid, state, group_name,
                seconds=0.0,
                clock_enabled=auto_prep,
            )

    # ── 테마 ──────────────────────────────────────────────────────

    def _apply_theme(self, dark: bool = True):
        qss_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "resources", "styles",
            "dark_theme.qss" if dark else "light_theme.qss",
        )
        try:
            with open(qss_path, "r", encoding="utf-8") as f:
                QApplication.instance().setStyleSheet(f.read())
        except Exception as e:
            _log.warning("테마 로드 실패: %s", e)

    # ── 전체화면 ──────────────────────────────────────────────────

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self._top_bar.set_fullscreen_button_state(False)
        else:
            self.showFullScreen()
            self._top_bar.set_fullscreen_button_state(True)

    # ── 설정 ──────────────────────────────────────────────────────────

    def _open_settings(self):
        if hasattr(self, "_settings_dlg") and self._settings_dlg.isVisible():
            self._settings_dlg.raise_()
            self._settings_dlg.activateWindow()
            return
        from ui.settings_dialog import SettingsDialog
        frozen_frame = self._video_widget.get_current_frame()
        self._settings_dlg = SettingsDialog(
            cfg=self._cfg,
            cmd_queue=self._cmd_queue,
            alarm=self._alarm,
            frozen_frame=frozen_frame,
            parent=self,
            cmd_event=self._cmd_event,
        )
        self._settings_dlg.config_saved.connect(self._on_config_saved)
        self._settings_dlg.show()

    def _apply_rois_to_video_widget(self, cfg: dict):
        rois_cfg = cfg.get("rois", {})
        video_rois = [ROI(**{**r, "roi_type": "video"}) for r in rois_cfg.get("video", [])]
        audio_rois = [ROI(**{**r, "roi_type": "audio"}) for r in rois_cfg.get("audio", [])]
        self._video_widget.set_rois(video_rois, audio_rois)

    def _on_config_saved(self, new_cfg: dict):
        old_video_file = self._cfg.get("video_file", "")
        self._cfg = new_cfg
        alarm_cfg = new_cfg.get("alarm", {})
        self._alarm.set_sound_enabled(alarm_cfg.get("sound_enabled", True))
        self._alarm.set_volume(alarm_cfg.get("volume", 80) / 100.0)
        sound_file = alarm_cfg.get("sound_file", "") or "resources/sounds/alarm.wav"
        self._alarm.set_sound_file("default", sound_file)
        self._apply_rois_to_video_widget(new_cfg)
        # 테스트 영상 파일이 지워지면 VideoWidget도 즉시 검은 화면으로
        new_video_file = new_cfg.get("video_file", "")
        if old_video_file and not new_video_file:
            self._video_widget.clear_signal()
        self._log_widget.add_log("[시스템] 설정 저장 완료")

    # ── cmd_queue 발행 헬퍼 ───────────────────────────────────────

    def _send_cmd(self, msg):
        if self._cmd_queue is None:
            return
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

    @staticmethod
    def _detect_type_to_log_type(detection_type: str) -> str:
        return {
            "black":       "error",
            "still":       "still",
            "audio_level": "audio",
            "embedded":    "embedded",
        }.get(detection_type, "info")

    # ── ROI 인라인 오버레이 ────────────────────────────────────────

    def start_roi_overlay(self, roi_type: str, roi_mgr,
                          rois_changed_cb=None, done_callback=None):
        """ROI 인라인 편집 시작. 이미 편집 중이면 오버레이를 앞으로 올리고 반환."""
        if self._roi_overlay is not None:
            self._roi_overlay.raise_()
            self._roi_overlay.setFocus()
            return

        from ui.roi_editor import ROIOverlayWidget
        frozen = self._video_widget.get_current_frame()
        self._frame_poller.stop()

        self._roi_overlay = ROIOverlayWidget(
            roi_mgr=roi_mgr,
            roi_type=roi_type,
            frozen_frame=frozen,
            parent=self._video_widget,
        )
        self._roi_overlay_type = roi_type

        if rois_changed_cb:
            self._roi_overlay.set_rois_changed_callback(rois_changed_cb)

        self._roi_overlay.editing_finished.connect(
            lambda: self._stop_roi_overlay(done_callback)
        )
        self._roi_overlay.move(0, 0)
        self._roi_overlay.resize(self._video_widget.size())
        self._roi_overlay.show()
        self._roi_overlay.raise_()
        self._roi_overlay.setFocus()
        self._video_widget.installEventFilter(self)

    def _stop_roi_overlay(self, done_callback=None):
        """ROI 오버레이 종료, 라이브 프레임 복원."""
        if self._roi_overlay is None:
            return
        self._video_widget.removeEventFilter(self)
        self._roi_overlay.hide()
        self._roi_overlay.deleteLater()
        self._roi_overlay = None
        self._roi_overlay_type = ""
        self._frame_poller.start()
        if done_callback:
            done_callback()

    def eventFilter(self, obj, event):
        """video_widget 리사이즈 시 오버레이 크기 동기화."""
        if (obj is self._video_widget
                and event.type() == QEvent.Resize
                and self._roi_overlay is not None):
            self._roi_overlay.resize(self._video_widget.size())
        return super().eventFilter(obj, event)

    # ── 종료 ──────────────────────────────────────────────────────

    def closeEvent(self, event: QCloseEvent):
        self._logger.info("SYSTEM - 창 닫기 → 종료 시작")

        # 현재 UI 상태 저장
        ui_state = self._cfg.get("ui_state", {})
        ui_state["detection_enabled"] = self._detection_enabled
        ui_state["fullscreen"] = self.isFullScreen()
        ui_state["roi_visible"] = self._video_widget._show_rois
        self._cfg["ui_state"] = ui_state
        self._cfg_mgr.save(self._cfg)

        # Detection에 종료 신호
        from ipc.messages import Shutdown
        self._send_cmd(Shutdown(reason="user"))

        # shutdown_event set (Watchdog/Detection 종료 트리거)
        if self._shutdown_event is not None:
            self._shutdown_event.set()

        # ROI 오버레이 정리
        if self._roi_overlay is not None:
            self._roi_overlay.hide()
            self._roi_overlay.deleteLater()
            self._roi_overlay = None

        # 타이머/스레드 정지
        self._level_timer.stop()
        self._summary_timer.stop()
        self._frame_poller.stop()
        self._bridge.stop_polling()

        event.accept()
