"""
회귀 시나리오 테스트 — Detector + SignoffManager 통합 검증
numpy 합성 프레임을 직접 주입 (영상 파일/캡처 카드 불필요).

시나리오:
  S1. 블랙 감지 → 알람 발생 → 복구 전 사이클
  S2. 스틸 감지 → 알람 발생 → 복구 전 사이클
  S3. 정파 준비 진입 → still 지속 → 정파 전환
  S4. 정파 억제 — SIGNOFF 상태에서 스틸 AlarmTrigger 미발행 확인
  S5. 알람 중복 방지 — 이미 alerting 시 AlarmTrigger 재발행 없음
  S6. 블랙/스틸 동시 알람 — 단일 프레임에 두 알람 독립 발행

실행: python -m pytest tests/test_regression.py -v
      또는 python tests/test_regression.py
"""
import queue
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from core.roi_manager import ROI
from detection.detector import Detector
from detection.signoff_manager import SignoffManager, SignoffGroup, SignoffState


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _roi(label="V1", w=100, h=100, roi_type="video"):
    return ROI(label=label, media_name="test", x=0, y=0, w=w, h=h, roi_type=roi_type)


def _black(h=200, w=200):
    return np.zeros((h, w, 3), dtype=np.uint8)


def _bright(h=200, w=200, v=200):
    return np.full((h, w, 3), v, dtype=np.uint8)


def _noise(h=200, w=200, seed=0):
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, (h, w, 3), dtype=np.uint8)


def _group(group_id=1, still_trigger_sec=0.05, prep_minutes=0,
           start_time="23:30", end_time="06:00", end_next_day=True,
           weekdays=None) -> SignoffGroup:
    """테스트용 정파 그룹 — still_trigger_sec 짧게 설정."""
    if weekdays is None:
        weekdays = [0, 1, 2, 3, 4, 5, 6]
    return SignoffGroup(
        group_id=group_id,
        name="테스트그룹",
        enter_roi={"video_label": "V1"},
        suppressed_labels=["V1"],
        start_time=start_time,
        end_time=end_time,
        prep_minutes=prep_minutes,
        exit_prep_minutes=0,
        end_next_day=end_next_day,
        every_day=True,
        weekdays=weekdays,
        still_trigger_sec=still_trigger_sec,
        exit_trigger_sec=5.0,
    )


def _alarm_q():
    """프로세스 간 Queue 대신 인메모리 Queue 사용."""
    return queue.Queue(maxsize=200)


def _collect(q, type_filter=None):
    """Queue에서 모든 메시지 꺼내 리스트 반환. type_filter 지정 시 해당 타입만."""
    msgs = []
    while True:
        try:
            msg = q.get_nowait()
            if type_filter is None or isinstance(msg, type_filter):
                msgs.append(msg)
        except queue.Empty:
            break
    return msgs


# ── S1: 블랙 감지 전 사이클 ──────────────────────────────────────────────────

def test_s1_black_alarm_and_recovery():
    """블랙 프레임이 black_duration 이상 지속 → alerting=True; 밝은 프레임 복구 → alerting=False."""
    d = Detector()
    d.black_duration = 0.05   # 빠른 테스트
    d.still_detection_enabled = False
    roi = _roi()
    d.update_roi_list([roi])

    # 블랙 상태 누적
    deadline = time.time() + 0.15
    alerting = False
    while time.time() < deadline:
        r = d.detect_frame(_black(), [roi])
        alerting = r["V1"]["black_alerting"]
        if alerting:
            break
        time.sleep(0.005)
    assert alerting, "블랙 지속 후 alerting=True 미발생"

    # 밝은 프레임으로 복구 — still_reset_frames=3 기본값이므로 3회 주입
    for _ in range(5):
        r = d.detect_frame(_bright(), [roi])
    assert not r["V1"]["black_alerting"], "밝은 프레임 복구 후 alerting=True 잔류"
    print("S1 PASS: 블랙 알람 발생 및 복구")


# ── S2: 스틸 감지 전 사이클 ──────────────────────────────────────────────────

