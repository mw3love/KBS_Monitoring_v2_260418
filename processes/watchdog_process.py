"""
Watchdog 프로세스
Detection 프로세스의 spawn/감시/재spawn 전담.
heartbeat.dat 10초 stale 감지 → Detection kill 후 재spawn.
main(UI) 생존 감시 (30초 주기 psutil.pid_exists) → 사라지면 Detection 정리 + 자신 종료.
shutdown_event set 시 "의도된 종료" 플래그 ON → false-positive respawn 방지.
[SYSTEM] prefix 텔레그램 직접 발송: Detection 재spawn / UI 사망 이벤트.
"""
import json
import logging
import os
import sys
import struct
import time
import multiprocessing

from ipc.messages import DetectionCrashed

_log = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import requests as _requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

_HEARTBEAT_PATH   = os.path.join(_ROOT, "data", "heartbeat.dat")
_CONFIG_PATH      = os.path.join(_ROOT, "config", "kbs_config.json")
_DEFAULT_CFG_PATH = os.path.join(_ROOT, "config", "default_config.json")
_HB_STALE_SEC     = 10.0
# spawn 직후 grace: 새 Detection이 첫 heartbeat를 쓸 시간을 보장한다.
# heartbeat.dat는 프로세스 사망·앱 재시작을 넘어 남으므로, grace 없이 검사하면
# 직전 세션의 묵은 timestamp를 "신규 Detection이 stale"로 오인해 재spawn 폭풍이 난다.
# Detection heartbeat 주기 5초 + startup 여유 → 15초 (stale 10초보다 크게).
_HB_GRACE_SEC     = 15.0
# UI(main) 크래시 시 Detection 고아 시간 단축 위해 30 → 10초 (psutil.pid_exists 부하 미미)
_PARENT_CHECK_SEC = 10.0
_SPAWN_COOLDOWN   = 5.0


# ── 텔레그램 직접 발송 (Watchdog 전용) ───────────────────────────────────────

def _load_telegram_cfg() -> dict:
    """kbs_config.json 또는 default_config.json에서 telegram 설정 로드."""
    for path in (_CONFIG_PATH, _DEFAULT_CFG_PATH):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            tg = cfg.get("telegram", {})
            if tg.get("bot_token") and tg.get("chat_id"):
                return tg
        except Exception:
            pass
    return {}


def _send_system_telegram(message: str, logger=None) -> bool:
    """
    [SYSTEM] prefix 텔레그램 메시지를 직접 HTTP 발송.
    TelegramWorker와 독립적으로 동작 — Detection이 죽어도 송신 가능.
    notify_system 설정이 False면 발송 건너뜀.
    """
    if not _REQUESTS_AVAILABLE:
        return False
    tg = _load_telegram_cfg()
    if not tg.get("enabled", False):
        return False
    if not tg.get("notify_system", True):
        return False
    token = tg.get("bot_token", "").strip()
    chat_id = (tg.get("system_chat_id", "") or tg.get("chat_id", "")).strip()
    if not token or not chat_id:
        return False

    text = f"<b>[SYSTEM]</b> {message}"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = _requests.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=(5.0, 15.0),
        )
        success = resp.status_code == 200
        if logger:
            if success:
                logger.info(f"[SYSTEM] 텔레그램 발송 완료: {message}")
            else:
                logger.error(f"[SYSTEM] 텔레그램 발송 실패 {resp.status_code}: {message}")
        return success
    except Exception as exc:
        if logger:
            logger.error(f"[SYSTEM] 텔레그램 발송 예외: {exc}: {message}")
        return False


# ── Watchdog 메인 ─────────────────────────────────────────────────────────────

