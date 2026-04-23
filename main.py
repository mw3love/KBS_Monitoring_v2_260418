"""
KBS Monitoring v2 — Launcher (= UI 프로세스)
역할: SharedMemory/Queue 생성, Watchdog spawn, QApplication + MainWindow 실행.
faulthandler 활성화, SharedMemory 잔존 정리, last_exit.json 기록.
예약 재시작: 날짜+시각(YYYY-MM-DD HH:MM) 조합으로 중복 방지 (Launcher 단독 관리).
"""
import datetime
import faulthandler
import json
import multiprocessing
import os
import sys
import time

# ── 경로 보장 ──────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ── 텔레그램 직접 발송 (main 전용) ────────────────────────────────

def _send_system_telegram_main(message: str):
    """
    [SYSTEM] prefix 텔레그램 직접 발송.
    Detection/Watchdog이 죽은 상황에서도 main이 직접 발송.
    """
    try:
        import requests as _req
    except ImportError:
        return
    cfg_path = os.path.join(_ROOT, "config", "kbs_config.json")
    default_path = os.path.join(_ROOT, "config", "default_config.json")
    tg = {}
    for path in (cfg_path, default_path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                c = json.load(f)
            tg = c.get("telegram", {})
            if tg.get("bot_token") and tg.get("chat_id"):
                break
        except Exception:
            pass
    if not tg.get("enabled", False):
        return
    if not tg.get("notify_system", True):
        return
    token = tg.get("bot_token", "").strip()
    chat_id = tg.get("chat_id", "").strip()
    if not token or not chat_id:
        return
    try:
        _req.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": f"[SYSTEM] {message}"},
            timeout=(5.0, 15.0),
        )
    except Exception:
        pass


