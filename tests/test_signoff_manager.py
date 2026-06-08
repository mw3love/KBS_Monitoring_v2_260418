"""
SignoffManager 단위 테스트
IDLE↔PREPARATION↔SIGNOFF 전환, 히스테리시스, 타이머 리셋 검증.

스키마: prep_start_time / exit_prep_start_time / end_time (3 직접 시각).
진입은 스틸 자동감지 단독, 해제는 시간 기반(end_time 하드캡 + 해제준비 조기감지).
"""
import sys
import os
import time
import queue
import datetime as real_datetime
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detection.signoff_manager import SignoffManager, SignoffState, SignoffGroup


def _make_manager():
    q = queue.Queue(maxsize=200)
    mgr = SignoffManager(result_queue=q)
    return mgr, q


def _make_group(gid=1, prep_start="00:30", end="05:00", every_day=True,
                enter_label="V1", exit_prep_start="", still=5.0, exit_trigger=5.0):
    return SignoffGroup(
        group_id=gid,
        name=f"Group{gid}",
        enter_roi={"video_label": enter_label},
        suppressed_labels=[enter_label],
        prep_start_time=prep_start,
        exit_prep_start_time=exit_prep_start,
        end_time=end,
        every_day=every_day,
        weekdays=list(range(7)),
        still_trigger_sec=still,
        exit_trigger_sec=exit_trigger,
    )


def _drain(q):
    """큐에 쌓인 메시지를 모두 꺼내 리스트로 반환."""
    msgs = []
    while not q.empty():
        msgs.append(q.get_nowait())
    return msgs


# ── 수동 전환 ─────────────────────────────────────────────────────────────────

def test_cycle_state_idle_to_prep():
    """IDLE → cycle_state → PREPARATION."""
    mgr, _ = _make_manager()
    mgr.set_group(_make_group())
    assert mgr.get_state(1) == SignoffState.IDLE
    mgr.cycle_state(1)
    assert mgr.get_state(1) == SignoffState.PREPARATION


def test_cycle_state_prep_to_idle_outside_window():
    """정파준비 윈도우 밖 PREPARATION → cycle_state → IDLE."""
    mgr, _ = _make_manager()
    # 현재 시각이 절대 들어가지 않는 윈도우 (00:00 ~ 00:01)
    grp = _make_group(prep_start="00:00", end="00:01", every_day=True)
    mgr.set_group(grp)
    mgr.cycle_state(1)   # PREPARATION
    assert mgr.get_state(1) == SignoffState.PREPARATION
    mgr.cycle_state(1)   # → IDLE (정파준비 윈도우 아님)
    assert mgr.get_state(1) == SignoffState.IDLE


def test_cycle_state_signoff_to_idle():
    """수동으로 SIGNOFF → cycle_state → IDLE."""
    mgr, _ = _make_manager()
    mgr.set_group(_make_group())
    mgr.set_state_direct(1, "SIGNOFF")
    assert mgr.get_state(1) == SignoffState.SIGNOFF
    mgr.cycle_state(1)
    assert mgr.get_state(1) == SignoffState.IDLE


def test_manual_signoff_in_prep_window():
    """정파준비 윈도우 안이면 수동 클릭으로 즉시 SIGNOFF 진입 허용."""
    mgr, _ = _make_manager()
    grp = _make_group(prep_start="02:00", end="05:00", every_day=True)
    mgr.set_group(grp)
    mgr.set_state_direct(1, "PREPARATION")

    fake_now = real_datetime.datetime(2026, 5, 13, 2, 30, 0)  # prep_window 내
    with patch("detection.signoff_manager.datetime") as mock_dt:
        mock_dt.datetime.now.return_value = fake_now
        mock_dt.timedelta = real_datetime.timedelta
        mgr.cycle_state(1)

    assert mgr.get_state(1) == SignoffState.SIGNOFF, "prep 윈도우 내 수동 SIGNOFF 실패"


# ── set_state_direct ──────────────────────────────────────────────────────────

def test_set_state_direct_all_transitions():
    """set_state_direct로 3가지 상태 직접 전환."""
    mgr, _ = _make_manager()
    mgr.set_group(_make_group())
    for state_str in ("PREPARATION", "SIGNOFF", "IDLE"):
        mgr.set_state_direct(1, state_str)
        assert mgr.get_state(1) == SignoffState(state_str)