def run(
    result_queue,
    cmd_queue,
    shutdown_event,
    state_lock,
    frame_shm_name: str,
    state_shm_name: str,
    parent_pid: int,
    version: str = "2.7",
    cmd_event=None,
):
    """
    Watchdog 프로세스 메인 함수.
    Detection 프로세스를 spawn하고 heartbeat 감시 루프를 실행.
    """
    from utils.logger import AppLogger
    logger = AppLogger(suffix="_watchdog")

    # faulthandler: 네이티브 폴트/스레드 덤프 전용 파일 (프로세스별 분리).
    import faulthandler
    try:
        os.makedirs(os.path.join(_ROOT, "logs"), exist_ok=True)
        _fault_fp = open(os.path.join(_ROOT, "logs", "fault_watchdog.log"), "a", encoding="utf-8")
        faulthandler.enable(file=_fault_fp)
    except Exception:
        _fault_fp = None

    def log(msg: str):
        logger.info(msg)

    def log_err(msg: str):
        logger.error(msg)

    def _nodrop_put(msg, max_retry: int = 3):
        """drop 금지 메시지 최대 3회 재시도 (docs_ipc_spec.md §2.3)."""
        for _ in range(max_retry):
            try:
                result_queue.put_nowait(msg)
                return
            except Exception:
                time.sleep(0.05)
        try:
            dropped = result_queue.get_nowait()
            result_queue.put_nowait(msg)
            log_err(f"result_queue FULL → {type(dropped).__name__} drop 후 {type(msg).__name__} 강제 삽입")
        except Exception as e:
            log_err(f"result_queue 심각 문제 → {type(msg).__name__} 저장 실패: {e}")

    def tg(msg: str):
        """daemon 스레드로 비동기 발송 — 블로킹 시 heartbeat 감시·shutdown 체크 지연 방지."""
        import threading
        threading.Thread(
            target=_send_system_telegram,
            args=(msg,),
            kwargs={"logger": logger},
            daemon=True,
            name="WatchdogTelegram",
        ).start()

    log(f"Watchdog 시작 (PID={os.getpid()}, parent={parent_pid})")

    _intentional_shutdown = False
    detection_proc = None
    last_spawn_time = 0.0
    last_parent_check = time.time()
    _spawn_count = 0  # 재spawn 횟수 (최초 spawn 제외)

    def _spawn_detection():
        nonlocal detection_proc, last_spawn_time, _spawn_count
        from processes.detection_process import run as detection_run
        p = multiprocessing.Process(
            target=detection_run,
            args=(result_queue, cmd_queue, shutdown_event,
                  state_lock, frame_shm_name, state_shm_name, version,
                  cmd_event),
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

    # ── HEALTH 블랙박스 (UI/detection HEALTH 의 watchdog 짝) ──────────────
    _health_last_t = time.time()
    _health_interval = 600.0   # 10분
    _health_degraded = [False]

    def _capture_onset_watchdog(psutil_err):
        try:
            log_err(f"HEALTH ONSET (WATCHDOG): 네이티브 쿼리 실패 감지 (psutil_err={psutil_err})")
            # 객체생성 프로브는 SIGSEGV 위험(try/except로 못 막음)이라 제외 — 무할당만.
            try:
                none_ok = (None is None) and (type(None).__name__ == "NoneType")
                import gc
                log_err(f"  PROBE: none_singleton_ok={none_ok} gc_counts={gc.get_count()}")
            except Exception as _e:
                log_err(f"  PROBE 실패: {_e!r}")
            if _fault_fp is not None:
                try:
                    faulthandler.dump_traceback(file=_fault_fp, all_threads=True)
                    _fault_fp.flush()
                    log_err("  THREAD DUMP: logs/fault_watchdog.log 에 기록")
                except Exception as _e:
                    log_err(f"  THREAD DUMP 실패: {_e!r}")
        except Exception:
            pass

    def _log_health_watchdog():
        """watchdog 자기 파일에 주기적 건강 스냅샷."""
        try:
            import threading as _th
            nthreads = _th.active_count()
            rss_mb = handles = -1
            psutil_err = ""
            try:
                if PSUTIL_AVAILABLE:
                    p = psutil.Process()
                    rss_mb = int(p.memory_info().rss / (1024 * 1024))
                    try:
                        handles = p.num_handles()
                    except Exception:
                        handles = -1
            except Exception as _pe:
                psutil_err = repr(_pe)
            msg = f"HEALTH WATCHDOG: RSS={rss_mb}MB threads={nthreads} handles={handles}"
            if psutil_err:
                msg += f" psutil_err={psutil_err}"
            log(msg)
            degraded_now = (rss_mb == -1 and PSUTIL_AVAILABLE)
            if degraded_now and not _health_degraded[0]:
                _health_degraded[0] = True
                _capture_onset_watchdog(psutil_err)
            elif not degraded_now and _health_degraded[0]:
                _health_degraded[0] = False
        except Exception:
            pass

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
                tg(f"KBS On-Air Monitoring v{version} UI 비정상 종료 감지 (PID={parent_pid}) → Detection 정리 후 Watchdog 종료")
                _kill_detection(detection_proc)
                break

        # ── Detection 프로세스 생존 확인 ──────────────────────────
        if detection_proc is not None and not detection_proc.is_alive():
            if not _intentional_shutdown:
                elapsed = now - last_spawn_time
                if elapsed >= _SPAWN_COOLDOWN:
                    dead_pid = detection_proc.pid
                    log_err(f"Detection 비정상 종료 감지 (PID={dead_pid}) → 재spawn")
                    tg(f"KBS On-Air Monitoring v{version} Detection 중단 감지 (PID={dead_pid}) → 재spawn 중")
                    _nodrop_put(DetectionCrashed(
                        dead_pid=dead_pid, reason="process_dead", stale_sec=0.0))
                    detection_proc = _spawn_detection()
                    _spawn_count += 1
                    tg(f"KBS On-Air Monitoring v{version} Detection 재spawn 완료 (PID={detection_proc.pid}, 누적 {_spawn_count}회)")
                    last_hb_value = 0.0
                    last_hb_check = now
                else:
                    log_err(f"재spawn 쿨다운 대기 ({_SPAWN_COOLDOWN - elapsed:.1f}초)")

        # ── heartbeat 감시 ────────────────────────────────────────
        # spawn 직후 grace 동안은 검사 건너뜀 (신규 Detection의 첫 heartbeat 대기).
        if (now - last_spawn_time >= _HB_GRACE_SEC) and (now - last_hb_check >= 2.0):
            last_hb_check = now
            hb_time = _read_heartbeat()
            if hb_time > 0 and (now - hb_time) > _HB_STALE_SEC:
                if not _intentional_shutdown:
                    stale_sec = now - hb_time
                    log_err(f"heartbeat stale ({stale_sec:.1f}초) → Detection kill 후 재spawn")
                    tg(f"KBS On-Air Monitoring v{version} Detection heartbeat stale ({stale_sec:.0f}초) → kill 후 재spawn 중")
                    _nodrop_put(DetectionCrashed(
                        dead_pid=detection_proc.pid if detection_proc else 0,
                        reason="heartbeat_stale",
                        stale_sec=stale_sec,
                    ))
                    _kill_detection(detection_proc)
                    if now - last_spawn_time >= _SPAWN_COOLDOWN:
                        detection_proc = _spawn_detection()
                        _spawn_count += 1
                        tg(f"KBS On-Air Monitoring v{version} Detection 재spawn 완료 (PID={detection_proc.pid}, 누적 {_spawn_count}회)")
                        last_hb_value = 0.0

        # ── HEALTH 파일 스냅샷 (10분 주기) ────────────────────────
        if now - _health_last_t >= _health_interval:
            _health_last_t = now
            _log_health_watchdog()

        time.sleep(1.0)

    log("Watchdog 종료 완료")