def main():
    # ── faulthandler 활성화 (C++ segfault 감지) ───────────────────
    os.makedirs(os.path.join(_ROOT, "logs"), exist_ok=True)
    fault_log = open(os.path.join(_ROOT, "logs", "fault.log"), "a", encoding="utf-8")
    faulthandler.enable(file=fault_log)

    from ipc.shared_frame import SharedFrameBuffer, SHM_NAME as FRAME_SHM
    from ipc.shared_state import SharedStateBuffer, SHM_NAME as STATE_SHM

    # ── SharedMemory 잔존 정리 ────────────────────────────────────
    import time as _time
    from multiprocessing.shared_memory import SharedMemory as _SHM
    for name in (FRAME_SHM, STATE_SHM):
        for _ in range(3):
            try:
                existing = _SHM(name=name, create=False)
                existing.close()
                existing.unlink()
                print(f"[main] 잔존 SHM '{name}' 정리 완료", flush=True)
                _time.sleep(0.05)  # Windows: unlink 후 핸들 반환 대기
                break
            except FileNotFoundError:
                break  # 없으면 정상
            except Exception:
                _time.sleep(0.1)

    # ── SharedMemory 생성 ─────────────────────────────────────────
    state_lock = multiprocessing.Lock()
    shared_frame = SharedFrameBuffer(create=True, name=FRAME_SHM)
    shared_state = SharedStateBuffer(create=True, name=STATE_SHM, lock=state_lock)

    # ── IPC 채널 생성 ─────────────────────────────────────────────
    result_queue   = multiprocessing.Queue(maxsize=200)
    cmd_queue      = multiprocessing.Queue(maxsize=50)
    shutdown_event = multiprocessing.Event()
    cmd_event      = multiprocessing.Event()   # cmd_queue에 메시지 도착 알림

    # ── Watchdog 프로세스 spawn ───────────────────────────────────
    from processes.watchdog_process import run as watchdog_run
    watchdog_proc = multiprocessing.Process(
        target=watchdog_run,
        args=(
            result_queue, cmd_queue, shutdown_event,
            state_lock, FRAME_SHM, STATE_SHM,
            os.getpid(),
            "2.0",
            cmd_event,
        ),
        daemon=False,
        name="WatchdogProcess",
    )
    watchdog_proc.start()
    print(f"[main] Watchdog spawn 완료 (PID={watchdog_proc.pid})", flush=True)

    # ── PySide6 QApplication + MainWindow ────────────────────────
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    from ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("KBS Monitoring v2")
    app.setOrganizationName("KBS")

    window = MainWindow(
        result_queue=result_queue,
        cmd_queue=cmd_queue,
        shutdown_event=shutdown_event,
        shared_frame=shared_frame,
        shared_state=shared_state,
        cmd_event=cmd_event,
    )
    window.show()

    # ── 예약 재시작 타이머 (Launcher 단독 관리) ────────────────────
    _last_restart_ts: list = [0.0]  # 마지막 재시작 실행 타임스탬프

    def _parse_exclude_ranges(exclude_str: str):
        """'HH:MM-HH:MM, HH:MM-HH:MM' 파싱 → [(start_min, end_min), ...] (자정 넘김 지원)"""
        ranges = []
        for part in exclude_str.split(","):
            part = part.strip()
            if "-" not in part:
                continue
            try:
                s, e = part.split("-", 1)
                sh, sm = map(int, s.strip().split(":"))
                eh, em = map(int, e.strip().split(":"))
                ranges.append((sh * 60 + sm, eh * 60 + em))
            except Exception:
                pass
        return ranges

    def _in_exclude(now_min: int, ranges) -> bool:
        for s, e in ranges:
            if s <= e:
                if s <= now_min < e:
                    return True
            else:  # 자정 넘김 (예: 23:30-00:30)
                if now_min >= s or now_min < e:
                    return True
        return False

    def _next_restart_time(base_hm: str, interval_h: int) -> datetime.datetime:
        """기준시각 + N×주기 중 현재 이후 가장 가까운 시각 반환"""
        try:
            bh, bm = map(int, base_hm.split(":"))
        except Exception:
            return datetime.datetime.max
        now = datetime.datetime.now()
        base_today = now.replace(hour=bh, minute=bm, second=0, microsecond=0)
        # 오늘 기준시각부터 주기 단위로 앞/뒤 탐색
        delta = datetime.timedelta(hours=interval_h)
        # 가장 최근 지난 기준 시각 계산
        diff_sec = (now - base_today).total_seconds()
        if diff_sec < 0:
            diff_sec += 86400  # 아직 오늘 기준시각 전이면 어제로 간주
            base_today -= datetime.timedelta(days=1)
        cycles_passed = int(diff_sec / delta.total_seconds())
        last_trigger = base_today + delta * cycles_passed
        next_trigger = last_trigger + delta
        return next_trigger

    def _check_scheduled_restart():
        try:
            cfg_path = os.path.join(_ROOT, "config", "kbs_config.json")
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            sys_cfg = cfg.get("system", {})
            if not sys_cfg.get("scheduled_restart_enabled", False):
                return

            base_hm = sys_cfg.get("scheduled_restart_base_time", "03:00").strip()
            interval_h = int(sys_cfg.get("scheduled_restart_interval_hours", 24))
            exclude_str = sys_cfg.get("scheduled_restart_exclude", "")

            next_dt = _next_restart_time(base_hm, interval_h)
            now = datetime.datetime.now()

            # 아직 예정 시각 도달 전
            if now < next_dt:
                return

            # 이미 이 주기에서 실행했으면 스킵 (30초 윈도우 내 중복 방지)
            if _last_restart_ts[0] >= next_dt.timestamp():
                return

            # 제외 시간대 확인
            now_min = now.hour * 60 + now.minute
            exclude_ranges = _parse_exclude_ranges(exclude_str)
            if _in_exclude(now_min, exclude_ranges):
                return  # 제외 시간대 종료 후 다음 30초 틱에서 재시도

            _last_restart_ts[0] = now.timestamp()
            label = now.strftime("%Y-%m-%d %H:%M")
            print(f"[main] 예약 재시작 실행: {label}", flush=True)
            _send_system_telegram_main(
                f"KBS Monitoring v2 예약 재시작 실행 ({label})"
            )
            window.close()
        except Exception:
            pass

    restart_timer = QTimer()
    restart_timer.setInterval(30_000)  # 30초 주기 확인
    restart_timer.timeout.connect(_check_scheduled_restart)
    restart_timer.start()

    exit_code = 0
    watchdog_abnormal = False
    try:
        exit_code = app.exec()
    finally:
        restart_timer.stop()

        # ── 정상 종료 처리 ────────────────────────────────────────
        shutdown_event.set()

        # Watchdog 종료 대기
        watchdog_proc.join(timeout=8.0)
        if watchdog_proc.is_alive():
            print("[main] Watchdog join 타임아웃 → terminate", flush=True)
            watchdog_proc.terminate()
            watchdog_proc.join(timeout=2.0)
            watchdog_abnormal = True

        if watchdog_abnormal:
            _send_system_telegram_main(
                "KBS Monitoring v2 Watchdog 비정상 종료 감지 — 수동 점검 필요"
            )

        # last_exit.json 기록
        _write_last_exit(exit_code, "user" if not watchdog_abnormal else "watchdog_crash")

        # SharedMemory 정리
        try:
            shared_frame.close()
            shared_frame.unlink()
        except Exception:
            pass
        try:
            shared_state.close()
            shared_state.unlink()
        except Exception:
            pass

        fault_log.close()

    return exit_code


def _write_last_exit(exit_code: int, reason: str):
    path = os.path.join(_ROOT, "data", "last_exit.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "exit_time": datetime.datetime.now().isoformat(),
                "exit_code": exit_code,
                "reason":    reason,
                "pid":       os.getpid(),
            }, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
