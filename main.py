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
    for name in (FRAME_SHM, STATE_SHM):
        try:
            from multiprocessing.shared_memory import SharedMemory
            existing = SharedMemory(name=name, create=False)
            existing.close()
            existing.unlink()
            print(f"[main] 잔존 SHM '{name}' 정리 완료", flush=True)
        except Exception:
            pass

    # ── SharedMemory 생성 ─────────────────────────────────────────
    state_lock = multiprocessing.Lock()
    shared_frame = SharedFrameBuffer(create=True, name=FRAME_SHM)
    shared_state = SharedStateBuffer(create=True, name=STATE_SHM, lock=state_lock)

    # ── IPC 채널 생성 ─────────────────────────────────────────────
    result_queue   = multiprocessing.Queue(maxsize=200)
    cmd_queue      = multiprocessing.Queue(maxsize=50)
    shutdown_event = multiprocessing.Event()

    # ── Watchdog 프로세스 spawn ───────────────────────────────────
    from processes.watchdog_process import run as watchdog_run
    watchdog_proc = multiprocessing.Process(
        target=watchdog_run,
        args=(
            result_queue, cmd_queue, shutdown_event,
            state_lock, FRAME_SHM, STATE_SHM,
            os.getpid(),
            "2.0",
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
    )
    window.show()

    # ── 예약 재시작 타이머 (Launcher 단독 관리) ────────────────────
    _last_restart_key: list = [""]  # 날짜+시각 조합 (리스트로 nonlocal 우회)

    def _check_scheduled_restart():
        try:
            cfg_path = os.path.join(_ROOT, "config", "kbs_config.json")
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            sys_cfg = cfg.get("system", {})
            if not sys_cfg.get("scheduled_restart_enabled", False):
                return
            now = datetime.datetime.now()
            now_hm = now.strftime("%H:%M")
            date_str = now.strftime("%Y-%m-%d")
            for key_name in ("scheduled_restart_time", "scheduled_restart_time_2"):
                target_hm = sys_cfg.get(key_name, "").strip()
                if not target_hm:
                    continue
                restart_key = f"{date_str} {target_hm}"
                if now_hm == target_hm and _last_restart_key[0] != restart_key:
                    _last_restart_key[0] = restart_key
                    print(f"[main] 예약 재시작 실행: {restart_key}", flush=True)
                    _send_system_telegram_main(
                        f"KBS Monitoring v2 예약 재시작 실행 ({restart_key})"
                    )
                    window.close()
                    return
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
