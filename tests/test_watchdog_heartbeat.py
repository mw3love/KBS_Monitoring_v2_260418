"""
HeartbeatAgeTracker 단위 테스트
2026-09-15·2026-10-27: 윈도우 시간 동기화로 벽시계가 8초 앞으로 뛰자 Watchdog이
멀쩡한 Detection을 heartbeat stale로 오판해 kill했다 → 값 변화 + monotonic 경과로 판정.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processes.watchdog_process import HeartbeatAgeTracker, _HB_STALE_SEC


def _old_judgement(hb_wall, now_wall):
    """수정 전 방식: 적힌 시각과 현재 벽시계 비교."""
    return (now_wall - hb_wall) > _HB_STALE_SEC


def test_clock_jump_forward_no_false_stale():
    """Detection은 5초마다 정상 기록 중, 벽시계만 8초 앞으로 점프 → stale 아님."""
    t = HeartbeatAgeTracker()
    wall_offset = 1_000_000.0     # 벽시계 = monotonic + offset
    t.reset(wall_offset - 30, 0.0)  # 직전 세션의 묵은 값

    hb = None
    old_fooled = False
    for tick in range(1, 201):    # 0.5초 단위, 100초
        mono = tick * 0.5
        if mono == 46.5:          # 45초 기록 직후 점프 → 48초 검사에서 예전 방식 10.9초로 오판
            wall_offset += 7.9    # 10/27 02:21:11 실제 점프 크기
        wall = mono + wall_offset
        if mono % 5.0 == 0.0:     # Detection: 5초마다 time.time() 기록
            hb = wall
        if hb is not None and mono % 2.0 == 0.0:   # Watchdog: 2초마다 검사
            assert t.age(hb, mono) <= _HB_STALE_SEC
            old_fooled = old_fooled or _old_judgement(hb, wall)
    assert old_fooled             # 같은 시나리오에서 예전 방식은 오판했어야 한다


def test_old_method_was_fooled_by_jump():
    """같은 상황에서 예전 방식은 오판했음을 재현 (테스트 시나리오가 사고와 같은지 확인)."""
    hb_wall = 1000.0              # 마지막 기록
    now_wall = hb_wall + 4.2 + 7.9  # 4.2초 뒤 + 7.9초 점프 = 12.1초 (실제 로그 stale=12.1초)
    assert _old_judgement(hb_wall, now_wall)

    t = HeartbeatAgeTracker()
    t.reset(None, 0.0)
    t.age(hb_wall, 0.0)
    assert t.age(hb_wall, 4.2) <= _HB_STALE_SEC   # 실제 경과는 4.2초뿐


def test_real_stall_detected():
    """값이 더 이상 안 바뀌면 10초 넘은 시점에 stale."""
    t = HeartbeatAgeTracker()
    t.reset(500.0, 0.0)
    assert t.age(510.0, 5.0) == 0.0               # 새 값 → 경과 0
    assert t.age(510.0, 14.0) <= _HB_STALE_SEC
    assert t.age(510.0, 15.5) > _HB_STALE_SEC     # 10.5초 무변화


def test_new_detection_never_writes_is_stale_after_grace():
    """재spawn 후 새 Detection이 한 번도 안 쓰면 묵은 값 그대로 → spawn 기준으로 stale."""
    t = HeartbeatAgeTracker()
    t.reset(777.0, 100.0)                         # spawn 시점 파일 값
    assert t.age(777.0, 115.0) > _HB_STALE_SEC    # grace(15초) 지나 첫 검사에서 바로 잡힘


def test_clock_jump_backward_still_detects_stall():
    """벽시계가 뒤로 가도(값이 작아져도) '변화'로 보고, 그 뒤 멈추면 잡는다."""
    t = HeartbeatAgeTracker()
    t.reset(1000.0, 0.0)
    assert t.age(992.0, 3.0) == 0.0
    assert t.age(992.0, 14.0) > _HB_STALE_SEC