def test_set_state_direct_invalid_ignored():
    """잘못된 state_str은 무시."""
    mgr, _ = _make_manager()
    mgr.set_group(_make_group())
    mgr.set_state_direct(1, "INVALID")
    assert mgr.get_state(1) == SignoffState.IDLE


# ── 타이머 초기화 원칙 검증 ───────────────────────────────────────────────────

def test_idle_resets_enter_timers():
    """IDLE 진입 시 enter_timer 초기화."""
    mgr, _ = _make_manager()
    mgr.set_group(_make_group())
    mgr.set_state_direct(1, "PREPARATION")
    mgr._video_enter_start[1] = time.time()
    mgr._video_enter_not_still[1] = 2

    mgr.set_state_direct(1, "IDLE")
    assert mgr._video_enter_start[1] is None
    assert mgr._video_enter_not_still[1] == 0


def test_signoff_resets_exit_timers():
    """SIGNOFF 진입 시 exit_timer 초기화."""
    mgr, _ = _make_manager()
    mgr.set_group(_make_group())
    mgr._video_exit_start[1] = time.time()
    mgr._video_exit_still[1] = 5

    mgr.set_state_direct(1, "SIGNOFF")
    assert mgr._video_exit_start[1] is None
    assert mgr._video_exit_still[1] == 0


# ── 알림 차단 ─────────────────────────────────────────────────────────────────

def test_is_signoff_label_blocks_suppressed():
    """SIGNOFF 중 suppressed_labels 포함 label은 차단."""
    mgr, _ = _make_manager()
    grp = _make_group(enter_label="V1")
    grp.suppressed_labels = ["V1", "A1"]
    mgr.set_group(grp)
    mgr.set_state_direct(1, "SIGNOFF")
    assert mgr.is_signoff_label("V1")
    assert mgr.is_signoff_label("A1")
    assert not mgr.is_signoff_label("V2")


def test_is_signoff_label_not_blocked_in_prep():
    """PREPARATION 상태에서는 is_signoff_label False."""
    mgr, _ = _make_manager()
    mgr.set_group(_make_group(enter_label="V1"))
    mgr.set_state_direct(1, "PREPARATION")
    assert not mgr.is_signoff_label("V1")


def test_is_prep_label_blocks_in_prep():
    """PREPARATION 상태에서 is_prep_label True."""
    mgr, _ = _make_manager()
    mgr.set_group(_make_group(enter_label="V1"))
    mgr.set_state_direct(1, "PREPARATION")
    assert mgr.is_prep_label("V1")


# ── SignoffStateChange 메시지 발행 ─────────────────────────────────────────────

def test_transition_emits_signoff_state_change():
    """상태 전환 시 result_queue에 SignoffStateChange 발행."""
    from ipc.messages import SignoffStateChange
    mgr, q = _make_manager()
    mgr.set_group(_make_group())
    mgr.set_state_direct(1, "PREPARATION")

    msgs = []
    while not q.empty():
        msgs.append(q.get_nowait())

    state_changes = [m for m in msgs if isinstance(m, SignoffStateChange)]
    assert len(state_changes) >= 1
    assert state_changes[0].new_state == "PREPARATION"
    assert state_changes[0].group_id == 1


# ── 진입 = 감지 단독 ──────────────────────────────────────────────────────────

def test_idle_enters_prep_in_window_no_still():
    """정파준비 윈도우 진입 시 PREPARATION으로만 가고, 스틸 없으면 SIGNOFF 안 됨."""
    mgr, _ = _make_manager()
    grp = _make_group(prep_start="03:00", end="05:00", every_day=True)
    mgr.set_group(grp)
    mgr._latest_video["V1"] = False   # 비스틸 (정파 아님)

    fake_now = real_datetime.datetime(2026, 5, 13, 3, 30, 0)
    with patch("detection.signoff_manager.datetime") as mock_dt:
        mock_dt.datetime.now.return_value = fake_now
        mock_dt.timedelta = real_datetime.timedelta
        mgr._tick_impl()   # IDLE → PREPARATION
        mgr._tick_impl()   # 비스틸 → SIGNOFF 진입 없음

    assert mgr.get_state(1) == SignoffState.PREPARATION, "시간만으로 SIGNOFF 진입함"


