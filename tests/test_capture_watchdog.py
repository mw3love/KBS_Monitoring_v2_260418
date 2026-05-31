"""
CaptureLossWatchdog 단위 테스트
캡처 입력 상실(화면 전체 frozen-black) → 자동 재오픈 복구 상태기계 검증.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detection.capture_watchdog import (
    CaptureLossWatchdog, NORMAL, RECOVERING, ESCALATED, COOLDOWN,
)


def _kinds(actions):
    return [a[0] for a in actions]


def _new(**kw):
    base = dict(trigger_sec=8.0, observe_sec=5.0, max_attempts=3, cooldown_sec=60.0)
    base.update(kw)
    return CaptureLossWatchdog(**base)


# ── 트리거 ────────────────────────────────────────────────────────────────────

def test_no_trigger_before_duration():
    """frozen-black 이 trigger_sec 미만이면 재오픈하지 않음."""
    w = _new()
    assert _kinds(w.update(0.0, True, True, False)) == []      # loss 시작
    assert _kinds(w.update(7.9, True, True, False)) == []      # 아직 8초 미만
    assert w.state == NORMAL


def test_trigger_after_duration():
    """frozen-black 이 trigger_sec 이상 지속 → reconnect + telegram 발행."""
    w = _new()
    w.update(0.0, True, True, False)
    acts = w.update(8.0, True, True, False)
    assert "reconnect" in _kinds(acts)
    assert "telegram" in _kinds(acts)
    assert w.state == RECOVERING
    assert w.attempts == 1


def test_live_black_never_triggers():
    """블랙이지만 frozen=False(살아있는 노이즈 검정)는 트리거 안 됨."""
    w = _new()
    for tick in range(0, 30):
        acts = w.update(float(tick), True, False, False)  # black=True, frozen=False
        assert acts == []
    assert w.state == NORMAL


def test_intermittent_frozen_resets_timer():
    """중간에 frozen 풀리면 누적 타이머 리셋 → 트리거 안 됨."""
    w = _new()
    w.update(0.0, True, True, False)
    w.update(5.0, False, False, False)   # 블랙 해제 → loss_since 리셋
    assert _kinds(w.update(9.0, True, True, False)) == []  # 다시 시작이라 미달
    assert w.state == NORMAL


# ── 복구 / 재시도 / 에스컬레이션 ──────────────────────────────────────────────

def test_recovery_within_observe():
    """재오픈 후 관찰창 내 비블랙 복귀 → 복구완료 + COOLDOWN."""
    w = _new()
    w.update(0.0, True, True, False)
    w.update(8.0, True, True, False)              # RECOVERING, attempt 1
    acts = w.update(9.0, False, False, False)     # 복구!
    assert "telegram" in _kinds(acts)
    assert w.state == COOLDOWN


def test_retry_then_escalate():
    """재오픈해도 계속 frozen-black → max_attempts 까지 재시도 후 ESCALATED."""
    w = _new(observe_sec=5.0, max_attempts=3)
    w.update(0.0, True, True, False)
    w.update(8.0, True, True, False)              # attempt 1, observe 시작(=8.0)
    a2 = w.update(13.0, True, True, False)        # observe 만료 → attempt 2 재오픈
    assert "reconnect" in _kinds(a2) and w.attempts == 2
    a3 = w.update(18.0, True, True, False)        # → attempt 3 재오픈
    assert "reconnect" in _kinds(a3) and w.attempts == 3
    a4 = w.update(23.0, True, True, False)        # 소진 → 실패
    assert w.state == ESCALATED
    assert "telegram" in _kinds(a4)               # "복구 실패" 발송


def test_escalated_recovers_later():
    """ESCALATED 상태에서 나중에 입력 복구되면 COOLDOWN 으로 정리."""
    w = _new(max_attempts=1)
    w.update(0.0, True, True, False)
    w.update(8.0, True, True, False)              # attempt 1
    w.update(13.0, True, True, False)             # observe 만료 → 실패(ESCALATED)
    assert w.state == ESCALATED
    acts = w.update(40.0, False, False, False)    # 입력 복구
    assert w.state == COOLDOWN
    assert _kinds(acts) == ["log"]                # 텔레그램 없이 로그만


def test_no_reconnect_loop_in_escalated():
    """ESCALATED 에서 계속 블랙이어도 더 이상 재오픈하지 않음(스래싱 방지)."""
    w = _new(max_attempts=1)
    w.update(0.0, True, True, False)
    w.update(8.0, True, True, False)
    w.update(13.0, True, True, False)             # ESCALATED
    for tick in range(14, 60):
        assert _kinds(w.update(float(tick), True, True, False)) == []


# ── None(프레임 없음) 처리 ────────────────────────────────────────────────────

def test_unknown_frames_count_toward_observe_timeout():
    """재오픈 후 프레임이 안 들어와도(None) 관찰창 만료 시 실패 처리되어야 함."""
    w = _new(observe_sec=5.0, max_attempts=2)
    w.update(0.0, True, True, False)
    w.update(8.0, True, True, False)              # attempt 1
    a = w.update(13.0, None, None, False)         # 관찰 만료 & 복구 미확인(None)
    assert "reconnect" in _kinds(a) and w.attempts == 2


def test_unknown_does_not_falsely_recover():
    """None(판단 불가)을 복구로 오인하지 않음."""
    w = _new()
    w.update(0.0, True, True, False)
    w.update(8.0, True, True, False)
    acts = w.update(8.5, None, None, False)       # 관찰 중 None
    assert acts == [] and w.state == RECOVERING


# ── 게이트 / 쿨다운 / enabled ─────────────────────────────────────────────────

def test_gated_aborts_cycle():
    """정파 등 gated=True 면 진행 중 사이클을 NORMAL 로 초기화하고 무동작."""
    w = _new()
    w.update(0.0, True, True, False)
    w.update(8.0, True, True, False)              # RECOVERING
    acts = w.update(9.0, True, True, True)        # gated
    assert acts == [] and w.state == NORMAL


def test_gated_prevents_trigger():
    """gated 중에는 frozen-black 이 지속돼도 트리거 안 됨."""
    w = _new()
    for tick in range(0, 30):
        assert w.update(float(tick), True, True, True) == []
    assert w.state == NORMAL


def test_cooldown_blocks_retrigger():
    """복구 후 cooldown_sec 동안 재트리거 억제, 이후 정상 복귀."""
    w = _new(cooldown_sec=60.0)
    w.update(0.0, True, True, False)
    w.update(8.0, True, True, False)
    w.update(9.0, False, False, False)            # 복구 → COOLDOWN until 69.0
    # 쿨다운 중 frozen-black 재발생해도 트리거 안 됨
    assert _kinds(w.update(20.0, True, True, False)) == []
    assert _kinds(w.update(30.0, True, True, False)) == []
    assert w.state == COOLDOWN
    w.update(70.0, False, False, False)           # 쿨다운 만료 → NORMAL
    assert w.state == NORMAL


def test_disabled_never_acts():
    """enabled=False 면 어떤 입력에도 무동작."""
    w = _new(enabled=False)
    for tick in range(0, 30):
        assert w.update(float(tick), True, True, False) == []
    assert w.state == NORMAL
