"""
비디오 표시 위젯
v1 ui/video_widget.py에서 프레임 소스를 SharedMemory 폴링으로 변경.
SharedFramePoller: QTimer 33ms 주기로 seq_no 변경 감지 → update_frame().
"""
import numpy as np
import cv2
from itertools import chain
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QImage, QPainter, QFont, QColor
from typing import List, Dict, Optional
from core.roi_manager import ROI

_NO_SIGNAL_W = 1920
_NO_SIGNAL_H = 1080


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
        text_overlays = []
        if self._show_rois or has_alerts:
            text_overlays = self._draw_rois(frame, w, h)

        self._display_numpy(frame, text_overlays)

    def _draw_rois(self, frame: np.ndarray, fw: int, fh: int) -> list:
        all_rois = ([("video", r) for r in self._video_rois] +
                    [("audio", r) for r in self._audio_rois])
        text_overlays = []
        for roi_type, roi in all_rois:
            alerting = self._alert_labels.get(roi.label, False)
            if not self._show_rois and not alerting:
                continue

            x1 = max(0, min(roi.x, fw - 1))
            y1 = max(0, min(roi.y, fh - 1))
            x2 = max(0, min(roi.x + roi.w, fw))
            y2 = max(0, min(roi.y + roi.h, fh))

            if roi_type == "video":
                normal_color = (0, 0, 200)
                alert_color  = (0, 0, 255)
                fill_color   = (0, 0, 180)
            else:
                normal_color = (0, 165, 255)
                alert_color  = (0, 0, 255)
                fill_color   = (0, 0, 180)

            if alerting and self._blink_on:
                overlay = frame.copy()
                cv2.rectangle(overlay, (x1, y1), (x2, y2), fill_color, -1)
                cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)
                cv2.rectangle(frame, (x1, y1), (x2, y2), alert_color, 2)
            else:
                cv2.rectangle(frame, (x1, y1), (x2, y2), normal_color, 2)

            label_text = (f"{roi.label} [{roi.media_name}]"
                          if roi.media_name else roi.label)
            text_overlays.append((x1 + 3, y1 + 18, label_text))

        return text_overlays

    def _display_numpy(self, frame: np.ndarray, text_overlays: list = None):
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

        if text_overlays and w > 0:
            scale = pixmap.width() / w
            font = QFont()
            font.setPixelSize(max(9, int(14 * scale)))
            painter = QPainter(pixmap)
            painter.setFont(font)
            for fx, fy, text in text_overlays:
                px = int(fx * scale)
                py = int(fy * scale)
                painter.setPen(QColor(0, 0, 0))
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    painter.drawText(px + dx, py + dy, text)
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(px, py, text)
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

    def start(self):
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def _poll(self):
        if self._shared_frame is None:
            return
        try:
            meta = self._shared_frame.read_meta()
            seq = meta.get("seq_no", 0)
            if seq != self._last_seq and seq % 2 == 0 and seq > 0:
                self._last_seq = seq
                frame = self._shared_frame.read_frame()
                if frame is not None:
                    self._video_widget.update_frame(frame)
        except Exception:
            pass
