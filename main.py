"""
KBS Monitoring v2 — Launcher (= UI 프로세스)
역할: SharedMemory/Queue 생성, Watchdog spawn, QApplication + MainWindow 실행.
faulthandler 활성화, SharedMemory 잔존 정리, last_exit.json 기록.
"""
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


def main():
    # ── faulthandler 활성화 (C++ segfault 감지) ───────────────────
    os.makedirs(os.path.join(_ROOT, "logs"), exist_ok=True)
    fault_log = open(os.path.join(_ROOT, "logs", "fault.log"), "a", encoding="utf-8")
    faulthandler.enable(file=fault_log)

    from ipc.shared_frame import SharedFrameBuffer, SHM_NAME as FRAME_SHM
    from ipc.shared_state import SharedStateBuffer, SHM_NAME as STATE_SHM

    # ── SharedMemory 잔존 정리 ────────────────────────────────────
    for name, cls in ((FRAME_SHM, SharedFrameBuffer), (STATE_SHM, SharedStateBuffer)):
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
            os.getpid(),   # parent_pid = UI 프로세스 PID
            "2.0",
        ),
        daemon=False,
        name="WatchdogProcess",
    )
    watchdog_proc.start()
    print(f"[main] Watchdog spawn 완료 (PID={watchdog_proc.pid})", flush=True)

    # ── PySide6 QApplication + MainWindow ────────────────────────
    from PySide6.QtWidgets import QApplication
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

    exit_code = 0
    try:
        exit_code = app.exec()
    finally:
        # ── 정상 종료 처리 ────────────────────────────────────────
        shutdown_event.set()

        # Watchdog 종료 대기
        watchdog_proc.join(timeout=8.0)
        if watchdog_proc.is_alive():
            print("[main] Watchdog join 타임아웃 → terminate", flush=True)
            watchdog_proc.terminate()
            watchdog_proc.join(timeout=2.0)

        # last_exit.json 기록
        _write_last_exit(exit_code, "user")

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
    import datetime
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
