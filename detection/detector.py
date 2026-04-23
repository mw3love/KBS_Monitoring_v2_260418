"""
영상/오디오 감지 엔진
블랙/스틸/레벨미터/임베디드오디오 감지 로직.
PySide6 임포트 없음. v1 core/detector.py에서 Signal 제거 및 임포트 경로 수정.
"""
import logging
import time
import cv2
import numpy as np
from collections import deque
from typing import Dict, List, Optional
from core.roi_manager import ROI
from detection.detection_state import DetectionState

_log = logging.getLogger(__name__)


class Detector:
    """
    영상/오디오 감지 엔진.
    블랙/스틸/레벨미터/임베디드오디오 감지 수행.
    모든 결과는 dict로 반환 (Signal 없음).
    """

    def __init__(self):
        self.scale_factor = 1.0
        self.black_detection_enabled = True
        self.still_detection_enabled = True
        self.audio_detection_enabled = True
        self.embedded_detection_enabled = True

        self.black_threshold = 5
        self.black_dark_ratio = 98.0
        self.black_duration = 10.0
        self.black_alarm_duration = 10.0
        self.black_motion_suppress_ratio = 0.2

        self.still_threshold = 4
        self.still_changed_ratio = 10.0
        self.still_duration = 10.0
        self.still_alarm_duration = 10.0
        self.still_reset_frames = 3

        self.audio_hsv_h_min = 40
        self.audio_hsv_h_max = 95
        self.audio_hsv_s_min = 80
        self.audio_hsv_s_max = 255
        self.audio_hsv_v_min = 60
        self.audio_hsv_v_max = 255
        self.audio_pixel_ratio = 5.0
        self.audio_level_duration = 5.0
        self.audio_level_alarm_duration = 10.0
        self.audio_level_recovery_seconds = 2.0

        self.embedded_silence_threshold = -50
        self.embedded_silence_duration = 10.0
        self.embedded_alarm_duration = 10.0

        self._black_states: Dict[str, DetectionState] = {}
        self._still_states: Dict[str, DetectionState] = {}
        self._prev_frames: Dict[str, np.ndarray] = {}

        self._audio_level_states: Dict[str, DetectionState] = {}
        self._audio_ratio_buffer: Dict[str, deque] = {}

        self.embedded_alerting = False
        self._embedded_alert_start: Optional[float] = None
        self._tone_states: Dict[str, DetectionState] = {}

        self._last_raw: Dict[str, dict] = {}
        self._near_miss_start: Dict[str, float] = {}

    def _check_still_by_blocks(self, changed_mask: np.ndarray) -> bool:
        bh, bw = changed_mask.shape[:2]
        if changed_mask.ndim == 3:
            changed_mask = changed_mask.any(axis=2)
        rows, cols = 5, 5
        row_edges = np.linspace(0, bh, rows + 1, dtype=int)
        col_edges = np.linspace(0, bw, cols + 1, dtype=int)
        threshold = self.still_changed_ratio
        for r in range(rows):
            for c in range(cols):
                block = changed_mask[row_edges[r]:row_edges[r + 1],
                                     col_edges[c]:col_edges[c + 1]]
                if block.size == 0:
                    continue
                if float(np.mean(block)) * 100.0 >= threshold:
                    return False
        return True

    def _apply_scale_factor(self, frame: np.ndarray) -> np.ndarray:
        if self.scale_factor < 1.0:
            return cv2.resize(frame, None,
                              fx=self.scale_factor, fy=self.scale_factor,
                              interpolation=cv2.INTER_AREA)
        return frame

    def _get_scaled_bounds(self, roi: ROI, frame_h: int, frame_w: int) -> tuple:
        sf = self.scale_factor
        x1 = max(0, int(roi.x * sf))
        y1 = max(0, int(roi.y * sf))
        x2 = min(frame_w, int((roi.x + roi.w) * sf))
        y2 = min(frame_h, int((roi.y + roi.h) * sf))
        return x1, y1, x2, y2

    def update_roi_list(self, rois: List[ROI]):
        labels = {roi.label for roi in rois}
        for d in (self._black_states, self._still_states, self._prev_frames,
                  self._near_miss_start, self._audio_ratio_buffer,
                  self._audio_level_states, self._last_raw, self._tone_states):
            for label in list(d.keys()):
                if label not in labels:
                    del d[label]
        for roi in rois:
            if roi.label not in self._black_states:
                self._black_states[roi.label] = DetectionState(roi)
            else:
                self._black_states[roi.label].roi = roi
            if roi.label not in self._still_states:
                self._still_states[roi.label] = DetectionState(roi)
            else:
                self._still_states[roi.label].roi = roi

    def detect_frame(self, frame: np.ndarray, rois: List[ROI],
                     force_still_labels: Optional[set] = None) -> Dict[str, dict]:
        """
        프레임을 분석하여 각 감지영역의 블랙/스틸 상태 반환.
        반환값: {label: {"black": bool, "still": bool, "black_alerting": bool, ...}}
        """
        results = {}
        frame = self._apply_scale_factor(frame)
        h, w = frame.shape[:2]

        for roi in rois:
            label = roi.label
            try:
                x1, y1, x2, y2 = self._get_scaled_bounds(roi, h, w)
                if x2 <= x1 or y2 <= y1:
                    continue
                crop = frame[y1:y2, x1:x2]
                if crop.size == 0:
                    continue

                dark_ratio = -1.0
                is_black = False
                if self.black_detection_enabled:
                    gray = crop if len(crop.shape) == 2 else crop.mean(axis=2)
                    dark_ratio = float(np.mean(gray < self.black_threshold)) * 100.0
                    is_black = dark_ratio >= self.black_dark_ratio

                changed_ratio = -1.0
                is_still = False
                should_calc_still = self.still_detection_enabled or (
                    force_still_labels is not None and label in force_still_labels
                )
                if should_calc_still:
                    if label in self._prev_frames:
                        prev = self._prev_frames[label]
                        crop_f = crop.astype(np.float32)
                        if prev.shape == crop_f.shape:
                            diff = np.abs(crop_f - prev)
                            changed_mask = diff > self.still_threshold
                            changed_ratio = float(np.mean(changed_mask)) * 100.0
                            is_still = self._check_still_by_blocks(changed_mask)
                    self._prev_frames[label] = crop.astype(np.float32)
                else:
                    self._prev_frames.pop(label, None)

                if is_black and self.black_motion_suppress_ratio > 0 and changed_ratio >= 0:
                    if changed_ratio >= self.black_motion_suppress_ratio:
                        is_black = False

                self._last_raw[label] = {
                    "dark_ratio": dark_ratio,
                    "changed_ratio": changed_ratio,
                }

                if label not in self._black_states:
                    self._black_states[label] = DetectionState(roi)
                if label not in self._still_states:
                    self._still_states[label] = DetectionState(roi)

                black_state = self._black_states[label]
                still_state = self._still_states[label]

                black_alerting = black_state.update(is_black, self.black_duration)
                prev_reset_time = still_state._last_reset_time
                still_alerting = still_state.update(is_still, self.still_duration,
                                                    reset_frames=self.still_reset_frames)
                if (still_state._last_reset_from >= 5.0
                        and still_state._last_reset_time != prev_reset_time):
                    _log.warning(
                        "DIAG - ROI[%s] 스틸 타이머 리셋 (누적 %.1f초 → 0, %d프레임 연속 모션)",
                        label, still_state._last_reset_from, self.still_reset_frames,
                    )

                now_nm = time.time()
                is_near_miss = (dark_ratio > 80.0) or (changed_ratio >= 0 and changed_ratio < 3.0)
                if is_near_miss:
                    if label not in self._near_miss_start:
                        self._near_miss_start[label] = now_nm
                    elif now_nm - self._near_miss_start[label] >= 30.0:
                        _log.debug("NEAR-MISS - ROI[%s]: dark=%.1f%% changed=%.2f%%",
                                   label, dark_ratio, changed_ratio)
                        self._near_miss_start[label] = now_nm
                else:
                    self._near_miss_start.pop(label, None)

                results[label] = {
                    "black": is_black,
                    "still": is_still,
                    "black_alerting": black_alerting,
                    "still_alerting": still_alerting,
                    "black_duration": black_state.alert_duration,
                    "still_duration": still_state.alert_duration,
                    "black_resolved": black_state.just_resolved,
                    "black_last_duration": black_state.last_alert_duration,
                    "still_resolved": still_state.just_resolved,
                    "still_last_duration": still_state.last_alert_duration,
                }
            except Exception as e:
                _log.error("detect_frame ROI[%s] 오류: %s", label, e)

        return results

    def detect_audio_roi(self, frame: np.ndarray, audio_rois: List[ROI]) -> Dict[str, dict]:
        """
        오디오 ROI에서 HSV 기반 레벨미터 색상 감지.
        반환값: {label: {"active": bool, "ratio": float, "alerting": bool, ...}}
        """
        if not self.audio_detection_enabled:
            return {roi.label: {"active": False, "ratio": 0.0, "alerting": False,
                                "duration": 0.0, "resolved": False,
                                "last_duration": 0.0} for roi in audio_rois}
        results = {}
        lower = np.array([self.audio_hsv_h_min, self.audio_hsv_s_min, self.audio_hsv_v_min])
        upper = np.array([self.audio_hsv_h_max, self.audio_hsv_s_max, self.audio_hsv_v_max])
        frame = self._apply_scale_factor(frame)
        fh, fw = frame.shape[:2]

        for roi in audio_rois:
            label = roi.label
            try:
                x1, y1, x2, y2 = self._get_scaled_bounds(roi, fh, fw)
                if x2 <= x1 or y2 <= y1:
                    continue
                crop_bgr = frame[y1:y2, x1:x2]
                if crop_bgr.size == 0:
                    continue
                crop = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
                mask = cv2.inRange(crop, lower, upper)
                total_pixels = crop.shape[0] * crop.shape[1]
                if total_pixels == 0:
                    continue

                ratio = int(np.sum(mask > 0)) / total_pixels * 100.0

                if label not in self._audio_ratio_buffer:
                    self._audio_ratio_buffer[label] = deque(maxlen=5)
                self._audio_ratio_buffer[label].append(ratio)
                avg_ratio = (sum(self._audio_ratio_buffer[label])
                             / len(self._audio_ratio_buffer[label]))
                is_active = avg_ratio >= self.audio_pixel_ratio
                is_abnormal = not is_active

                if label not in self._audio_level_states:
                    self._audio_level_states[label] = DetectionState(roi)
                state = self._audio_level_states[label]
                state.roi = roi

                alerting = state.update(is_abnormal, self.audio_level_duration,
                                        self.audio_level_recovery_seconds)

                results[label] = {
                    "active": is_active,
                    "ratio": avg_ratio,
                    "alerting": alerting,
                    "duration": state.alert_duration,
                    "resolved": state.just_resolved,
                    "last_duration": state.last_alert_duration,
                }
            except Exception as e:
                _log.error("detect_audio_roi ROI[%s] 오류: %s", label, e)

        return results

    def update_embedded_silence(self, silence_seconds: float) -> bool:
        if not self.embedded_detection_enabled:
            return False
        if silence_seconds > 0:
            if self._embedded_alert_start is None:
                self._embedded_alert_start = time.time() - silence_seconds
            elapsed = time.time() - self._embedded_alert_start
            if elapsed >= self.embedded_silence_duration and not self.embedded_alerting:
                self.embedded_alerting = True
        else:
            self._embedded_alert_start = None
            self.embedded_alerting = False
        return self.embedded_alerting

    def reset_embedded_silence(self):
        self._embedded_alert_start = None
        self.embedded_alerting = False

    def reset_all(self):
        for state in self._black_states.values():
            state.reset()
        for state in self._still_states.values():
            state.reset()
        for state in self._audio_level_states.values():
            state.reset()
        for state in self._tone_states.values():
            state.reset()
        self.reset_embedded_silence()
