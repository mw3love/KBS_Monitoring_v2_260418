"""
Chaos 테스트 — Detection 프로세스 강제 kill 후 재spawn 성공률 검증
실제 multiprocessing.Process로 Detection을 spawn하고, 랜덤 시점에 kill 후 재spawn.
Watchdog 없이 독립 실행 (main.py / UI 불필요).

사용법:
  python tests/test_chaos.py                    # 기본: 3라운드, kill까지 8초 대기
  python tests/test_chaos.py --rounds 5 --kill-after 12   # 5라운드, kill까지 12초
  python tests/test_chaos.py --rounds 10 --kill-after 30  # 30초 운영 후 kill, 10회

종료 코드: 0 = 전 라운드 성공, 1 = 실패 있음
"""
import argparse
import multiprocessing
import os
import sys
import time
import queue as _queue_mod
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DETECTION_READY_TIMEOUT = 20.0   # DetectionReady 수신 최대 대기(초)
_SHM_FRAME = "kbs_chaos_frame"
_SHM_STATE = "kbs_chaos_state"


def _cleanup_shm():
    """테스트용 SHM 잔존 정리."""
    from multiprocessing.shared_memory import SharedMemory
    for name in (_SHM_FRAME, _SHM_STATE):
        for _ in range(3):
            try:
                s = SharedMemory(name=name, create=False)
                s.close()
                s.unlink()
                break
            except FileNotFoundError:
                break
            except Exception:
                time.sleep(0.1)


def _setup_ipc():
    """SharedMemory + Queue + Event 생성 및 반환."""
    from ipc.shared_frame import SharedFrameBuffer
    from ipc.shared_state import SharedStateBuffer

    _cleanup_shm()

    state_lock  = multiprocessing.Lock()
    shared_frame = SharedFrameBuffer(create=True, name=_SHM_FRAME)
    shared_state = SharedStateBuffer(create=True, name=_SHM_STATE, lock=state_lock)

    result_queue   = multiprocessing.Queue(maxsize=200)
    cmd_queue      = multiprocessing.Queue(maxsize=50)
    shutdown_event = multiprocessing.Event()
    cmd_event      = multiprocessing.Event()

    return (shared_frame, shared_state, state_lock,
            result_queue, cmd_queue, shutdown_event, cmd_event)


def _spawn_detection(result_queue, cmd_queue, shutdown_event,
                     state_lock, cmd_event):
    """Detection 프로세스 spawn. Process 객체 반환."""
    from processes.detection_process import run as det_run
    p = multiprocessing.Process(
        target=det_run,
        args=(result_queue, cmd_queue, shutdown_event,
              state_lock, _SHM_FRAME, _SHM_STATE),
        kwargs={"version": "chaos-test"},
        daemon=False,
        name="Detection-Chaos",
    )
    p.start()
    return p


def _drain_to_ready(result_queue, timeout: float) -> bool:
    """
    result_queue에서 DetectionReady 메시지를 기다린다.
    timeout 초 내에 수신하면 True, 아니면 False.
    """
    from ipc.messages import DetectionReady
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            msg = result_queue.get(timeout=0.5)
            if isinstance(msg, DetectionReady):
                return True
        except Exception:
            pass
    return False


def _kill_process(p: multiprocessing.Process):
    """플랫폼 무관 강제 종료."""
    try:
        if sys.platform == "win32":
            import ctypes
            PROCESS_TERMINATE = 0x0001
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_TERMINATE, False, p.pid)
            if handle:
                ctypes.windll.kernel32.TerminateProcess(handle, 1)
                ctypes.windll.kernel32.CloseHandle(handle)
        else:
            import signal
            os.kill(p.pid, signal.SIGKILL)
    except Exception:
        p.terminate()
    p.join(timeout=5.0)


def run_chaos(rounds: int, kill_after_sec: float, jitter_sec: float = 2.0):
    """
    메인 Chaos 루프.
    rounds: 총 kill/respawn 반복 횟수
    kill_after_sec: spawn 후 kill까지 기본 대기 시간
    jitter_sec: kill 타이밍에 ±jitter_sec 랜덤 추가
    """
    print(f"\n[Chaos] 시작 — {rounds}라운드, kill 기준 {kill_after_sec}s ±{jitter_sec}s")

    ipc = _setup_ipc()
    (shared_frame, shared_state, state_lock,
     result_queue, cmd_queue, shutdown_event, cmd_event) = ipc

    results = []
    det_proc = None

    try:
        for rnd in range(1, rounds + 1):
            print(f"\n[Chaos] 라운드 {rnd}/{rounds} — Detection spawn")

            det_proc = _spawn_detection(
                result_queue, cmd_queue, shutdown_event, state_lock, cmd_event)

            # DetectionReady 수신 대기
            ready = _drain_to_ready(result_queue, _DETECTION_READY_TIMEOUT)
            if not ready:
                print(f"[Chaos] 라운드 {rnd}: DetectionReady 미수신 (FAIL)")
                results.append(False)
                _kill_process(det_proc)
                det_proc = None
                # SHM 재사용을 위해 프로세스가 정리되길 기다림
                time.sleep(1.0)
                continue

            pid = det_proc.pid
            print(f"[Chaos] 라운드 {rnd}: DetectionReady 수신 (PID={pid}) ✓")

            # 운영 시뮬레이션
            wait_sec = kill_after_sec + random.uniform(-jitter_sec, jitter_sec)
            wait_sec = max(2.0, wait_sec)
            print(f"[Chaos] {wait_sec:.1f}초 운영 후 강제 kill 예정...")
            time.sleep(wait_sec)

            # 강제 kill
            print(f"[Chaos] PID {pid} 강제 kill")
            _kill_process(det_proc)
            det_proc = None
            print(f"[Chaos] 라운드 {rnd}: kill 완료")

            # queue 잔류 메시지 정리
            while True:
                try:
                    result_queue.get_nowait()
                except Exception:
                    break

            if rnd < rounds:
                time.sleep(1.0)   # 다음 spawn 전 짧은 대기
                results.append(True)
            else:
                results.append(True)

    except KeyboardInterrupt:
        print("\n[Chaos] 사용자 중단")
    finally:
        # 정리
        if det_proc and det_proc.is_alive():
            shutdown_event.set()
            det_proc.join(timeout=5.0)
            if det_proc.is_alive():
                _kill_process(det_proc)

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
        _cleanup_shm()

    # 결과 집계
    total   = len(results)
    success = sum(results)
    rate    = (success / total * 100) if total else 0.0

    print(f"\n{'='*50}")
    print(f"[Chaos] 최종 결과: {success}/{total} 성공 ({rate:.0f}%)")
    print(f"{'='*50}")

    if rate < 100.0:
        print("[Chaos] FAIL — 재spawn 성공률 100% 미달")
        return False
    print("[Chaos] PASS — 재spawn 성공률 100%")
    return True


def main():
    multiprocessing.freeze_support()

    parser = argparse.ArgumentParser(description="KBS Monitoring Chaos 테스트")
    parser.add_argument("--rounds",     type=int,   default=3,
                        help="kill/respawn 반복 횟수 (기본 3)")
    parser.add_argument("--kill-after", type=float, default=8.0,
                        help="spawn 후 kill까지 기본 대기 시간(초) (기본 8)")
    parser.add_argument("--jitter",     type=float, default=2.0,
                        help="kill 타이밍 ±jitter(초) 랜덤 추가 (기본 2)")
    args = parser.parse_args()

    ok = run_chaos(
        rounds=args.rounds,
        kill_after_sec=args.kill_after,
        jitter_sec=args.jitter,
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