def test_still_detect_enters_signoff():
    """PREPARATION에서 스틸 지속 시 SIGNOFF 전환 (source='auto-detect')."""
    from ipc.messages import SignoffStateChange
    mgr, q = _make_manager()
    grp = _make_group(prep_start="02:30", end="05:00", every_day=True, still=5.0)
    mgr.set_group(grp)
    mgr.set_state_direct(1, "PREPARATION")
    while not q.empty():
        q.get_nowait()
    # still_trigger_sec=5.0 → 10초 전부터 스틸로 설정
    mgr._latest_video["V1"] = True
    mgr._video_enter_start[1] = time.time() - 10.0

    fake_now = real_datetime.datetime(2026, 5, 13, 3, 0, 0)  # prep_window 내
    with patch("detection.signoff_manager.datetime") as mock_dt:
        mock_dt.datetime.now.return_value = fake_now
        mock_dt.timedelta = real_datetime.timedelta
        mgr._tick_impl()

    assert mgr.get_state(1) == SignoffState.SIGNOFF
    msgs = []
    while not q.empty():
        msgs.append(q.get_nowait())
    sc = [m for m in msgs if isinstance(m, SignoffStateChange)]
    assert any(m.new_state == "SIGNOFF" and m.source == "auto-detect" for m in sc), \
        f"스틸 감지 진입 source 불일치: {[(m.new_state, m.source) for m in sc]}"


# ── 해제 = 시간 기반 ──────────────────────────────────────────────────────────

def test_signoff_auto_release_at_end_time():
    """SIGNOFF 진입 후 end_time 도달(prep_window 이탈) 시 자동 IDLE 전환."""
    from ipc.messages import SignoffStateChange
    mgr, q = _make_manager()
    grp = _make_group(prep_start="02:30", end="05:00", every_day=True)
    mgr.set_group(grp)
    mgr.set_state_direct(1, "SIGNOFF")
    assert mgr.get_state(1) == SignoffState.SIGNOFF

    fake_now = real_datetime.datetime(2026, 5, 13, 5, 1, 0)  # end_time 이후
    with patch("detection.signoff_manager.datetime") as mock_dt:
        mock_dt.datetime.now.return_value = fake_now
        mock_dt.timedelta = real_datetime.timedelta
        mgr._tick_impl()

    assert mgr.get_state(1) == SignoffState.IDLE
    msgs = []
    while not q.empty():
        msgs.append(q.get_nowait())
    sc = [m for m in msgs if isinstance(m, SignoffStateChange)]
    assert any(m.new_state == "IDLE" and m.source == "auto-time" for m in sc), \
        f"SIGNOFF→IDLE source 불일치: {[(m.new_state, m.source) for m in sc]}"


def test_exit_prep_early_release():
    """해제준비 구간에서 비스틸 감지 시 end_time 전 조기 해제 (auto-detect)."""
    from ipc.messages import SignoffStateChange
    mgr, q = _make_manager()
    grp = _make_group(prep_start="00:30", end="05:00", exit_prep_start="04:30",
                      every_day=True, exit_trigger=5.0)
    mgr.set_group(grp)
    mgr.set_state_direct(1, "SIGNOFF")
    while not q.empty():
        q.get_nowait()
    # 비스틸이 exit_trigger_sec(5s) 이상 지속된 상태로 셋업
    mgr._latest_video["V1"] = False
    mgr._video_exit_start[1] = time.time() - 10.0

    fake_now = real_datetime.datetime(2026, 5, 13, 4, 45, 0)  # 해제준비 윈도우(04:30~05:00) 내
    with patch("detection.signoff_manager.datetime") as mock_dt:
        mock_dt.datetime.now.return_value = fake_now
        mock_dt.timedelta = real_datetime.timedelta
        mgr._tick_impl()

    assert mgr.get_state(1) == SignoffState.IDLE
    msgs = []
    while not q.empty():
        msgs.append(q.get_nowait())
    sc = [m for m in msgs if isinstance(m, SignoffStateChange)]
    assert any(m.new_state == "IDLE" and m.source == "auto-detect" for m in sc), \
        f"조기 해제 source 불일치: {[(m.new_state, m.source) for m in sc]}"


