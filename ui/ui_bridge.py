"""
UIBridge — result_queue 폴링 → Qt Signal 변환 (QThread)
50ms 주기로 result_queue를 드레인하여 각 메시지 타입별 Signal 발행.
DetectionReady 수신 시 런타임 상태 재주입 트리거 Signal 발행.
"""
from PySide6.QtCore import QThread, Signal, QTimer
from PySide6.QtWidgets import QApplication


class UIBridge(QThread):
    """
    result_queue를 폴링하여 Qt Signal로 변환.
    모든 Signal은 QThread → Qt 이벤트 루프로 마샬링되므로
    수신 슬롯은 UI 스레드에서 안전하게 실행됨.
    """

    # result_queue 메시지별 Signal
    detection_result_received  = Signal(object)   # DetectionResult
    alarm_trigger_received     = Signal(object)   # AlarmTrigger
    alarm_resolve_received     = Signal(object)   # AlarmResolve
    log_entry_received         = Signal(object)   # LogEntry
    diag_snapshot_received     = Signal(object)   # DiagSnapshot
    signoff_state_received     = Signal(object)   # SignoffStateChange
    recording_event_received   = Signal(object)   # RecordingEvent
    telegram_status_received   = Signal(object)   # TelegramStatus
    stream_error_received      = Signal(object)   # StreamError
    detection_ready_received   = Signal(object)   # DetectionReady
    perf_measurement_received  = Signal(object)   # PerfMeasurement

    def __init__(self, result_queue, parent=None):
        super().__init__(parent)
        self._result_queue = result_queue
        self._running = False

    def start_polling(self):
        self._running = True
        self.start()

    def stop_polling(self):
        self._running = False
        self.wait(3000)

    def run(self):
        from ipc.messages import (
            DetectionResult, AlarmTrigger, AlarmResolve, LogEntry,
            DiagSnapshot, SignoffStateChange, RecordingEvent, TelegramStatus,
            StreamError, DetectionReady, PerfMeasurement,
        )

        _DISPATCH = {
            DetectionResult:  self.detection_result_received,
            AlarmTrigger:     self.alarm_trigger_received,
            AlarmResolve:     self.alarm_resolve_received,
            LogEntry:         self.log_entry_received,
            DiagSnapshot:     self.diag_snapshot_received,
            SignoffStateChange: self.signoff_state_received,
            RecordingEvent:   self.recording_event_received,
            TelegramStatus:   self.telegram_status_received,
            StreamError:      self.stream_error_received,
            DetectionReady:   self.detection_ready_received,
            PerfMeasurement:  self.perf_measurement_received,
        }

        while self._running:
            # 최대 20개씩 드레인 (50ms × 20 = 최대 1초 지연 방지)
            drained = 0
            while drained < 20:
                try:
                    msg = self._result_queue.get_nowait()
                except Exception:
                    break
                signal = _DISPATCH.get(type(msg))
                if signal is not None:
                    signal.emit(msg)
                drained += 1

            self.msleep(50)
