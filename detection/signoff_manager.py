"""
정파준비/정파모드 상태 관리 모듈
v1 core/signoff_manager.py에서 QObject/QTimer/Signal 제거.
1초 주기 점검: threading.Thread + time.sleep(1).
상태 전환 이벤트는 result_queue에 SignoffStateChange 발행 (사람이 읽는 문장은 message 필드로 동봉).
PySide6 임포트 없음.
"""
import time
import datetime
import threading
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional

_log = logging.getLogger(__name__)

_SIGNOFF_HYSTERESIS_TICKS = 3


class SignoffState(Enum):
    IDLE        = "IDLE"
    PREPARATION = "PREPARATION"
    SIGNOFF     = "SIGNOFF"


def _valid_hm(s: str, default: str) -> str:
    """'HH:MM' 형식 검증 후 정규화. 실패 시 default 반환."""
    try:
        h, m = s.split(":")
        h, m = int(h), int(m)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return f"{h:02d}:{m:02d}"
    except (ValueError, AttributeError):
        pass
    return default


@dataclass
class SignoffGroup:
    group_id: int
    name: str
    enter_roi: dict
    suppressed_labels: List[str]
    prep_start_time: str        # 정파준비 시작 시간 "HH:MM"
    exit_prep_start_time: str   # 정파해제 준비 시작 시간 "HH:MM" ("" = 미사용)
    end_time: str               # 정파해제 시간 "HH:MM" (하드캡)
    every_day: bool
    weekdays: List[int]
    still_trigger_sec: float
    exit_trigger_sec: float

    def to_dict(self) -> dict:
        return {
            "name":                 self.name,
            "enter_roi":            dict(self.enter_roi),
            "suppressed_labels":    list(self.suppressed_labels),
            "prep_start_time":      self.prep_start_time,
            "exit_prep_start_time": self.exit_prep_start_time,
            "end_time":             self.end_time,
            "still_trigger_sec":    self.still_trigger_sec,
            "exit_trigger_sec":     self.exit_trigger_sec,
            "every_day":            self.every_day,
            "weekdays":             list(self.weekdays),
        }

    @classmethod
    def from_dict(cls, d: dict, group_id: int) -> "SignoffGroup":
        enter_roi = d.get("enter_roi", {})
        if not enter_roi:
            old_rules = d.get("roi_rules", [])
            if old_rules:
                enter_roi = {"video_label": old_rules[0].get("video_label", "")}
        if not enter_roi:
            old_labels = d.get("roi_labels", [])
            if old_labels:
                v_lbl = next((l for l in old_labels if l.startswith("V")), "")
                if v_lbl:
                    enter_roi = {"video_label": v_lbl}
        if not enter_roi:
            enter_roi = {"video_label": ""}

        suppressed_labels = list(d.get("suppressed_labels", []))
        if not suppressed_labels:
            v_label = enter_roi.get("video_label", "")
            if v_label:
                suppressed_labels = [v_label]

        raw_weekdays = list(d.get("weekdays", [0, 1, 2, 3, 4, 5, 6]))
        every_day = d.get("every_day", len(raw_weekdays) == 7)

        prep_start_time = _valid_hm(d.get("prep_start_time", "00:30"), "00:30")
        end_time = _valid_hm(d.get("end_time", "05:00"), "05:00")
        # exit_prep_start_time: "" 이면 해제준비 미사용 (파싱하지 않음)
        raw_exit_prep = d.get("exit_prep_start_time", "04:30")
        exit_prep_start_time = "" if not raw_exit_prep else _valid_hm(raw_exit_prep, "04:30")
        still_trigger_sec = max(1.0, float(d.get("still_trigger_sec", 60.0)))
        exit_trigger_sec = max(0.0, float(d.get("exit_trigger_sec", 30.0)))

        return cls(
            group_id=group_id,
            name=d.get("name", f"Group{group_id}"),
            enter_roi=enter_roi,
            suppressed_labels=suppressed_labels,
            prep_start_time=prep_start_time,
            exit_prep_start_time=exit_prep_start_time,
            end_time=end_time,
            exit_trigger_sec=exit_trigger_sec,
            every_day=every_day,
            weekdays=raw_weekdays,
            still_trigger_sec=still_trigger_sec,
        )