def test_s2_still_alarm_and_recovery():
    """동일 프레임 still_duration 이상 지속 → still_alerting=True; 노이즈 프레임 → False."""
    d = Detector()
    d.still_duration = 0.05
    d.black_detection_enabled = False
    roi = _roi()
    d.update_roi_list([roi])

    fixed = _bright()
    deadline = time.time() + 0.15
    alerting = False
    while time.time() < deadline:
        r = d.detect_frame(fixed, [roi])
        alerting = r["V1"].get("still_alerting", False)
        if alerting:
            break
        time.sleep(0.005)
    assert alerting, "스틸 지속 후 still_alerting=True 미발생"

    # 노이즈 프레임으로 복구 (still_reset_frames=3)
    for i in range(5):
        r = d.detect_frame(_noise(seed=i), [roi])
    assert not r["V1"]["still_alerting"], "노이즈 복구 후 still_alerting=True 잔류"
    print("S2 PASS: 스틸 알람 발생 및 복구")


# ── S3: 정파 전환 ─────────────────────────────────────────────────────────────

def test_s3_signoff_transition():
    """수동 cycle_state() → PREPARATION, still 지속 → SIGNOFF 전환.
    SignoffManager tick 주기 = 1s → 최대 2회 tick 대기 필요 → 데드라인 3.5s.
    """
    q = _alarm_q()
    sm = SignoffManager(result_queue=q)
    # still_trigger_sec=0.5: 첫 tick(1s)에서 start 설정, 두 번째 tick(2s)에서 elapsed>=0.5 확인
    sm.set_group(_group(still_trigger_sec=0.5))
    sm.start()

    # 수동으로 PREPARATION 진입
    sm.cycle_state(1)
    assert sm.get_state(1) == SignoffState.PREPARATION, "PREPARATION 전환 실패"

    # still=True 를 계속 주입 → still_trigger_sec 경과 후 SIGNOFF 전환
    # tick 2회(~2s) + 여유 1.5s = 3.5s
    deadline = time.time() + 3.5
    while time.time() < deadline:
        sm.update_detection({"V1": True})
        if sm.get_state(1) == SignoffState.SIGNOFF:
            break
        time.sleep(0.05)

    sm.stop()

    assert sm.get_state(1) == SignoffState.SIGNOFF, "SIGNOFF 전환 실패"

    # SignoffStateChange 이벤트 발행 확인
    from ipc.messages import SignoffStateChange
    changes = _collect(q, SignoffStateChange)
    new_states = [c.new_state for c in changes]
    assert "PREPARATION" in new_states, "PREPARATION SignoffStateChange 미발행"
    assert "SIGNOFF" in new_states, "SIGNOFF SignoffStateChange 미발행"
    print("S3 PASS: 정파 전환 (IDLE→PREPARATION→SIGNOFF)")


# ── S4: 정파 억제 ─────────────────────────────────────────────────────────────

def test_s4_signoff_suppression():
    """SIGNOFF 상태에서 스틸 알람은 AlarmTrigger가 result_queue에 삽입되지 않아야 한다."""
    from ipc.messages import AlarmTrigger
    from processes.detection_process import _process_alarms

    q = _alarm_q()
    sm = SignoffManager(result_queue=_alarm_q())  # signoff용 별도 큐
    sm.set_group(_group())
    sm.set_state_direct(1, "SIGNOFF")
    assert sm.get_state(1) == SignoffState.SIGNOFF

    # still_alerting=True인 결과 생성
    vid_results = {"V1": {
        "black": False, "still": True,
        "black_alerting": False, "still_alerting": True,
        "black_duration": 0.0, "still_duration": 5.0,
        "black_resolved": False, "black_last_duration": 0.0,
        "still_resolved": False, "still_last_duration": 0.0,
    }}
    prev_black = {}
    prev_still = {}
    prev_audio = {}

    d = Detector()

    _process_alarms(
        q, [0],
        vid_results, {}, False,
        prev_black, prev_still, prev_audio,
        sm, d, _DummyTelegram(), _DummyRecorder(),
        [_roi()], [], None,
    )

    triggers = _collect(q, AlarmTrigger)
    still_triggers = [t for t in triggers if t.detection_type == "still"]
    assert len(still_triggers) == 0, f"SIGNOFF 억제 실패: {len(still_triggers)}건 AlarmTrigger 발행"
    print("S4 PASS: 정파 억제 (SIGNOFF 상태 스틸 AlarmTrigger 차단)")


