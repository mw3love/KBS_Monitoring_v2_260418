"""
Watchdog 프로세스
Detection 프로세스의 spawn/감시/재spawn 전담.
heartbeat.dat 10초 stale 감지 → Detection kill 후 재spawn.
main(UI) 생존 감시 (30초 주기 psutil.pid_exists) → 사라지면 Detection 정리 + 자신 종료.
shutdown_event set 시 "의도된 종료" 플래그 ON → false-positive respawn 방지.

Phase 4에서 텔레그램 직접 발송 및 상세 로직 완성.
"""
import os
import sys
import struct
import time
import multiprocessing
import logging

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

_HEARTBEAT_PATH   = os.path.join(_ROOT, "data", "heartbeat.dat")
_HB_STALE_SEC     = 10.0    # heartbeat 이 시간 이상 갱신 없으면 재spawn
_PARENT_CHECK_SEC = 30.0    # UI 프로세스 생존 확인 주기
_SPAWN_COOLDOWN   = 5.0     # 재spawn 최소 간격 (연속 크래시 루프 방지)


def run(
    result_queue,
    cmd_queue,
    shutdown_event,
    state_lock,
    frame_shm_name: str,
    state_shm_name: str,
    parent_pid: int,
    version: str = "2.0",
):
    """
    Watchdog 프로세스 메인 함수.
    Detection 프로세스를 spawn하고 heartbeat 감시 루프를 실행.
    """
    from utils.logger import AppLogger
    logger = AppLogger(suffix="_watchdog")

    def log(msg: str):
        logger.info(msg)

    def log_err(msg: str):
        logger.error(msg)

    log(f"Watchdog 시작 (PID={os.getpid()}, parent={parent_pid})")

    _intentional_shutdown = False
    detection_proc = None
    last_spawn_time = 0.0
    last_parent_check = time.time()

    def _spawn_detection():
        nonlocal detection_proc, last_spawn_time
        from processes.detection_process import run as detection_run
        p = multiprocessing.Process(
            target=detection_run,
            args=(result_queue, cmd_queue, shutdown_event,
                  state_lock, frame_shm_name, state_shm_name, version),
            daemon=False,
            name="DetectionProcess",
        )
        p.start()
        last_spawn_time = time.time()
        log(f"Detection spawn 완료 (PID={p.pid})")
        return p

    def _kill_detection(proc):
        if proc is None or not proc.is_alive():
            return
        log(f"Detection 종료 중 (PID={proc.pid})")
        proc.terminate()
        proc.join(timeout=3.0)
        if proc.is_alive():
            log_err("Detection terminate 실패 → kill")
            proc.kill()
            proc.join(timeout=2.0)

    def _read_heartbeat() -> float:
        """heartbeat.dat 마지막 갱신 시각 반환. 파일 없으면 0."""
        try:
            with open(_HEARTBEAT_PATH, "rb") as f:
                return struct.unpack("<d", f.read(8))[0]
        except Exception:
            return 0.0

    # 최초 Detection spawn
    detection_proc = _spawn_detection()
    last_hb_check = time.time()
    last_hb_value = _read_heartbeat()

    while True:
        now = time.time()

        # ── shutdown_event 감지 ────────────────────────────────────
        if shutdown_event is not None and shutdown_event.is_set():
            log("shutdown_event 감지 → 의도된 종료")
            _intentional_shutdown = True
            _kill_detection(detection_proc)
            break

        # ── UI 프로세스 생존 확인 (30초 주기) ──────────────────────
        if now - last_parent_check >= _PARENT_CHECK_SEC:
            last_parent_check = now
            if PSUTIL_AVAILABLE and not psutil.pid_exists(parent_pid):
                log_err(f"UI 프로세스(PID={parent_pid}) 사라짐 → Watchdog 종료")
                _kill_detection(detection_proc)
                break

        # ── Detection 프로세스 생존 확인 ──────────────────────────
        if detection_proc is not None and not detection_proc.is_alive():
            if not _intentional_shutdown:
                elapsed = now - last_spawn_time
                if elapsed >= _SPAWN_COOLDOWN:
                    log_err("Detection 비정상 종료 감지 → 재spawn")
                    detection_proc = _spawn_detection()
                    last_hb_value = 0.0
                    last_hb_check = now
                else:
                    log_err(f"재spawn 쿨다운 대기 ({_SPAWN_COOLDOWN - elapsed:.1f}초)")

        # ── heartbeat 감시 ────────────────────────────────────────
        if now - last_hb_check >= 2.0:
            last_hb_check = now
            hb_time = _read_heartbeat()
            if hb_time > 0 and (now - hb_time) > _HB_STALE_SEC:
                if not _intentional_shutdown:
                    log_err(
                        f"heartbeat stale ({now - hb_time:.1f}초) → "
                        "Detection kill 후 재spawn"
                    )
                    _kill_detection(detection_proc)
                    if now - last_spawn_time >= _SPAWN_COOLDOWN:
                        detection_proc = _spawn_detection()
                        last_hb_value = 0.0

        time.sleep(1.0)

    log("Watchdog 종료 완료")
