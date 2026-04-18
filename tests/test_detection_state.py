"""
DetectionState 단위 테스트
still_reset_frames 카운터, audio_level_recovery_seconds, 히스테리시스 검증.
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detection.detection_state import DetectionState
from core.roi_manager import ROI


def _make_roi(label="V1"):
    return ROI(label=label, media_name="test", x=0, y=0, w=100, h=100)


# ── 기본 알람 발생 ────────────────────────────────────────────────────────────

def test_alert_fires_after_threshold():
    """이상 상태가 threshold_seconds 이상 지속 시 alerting=True."""
    state = DetectionState(_make_roi())
    # threshold 0.05초 — 3회 업데이트로 충분
    for _ in range(5):
        state.update(True, threshold_seconds=0.0)
    assert state.is_alerting


def test_no_alert_below_threshold():
    """짧은 이상 후 정상 복귀 시 alerting=False."""
    state = DetectionState(_make_roi())
    state.update(True, threshold_seconds=10.0)   # 10초 기준 → 미달
    assert not state.is_alerting


# ── 히스테리시스 (reset_frames) ───────────────────────────────────────────────

def test_still_reset_frames_prevents_premature_reset():
    """reset_frames=3 일 때 정상 프레임 2개로는 타이머 리셋 안 됨."""
    state = DetectionState(_make_roi())
    # 알람 발생
    for _ in range(10):
        state.update(True, threshold_seconds=0.0)
    assert state.is_alerting

    # 정상 프레임 2개 — 히스테리시스 미충족
    state.update(False, threshold_seconds=0.0, reset_frames=3)
    state.update(False, threshold_seconds=0.0, reset_frames=3)
    assert state.is_alerting, "2프레임 정상으로 경보 해제되면 안 됨"


def test_still_reset_frames_resolves_after_enough():
    """reset_frames=3 충족 시 경보 해제."""
    state = DetectionState(_make_roi())
    for _ in range(10):
        state.update(True, threshold_seconds=0.0)
    assert state.is_alerting

    for _ in range(3):
        state.update(False, threshold_seconds=0.0, reset_frames=3)
    assert not state.is_alerting
    assert state.just_resolved


def test_timer_reset_requires_reset_frames():
    """비경보 상태에서도 reset_frames 미충족 시 타이머 유지."""
    state = DetectionState(_make_roi())
    # 이상 시작 (알람 미발생)
    state.update(True, threshold_seconds=100.0, reset_frames=3)
    assert state.alert_start_time is not None

    # 정상 1프레임 — 타이머 유지
    state.update(False, threshold_seconds=100.0, reset_frames=3)
    assert state.alert_start_time is not None, "1프레임 정상으로 타이머 리셋되면 안 됨"

    # 정상 3프레임 — 타이머 리셋
    for _ in range(3):
        state.update(False, threshold_seconds=100.0, reset_frames=3)
    assert state.alert_start_time is None


# ── recovery_seconds ──────────────────────────────────────────────────────────

def test_recovery_seconds_delays_resolve():
    """recovery_seconds > 0 일 때 짧은 정상 구간으로 해제 안 됨."""
    state = DetectionState(_make_roi())
    for _ in range(10):
        state.update(True, threshold_seconds=0.0)
    assert state.is_alerting

    # 정상 1회 — recovery_seconds=60 미충족
    state.update(False, threshold_seconds=0.0, recovery_seconds=60.0)
    assert state.is_alerting, "recovery_seconds 미충족 → 경보 유지"
    assert not state.just_resolved


def test_recovery_seconds_resolves_after_delay():
    """recovery_seconds 충족 후 해제."""
    state = DetectionState(_make_roi())
    for _ in range(10):
        state.update(True, threshold_seconds=0.0)
    assert state.is_alerting

    # recovery_seconds=0 으로 즉시 해제 가능 여부 확인 (reset_frames=1 기본)
    state.update(False, threshold_seconds=0.0, recovery_seconds=0.0, reset_frames=1)
    assert not state.is_alerting
    assert state.just_resolved


# ── _do_resolve 후 상태 초기화 ────────────────────────────────────────────────

def test_reset_clears_all_state():
    """reset() 호출 후 모든 상태 초기화."""
    state = DetectionState(_make_roi())
    for _ in range(10):
        state.update(True, threshold_seconds=0.0)
    state.reset()

    assert not state.is_alerting
    assert state.alert_start_time is None
    assert state.alert_duration == 0.0
    assert state._not_still_count == 0
    assert state._resolve_count == 0


def test_last_alert_duration_preserved_after_resolve():
    """해제 시 last_alert_duration에 이전 지속 시간 보존."""
    state = DetectionState(_make_roi())
    for _ in range(10):
        state.update(True, threshold_seconds=0.0)
    dur = state.alert_duration
    assert dur > 0

    state.update(False, threshold_seconds=0.0, reset_frames=1)
    assert state.last_alert_duration == dur


# ── 직접 실행 지원 ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_alert_fires_after_threshold,
        test_no_alert_below_threshold,
        test_still_reset_frames_prevents_premature_reset,
        test_still_reset_frames_resolves_after_enough,
        test_timer_reset_requires_reset_frames,
        test_recovery_seconds_delays_resolve,
        test_recovery_seconds_resolves_after_delay,
        test_reset_clears_all_state,
        test_last_alert_duration_preserved_after_resolve,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}  {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {t.__name__}  {e}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    sys.exit(0 if failed == 0 else 1)
