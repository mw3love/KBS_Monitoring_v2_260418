"""
정파 플래핑(짧은 시간에 SIGNOFF⇄정파준비 반복) 감지·묶음 처리 추적기.

본사 테스트영상 송출 등으로 V영상이 정지↔움직임을 반복하면 상태기계가
SIGNOFF ⇄ PREPARATION을 왕복하며 텔레그램/현장 알림음이 폭주한다(docs_signoff_운영.md §7).
이 추적기는 "묶음 모드"를 판정만 하고, 실제 텔레그램 발송/큐 I/O·현장음 억제는
detection_process / UI가 이 판정을 공유해 수행한다.

PySide6 임포트 없음 (Detection 프로세스 전용). 상수는 운영 보고 후 조정.
"""
import time

# ── 플래핑 판정 파라미터 (설정 노출 없음 — 상수) ──────────────────────────────
FLAP_WINDOW_SEC = 600.0     # 변동 집계 창 (10분) — 이 창 안의 전환 횟수로 판정
FLAP_ENTER_COUNT = 3        # 창 안 전환이 이 횟수 이상이면 묶음 모드 진입
FLAP_STABLE_SEC = 1500.0    # 전환 없이 이 시간 경과 시 안정화 → 요약 (25분)
                            #   2026-06-09 로그 검증: 짧은 안정 구간(~17분)의 과도한
                            #   에피소드 분할을 막아 요약 중복을 줄임(15분=12건 → 25분=8건).


class SignoffFlapTracker:
    """그룹별 정파 전환 빈도를 추적해 묶음 모드 진입/안정화를 판정한다.

    전환(transition)으로 집계하는 대상은 SIGNOFF 진입·정파준비 복귀(enter/revert)다.
    정파준비 시작(IDLE→PREP)·정파 해제(→IDLE)는 집계하지 않으며, 해제는 묶음 종료로 본다.
    """

    def __init__(
        self,
        window_sec: float = FLAP_WINDOW_SEC,
        enter_count: int = FLAP_ENTER_COUNT,
        stable_sec: float = FLAP_STABLE_SEC,
    ):
        self._window_sec = window_sec
        self._enter_count = enter_count
        self._stable_sec = stable_sec
        self._ts = {}          # gid -> list[float] 창 내 전환 타임스탬프
        self._flapping = {}    # gid -> bool 묶음 모드 여부
        self._flap_start = {}  # gid -> float 변동 구간 시작 시각(묶음 진입 시 고정)
        self._flap_count = {}  # gid -> int 변동 누적 횟수
        self._last_ts = {}     # gid -> float 마지막 전환 시각(안정화 판정용)

    def record_transition(self, gid: int, now: float = None) -> dict:
        """enter/revert 전환 1건 기록 후 현재 묶음 상태를 반환.

        반환 dict:
          flapping     — 이 전환 시점에 묶음 모드인가
          just_entered — 이번 전환으로 막 묶음 모드에 진입했나(묶음 시작 알림 1회용)
          count        — 묶음 구간 누적 변동 횟수
          start_ts     — 변동 구간 시작 시각
        """
        now = now if now is not None else time.time()
        lst = self._ts.setdefault(gid, [])
        lst.append(now)
        cutoff = now - self._window_sec
        while lst and lst[0] < cutoff:
            lst.pop(0)
        self._last_ts[gid] = now

        was_flapping = self._flapping.get(gid, False)
        just_entered = False
        if not was_flapping and len(lst) >= self._enter_count:
            self._flapping[gid] = True
            just_entered = True
            self._flap_start[gid] = lst[0]   # 창 내 첫 전환 = 변동 구간 시작
            self._flap_count[gid] = len(lst)
        elif was_flapping:
            self._flap_count[gid] = self._flap_count.get(gid, 0) + 1

        return {
            "flapping": self._flapping.get(gid, False),
            "just_entered": just_entered,
            "count": self._flap_count.get(gid, len(lst)),
            "start_ts": self._flap_start.get(gid, lst[0] if lst else now),
        }

    def is_flapping(self, gid: int) -> bool:
        return self._flapping.get(gid, False)

    def check_stabilized(self, gid: int, now: float = None):
        """주기 호출용. 묶음 모드인데 stable_sec 동안 전환이 없으면 요약 dict 반환 후 리셋.

        반환: {'count', 'start_ts', 'end_ts'} 또는 None.
        """
        if not self._flapping.get(gid, False):
            return None
        now = now if now is not None else time.time()
        if now - self._last_ts.get(gid, now) < self._stable_sec:
            return None
        return self._finish(gid, now)

    def finish_on_release(self, gid: int, now: float = None):
        """정파 해제 등으로 묶음 모드를 강제 종료. 묶음 중이었으면 요약 dict 반환, 아니면 None."""
        if not self._flapping.get(gid, False):
            return None
        now = now if now is not None else time.time()
        return self._finish(gid, now)

    def _finish(self, gid: int, now: float) -> dict:
        info = {
            "count": self._flap_count.get(gid, 0),
            "start_ts": self._flap_start.get(gid, now),
            "end_ts": self._last_ts.get(gid, now),
        }
        self._flapping[gid] = False
        self._flap_count[gid] = 0
        self._ts[gid] = []
        return info
