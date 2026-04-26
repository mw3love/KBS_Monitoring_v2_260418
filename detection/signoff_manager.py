"""
정파준비/정파모드 상태 관리 모듈
v1 core/signoff_manager.py에서 QObject/QTimer/Signal 제거.
1초 주기 점검: threading.Thread + time.sleep(1).
상태 전환 이벤트는 result_queue에 SignoffStateChange / LogEntry 발행.
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


@dataclass
class SignoffGroup:
    group_id: int
    name: str
    enter_roi: dict
    suppressed_labels: List[str]
    start_time: str
    end_time: str
    prep_minutes: int
    exit_prep_minutes: int
    end_next_day: bool
    every_day: bool
    weekdays: List[int]
    still_trigger_sec: float
    exit_trigger_sec: float

    def to_dict(self) -> dict:
        return {
            "name":              self.name,
            "enter_roi":         dict(self.enter_roi),
            "suppressed_labels": list(self.suppressed_labels),
            "start_time":        self.start_time,
            "end_time":          self.end_time,
            "prep_minutes":      self.prep_minutes,
            "exit_prep_minutes": self.exit_prep_minutes,
            "exit_trigger_sec":  self.exit_trigger_sec,
            "end_next_day":      self.end_next_day,
            "every_day":         self.every_day,
            "weekdays":          list(self.weekdays),
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

        prep_minutes = int(d.get("prep_minutes", 30))
        prep_minutes = max(0, min(240, (prep_minutes // 30) * 30))
        exit_prep_minutes = int(d.get("exit_prep_minutes", 0))
        exit_prep_minutes = max(0, min(180, (exit_prep_minutes // 30) * 30))
        still_trigger_sec = max(1.0, float(d.get("still_trigger_sec", 60.0)))
        exit_trigger_sec = max(0.0, float(d.get("exit_trigger_sec", 5.0)))

        return cls(
            group_id=group_id,
            name=d.get("name", f"Group{group_id}"),
            enter_roi=enter_roi,
            suppressed_labels=suppressed_labels,
            start_time=d.get("start_time", "00:30"),
            end_time=d.get("end_time", "06:00"),
            prep_minutes=prep_minutes,
            exit_prep_minutes=exit_prep_minutes,
            exit_trigger_sec=exit_trigger_sec,
            end_next_day=bool(d.get("end_next_day", False)),
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
        self._manual_override: Dict[int, bool] = {}
        self._exit_released: Dict[int, bool] = {}

        self._latest_video: Dict[str, bool] = {}

        self._dbg_prev_still: Dict[int, Optional[bool]] = {}
        self._dbg_last_prep_log: Dict[int, float] = {}
        self._dbg_prev_exit_still: Dict[int, Optional[bool]] = {}

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
            self._manual_override[gid] = False
            self._exit_released[gid] = False
        elif old_group is not None:
            schedule_changed = (
                old_group.start_time != group.start_time
                or old_group.end_time != group.end_time
                or set(old_group.weekdays) != set(group.weekdays)
                or old_group.every_day != group.every_day
                or old_group.prep_minutes != group.prep_minutes
                or old_group.exit_prep_minutes != group.exit_prep_minutes
                or old_group.end_next_day != group.end_next_day
            )
            if schedule_changed:
                self._exit_released[gid] = False
                self._reset_enter_timers(gid)
                self._reset_exit_timers(gid)
                if not self._manual_override.get(gid, False):
                    now = datetime.datetime.now()
                    weekday = now.weekday()
                    current_time = now.strftime("%H:%M")
                    current_state = self._states.get(gid, SignoffState.IDLE)
                    in_prep_window = self._is_in_prep_window(group, current_time, weekday)
                    in_signoff_window = self._is_in_signoff_window(group, current_time, weekday)
                    if current_state == SignoffState.SIGNOFF:
                        if not in_prep_window:
                            self._signoff_entered_at[gid] = None
                            self._transition_to(gid, SignoffState.IDLE)
                        elif not in_signoff_window:
                            self._signoff_entered_at[gid] = None
                            self._transition_to(gid, SignoffState.PREPARATION)
                    elif current_state == SignoffState.PREPARATION:
                        if not in_prep_window:
                            self._reset_enter_timers(gid)
                            self._transition_to(gid, SignoffState.IDLE)
                    elif current_state == SignoffState.IDLE:
                        if in_signoff_window:
                            self._transition_to(gid, SignoffState.SIGNOFF)
                        elif in_prep_window:
                            self._transition_to(gid, SignoffState.PREPARATION)

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
            "manual": self._manual_override.get(group_id, False),
        }

    # ── 수동 상태 전환 ────────────────────────────────────────────────────────

    def cycle_state(self, group_id: int):
        current = self._states.get(group_id, SignoffState.IDLE)
        if current == SignoffState.IDLE:
            self._manual_override[group_id] = True
            self._reset_enter_timers(group_id)
            self._transition_to(group_id, SignoffState.PREPARATION)
        elif current == SignoffState.PREPARATION:
            now = datetime.datetime.now()
            group = self._groups.get(group_id)
            in_signoff = (
                group is not None
                and self._is_in_signoff_window(group, now.strftime("%H:%M"), now.weekday())
            )
            if in_signoff:
                self._manual_override[group_id] = True
                self._reset_enter_timers(group_id)
                self._transition_to(group_id, SignoffState.SIGNOFF)
            else:
                self._reset_enter_timers(group_id)
                self._manual_override[group_id] = False
                self._transition_to(group_id, SignoffState.IDLE)
        elif current == SignoffState.SIGNOFF:
            self._signoff_entered_at[group_id] = None
            self._manual_override[group_id] = False
            self._transition_to(group_id, SignoffState.IDLE)

    def set_state_direct(self, group_id: int, new_state: str):
        """cmd_queue SetSignoffState 수신 시 직접 상태 설정."""
        try:
            target = SignoffState(new_state)
        except ValueError:
            return
        current = self._states.get(group_id, SignoffState.IDLE)
        if current == target:
            return
        if target == SignoffState.SIGNOFF:
            self._manual_override[group_id] = True
        elif target == SignoffState.IDLE:
            self._manual_override[group_id] = False
        self._transition_to(group_id, target)

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
            start_h, start_m = map(int, group.start_time.split(":"))
            signoff_dt = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
            if signoff_dt <= now:
                signoff_dt += datetime.timedelta(days=1)
            return max(0.0, (signoff_dt - now).total_seconds())
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
        start_h = int(group.start_time.split(":")[0])
        if start_h >= 9:
            check_weekday = now.weekday()
        else:
            check_weekday = (now + datetime.timedelta(days=1)).weekday()
        return check_weekday in group.weekdays

    # ── 내부 헬퍼 ────────────────────────────────────────────────────────────

    def _calc_prep_start_str(self, group: SignoffGroup) -> str:
        if group.prep_minutes == 0:
            return group.start_time
        start_h, start_m = map(int, group.start_time.split(":"))
        total_min = (start_h * 60 + start_m - group.prep_minutes) % (24 * 60)
        return f"{total_min // 60:02d}:{total_min % 60:02d}"

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

        for gid, group in self._groups.items():
            current_state = self._states[gid]
            in_prep_window    = self._is_in_prep_window(group, current_time, weekday)
            in_signoff_window = self._is_in_signoff_window(group, current_time, weekday)

            if current_state == SignoffState.IDLE:
                if self._auto_preparation:
                    if self._exit_released.get(gid, False):
                        if not in_prep_window:
                            self._exit_released[gid] = False
                    elif in_signoff_window:
                        self._transition_to(gid, SignoffState.SIGNOFF)
                    elif in_prep_window:
                        self._transition_to(gid, SignoffState.PREPARATION)

            elif current_state == SignoffState.PREPARATION:
                is_manual = self._manual_override.get(gid, False)
                if not in_prep_window and not is_manual:
                    self._reset_enter_timers(gid)
                    self._transition_to(gid, SignoffState.IDLE)
                elif in_signoff_window:
                    self._reset_enter_timers(gid)
                    self._transition_to(gid, SignoffState.SIGNOFF)
                else:
                    self._tick_preparation(gid, group)

            elif current_state == SignoffState.SIGNOFF:
                is_manual = self._manual_override.get(gid, False)
                if not in_prep_window and not is_manual:
                    self._signoff_entered_at[gid] = None
                    self._manual_override[gid] = False
                    self._transition_to(gid, SignoffState.IDLE)
                elif group.exit_prep_minutes > 0:
                    if self._is_in_exit_prep_window(group):
                        self._tick_exit_preparation(gid, group)

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
                _log.debug("PREP-DBG [%s] %s 스틸 중단→리셋 (직전 경과: %.1fs)",
                           group.name, lbl_str, elapsed)

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
            self._transition_to(gid, SignoffState.SIGNOFF)

    def _is_in_signoff_window(self, group: SignoffGroup, current_time: str, weekday: int) -> bool:
        return self._is_in_time_range(group, current_time, weekday,
                                      group.start_time, group.end_time)

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
        if group.exit_prep_minutes == 0:
            return False
        now = datetime.datetime.now()
        end_h, end_m = map(int, group.end_time.split(":"))
        end_dt = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
        if end_dt <= now:
            end_dt += datetime.timedelta(days=1)
        return (end_dt - now).total_seconds() <= group.exit_prep_minutes * 60

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
                self._manual_override[gid] = False
                self._exit_released[gid] = True
                self._transition_to(gid, SignoffState.IDLE)
        else:
            self._video_exit_still[gid] = self._video_exit_still.get(gid, 0) + 1
            if self._video_exit_still[gid] >= _SIGNOFF_HYSTERESIS_TICKS:
                self._video_exit_start[gid] = None

    def _is_in_time_range(self, group: SignoffGroup, current_time: str, weekday: int,
                           start: str, end: str) -> bool:
        if group.end_next_day:
            if current_time >= start:
                if not group.every_day and weekday not in group.weekdays:
                    return False
                return True
            elif current_time < end:
                prev_weekday = (weekday - 1) % 7
                if not group.every_day and prev_weekday not in group.weekdays:
                    return False
                return True
            else:
                return False
        else:
            if not group.every_day and weekday not in group.weekdays:
                return False
            return start <= current_time < end

    def _transition_to(self, group_id: int, new_state: SignoffState):
        from ipc.messages import SignoffStateChange, LogEntry
        old_state = self._states.get(group_id)
        if old_state == new_state:
            return

        self._states[group_id] = new_state

        if new_state == SignoffState.IDLE:
            self._manual_override[group_id] = False
            self._preparation_entered_at[group_id] = None
            self._reset_enter_timers(group_id)   # IDLE 진입 시 진입 타이머 초기화

        if new_state == SignoffState.PREPARATION:
            self._preparation_entered_at[group_id] = time.time()
            self._dbg_prev_still[group_id] = None

        if new_state == SignoffState.SIGNOFF:
            self._signoff_entered_at[group_id] = time.time()
            self._preparation_entered_at[group_id] = None
            self._reset_exit_timers(group_id)    # SIGNOFF 진입 시 퇴출 타이머 초기화
            self._dbg_prev_exit_still[group_id] = None

        group = self._groups[group_id]
        prev_str = old_state.value if old_state else "NONE"
        if new_state == SignoffState.PREPARATION:
            msg = (f"{group.name} 정파준비모드를 시작합니다"
                   if old_state == SignoffState.IDLE
                   else f"{group.name} 정파모드를 해제합니다")
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
            source="auto",
        ))
        self._emit(LogEntry(level="info", source="signoff", message=msg))
        _log.info("SignoffManager [%s] %s → %s", group.name, prev_str, new_state.value)
