"""
비디오 표시 위젯
v1 ui/video_widget.py에서 프레임 소스를 SharedMemory 폴링으로 변경.
SharedFramePoller: QTimer 33ms 주기로 seq_no 변경 감지 → update_frame().
깜빡임 방지: QLabel.setPixmap 대신 paintEvent 직접 그리기 (Qt 더블버퍼링 활용).
"""
import numpy as np
import cv2
from itertools import chain
from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Qt, QTimer, QRect
from PySide6.QtGui import QPixmap, QImage, QPainter, QFont, QColor
from typing import List, Dict, Optional
from core.roi_manager import ROI

_NO_SIGNAL_W = 1920
_NO_SIGNAL_H = 1080


class VideoWidget(QWidget):
    """16분할 멀티뷰 영상을 표시하는 위젯. paintEvent 기반으로 깜빡임 없음."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_frame: Optional[np.ndarray] = None
        self._show_rois = True
        self._video_rois: List[ROI] = []
        self._audio_rois: List[ROI] = []
        self._alert_labels: Dict[str, bool] = {}
        self._blink_on = False
        self._no_signal_frame: Optional[np.ndarray] = None

        # 화면에 그릴 픽셀맵 (스케일 적용 전 원본 해상도)
        self._display_pixmap: Optional[QPixmap] = None

        self.setMinimumSize(640, 360)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Qt 더블버퍼링 — WA_OpaquePaintEvent로 배경 지우기 스킵해 깜빡임 제거
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self._rebuild_pixmap()

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

    # ── 외부에서 상태 변경 ────────────────────────────────────────

    def update_frame(self, frame: np.ndarray):
        self._current_frame = frame
        self._rebuild_pixmap()
        self.update()  # paintEvent 예약 (더블버퍼링)

    def set_show_rois(self, show: bool):
        self._show_rois = show
        self._rebuild_pixmap()
        self.update()

    def set_rois(self, video_rois: List[ROI], audio_rois: List[ROI]):
        self._video_rois = video_rois
        self._audio_rois = audio_rois
        self._rebuild_pixmap()
        self.update()

    def set_alert_state(self, label: str, alerting: bool):
        if self._alert_labels.get(label) == alerting:
            return
        self._alert_labels[label] = alerting
        self._rebuild_pixmap()
        self.update()

    def set_blink_state(self, blink_on: bool):
        self._blink_on = blink_on
        if any(self._alert_labels.values()):
            self._rebuild_pixmap()
            self.update()

    def clear_signal(self):
        self._current_frame = None
        self._display_pixmap = None
        self.update()

    # ── 픽셀맵 빌드 (BGR→RGB 변환 + ROI 오버레이) ────────────────

    def _rebuild_pixmap(self):
        """현재 프레임(또는 NO SIGNAL)으로 _display_pixmap을 재빌드."""
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

        # BGR → RGB 변환 후 QPixmap 생성
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        ch = rgb.shape[2]
        image = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(image)

        if text_overlays:
            scale = 1.0  # 원본 해상도에서 텍스트 그리기
            font = QFont()
            font.setPixelSize(14)
            painter = QPainter(pixmap)
            painter.setFont(font)
            for fx, fy, text in text_overlays:
                painter.setPen(QColor(0, 0, 0))
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    painter.drawText(fx + dx, fy + dy, text)
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(fx, fy, text)
            painter.end()

        self._display_pixmap = pixmap

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
                normal_color = (0, 0, 204)
                alert_color  = (0, 0, 255)
                fill_color   = (0, 0, 160)
            else:
                normal_color = (190, 47, 123)
                alert_color  = (0, 0, 255)
                fill_color   = (160, 40, 100)

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

    # ── Qt 이벤트 ────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        if self._display_pixmap is None:
            painter.fillRect(self.rect(), QColor(0, 0, 0))
            return

        pw = self._display_pixmap.width()
        ph = self._display_pixmap.height()
        ww = self.width()
        wh = self.height()

        # 비율 유지 스케일
        scale = min(ww / pw, wh / ph) if pw > 0 and ph > 0 else 1.0
        dw = int(pw * scale)
        dh = int(ph * scale)
        dx = (ww - dw) // 2
        dy = (wh - dh) // 2

        painter.fillRect(self.rect(), QColor(0, 0, 0))
        painter.drawPixmap(QRect(dx, dy, dw, dh), self._display_pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # paintEvent가 알아서 리사이즈에 맞춰 그리므로 update()만 호출
        self.update()

    # ── 좌표 변환 (ROI 편집 등에 사용) ──────────────────────────

    def get_current_frame(self) -> Optional[np.ndarray]:
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

        if self._display_pixmap is None:
            return 0, 0

        pw = self._display_pixmap.width()
        ph = self._display_pixmap.height()
        ww = self.width()
        wh = self.height()
        scale = min(ww / pw, wh / ph) if pw > 0 and ph > 0 else 1.0
        dw = int(pw * scale)
        dh = int(ph * scale)
        off_x = (ww - dw) / 2
        off_y = (wh - dh) / 2

        # 위젯 좌표 → 픽셀맵 좌표 → 원본 프레임 좌표
        px = (wx - off_x) / scale
        py = (wy - off_y) / scale
        fx = max(0, min(fw, int(px)))
        fy = max(0, min(fh, int(py)))
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
