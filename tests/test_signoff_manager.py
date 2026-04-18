"""
SignoffManager 단위 테스트
IDLE↔PREPARATION↔SIGNOFF 전환, 히스테리시스, 타이머 리셋 검증.
"""
import sys
import os
import time
import queue

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detection.signoff_manager import SignoffManager, SignoffState, SignoffGroup


def _make_manager():
    q = queue.Queue(maxsize=200)
    mgr = SignoffManager(result_queue=q)
    return mgr, q


def _make_group(gid=1, start="03:00", end="05:00", prep=30,
                every_day=True, enter_label="V1",
                exit_prep=0, exit_trigger=5.0):
    return SignoffGroup(
        group_id=gid,
        name=f"Group{gid}",
        enter_roi={"video_label": enter_label},
        suppressed_labels=[enter_label],
        start_time=start,
        end_time=end,
        prep_minutes=prep,
        exit_prep_minutes=exit_prep,
        end_next_day=False,
        every_day=every_day,
        weekdays=list(range(7)),
        still_trigger_sec=5.0,
        exit_trigger_sec=exit_trigger,
    )


# ── 수동 전환 ─────────────────────────────────────────────────────────────────

def test_cycle_state_idle_to_prep():
    """IDLE → cycle_state → PREPARATION."""
    mgr, _ = _make_manager()
    mgr.set_group(_make_group())
    assert mgr.get_state(1) == SignoffState.IDLE
    mgr.cycle_state(1)
    assert mgr.get_state(1) == SignoffState.PREPARATION


def test_cycle_state_prep_to_idle_outside_window():
    """정파 시간 범위 밖 PREPARATION → cycle_state → IDLE."""
    mgr, _ = _make_manager()
    # 현재 시각이 절대 들어가지 않는 시간대 (00:00 ~ 00:01)
    grp = _make_group(start="00:00", end="00:01", prep=0, every_day=True)
    mgr.set_group(grp)
    mgr.cycle_state(1)   # PREPARATION
    assert mgr.get_state(1) == SignoffState.PREPARATION
    mgr.cycle_state(1)   # → IDLE (정파 시간 아님)
    assert mgr.get_state(1) == SignoffState.IDLE


def test_cycle_state_signoff_to_idle():
    """수동으로 SIGNOFF → cycle_state → IDLE."""
    mgr, _ = _make_manager()
    mgr.set_group(_make_group())
    # set_state_direct로 강제 SIGNOFF
    mgr.set_group(_make_group())
    mgr.set_state_direct(1, "SIGNOFF")
    assert mgr.get_state(1) == SignoffState.SIGNOFF
    mgr.cycle_state(1)
    assert mgr.get_state(1) == SignoffState.IDLE


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
    # enter 타이머 설정
    mgr._video_enter_start[1] = time.time()
    mgr._video_enter_not_still[1] = 2

    mgr.set_state_direct(1, "IDLE")
    # _transition_to에서 _reset_enter_timers 호출
    assert mgr._video_enter_start[1] is None
    assert mgr._video_enter_not_still[1] == 0


def test_signoff_resets_exit_timers():
    """SIGNOFF 진입 시 exit_timer 초기화."""
    mgr, _ = _make_manager()
    mgr.set_group(_make_group())
    # exit 타이머 임의 설정
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


# ── 직접 실행 지원 ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_cycle_state_idle_to_prep,
        test_cycle_state_prep_to_idle_outside_window,
        test_cycle_state_signoff_to_idle,
        test_set_state_direct_all_transitions,
        test_set_state_direct_invalid_ignored,
        test_idle_resets_enter_timers,
        test_signoff_resets_exit_timers,
        test_is_signoff_label_blocks_suppressed,
        test_is_signoff_label_not_blocked_in_prep,
        test_is_prep_label_blocks_in_prep,
        test_transition_emits_signoff_state_change,
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