# ── S5: 알람 중복 방지 ────────────────────────────────────────────────────────

def test_s5_no_duplicate_alarm():
    """already alerting 상태에서 _process_alarms 재호출 시 AlarmTrigger 중복 발행 없음."""
    from ipc.messages import AlarmTrigger
    from processes.detection_process import _process_alarms

    q = _alarm_q()
    sm = SignoffManager(result_queue=_alarm_q())
    d = Detector()

    vid_results = {"V1": {
        "black": True, "still": False,
        "black_alerting": True, "still_alerting": False,
        "black_duration": 15.0, "still_duration": 0.0,
        "black_resolved": False, "black_last_duration": 0.0,
        "still_resolved": False, "still_last_duration": 0.0,
    }}

    prev_black = {}
    prev_still = {}
    prev_audio = {}

    # 1회 호출 → AlarmTrigger 1건
    _process_alarms(q, [0], vid_results, {}, False,
                    prev_black, prev_still, prev_audio,
                    sm, d, _DummyTelegram(), _DummyRecorder(),
                    [_roi()], [], None)
    first = _collect(q, AlarmTrigger)
    assert len(first) == 1, f"첫 호출: AlarmTrigger {len(first)}건 (기대: 1건)"

    # 2회 이상 호출 → 추가 AlarmTrigger 없음
    for _ in range(3):
        _process_alarms(q, [0], vid_results, {}, False,
                        prev_black, prev_still, prev_audio,
                        sm, d, _DummyTelegram(), _DummyRecorder(),
                        [_roi()], [], None)
    dup = _collect(q, AlarmTrigger)
    assert len(dup) == 0, f"중복 AlarmTrigger {len(dup)}건 발행"
    print("S5 PASS: AlarmTrigger 중복 방지")


# ── S6: 블랙/스틸 동시 알람 ──────────────────────────────────────────────────

def test_s6_black_and_still_simultaneous():
    """블랙/스틸 동시 알람 — 각 AlarmTrigger 독립 발행."""
    from ipc.messages import AlarmTrigger
    from processes.detection_process import _process_alarms

    q = _alarm_q()
    sm = SignoffManager(result_queue=_alarm_q())
    d = Detector()

    vid_results = {"V1": {
        "black": True, "still": True,
        "black_alerting": True, "still_alerting": True,
        "black_duration": 15.0, "still_duration": 15.0,
        "black_resolved": False, "black_last_duration": 0.0,
        "still_resolved": False, "still_last_duration": 0.0,
    }}

    _process_alarms(q, [0], vid_results, {}, False,
                    {}, {}, {},
                    sm, d, _DummyTelegram(), _DummyRecorder(),
                    [_roi()], [], None)

    triggers = _collect(q, AlarmTrigger)
    types = {t.detection_type for t in triggers}
    assert "black" in types, "블랙 AlarmTrigger 미발행"
    assert "still" in types, "스틸 AlarmTrigger 미발행"
    assert len(triggers) == 2, f"AlarmTrigger {len(triggers)}건 (기대: 2건)"
    print("S6 PASS: 블랙/스틸 동시 AlarmTrigger 독립 발행")


# ── 더미 객체 ─────────────────────────────────────────────────────────────────

class _DummyTelegram:
    def notify(self, *a, **kw): pass


class _DummyRecorder:
    def trigger(self, *a, **kw): pass


# ── 러너 ─────────────────────────────────────────────────────────────────────

def _run_all():
    tests = [
        test_s1_black_alarm_and_recovery,
        test_s2_still_alarm_and_recovery,
        test_s3_signoff_transition,
        test_s4_signoff_suppression,
        test_s5_no_duplicate_alarm,
        test_s6_black_and_still_simultaneous,
    ]
    passed = failed = 0
    for fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"FAIL {fn.__name__}: {e}")
            import traceback; traceback.print_exc()
            failed += 1
    print(f"\n결과: {passed}/{passed + failed} PASS")
    return failed == 0


if __name__ == "__main__":
    ok = _run_all()
    sys.exit(0 if ok else 1)