def test_exit_prep_disabled_reverts_to_prep():
    """해제준비 미사용('') 그룹도 비스틸 지속 시 PREPARATION 조기복귀.

    예전 동작: 해제준비 미사용이면 end_time까지 SIGNOFF 유지.
    조기복귀 도입 후: 해제준비 윈도우가 없으니 end_time 전 내내 복귀검사 적용
    → 비스틸 시 PREPARATION 복귀(진짜 해제는 여전히 end_time 하드캡).
    """
    from ipc.messages import SignoffStateChange
    mgr, q = _make_manager()
    grp = _make_group(prep_start="00:30", end="05:00", exit_prep_start="",
                      every_day=True, exit_trigger=5.0)
    mgr.set_group(grp)
    mgr.set_state_direct(1, "SIGNOFF")
    while not q.empty():
        q.get_nowait()
    mgr._latest_video["V1"] = False
    mgr._video_exit_start[1] = time.time() - 10.0

    fake_now = real_datetime.datetime(2026, 5, 13, 4, 45, 0)  # prep_window 내, end 전
    with patch("detection.signoff_manager.datetime") as mock_dt:
        mock_dt.datetime.now.return_value = fake_now
        mock_dt.timedelta = real_datetime.timedelta
        mgr._tick_impl()

    assert mgr.get_state(1) == SignoffState.PREPARATION, "해제준비 미사용 그룹 조기복귀 실패"
    sc = [m for m in _drain(q) if isinstance(m, SignoffStateChange)]
    assert any(m.new_state == "PREPARATION" and m.source == "auto-revert" for m in sc)


# ── 조기복귀 (Early-Revert): 해제준비 시각 전 오감지 SIGNOFF 복귀 ──────────────

def test_signoff_reverts_to_prep_before_exit_prep():
    """해제준비 시각(04:30) 전 SIGNOFF 중 비스틸 지속 → PREPARATION 조기복귀 (auto-revert)."""
    from ipc.messages import SignoffStateChange
    mgr, q = _make_manager()
    grp = _make_group(prep_start="00:30", end="05:00", exit_prep_start="04:30",
                      every_day=True, exit_trigger=5.0)
    mgr.set_group(grp)
    mgr.set_state_direct(1, "SIGNOFF")
    while not q.empty():
        q.get_nowait()
    mgr._latest_video["V1"] = False           # 화면 다시 움직임(가짜 정파였음)
    mgr._video_exit_start[1] = time.time() - 10.0   # 비스틸 10s 지속

    fake_now = real_datetime.datetime(2026, 5, 13, 2, 0, 0)  # 해제준비(04:30) 전, prep_window 내
    with patch("detection.signoff_manager.datetime") as mock_dt:
        mock_dt.datetime.now.return_value = fake_now
        mock_dt.timedelta = real_datetime.timedelta
        mgr._tick_impl()

    assert mgr.get_state(1) == SignoffState.PREPARATION, "조기복귀 실패"
    sc = [m for m in _drain(q) if isinstance(m, SignoffStateChange)]
    assert any(m.new_state == "PREPARATION" and m.source == "auto-revert" for m in sc), \
        f"조기복귀 source 불일치: {[(m.new_state, m.source) for m in sc]}"


def test_signoff_still_no_revert_before_exit_prep():
    """SIGNOFF 중 계속 스틸이면(진짜 정파) 해제준비 전이라도 조기복귀하지 않음."""
    mgr, _ = _make_manager()
    grp = _make_group(prep_start="00:30", end="05:00", exit_prep_start="04:30",
                      every_day=True, exit_trigger=5.0)
    mgr.set_group(grp)
    mgr.set_state_direct(1, "SIGNOFF")
    mgr._latest_video["V1"] = True            # 스틸 유지(진짜 정파)

    fake_now = real_datetime.datetime(2026, 5, 13, 2, 0, 0)
    with patch("detection.signoff_manager.datetime") as mock_dt:
        mock_dt.datetime.now.return_value = fake_now
        mock_dt.timedelta = real_datetime.timedelta
        mgr._tick_impl()
        mgr._tick_impl()

    assert mgr.get_state(1) == SignoffState.SIGNOFF, "스틸 유지인데 조기복귀됨"


