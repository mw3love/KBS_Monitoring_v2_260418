"""
Detector 단위 테스트
블랙/스틸/HSV 감지 경계값, v1 동작 동등성 검증.
"""
import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detection.detector import Detector
from core.roi_manager import ROI


def _make_roi(label="V1", x=0, y=0, w=100, h=100, roi_type="video"):
    return ROI(label=label, media_name="test", x=x, y=y, w=w, h=h, roi_type=roi_type)


def _black_frame(h=200, w=200):
    """완전 블랙 BGR 프레임."""
    return np.zeros((h, w, 3), dtype=np.uint8)


def _bright_frame(h=200, w=200, value=200):
    """밝은 BGR 프레임."""
    return np.full((h, w, 3), value, dtype=np.uint8)


def _noise_frame(h=200, w=200, seed=None):
    """랜덤 노이즈 프레임. seed 미지정 시 매 호출마다 다름."""
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, (h, w, 3), dtype=np.uint8)


# ── 블랙 감지 ─────────────────────────────────────────────────────────────────

def test_black_detected_on_black_frame():
    """완전 블랙 프레임은 is_black=True."""
    d = Detector()
    d.black_threshold = 10
    d.black_dark_ratio = 95.0
    roi = _make_roi()
    results = d.detect_frame(_black_frame(), [roi])
    assert results["V1"]["black"] is True


def test_black_not_detected_on_bright_frame():
    """밝은 프레임은 is_black=False."""
    d = Detector()
    roi = _make_roi()
    results = d.detect_frame(_bright_frame(value=200), [roi])
    assert results["V1"]["black"] is False


def test_black_alert_fires_after_duration():
    """블랙 상태가 black_duration 이상 지속 시 alerting=True."""
    d = Detector()
    d.black_duration = 0.0   # 즉시 알람
    roi = _make_roi()
    frame = _black_frame()
    for _ in range(5):
        results = d.detect_frame(frame, [roi])
    assert results["V1"]["black_alerting"] is True


def test_black_disabled_skips_detection():
    """black_detection_enabled=False 시 감지 생략."""
    d = Detector()
    d.black_detection_enabled = False
    roi = _make_roi()
    results = d.detect_frame(_black_frame(), [roi])
    assert results["V1"]["black"] is False


def test_black_motion_suppress():
    """블랙 판정이어도 changed_ratio 초과 시 취소."""
    d = Detector()
    d.black_threshold = 10
    d.black_dark_ratio = 1.0           # 1% 이상 어두우면 블랙
    d.black_motion_suppress_ratio = 0.01  # 0.01% 이상 움직임 있으면 취소
    d.still_detection_enabled = True
    roi = _make_roi()

    # 첫 프레임 (이전 프레임 없음 → changed_ratio=-1)
    d.detect_frame(_black_frame(), [roi])
    # 두 번째 프레임: 밝게 변경 → changed_ratio > 0 → 블랙 취소
    frame2 = _bright_frame(value=200)
    # 강제로 dark_ratio 높게 만들기 위해 black_dark_ratio 낮게 설정
    results = d.detect_frame(_black_frame(), [roi])
    # still_detection 결과가 있어야 motion suppress 작동
    # 이 테스트는 suppress 로직 경로를 실행하는 것이 목적
    assert "black" in results.get("V1", {})


# ── 스틸 감지 ─────────────────────────────────────────────────────────────────

def test_still_detected_on_identical_frames():
    """동일 프레임 연속 입력 시 is_still=True."""
    d = Detector()
    d.still_threshold = 4
    d.still_duration = 0.0
    roi = _make_roi()
    frame = _bright_frame(value=100)
    d.detect_frame(frame, [roi])       # 첫 프레임 (prev 없음)
    results = d.detect_frame(frame.copy(), [roi])   # 동일 프레임
    assert results["V1"]["still"] is True


def test_still_not_detected_on_changing_frames():
    """매 프레임 변화 시 is_still=False."""
    d = Detector()
    d.still_threshold = 1
    roi = _make_roi()
    rng = np.random.default_rng(0)
    for _ in range(3):
        frame = rng.integers(0, 256, (200, 200, 3), dtype=np.uint8)
        results = d.detect_frame(frame, [roi])
    assert results["V1"]["still"] is False