class SignoffManager:
    """
    정파준비/정파모드 상태 관리자.
    threading.Thread 기반으로 1초마다 상태 전환 조건 점검.
    상태 전환 시 result_queue에 SignoffStateChange 발행.
    """

    def __init__(self, result_queue=None):
        self._result_queue = result_queue
        self._groups: Dict[int, SignoffGroup] = {}
        self._states: Dict[int, SignoffState] = {}

        self._video_enter_start: Dict[int, Optional[float]] = {}
        self._video_enter_not_still: Dict[int, int] = {}
        self._video_exit_start: Dict[int, Optional[float]] = {}
        self._video_exit_still: Dict[int, int] = {}

        self._signoff_entered_at: Dict[int, Optional[float]] = {}
        self._preparation_entered_at: Dict[int, Optional[float]] = {}
        self._exit_released: Dict[int, bool] = {}

        self._latest_video: Dict[str, bool] = {}

        self._dbg_prev_still: Dict[int, Optional[bool]] = {}
        self._dbg_last_prep_log: Dict[int, float] = {}
        self._dbg_prev_exit_still: Dict[int, Optional[bool]] = {}
        self._dbg_prev_revert_still: Dict[int, Optional[bool]] = {}

        self._auto_preparation: bool = True
        self._media_names: Dict[str, str] = {}

        self._running = False
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="SignoffManager"
        )

    def start(self):
        self._running = True
        try:
            self._thread.start()
        except OSError as e:
            _log.error("SignoffManager 스레드 시작 실패: %s", e)

    def stop(self):
        self._running = False

    def _emit(self, msg):
        if self._result_queue is None:
            return
        try:
            self._result_queue.put_nowait(msg)
        except Exception:
            try:
                self._result_queue.get_nowait()
                self._result_queue.put_nowait(msg)
            except Exception:
                pass

    # ── 1초 주기 루프 ─────────────────────────────────────────────────────────

    def _run_loop(self):
        while self._running:
            try:
                self._tick_impl()
            except Exception as e:
                _log.error("SignoffManager._tick_impl() 오류 (루프 유지): %s", e)
            time.sleep(1.0)

    # ── 그룹 설정 ─────────────────────────────────────────────────────────────

    def set_group(self, group: SignoffGroup):
        gid = group.group_id
        old_group = self._groups.get(gid)
        self._groups[gid] = group
        if gid not in self._states:
            self._states[gid] = SignoffState.IDLE
            self._video_enter_start[gid] = None
            self._video_enter_not_still[gid] = 0
            self._video_exit_start[gid] = None
            self._video_exit_still[gid] = 0
            self._signoff_entered_at[gid] = None
            self._preparation_entered_at[gid] = None
            self._exit_released[gid] = False
        elif old_group is not None:
            schedule_changed = (
                old_group.prep_start_time != group.prep_start_time
                or old_group.exit_prep_start_time != group.exit_prep_start_time
                or old_group.end_time != group.end_time
                or set(old_group.weekdays) != set(group.weekdays)
                or old_group.every_day != group.every_day
            )
            if schedule_changed and self._auto_preparation:
                # auto OFF = 완전 수동 모드: 스케줄 저장 시 즉시 재평가도 억제 (수동 상태 유지)
                self._exit_released[gid] = False
                self._reset_enter_timers(gid)
                self._reset_exit_timers(gid)
                now = datetime.datetime.now()
                weekday = now.weekday()
                current_time = now.strftime("%H:%M")
                current_state = self._states.get(gid, SignoffState.IDLE)
                in_prep_window = self._is_in_prep_window(group, current_time, weekday)
                if current_state == SignoffState.SIGNOFF:
                    # 진입은 감지 기반 → 시간대 이탈(prep_window 밖) 시에만 IDLE 해제
                    if not in_prep_window:
                        self._signoff_entered_at[gid] = None
                        self._transition_to(gid, SignoffState.IDLE, source="auto-time")
                elif current_state == SignoffState.PREPARATION:
                    if not in_prep_window:
                        self._reset_enter_timers(gid)
                        self._transition_to(gid, SignoffState.IDLE, source="auto-time")
                elif current_state == SignoffState.IDLE:
                    if in_prep_window:
                        self._transition_to(gid, SignoffState.PREPARATION, source="auto-time")

    def get_state(self, group_id: int) -> SignoffState:
        return self._states.get(group_id, SignoffState.IDLE)

    def get_groups(self) -> Dict[int, SignoffGroup]:
        return dict(self._groups)

    def configure_from_dict(self, signoff_cfg: dict):
        self._auto_preparation = bool(signoff_cfg.get("auto_preparation", True))
        for gid in (1, 2):
            key = f"group{gid}"
            grp_data = signoff_cfg.get(key, {})
            group = SignoffGroup.from_dict(grp_data, gid)
            self.set_group(group)

    # ── 감지 데이터 수신 ──────────────────────────────────────────────────────

    def update_detection(self, still_results: dict):
        self._latest_video.update(still_results)

    def update_media_names(self, media_name_map: Dict[str, str]):
        self._media_names = dict(media_name_map)

    def get_debug_flags(self, group_id: int) -> dict:
        return {
            "exit_released": self._exit_released.get(group_id, False),
        }

    # ── 수동 상태 전환 ────────────────────────────────────────────────────────

    def cycle_state(self, group_id: int):
        current = self._states.get(group_id, SignoffState.IDLE)
        if current == SignoffState.IDLE:
            self._reset_enter_timers(group_id)
            self._transition_to(group_id, SignoffState.PREPARATION, source="manual")
        elif current == SignoffState.PREPARATION:
            now = datetime.datetime.now()
            group = self._groups.get(group_id)
            # 정파준비 윈도우 안에서만 수동 SIGNOFF 허용(운용자 즉시 강제), 밖이면 IDLE로.
            can_signoff = (
                group is not None
                and self._is_in_prep_window(group, now.strftime("%H:%M"), now.weekday())
            )
            if can_signoff:
                self._reset_enter_timers(group_id)
                self._transition_to(group_id, SignoffState.SIGNOFF, source="manual")
            else:
                self._reset_enter_timers(group_id)
                self._transition_to(group_id, SignoffState.IDLE, source="manual")
        elif current == SignoffState.SIGNOFF:
            self._signoff_entered_at[group_id] = None
            self._transition_to(group_id, SignoffState.IDLE, source="manual")

    def set_state_direct(
        self,
        group_id: int,
        new_state: str,
        source: str = "manual",
        entered_at: float = 0.0,
    ):
        """cmd_queue SetSignoffState 수신 시 직접 상태 설정.

        source="restore"는 재spawn 후 UI 재주입을 의미. detection_process의
        _signoff_emit_safe가 source 값으로 텔레그램 발송 중복을 회피한다.
        entered_at>0 이면 SIGNOFF 진입 시각을 복원해 elapsed_sec 정확도를 유지.
        """
        try:
            target = SignoffState(new_state)
        except ValueError:
            return
        current = self._states.get(group_id, SignoffState.IDLE)
        if current == target:
            return
        self._transition_to(group_id, target, source=source, entered_at=entered_at)

    # ── 알림 차단 판단 ────────────────────────────────────────────────────────

    def is_signoff_label(self, label: str, group_id: int = None) -> bool:
        """해당 label이 SIGNOFF 상태 그룹의 억제 대상인지 반환. group_id 지정 시 해당 그룹만."""
        for gid, group in self._groups.items():
            if group_id is not None and gid != group_id:
                continue
            if self._states.get(gid) == SignoffState.SIGNOFF:
                v_label = group.enter_roi.get("video_label", "")
                if (v_label and label == v_label) or label in group.suppressed_labels:
                    return True
        return False

    def is_prep_label(self, label: str) -> bool:
        for gid, group in self._groups.items():
            if self._states.get(gid) == SignoffState.PREPARATION:
                v_label = group.enter_roi.get("video_label", "")
                if (v_label and label == v_label) or label in group.suppressed_labels:
                    return True
        return False

    def is_any_signoff(self) -> bool:
        return any(self._states.get(gid) == SignoffState.SIGNOFF for gid in self._groups)

    def is_group_enabled(self, group_id: int) -> bool:
        if not self._auto_preparation:
            return False
        group = self._groups.get(group_id)
        if group is None:
            return False
        return group.every_day or len(group.weekdays) > 0

    # ── 잔여/경과 시간 ────────────────────────────────────────────────────────

    def get_elapsed_seconds(self, group_id: int) -> float:
        state = self._states.get(group_id, SignoffState.IDLE)
        group = self._groups.get(group_id)
        if group is None:
            return 0.0
        now = datetime.datetime.now()
        if state == SignoffState.IDLE:
            prep_start = self._calc_prep_start_str(group)
            if not prep_start:
                return 0.0
            h, m = map(int, prep_start.split(":"))
            for offset in range(8):
                candidate = now.replace(hour=h, minute=m, second=0, microsecond=0
                                        ) + datetime.timedelta(days=offset)
                if candidate <= now:
                    continue
                wd = candidate.weekday()
                if group.every_day or wd in group.weekdays:
                    return max(0.0, (candidate - now).total_seconds())
            return 0.0
        elif state == SignoffState.PREPARATION:
            # 정파 예정시각 개념 제거 → PREPARATION은 카운트다운 없음(UI는 "감지중" 표시).
            # 이 값은 DIAG 진단용으로만 흘러가므로 0 반환.
            return 0.0
        elif state == SignoffState.SIGNOFF:
            entered = self._signoff_entered_at.get(group_id)
            if entered is None:
                return 0.0
            return time.time() - entered
        return 0.0

    def get_end_remaining_seconds(self, group_id: int) -> float:
        group = self._groups.get(group_id)
        if group is None:
            return 0.0
        now = datetime.datetime.now()
        end_h, end_m = map(int, group.end_time.split(":"))
        end_dt = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
        if end_dt <= now:
            end_dt += datetime.timedelta(days=1)
        return max(0.0, (end_dt - now).total_seconds())

    def get_preparation_elapsed(self, group_id: int) -> float:
        if self._states.get(group_id) != SignoffState.PREPARATION:
            return 0.0
        entered = self._preparation_entered_at.get(group_id)
        if entered is None:
            return 0.0
        return time.time() - entered

    def has_schedule_in_window(self, group_id: int) -> bool:
        group = self._groups.get(group_id)
        if group is None:
            return False
        if not group.every_day and not group.weekdays:
            return False
        if group.every_day:
            return True
        now = datetime.datetime.now()
        prep_h = int(group.prep_start_time.split(":")[0])
        if prep_h >= 9:
            check_weekday = now.weekday()
        else:
            check_weekday = (now + datetime.timedelta(days=1)).weekday()
        return check_weekday in group.weekdays

    # ── 내부 헬퍼 ────────────────────────────────────────────────────────────

    def _calc_prep_start_str(self, group: SignoffGroup) -> str:
        return group.prep_start_time

    def _reset_enter_timers(self, gid: int):
        """IDLE 진입 시 반드시 호출 (stale 타이머 방지)."""
        self._video_enter_start[gid] = None
        self._video_enter_not_still[gid] = 0

    def _reset_exit_timers(self, gid: int):
        """SIGNOFF 진입 시 반드시 호출 (stale 타이머 방지)."""
        self._video_exit_start[gid] = None
        self._video_exit_still[gid] = 0

    # ── 1초 주기 상태 점검 구현 ───────────────────────────────────────────────

    def _tick_impl(self):
        now = datetime.datetime.now()
        weekday = now.weekday()
        current_time = now.strftime("%H:%M")

        groups_snapshot = dict(self._groups)  # 순회 중 set_group() 동시 수정 방지
        for gid, group in groups_snapshot.items():
            current_state = self._states[gid]
            in_prep_window = self._is_in_prep_window(group, current_time, weekday)

            if current_state == SignoffState.IDLE:
                if self._auto_preparation:
                    if self._exit_released.get(gid, False):
                        if not in_prep_window:
                            self._exit_released[gid] = False
                    elif in_prep_window:
                        self._transition_to(gid, SignoffState.PREPARATION, source="auto-time")

            elif current_state == SignoffState.PREPARATION:
                # auto OFF = 완전 수동 모드: 자동 강등/진입/감지 모두 억제 (수동 상태 유지)
                if self._auto_preparation:
                    if not in_prep_window:
                        self._reset_enter_timers(gid)
                        self._transition_to(gid, SignoffState.IDLE, source="auto-time")
                    else:
                        # 진입은 항상 감지 기반(스틸 지속 시 SIGNOFF)
                        self._tick_preparation(gid, group)

            elif current_state == SignoffState.SIGNOFF:
                # auto OFF = 완전 수동 모드: 자동 해제(강등/exit-prep/조기복귀) 억제 (수동 해제까지 유지)
                if self._auto_preparation:
                    if not in_prep_window:
                        self._signoff_entered_at[gid] = None
                        self._transition_to(gid, SignoffState.IDLE, source="auto-time")
                    elif group.exit_prep_start_time and self._is_in_exit_prep_window(group):
                        self._tick_exit_preparation(gid, group)   # 해제준비 윈도우: 비스틸 → IDLE(진짜 해제)
                    else:
                        self._tick_signoff_revert(gid, group)     # 해제준비 전: 비스틸 → PREPARATION(조기복귀)

    def _tick_preparation(self, gid: int, group: SignoffGroup):
        v_label = group.enter_roi.get("video_label", "")
        if not v_label:
            return
        now = time.time()
        is_still = self._latest_video.get(v_label, False)
        prev_still = self._dbg_prev_still.get(gid)
        media = self._media_names.get(v_label, "")
        lbl_str = f"{v_label}({media})" if media else v_label

        if is_still:
            self._video_enter_not_still[gid] = 0
            if self._video_enter_start[gid] is None:
                self._video_enter_start[gid] = now
        else:
            self._video_enter_not_still[gid] = self._video_enter_not_still.get(gid, 0) + 1
            if self._video_enter_not_still[gid] >= _SIGNOFF_HYSTERESIS_TICKS:
                self._video_enter_start[gid] = None

        if is_still != prev_still:
            self._dbg_prev_still[gid] = is_still
            if is_still:
                _log.debug("PREP-DBG [%s] %s 스틸 감지 시작 (기준: %.0fs)",
                           group.name, lbl_str, group.still_trigger_sec)
            else:
                elapsed = (now - self._video_enter_start[gid]
                           ) if self._video_enter_start[gid] else 0.0
                _log.debug("PREP-DBG [%s] %s 스틸 중단 (직전 경과: %.1fs, 히스테리시스: 1/%d)",
                           group.name, lbl_str, elapsed, _SIGNOFF_HYSTERESIS_TICKS)

        if self._video_enter_start[gid] is not None:
            v_elapsed = now - self._video_enter_start[gid]
            last_log = self._dbg_last_prep_log.get(gid, 0.0)
            if now - last_log >= 10.0:
                self._dbg_last_prep_log[gid] = now
                _log.debug("PREP-DBG [%s] %s 스틸 지속 중 %.1fs / %.0fs",
                           group.name, lbl_str, v_elapsed, group.still_trigger_sec)
        else:
            self._dbg_last_prep_log[gid] = 0.0

        v_elapsed = (now - self._video_enter_start[gid]
                     ) if self._video_enter_start[gid] else 0.0
        if v_elapsed >= group.still_trigger_sec:
            self._reset_enter_timers(gid)
            self._transition_to(gid, SignoffState.SIGNOFF, source="auto-detect")

    def _is_in_prep_window(self, group: SignoffGroup, current_time: str, weekday: int) -> bool:
        prep_start = self._calc_prep_start_str(group)
        if prep_start > group.end_time:
            if current_time >= prep_start:
                if not group.every_day and weekday not in group.weekdays:
                    return False
                return True
            elif current_time < group.end_time:
                prev_weekday = (weekday - 1) % 7
                if not group.every_day and prev_weekday not in group.weekdays:
                    return False
                return True
            else:
                return False
        return self._is_in_time_range(group, current_time, weekday,
                                      prep_start, group.end_time)

    def _is_in_exit_prep_window(self, group: SignoffGroup) -> bool:
        if not group.exit_prep_start_time:
            return False
        end_h, end_m = map(int, group.end_time.split(":"))
        ep_h, ep_m = map(int, group.exit_prep_start_time.split(":"))
        # 해제준비 시작~정파해제 사이의 길이(분). 자정 넘김 % 1440 처리.
        gap_min = (end_h * 60 + end_m - (ep_h * 60 + ep_m)) % (24 * 60)
        if gap_min == 0:
            return False
        now = datetime.datetime.now()
        end_dt = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
        if end_dt <= now:
            end_dt += datetime.timedelta(days=1)
        return (end_dt - now).total_seconds() <= gap_min * 60

    def _tick_exit_preparation(self, gid: int, group: SignoffGroup):
        v_label = group.enter_roi.get("video_label", "")
        if not v_label:
            return
        now = time.time()
        is_still = self._latest_video.get(v_label, True)
        is_not_still = not is_still
        prev_exit_still = self._dbg_prev_exit_still.get(gid)
        media = self._media_names.get(v_label, "")
        lbl_str = f"{v_label}({media})" if media else v_label

        if is_not_still != prev_exit_still:
            self._dbg_prev_exit_still[gid] = is_not_still
            if is_not_still:
                _log.debug("EXIT-DBG [%s] %s 비스틸 감지 시작 (기준: %.0fs)",
                           group.name, lbl_str, group.exit_trigger_sec)

        if is_not_still:
            self._video_exit_still[gid] = 0
            if self._video_exit_start[gid] is None:
                self._video_exit_start[gid] = now
            if now - self._video_exit_start[gid] >= group.exit_trigger_sec:
                self._video_exit_start[gid] = None
                self._signoff_entered_at[gid] = None
                self._exit_released[gid] = True
                self._transition_to(gid, SignoffState.IDLE, source="auto-detect")
        else:
            self._video_exit_still[gid] = self._video_exit_still.get(gid, 0) + 1
            if self._video_exit_still[gid] >= _SIGNOFF_HYSTERESIS_TICKS:
                self._video_exit_start[gid] = None

    def _tick_signoff_revert(self, gid: int, group: SignoffGroup):
        """해제준비 시각 전 SIGNOFF 중 비스틸이 exit_trigger_sec 지속되면
        PREPARATION으로 조기복귀(재무장)한다.

        오감지로 진입한 SIGNOFF가 해제준비 시각까지 갇혀 알람을 묵살하는
        문제(docs_signoff_운영.md §4) 해소. 진짜 정파는 계속 스틸이라 복귀가
        걸리지 않고, 가짜 정파는 화면이 다시 움직이면 PREPARATION으로 돌아가
        스틸 재감지(still_trigger_sec)를 다시 수행한다.

        타이머는 _tick_exit_preparation과 동일한 _video_exit_* 재사용
        (두 검사는 해제준비 시각을 경계로 상호배타, SIGNOFF 진입 시 함께 초기화).
        IDLE 해제와 달리 _exit_released는 건드리지 않는다(IDLE 경로 전용 플래그).
        """
        v_label = group.enter_roi.get("video_label", "")
        if not v_label:
            return
        now = time.time()
        is_still = self._latest_video.get(v_label, True)
        is_not_still = not is_still
        prev_revert_still = self._dbg_prev_revert_still.get(gid)
        media = self._media_names.get(v_label, "")
        lbl_str = f"{v_label}({media})" if media else v_label

        if is_not_still != prev_revert_still:
            self._dbg_prev_revert_still[gid] = is_not_still
            if is_not_still:
                _log.debug("REVERT-DBG [%s] %s 비스틸 감지 시작 (기준: %.0fs → 정파준비 복귀)",
                           group.name, lbl_str, group.exit_trigger_sec)

        if is_not_still:
            self._video_exit_still[gid] = 0
            if self._video_exit_start[gid] is None:
                self._video_exit_start[gid] = now
            if now - self._video_exit_start[gid] >= group.exit_trigger_sec:
                self._video_exit_start[gid] = None
                self._transition_to(gid, SignoffState.PREPARATION, source="auto-revert")
        else:
            self._video_exit_still[gid] = self._video_exit_still.get(gid, 0) + 1
            if self._video_exit_still[gid] >= _SIGNOFF_HYSTERESIS_TICKS:
                self._video_exit_start[gid] = None

    def _is_in_time_range(self, group: SignoffGroup, current_time: str, weekday: int,
                           start: str, end: str) -> bool:
        # 같은 날(start ≤ end) 윈도우 전용. 자정 넘김은 _is_in_prep_window의 wrap 분기가 처리.
        if not group.every_day and weekday not in group.weekdays:
            return False
        return start <= current_time < end

    def _transition_to(
        self,
        group_id: int,
        new_state: SignoffState,
        source: str = "auto",
        entered_at: float = 0.0,
    ):
        """
        entered_at>0 이면 SIGNOFF 진입 시각을 그 값으로 설정(restore 경로용).
        그 외에는 time.time(). _emit 직전에 확정되므로 _signoff_emit_safe가
        signoff_mgr._signoff_entered_at[gid]를 안전하게 읽을 수 있다.
        """
        from ipc.messages import SignoffStateChange
        old_state = self._states.get(group_id)
        if old_state == new_state:
            return

        self._states[group_id] = new_state

        if new_state == SignoffState.IDLE:
            self._preparation_entered_at[group_id] = None
            self._reset_enter_timers(group_id)   # IDLE 진입 시 진입 타이머 초기화

        if new_state == SignoffState.PREPARATION:
            self._preparation_entered_at[group_id] = time.time()
            self._dbg_prev_still[group_id] = None

        if new_state == SignoffState.SIGNOFF:
            self._signoff_entered_at[group_id] = (
                entered_at if entered_at > 0 else time.time()
            )
            self._preparation_entered_at[group_id] = None
            self._reset_exit_timers(group_id)    # SIGNOFF 진입 시 퇴출 타이머 초기화
            self._dbg_prev_exit_still[group_id] = None
            self._dbg_prev_revert_still[group_id] = None

        group = self._groups[group_id]
        prev_str = old_state.value if old_state else "NONE"
        if new_state == SignoffState.PREPARATION:
            if source == "auto-revert":
                msg = f"{group.name} 화면 움직임 감지 — 정파준비로 복귀"
            elif old_state == SignoffState.IDLE:
                msg = f"{group.name} 정파준비모드를 시작합니다"
            else:
                msg = f"{group.name} 정파모드를 해제합니다"
        elif new_state == SignoffState.SIGNOFF:
            msg = f"{group.name} 정파모드에 돌입합니다"
        else:
            msg = (f"{group.name} 정파모드를 해제합니다"
                   if old_state == SignoffState.SIGNOFF
                   else f"{group.name} 정파준비모드를 종료합니다")

        self._emit(SignoffStateChange(
            group_id=group_id,
            prev_state=prev_str,
            new_state=new_state.value,
            source=source,
            message=msg,
        ))
        _log.info("SignoffManager [%s] %s → %s [%s]", group.name, prev_str, new_state.value, source)
