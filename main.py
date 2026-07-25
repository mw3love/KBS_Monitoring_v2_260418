"""
KBS Monitoring v2 — Launcher (= UI 프로세스)
역할: SharedMemory/Queue 생성, Watchdog spawn, QApplication + MainWindow 실행.
faulthandler 활성화, SharedMemory 잔존 정리, last_exit.json 기록.
예약 재시작: 날짜+시각(YYYY-MM-DD HH:MM) 조합으로 중복 방지 (Launcher 단독 관리).
"""
import ctypes
import datetime
import faulthandler
import json
import multiprocessing
import os
import sys
import threading
import time
import traceback


# ── 필수 의존성 사전 점검 (PySide6/OpenCV 없으면 친절한 안내 후 종료) ──────
# install.ps1을 건너뛰고 main.py를 바로 실행한 경우, 운용자가 알아볼 수 있는
# 한국어 메시지로 안내한다. (Python 기본 ImportError 추적은 비기술자에게 불친절.)
def _check_critical_deps():
    missing = []
    try:
        import PySide6  # noqa: F401
    except ImportError:
        missing.append("PySide6")
    try:
        import cv2  # noqa: F401
    except ImportError:
        missing.append("opencv-python")
    if missing:
        msg = (
            f"필수 패키지가 설치되어 있지 않습니다: {', '.join(missing)}\n\n"
            f"install.bat 또는 install.ps1을 실행하여 의존성을 설치하세요.\n"
            f"(상세 절차는 '★ KBS Monitoring v2 설치 안내.txt' 참조)"
        )
        try:
            ctypes.windll.user32.MessageBoxW(
                0, msg, "KBS On-Air Monitoring v2", 0x10,  # MB_ICONERROR
            )
        except Exception:
            print(msg, file=sys.stderr, flush=True)
        sys.exit(1)


_check_critical_deps()

# ── 경로 보장 ──────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# cwd 를 프로젝트 루트로 고정 — PC별 실행 방식(관리자 셸/단축키 시작위치 미지정 등)으로
# cwd 가 System32 같은 곳으로 잡혀 logs/·config/ 상대 경로 쓰기가 PermissionError 나는 것을 방지.
os.chdir(_ROOT)


# ── 단일 인스턴스 가드 ────────────────────────────────────────────
# 뮤텍스 핸들은 프로세스 수명 동안 유지 (OS가 종료/크래시 시 자동 해제 — stale 없음).
_single_instance_handle: object = None


def _check_single_instance() -> bool:
    """
    Windows 네이티브 뮤텍스로 단일 인스턴스 보장.
    True 반환: 이 프로세스가 첫 실행 — 진행 가능.
    False 반환: 이미 실행 중 — 호출자는 즉시 return (안내 메시지는 이 함수가 표시).
    ctypes/Windows API 실패 시 True 반환 (가드 실패가 기동을 막지 않음).
    Local\\ 네임스페이스 사용 — 일반 사용자 권한에서 동작.
    """
    global _single_instance_handle
    try:
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [
            ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR,
        ]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        _single_instance_handle = kernel32.CreateMutexW(
            None, False, r"Local\KBS_Monitoring_v2",
        )
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            try:
                ctypes.windll.user32.MessageBoxW(
                    0,
                    "KBS On-Air Monitoring v2 가 이미 실행 중입니다.\n\n"
                    "기존 창을 확인해 주세요.",
                    "KBS On-Air Monitoring v2",
                    0x00 | 0x40,  # MB_OK | MB_ICONINFORMATION
                )
            except Exception:
                print("[main] 이미 실행 중 — 기존 인스턴스 보호를 위해 종료합니다.",
                      flush=True)
            return False
        return True
    except Exception:
        return True


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
    chat_id = (tg.get("system_chat_id", "") or tg.get("chat_id", "")).strip()
    if not token or not chat_id:
        return
    try:
        _req.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": f"<b>[SYSTEM]</b> {message}",
                  "parse_mode": "HTML"},
            timeout=(5.0, 15.0),
        )
    except Exception:
        pass