def test_auto_off_signoff_no_revert():
    """auto OFF(완전 수동) 시 SIGNOFF는 비스틸이어도 조기복귀하지 않음(수동 동결)."""
    mgr, _ = _make_manager()
    mgr._auto_preparation = False
    grp = _make_group(prep_start="00:30", end="05:00", exit_prep_start="04:30",
                      every_day=True, exit_trigger=5.0)
    mgr.set_group(grp)
    mgr.set_state_direct(1, "SIGNOFF")
    mgr._latest_video["V1"] = False
    mgr._video_exit_start[1] = time.time() - 10.0

    fake_now = real_datetime.datetime(2026, 5, 13, 2, 0, 0)  # 해제준비 전
    with patch("detection.signoff_manager.datetime") as mock_dt:
        mock_dt.datetime.now.return_value = fake_now
        mock_dt.timedelta = real_datetime.timedelta
        mgr._tick_impl()

    assert mgr.get_state(1) == SignoffState.SIGNOFF, "auto OFF인데 조기복귀됨"


# ── auto_preparation OFF = 완전 수동 모드 (W11) ───────────────────────────────

def test_auto_off_signoff_persists_at_end_time():
    """auto OFF 시 수동 SIGNOFF는 end_time(prep_window 이탈)에도 자동 강등되지 않음."""
    mgr, _ = _make_manager()
    mgr._auto_preparation = False
    grp = _make_group(prep_start="02:30", end="05:00", every_day=True)
    mgr.set_group(grp)
    mgr.set_state_direct(1, "SIGNOFF")
    assert mgr.get_state(1) == SignoffState.SIGNOFF

    fake_now = real_datetime.datetime(2026, 5, 13, 5, 1, 0)  # prep_window 완전 이탈
    with patch("detection.signoff_manager.datetime") as mock_dt:
        mock_dt.datetime.now.return_value = fake_now
        mock_dt.timedelta = real_datetime.timedelta
        mgr._tick_impl()

    assert mgr.get_state(1) == SignoffState.SIGNOFF, "auto OFF인데 자동 강등됨"


def test_auto_off_preparation_persists_outside_window():
    """auto OFF 시 수동 PREPARATION은 윈도우 밖에서도 자동 강등되지 않음."""
    mgr, _ = _make_manager()
    mgr._auto_preparation = False
    grp = _make_group(prep_start="02:30", end="05:00", every_day=True)
    mgr.set_group(grp)
    mgr.set_state_direct(1, "PREPARATION")
    assert mgr.get_state(1) == SignoffState.PREPARATION

    fake_now = real_datetime.datetime(2026, 5, 13, 12, 0, 0)  # prep_window 밖
    with patch("detection.signoff_manager.datetime") as mock_dt:
        mock_dt.datetime.now.return_value = fake_now
        mock_dt.timedelta = real_datetime.timedelta
        mgr._tick_impl()

    assert mgr.get_state(1) == SignoffState.PREPARATION, "auto OFF인데 자동 강등됨"


# ── from_dict 스키마 검증 ─────────────────────────────────────────────────────

def test_from_dict_defaults_and_validation():
    """잘못된 시각/빈 exit_prep 처리."""
    g = SignoffGroup.from_dict({
        "name": "1TV",
        "enter_roi": {"video_label": "V1"},
        "prep_start_time": "99:99",       # 잘못된 값 → 기본값
        "exit_prep_start_time": "",       # 미사용
        "end_time": "05:00",
    }, 1)
    assert g.prep_start_time == "00:30"          # fallback
    assert g.exit_prep_start_time == ""          # 미사용 유지
    assert g.end_time == "05:00"


# ── 직접 실행 지원 ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_cycle_state_idle_to_prep,
        test_cycle_state_prep_to_idle_outside_window,
        test_cycle_state_signoff_to_idle,
        test_manual_signoff_in_prep_window,
        test_set_state_direct_all_transitions,
        test_set_state_direct_invalid_ignored,
        test_idle_resets_enter_timers,
        test_signoff_resets_exit_timers,
        test_is_signoff_label_blocks_suppressed,
        test_is_signoff_label_not_blocked_in_prep,
        test_is_prep_label_blocks_in_prep,
        test_transition_emits_signoff_state_change,
        test_idle_enters_prep_in_window_no_still,
        test_still_detect_enters_signoff,
        test_signoff_auto_release_at_end_time,
        test_exit_prep_early_release,
        test_exit_prep_disabled_reverts_to_prep,
        test_signoff_reverts_to_prep_before_exit_prep,
        test_signoff_still_no_revert_before_exit_prep,
        test_auto_off_signoff_no_revert,
        test_auto_off_signoff_persists_at_end_time,
        test_auto_off_preparation_persists_outside_window,
        test_from_dict_defaults_and_validation,
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
