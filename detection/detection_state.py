"""
단일 감지영역 상태 추적 클래스
v1 core/detector.py에서 DetectionState 클래스 분리.
PySide6 임포트 없음.
"""
import time
from typing import Optional


class DetectionState:
    """단일 감지영역의 상태 추적"""

    def __init__(self, roi):
        self.roi = roi
        self.is_alerting = False
        self.alert_start_time: Optional[float] = None
        self.alert_duration = 0.0
        self.last_alert_duration = 0.0
        self.just_resolved = False
        self.recovery_start_time: Optional[float] = None
        self.last_check_time = time.time()
        # 히스테리시스: 연속 N프레임 정상이어야 타이머 리셋
        self._not_still_count: int = 0
        self._last_reset_time: float = 0.0
        self._last_reset_from: float = 0.0
        self._resolve_count: int = 0

    def update(self, is_abnormal: bool, threshold_seconds: float,
               recovery_seconds: float = 0.0, reset_frames: int = 1) -> bool:
        """
        상태 업데이트. 알림 발생 여부 반환.
        is_abnormal: 현재 이상 상태 여부
        threshold_seconds: 몇 초 이상 지속 시 알림 발생
        recovery_seconds: 알림 상태에서 정상으로 복구되기 위한 최소 정상 지속 시간(초)
                          0이면 reset_frames 히스테리시스 적용
        reset_frames: 연속 정상 프레임 수 임계값 (경보 전/후 동일 적용)
        """
        now = time.time()
        was_alerting = self.is_alerting

        if is_abnormal:
            self.just_resolved = False
            self.recovery_start_time = None
            self._not_still_count = 0
            if self.alert_start_time is None:
                self.alert_start_time = now
            self.alert_duration = now - self.alert_start_time

            if self.alert_duration >= threshold_seconds and not self.is_alerting:
                self.is_alerting = True
        else:
            self._not_still_count += 1

            if was_alerting:
                if recovery_seconds > 0:
                    if self.recovery_start_time is None:
                        self.recovery_start_time = now
                    if now - self.recovery_start_time >= recovery_seconds:
                        self.last_alert_duration = self.alert_duration
                        self.just_resolved = True
                        self._do_resolve(now)
                    else:
                        self.just_resolved = False
                        self.last_check_time = now
                        return self.is_alerting
                elif self._not_still_count >= reset_frames:
                    self.last_alert_duration = self.alert_duration
                    self.just_resolved = True
                    self._do_resolve(now)
                else:
                    self.just_resolved = False
                    self.last_check_time = now
                    return self.is_alerting
            else:
                self.just_resolved = False
                if self._not_still_count >= reset_frames:
                    self._last_reset_from = self.alert_duration
                    self._last_reset_time = now
                    self.alert_start_time = None
                    self.alert_duration = 0.0
                    self.recovery_start_time = None
                    self._not_still_count = 0

        self.last_check_time = now
        return self.is_alerting

    def _do_resolve(self, now: float = None):
        """알림 → 정상 전환 처리"""
        if now is None:
            now = time.time()
        self._resolve_count += 1
        self._last_reset_from = self.alert_duration
        self._last_reset_time = now
        self.alert_start_time = None
        self.alert_duration = 0.0
        self.is_alerting = False
        self.recovery_start_time = None
        self._not_still_count = 0

    def reset(self):
        self.is_alerting = False
        self.alert_start_time = None
        self.alert_duration = 0.0
        self.just_resolved = False
        self.recovery_start_time = None
        self._not_still_count = 0
        self._last_reset_time = 0.0
        self._last_reset_from = 0.0
        self._resolve_count = 0