# ── UI 손상(onset) 통보 채널 ──────────────────────────────────────
# 손상된 UI 프로세스는 순수 파이썬 객체 생성이 전부 실패하므로 requests(=텔레그램)를
# 직접 쓸 수 없다(4차 로그: onset 시점의 무결성 프로브가 `import gc`에서 이미 실패).
# 손상 상태에서 42시간 동안 계속 작동한 것이 확인된 유일한 경로가 open()+write()이므로,
# UI는 플래그 파일만 떨어뜨리고 텔레그램은 건강한 Watchdog이 대신 보낸다.
# 배경: fix/260526_설정다이얼로그_TypeError_재현불가.md
_DEGRADED_FLAG = os.path.join(_ROOT, "data", "ui_degraded.flag")


def main():
    # ── 단일 인스턴스 가드 (Windows 네이티브 뮤텍스) ─────────────────
    # 이중 실행 시 아래 SHM 잔존정리(unlink)가 돌아가던 인스턴스를 파괴하는 것을 방지.
    # 가드 통과 후의 잔존정리는 "이전 비정상 종료의 잔재"만 안전하게 정리하게 됨.
    if not _check_single_instance():
        return 0

    # ── faulthandler 활성화 (C++ segfault 감지) ───────────────────
    os.makedirs(os.path.join(_ROOT, "logs"), exist_ok=True)
    fault_log = open(os.path.join(_ROOT, "logs", "fault.log"), "a", encoding="utf-8")
    faulthandler.enable(file=fault_log)

    # 이전 세션의 손상 플래그 제거 (남아 있으면 Watchdog이 즉시 오탐 통보)
    os.makedirs(os.path.join(_ROOT, "data"), exist_ok=True)
    try:
        os.remove(_DEGRADED_FLAG)
    except OSError:
        pass

    # ── sys.excepthook 후킹: unhandled exception을 ui 로그에 기록 ──
    # 사유: fix/260526_설정다이얼로그_TypeError_재현불가.md 참조.
    # PySide6 슬롯 등에서 던져진 예외가 stderr로만 나가고 콘솔 닫히면 사라지는
    # 문제를 막기 위해 traceback을 ui 로그 파일에도 함께 남긴다.
    def _append_ui_log(block: str):
        """ui 로그 파일에 한 블록을 append. 어떤 상황에서도 예외를 밖으로 내지 않는다."""
        try:
            today = datetime.datetime.now().strftime("%Y%m%d")
            log_path = os.path.join(_ROOT, "logs", f"{today}_ui.txt")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(block)
                f.flush()
        except Exception:
            pass

    def _format_exc_block(prefix, exc_type, exc_value, exc_tb) -> str:
        """예외를 로그 블록 문자열로. 타입+메시지를 *먼저* 확보해, traceback 포매팅이
        손상으로 실패해도 최소 정보는 보존한다 (헤더만 남던 기존 문제 보완)."""
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        parts = [f"{ts} [ERROR] {prefix}\n"]
        try:
            parts.append(f"  {getattr(exc_type, '__name__', exc_type)}: {exc_value!r}\n")
        except Exception:
            parts.append("  (예외 정보 표현 실패)\n")
        try:
            parts.append("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
        except Exception as _fe:
            parts.append(f"  [traceback 포매팅 실패: {_fe!r}]\n")
        parts.append("\n")
        return "".join(parts)

    _orig_excepthook = sys.excepthook

    def _logging_excepthook(exc_type, exc_value, exc_tb):
        _append_ui_log(_format_exc_block(
            "UNHANDLED EXCEPTION (sys.excepthook)", exc_type, exc_value, exc_tb))
        _orig_excepthook(exc_type, exc_value, exc_tb)

    sys.excepthook = _logging_excepthook

    # threading.excepthook: 워커 스레드(threading.Thread)의 미처리 예외도 파일에 기록.
    # (지금까지 스레드 예외는 콘솔로만 새고 콘솔 닫히면 사라졌음)
    _orig_threadhook = threading.excepthook

    def _logging_threadhook(args):
        tname = getattr(getattr(args, "thread", None), "name", "?")
        _append_ui_log(_format_exc_block(
            f"THREAD EXCEPTION ({tname})", args.exc_type, args.exc_value, args.exc_traceback))
        try:
            _orig_threadhook(args)
        except Exception:
            pass

    threading.excepthook = _logging_threadhook

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
            "2.8",
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
    # Windows 11 네이티브 스타일은 콤보 팝업을 반투명 창으로 렌더링해 QSS 배경을
    # 무시한다(드롭다운 글자 뒤섞임). Fusion 스타일은 QSS를 일관 적용해 이를 해결한다.
    app.setStyle("Fusion")
    app.setApplicationName("KBS On-Air Monitoring")
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
    _restart_requested: list = [False]  # 예약 재시작 트리거 → 배치 래퍼 재가동 신호
    RESTART_EXIT_CODE = 42  # 실행.bat 루프가 이 종료코드를 보면 재가동
    _startup_ts = time.time()  # 기동 시각 — 이 이전의 예정 재시각은 무시(기동·재가동 직후 즉시 재시작 방지)

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

    def _due_restart_time(base_hm: str, interval_h: int):
        """기준시각 + N×주기 중 '현재 시각 이전(포함)' 가장 최근 예정 시각 반환.
        base 파싱 실패 시 None. (이 시각이 _startup_ts·_last_restart_ts보다 미래면 1회 발화)"""
        try:
            bh, bm = map(int, base_hm.split(":"))
        except Exception:
            return None
        now = datetime.datetime.now()
        base_today = now.replace(hour=bh, minute=bm, second=0, microsecond=0)
        delta = datetime.timedelta(hours=max(1, interval_h))
        diff_sec = (now - base_today).total_seconds()
        if diff_sec < 0:
            diff_sec += 86400  # 아직 오늘 기준시각 전이면 어제 기준으로
            base_today -= datetime.timedelta(days=1)
        cycles_passed = int(diff_sec / delta.total_seconds())
        return base_today + delta * cycles_passed  # 가장 최근 지난 예정 시각 (<= now)

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

            due = _due_restart_time(base_hm, interval_h)
            if due is None:
                return
            due_ts = due.timestamp()

            # 기동(또는 직전 재가동) 이전의 예정 시각은 무시 → 즉시 재시작 방지
            if due_ts <= _startup_ts:
                return

            # 이미 이 예정 시각을 처리했으면 스킵 (30초 다중 틱 중복 방지)
            if _last_restart_ts[0] >= due_ts:
                return

            # 제외 시간대 확인
            now = datetime.datetime.now()
            now_min = now.hour * 60 + now.minute
            exclude_ranges = _parse_exclude_ranges(exclude_str)
            if _in_exclude(now_min, exclude_ranges):
                return  # 제외 시간대 종료 후 다음 30초 틱에서 재시도

            _last_restart_ts[0] = due_ts
            label = due.strftime("%Y-%m-%d %H:%M")
            print(f"[main] 예약 재시작 실행: {label}", flush=True)
            _send_system_telegram_main(
                f"KBS On-Air Monitoring v2 예약 재시작 실행 ({label})"
            )
            _restart_requested[0] = True   # 종료 후 RESTART_EXIT_CODE 반환 → 배치 재가동
            window.close()
        except Exception:
            pass

    restart_timer = QTimer()
    restart_timer.setInterval(30_000)  # 30초 주기 확인
    restart_timer.timeout.connect(_check_scheduled_restart)
    restart_timer.start()

    # ── 헬스 스냅샷 (누적 추세 가시화: 스레드 수·핸들·RSS) ───────────
    # 며칠에 걸쳐 threads/handles가 꾸준히 늘면 누수의 직접 단서가 된다.
    # psutil 쿼리가 실패(RSS=-1)로 *전환*되는 순간 = 네이티브 손상 추정 시점 →
    # 그 1회에 한해 전체 스레드 덤프 + 인터프리터 무결성 프로브를 남긴다.
    # (fix/260526 설정다이얼로그 TypeError 의 onset 포착용)
    _health_degraded = [False]

    def _capture_onset_dump(ts, psutil_err):
        """psutil 쿼리 실패 첫 전환 시 1회 심층 덤프. 어떤 예외도 밖으로 내지 않는다."""
        parts = [f"{ts} [ERROR] HEALTH ONSET (UI): 네이티브 쿼리 실패 감지 "
                 f"(psutil_err={psutil_err})\n"]
        # 주의: 객체 생성 프로브(type(...)())는 손상 상태에서 SIGSEGV 위험(try/except로
        # 못 막음) → 의도적으로 제외. 무할당 프로브(None 싱글톤·gc)만 둔다.
        try:
            none_ok = (None is None) and (type(None).__name__ == "NoneType")
            import gc
            parts.append(f"  PROBE: none_singleton_ok={none_ok} gc_counts={gc.get_count()}\n")
        except Exception as _e:
            parts.append(f"  PROBE 실패: {_e!r}\n")
        try:
            faulthandler.dump_traceback(file=fault_log, all_threads=True)
            fault_log.flush()
            parts.append("  THREAD DUMP: logs/fault.log 에 기록\n")
        except Exception as _e:
            parts.append(f"  THREAD DUMP 실패: {_e!r}\n")
        # 손상 플래그 기록 → Watchdog이 1초 루프에서 읽어 텔레그램 발송.
        # open()+write()만 쓴다 (손상 상태에서 작동이 실증된 유일한 경로).
        try:
            with open(_DEGRADED_FLAG, "w", encoding="utf-8") as f:
                f.write(f"{ts}\n{psutil_err}\n")
                f.flush()
            parts.append(f"  손상 플래그 기록: {_DEGRADED_FLAG}\n")
        except Exception as _e:
            parts.append(f"  손상 플래그 기록 실패: {_e!r}\n")
        # 화면 로그창 시도(best-effort) — 새 객체 생성(add_log 내부의 QListWidgetItem 등)이라
        # 손상 상태에서 이 자체도 실패할 수 있음. 되면 현장에서 접속 없이 바로 보이는 보너스,
        # 안 되도 위 텔레그램 플래그 경로가 최종 안전망이라 무해하다.
        try:
            window._log_widget.add_log(
                f"⚠ UI 프로세스 손상 감지 — 알림음·설정창·조작 먹통 가능. "
                f"즉시 재시작 필요 (psutil_err={psutil_err})",
                log_type="error",
                source="시스템",
            )
            parts.append("  화면 로그창 표시: 성공\n")
        except Exception as _e:
            parts.append(f"  화면 로그창 표시 실패(예상 가능한 경로): {_e!r}\n")
        parts.append("\n")
        return "".join(parts)

    def _log_health_snapshot():
        try:
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            nthreads = threading.active_count()
            rss_mb = handles = -1
            psutil_err = ""
            try:
                import psutil
                p = psutil.Process()
                rss_mb = int(p.memory_info().rss / (1024 * 1024))
                try:
                    handles = p.num_handles()  # Windows 전용
                except Exception:
                    handles = -1
            except Exception as _pe:
                psutil_err = repr(_pe)
            line = (f"{ts} [INFO] HEALTH UI: RSS={rss_mb}MB "
                    f"threads={nthreads} handles={handles}")
            if psutil_err:
                line += f" psutil_err={psutil_err}"
            _append_ui_log(line + "\n")

            # onset 캡처: psutil 실패로 처음 전환되는 순간 1회 심층 덤프
            degraded_now = (rss_mb == -1)
            if degraded_now and not _health_degraded[0]:
                _health_degraded[0] = True
                _append_ui_log(_capture_onset_dump(ts, psutil_err))
            elif not degraded_now and _health_degraded[0]:
                _health_degraded[0] = False  # 회복 시 다음 전환도 재포착
                try:
                    os.remove(_DEGRADED_FLAG)
                except OSError:
                    pass
        except Exception:
            pass

    health_timer = QTimer()
    health_timer.setInterval(600_000)  # 10분 주기
    health_timer.timeout.connect(_log_health_snapshot)
    health_timer.start()
    _log_health_snapshot()  # 기동 직후 기준선 1회

    exit_code = 0
    watchdog_abnormal = False
    try:
        exit_code = app.exec()
    finally:
        restart_timer.stop()
        health_timer.stop()

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
                "KBS On-Air Monitoring v2 Watchdog 비정상 종료 감지 — 수동 점검 필요"
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

    if _restart_requested[0]:
        return RESTART_EXIT_CODE   # 배치 래퍼(실행.bat)가 감지해 재가동
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