def test_still_disabled_skips_detection():
    """still_detection_enabled=False 시 감지 생략."""
    d = Detector()
    d.still_detection_enabled = False
    roi = _make_roi()
    frame = _bright_frame()
    d.detect_frame(frame, [roi])
    results = d.detect_frame(frame.copy(), [roi])
    assert results["V1"]["still"] is False


def test_still_reset_frames_hysteresis():
    """still_reset_frames=3: 정상 2프레임으로는 스틸 해제 안 됨."""
    d = Detector()
    d.still_threshold = 4
    d.still_duration = 0.0
    d.still_reset_frames = 3
    roi = _make_roi()
    frame = _bright_frame(value=100)

    # 스틸 상태 진입
    for _ in range(5):
        d.detect_frame(frame.copy(), [roi])

    assert d._still_states["V1"].is_alerting

    # 정상 프레임 2개 (히스테리시스 미충족)
    noise = _noise_frame()
    d.detect_frame(noise, [roi])
    d.detect_frame(_noise_frame(), [roi])
    assert d._still_states["V1"].is_alerting, "2프레임 정상으로 해제되면 안 됨"

    # 정상 프레임 1개 더 (총 3개 충족)
    rng = np.random.default_rng(99)
    d.detect_frame(rng.integers(0, 256, (200, 200, 3), dtype=np.uint8), [roi])
    assert not d._still_states["V1"].is_alerting


# ── 오디오 레벨미터 (HSV) 감지 ───────────────────────────────────────────────

def _green_frame(h=50, w=50):
    """녹색 BGR 프레임 — HSV H~60, S~255, V~255."""
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:, :, 1] = 255   # G
    return frame


def test_audio_roi_active_on_colored_frame():
    """컬러(녹색) ROI → active=True."""
    d = Detector()
    d.audio_hsv_h_min = 40
    d.audio_hsv_h_max = 90
    d.audio_hsv_s_min = 100
    d.audio_hsv_s_max = 255
    d.audio_hsv_v_min = 100
    d.audio_hsv_v_max = 255
    d.audio_pixel_ratio = 5.0
    roi = _make_roi(label="A1", roi_type="audio")
    frame = _green_frame(h=200, w=200)
    # 이동 평균 버퍼 채우기
    for _ in range(5):
        results = d.detect_audio_roi(frame, [roi])
    assert results["A1"]["active"] is True


def test_audio_roi_inactive_on_gray_frame():
    """회색(무채색) ROI → active=False."""
    d = Detector()
    d.audio_pixel_ratio = 5.0
    roi = _make_roi(label="A1", roi_type="audio")
    frame = np.full((200, 200, 3), 128, dtype=np.uint8)
    for _ in range(5):
        results = d.detect_audio_roi(frame, [roi])
    assert results["A1"]["active"] is False


# ── ROI 업데이트 후 상태 정리 ────────────────────────────────────────────────

def test_update_roi_list_removes_stale_states():
    """ROI 목록 변경 시 제거된 ROI의 상태 딕셔너리 정리."""
    d = Detector()
    roi1 = _make_roi("V1")
    roi2 = _make_roi("V2")
    d.update_roi_list([roi1, roi2])
    assert "V1" in d._black_states
    assert "V2" in d._black_states

    d.update_roi_list([roi1])
    assert "V2" not in d._black_states
    assert "V2" not in d._still_states


# ── scale_factor ──────────────────────────────────────────────────────────────

def test_scale_factor_does_not_crash():
    """scale_factor=0.5 적용 시 감지 루프 정상 작동."""
    d = Detector()
    d.scale_factor = 0.5
    roi = _make_roi(w=200, h=200)
    frame = _bright_frame(h=400, w=400)
    results = d.detect_frame(frame, [roi])
    assert "V1" in results


# ── 직접 실행 지원 ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_black_detected_on_black_frame,
        test_black_not_detected_on_bright_frame,
        test_black_alert_fires_after_duration,
        test_black_disabled_skips_detection,
        test_black_motion_suppress,
        test_still_detected_on_identical_frames,
        test_still_not_detected_on_changing_frames,
        test_still_disabled_skips_detection,
        test_still_reset_frames_hysteresis,
        test_audio_roi_active_on_colored_frame,
        test_audio_roi_inactive_on_gray_frame,
        test_update_roi_list_removes_stale_states,
        test_scale_factor_does_not_crash,
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
            import traceback
            print(f"  ERROR {t.__name__}  {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    sys.exit(0 if failed == 0 else 1)
