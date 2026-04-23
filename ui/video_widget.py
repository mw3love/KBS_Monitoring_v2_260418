"""
비디오 표시 위젯
v1 ui/video_widget.py에서 프레임 소스를 SharedMemory 폴링으로 변경.
SharedFramePoller: QTimer 33ms 주기로 seq_no 변경을 감지 → update_frame().
"""
import numpy as np
import cv2
from itertools import chain
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QImage, QPainter, QPen, QFont, QColor
from typing import List, Dict, Optional
from core.roi_manager import ROI

_NO_SIGNAL_W = 1920
_NO_SIGNAL_H = 1080

# 에디터(roi_editor.py)와 동일한 색상 상수
_VIDEO_COLOR        = QColor("#cc0000")
_VIDEO_ALERT_COLOR  = QColor("#ff4444")
_VIDEO_FILL_COLOR   = QColor(204, 0, 0, 60)
_AUDIO_COLOR        = QColor("#D97757")
_AUDIO_ALERT_COLOR  = QColor("#ff9955")
_AUDIO_FILL_COLOR   = QColor(217, 119, 87, 60)


class VideoWidget(QWidget):
    """16분할 멀티뷰 영상을 표시하는 위젯"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_frame: Optional[np.ndarray] = None
        self._show_rois = True
        self._video_rois: List[ROI] = []
        self._audio_rois: List[ROI] = []
        self._alert_labels: Dict[str, bool] = {}
        self._blink_on = False
        self._no_signal_frame: Optional[np.ndarray] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel()
        self._label.setObjectName("videoLabel")
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._label.setMinimumSize(640, 360)
        layout.addWidget(self._label)

        self._render()

    def _make_no_signal_frame(self) -> np.ndarray:
        if self._no_signal_frame is not None:
            return self._no_signal_frame
        img = np.zeros((_NO_SIGNAL_H, _NO_SIGNAL_W, 3), dtype=np.uint8)
        text = "NO SIGNAL INPUT"
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 3.0
        thickness = 4
        text_size, _ = cv2.getTextSize(text, font, font_scale, thickness)
        tx = (_NO_SIGNAL_W - text_size[0]) // 2
        ty = (_NO_SIGNAL_H + text_size[1]) // 2
        cv2.putText(img, text, (tx, ty), font, font_scale,
                    (80, 80, 80), thickness, cv2.LINE_AA)
        self._no_signal_frame = img
        return img

    def update_frame(self, frame: np.ndarray):
        self._current_frame = frame
        self._render()

    def set_show_rois(self, show: bool):
        self._show_rois = show
        self._render()

    def set_rois(self, video_rois: List[ROI], audio_rois: List[ROI]):
        self._video_rois = video_rois
        self._audio_rois = audio_rois
        self._render()

    def set_alert_state(self, label: str, alerting: bool):
        if self._alert_labels.get(label) == alerting:
            return
        self._alert_labels[label] = alerting
        self._render()

    def set_blink_state(self, blink_on: bool):
        self._blink_on = blink_on
        self._render()

    def clear_signal(self):
        self._current_frame = None
        self._render()

    def _render(self):
        frame = (self._current_frame.copy()
                 if self._current_frame is not None
                 else self._make_no_signal_frame().copy())
        h, w = frame.shape[:2]

        has_alerts = any(
            self._alert_labels.get(r.label, False)
            for r in chain(self._video_rois, self._audio_rois)
        )
        roi_overlays = []
        if self._show_rois or has_alerts:
            roi_overlays = self._collect_roi_overlays(w, h)

        self._display_numpy(frame, roi_overlays)

    def _collect_roi_overlays(self, fw: int, fh: int) -> list:
        """ROI 좌표·색상 정보를 수집 (프레임 좌표계). 실제 그리기는 QPainter로."""
        overlays = []
        all_rois = ([("video", r) for r in self._video_rois] +
                    [("audio", r) for r in self._audio_rois])
        for roi_type, roi in all_rois:
            alerting = self._alert_labels.get(roi.label, False)
            if not self._show_rois and not alerting:
                continue

            x1 = max(0, min(roi.x, fw - 1))
            y1 = max(0, min(roi.y, fh - 1))
            x2 = max(0, min(roi.x + roi.w, fw))
            y2 = max(0, min(roi.y + roi.h, fh))

            if roi_type == "video":
                color = _VIDEO_ALERT_COLOR if (alerting and self._blink_on) else _VIDEO_COLOR
                fill  = _VIDEO_FILL_COLOR  if (alerting and self._blink_on) else None
            else:
                color = _AUDIO_ALERT_COLOR if (alerting and self._blink_on) else _AUDIO_COLOR
                fill  = _AUDIO_FILL_COLOR  if (alerting and self._blink_on) else None

            label_text = (f"{roi.label} [{roi.media_name}]"
                          if roi.media_name else roi.label)
            overlays.append({
                "rect": (x1, y1, x2 - x1, y2 - y1),
                "color": color,
                "fill": fill,
                "label": label_text,
            })
        return overlays

    def _display_numpy(self, frame: np.ndarray, roi_overlays: list = None):
        h, w, ch = frame.shape
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = QImage(rgb.tobytes(), w, h, ch * w, QImage.Format_RGB888)

        lw = self._label.width()
        lh = self._label.height()
        if lw > 0 and lh > 0:
            pixmap = QPixmap.fromImage(image).scaled(
                lw, lh, Qt.KeepAspectRatio, Qt.FastTransformation,
            )
        else:
            pixmap = QPixmap.fromImage(image)

        if roi_overlays and w > 0:
            scale = pixmap.width() / w
            font = QFont()
            font.setPixelSize(max(9, int(14 * scale)))

            painter = QPainter(pixmap)
            painter.setFont(font)

            for ov in roi_overlays:
                fx, fy, fw_roi, fh_roi = ov["rect"]
                px = int(fx * scale)
                py = int(fy * scale)
                pw = int(fw_roi * scale)
                ph = int(fh_roi * scale)
                color = ov["color"]

                if ov["fill"]:
                    painter.fillRect(px, py, pw, ph, ov["fill"])

                painter.setPen(QPen(color, 2.0))
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(px, py, pw, ph)

                tx = px + 3
                ty = py + max(9, int(14 * scale))
                painter.setPen(QColor(0, 0, 0))
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    painter.drawText(tx + dx, ty + dy, ov["label"])
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(tx, ty, ov["label"])

            painter.end()

        self._label.setPixmap(pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render()

    def get_current_frame(self):
        """현재 프레임 복사본 반환 (ROI 편집 등에 사용). 없으면 None."""
        if self._current_frame is not None:
            return self._current_frame.copy()
        return None

    def get_frame_size(self) -> tuple:
        if self._current_frame is not None:
            h, w = self._current_frame.shape[:2]
            return w, h
        return _NO_SIGNAL_W, _NO_SIGNAL_H

    def widget_to_frame_coords(self, wx: int, wy: int) -> tuple:
        if self._current_frame is not None:
            fh, fw = self._current_frame.shape[:2]
        else:
            fw, fh = _NO_SIGNAL_W, _NO_SIGNAL_H

        lw = self._label.width()
        lh = self._label.height()
        scale = min(lw / fw, lh / fh)
        if scale == 0:
            return 0, 0

        off_x = (lw - fw * scale) / 2
        off_y = (lh - fh * scale) / 2
        fx = max(0, min(fw, int((wx - off_x) / scale)))
        fy = max(0, min(fh, int((wy - off_y) / scale)))
        return fx, fy


class SharedFramePoller:
    """
    QTimer 33ms 주기로 SharedFrameBuffer의 seq_no 변경을 감지하여
    VideoWidget.update_frame()을 호출.
    main 프로세스의 QApplication 이벤트 루프 내에서 동작.
    """

    def __init__(self, shared_frame, video_widget: VideoWidget, parent=None):
        self._shared_frame = shared_frame
        self._video_widget = video_widget
        self._last_seq = -1
        self._timer = QTimer(parent)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._poll)
        # 측정 카운터
        self._stat_ok = 0
        self._stat_writing = 0
        self._stat_torn = 0
        self._stat_no_signal = 0
        self._stat_t0 = 0.0

    def start(self):
        import time
        self._stat_t0 = time.monotonic()
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def _poll(self):
        if self._shared_frame is None:
            return
        try:
            import time
            meta = self._shared_frame.read_meta()
            seq = meta.get("seq_no", 0)
            if seq != self._last_seq and seq % 2 == 0 and seq > 0:
                frame, reason = self._shared_frame.read_frame_debug()
                if frame is not None:
                    self._last_seq = seq   # 성공 시에만 갱신 (실패 시 다음 poll 재시도)
                    self._stat_ok += 1
                    self._video_widget.update_frame(frame)
                else:
                    # None은 일시적 tearing/쓰기중 — 이전 프레임 유지, clear_signal 호출 안 함
                    if reason == "writing":
                        self._stat_writing += 1
                    elif reason == "torn":
                        self._stat_torn += 1
                    else:
                        self._stat_no_signal += 1

            # 5초마다 None 비율 로그 출력
            elapsed = time.monotonic() - self._stat_t0
            if elapsed >= 5.0:
                total = self._stat_ok + self._stat_writing + self._stat_torn + self._stat_no_signal
                if total > 0:
                    import logging
                    logging.getLogger(__name__).debug(
                        "[SharedFramePoller] 5s 통계: ok=%d writing=%d torn=%d no_signal=%d "
                        "(None율=%.1f%%)",
                        self._stat_ok, self._stat_writing, self._stat_torn, self._stat_no_signal,
                        100.0 * (total - self._stat_ok) / total,
                    )
                self._stat_ok = self._stat_writing = self._stat_torn = self._stat_no_signal = 0
                self._stat_t0 = time.monotonic()
        except Exception:
            pass
