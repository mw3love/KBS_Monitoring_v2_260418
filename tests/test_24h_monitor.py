"""
24시간 연속 실행 모니터링 스크립트
실행 중인 KBS Monitoring 프로세스(main.py)의 RSS 메모리 + DIAG 로그를 주기적으로 관찰.
결과는 logs/monitor_24h_YYYYMMDD_HHMMSS.csv 에 저장되고 콘솔에 매 시간 요약 출력.

사용법:
  # 앱 실행 후 별도 터미널에서:
  python tests/test_24h_monitor.py
  python tests/test_24h_monitor.py --interval 60 --duration 86400
  python tests/test_24h_monitor.py --interval 30 --duration 3600   # 단축 테스트 (1시간)

옵션:
  --interval  INT   샘플링 주기(초), 기본 60
  --duration  INT   총 관찰 시간(초), 기본 86400 (24시간)
  --baseline-min INT  시작 후 이 시간(분) 동안 RSS 기준치 측정, 기본 5
"""
import argparse
import csv
import datetime
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    import psutil
    PSUTIL_OK = True
except ImportError:
    PSUTIL_OK = False
    print("[경고] psutil 미설치 — RSS 측정 불가 (pip install psutil)")


# ── 프로세스 탐색 ─────────────────────────────────────────────────────────────

def _find_kbs_processes():
    """
    실행 중인 KBS Monitoring 프로세스 탐색.
    반환: {role: psutil.Process} — role은 'main', 'detection', 'watchdog' 중 하나.

    탐색 전략:
    1) main 프로세스를 cmdline으로 탐색 (직접 실행 → 경로 포함)
    2) main의 자손 프로세스 전체(recursive=True)에서 watchdog·detection 식별
       - detection은 watchdog의 자식(손자)이므로 recursive 필수
       - 앱이 관리자 권한으로 실행된 경우 children() AccessDenied 가능
         → 폴백: 전체 프로세스에서 main과 같은 Python 인터프리터 + 유사 생성시각 탐색
    """
    result = {}
    if not PSUTIL_OK:
        return result

    # 1단계: main 프로세스 탐색
    _root_lower = _ROOT.lower().replace("\\", "/")
    for proc in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
        try:
            cmd = " ".join(proc.info.get("cmdline") or [])
            cmd_lower = cmd.lower().replace("\\", "/")
            if "main.py" in cmd_lower and _root_lower in cmd_lower:
                result["main"] = proc
                break
            if "main.py" in cmd and "kbs" in cmd_lower:
                result["main"] = proc
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if "main" not in result:
        return result

    # 2단계: main 자손 프로세스(recursive=True) → watchdog·detection 식별
    # detection = watchdog의 자식(손자)이므로 recursive=True 필수
    try:
        descendants = result["main"].children(recursive=True)
        descendants.sort(key=lambda p: p.create_time())
        unidentified = []
        for child in descendants:
            try:
                child_cmd = " ".join(child.cmdline()).lower()
                if "detection_process" in child_cmd:
                    result["detection"] = child
                elif "watchdog_process" in child_cmd:
                    result["watchdog"] = child
                else:
                    unidentified.append(child)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                unidentified.append(child)
        # cmdline 미식별 → 생성 시간 순으로 배정 (watchdog 먼저, detection 나중)
        for child in unidentified:
            if "watchdog" not in result:
                result["watchdog"] = child
            elif "detection" not in result:
                result["detection"] = child
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        # 앱이 관리자 권한으로 실행된 경우 children() 자체가 AccessDenied
        # 폴백: 전체 프로세스에서 main 생성 직후 시작된 Python 프로세스 탐색
        _fallback_find_children(result)

    return result


def _fallback_find_children(result: dict):
    """
    children() AccessDenied 폴백.
    main과 동일한 Python 인터프리터 경로를 쓰고,
    main 생성 시각 이후에 시작된 Python 프로세스를 watchdog·detection으로 추정.
    """
    try:
        main_proc = result["main"]
        main_exe  = main_proc.exe().lower()
        main_ct   = main_proc.create_time()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return

    candidates = []
    for proc in psutil.process_iter(["pid", "exe", "create_time", "cmdline"]):
        try:
            if proc.pid == main_proc.pid:
                continue
            exe = (proc.info.get("exe") or "").lower()
            if exe != main_exe:
                continue
            ct = proc.info.get("create_time", 0)
            if ct <= main_ct:
                continue
            cmd = " ".join(proc.info.get("cmdline") or []).lower()
            if "detection_process" in cmd:
                result["detection"] = proc
            elif "watchdog_process" in cmd:
                result["watchdog"] = proc
            else:
                candidates.append((ct, proc))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    candidates.sort(key=lambda x: x[0])
    for _, proc in candidates:
        if "watchdog" not in result:
            result["watchdog"] = proc
        elif "detection" not in result:
            result["detection"] = proc
        else:
            break


def _rss_mb(proc) -> float:
    """프로세스 RSS(MB). 프로세스 사라지면 -1."""
    try:
        return proc.memory_info().rss / 1024 / 1024
    except Exception:
        return -1.0


def _cpu_pct(proc) -> float:
    try:
        return proc.cpu_percent(interval=None)
    except Exception:
        return -1.0


# ── DIAG 로그 파싱 ────────────────────────────────────────────────────────────

def _parse_diag_log(log_path: str, from_offset: int) -> tuple:
    """
    detection 로그에서 DIAG-IPC 섹션의 result_dropped / queue drop 누적값 파싱.
    반환: (result_dropped, cmd_dropped, new_offset)
    """
    result_dropped = 0
    cmd_dropped    = 0
    new_offset     = from_offset

    if not os.path.exists(log_path):
        return result_dropped, cmd_dropped, new_offset

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(from_offset)
            chunk = f.read(1024 * 1024)   # 최대 1MB씩 읽기
            new_offset = from_offset + len(chunk.encode("utf-8", errors="replace"))

        # DIAG-IPC 라인에서 숫자 추출
        for line in chunk.splitlines():
            if "DIAG-IPC" not in line:
                continue
            m = re.search(r"result_dropped['\"]?\s*[:\s]+(\d+)", line)
            if m:
                result_dropped = int(m.group(1))
            m = re.search(r"cmd_dropped['\"]?\s*[:\s]+(\d+)", line)
            if m:
                cmd_dropped = int(m.group(1))
    except Exception:
        pass

    return result_dropped, cmd_dropped, new_offset


def _detection_log_path() -> str:
    today = datetime.datetime.now().strftime("%Y%m%d")
    return os.path.join(_ROOT, "logs", f"{today}_detection.txt")


# ── RSS 기준치 계산 ───────────────────────────────────────────────────────────

class _BaselineCollector:
    def __init__(self, duration_sec: float):
        self._end = time.time() + duration_sec
        self._samples = []
        self.done = False
        self.value_mb = 0.0

    def feed(self, rss_mb: float):
        if self.done:
            return
        if rss_mb > 0:
            self._samples.append(rss_mb)
        if time.time() >= self._end and self._samples:
            self.value_mb = sum(self._samples) / len(self._samples)
            self.done = True

    def growth_pct(self, current_mb: float) -> float:
        if self.value_mb <= 0:
            return 0.0
        return (current_mb - self.value_mb) / self.value_mb * 100.0


# ── 메인 모니터링 루프 ────────────────────────────────────────────────────────

def run_monitor(interval_sec: int, duration_sec: int, baseline_min: int):
    ts_start = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(os.path.join(_ROOT, "logs"), exist_ok=True)
    csv_path = os.path.join(_ROOT, "logs", f"monitor_24h_{ts_start}.csv")

    print(f"[Monitor] 시작: {ts_start}")
    print(f"[Monitor] 설정: interval={interval_sec}s, duration={duration_sec}s "
          f"({duration_sec/3600:.1f}h), baseline={baseline_min}m")
    print(f"[Monitor] CSV: {csv_path}")

    fieldnames = [
        "timestamp", "elapsed_h",
        "main_rss_mb", "main_cpu_pct",
        "detect_rss_mb", "detect_cpu_pct",
        "watchdog_rss_mb",
        "rss_growth_pct",
        "result_dropped_total", "cmd_dropped_total",
        "procs_alive",
    ]

    baseline = _BaselineCollector(duration_sec=baseline_min * 60)
    log_offset = 0
    cumulative_dropped = 0
    cumulative_cmd_dropped = 0
    start_time = time.time()
    end_time   = start_time + duration_sec
    next_hourly_report = start_time + 3600
    hour_max_rss = 0.0
    hour_min_rss = float("inf")

    # psutil 첫 cpu_percent 호출 (0.0 반환 버림)
    if PSUTIL_OK:
        for proc in _find_kbs_processes().values():
            try:
                proc.cpu_percent(interval=None)
            except Exception:
                pass

    with open(csv_path, "w", newline="", encoding="utf-8") as csvf:
        writer = csv.DictWriter(csvf, fieldnames=fieldnames)
        writer.writeheader()
        csvf.flush()

        try:
            while time.time() < end_time:
                sample_ts = datetime.datetime.now().isoformat(timespec="seconds")
                elapsed_h = (time.time() - start_time) / 3600.0

                procs = _find_kbs_processes()
                main_rss      = _rss_mb(procs["main"])      if "main"      in procs else -1.0
                det_rss       = _rss_mb(procs["detection"]) if "detection" in procs else -1.0
                wd_rss        = _rss_mb(procs["watchdog"])  if "watchdog"  in procs else -1.0
                main_cpu      = _cpu_pct(procs["main"])     if "main"      in procs else -1.0
                det_cpu       = _cpu_pct(procs["detection"])if "detection" in procs else -1.0
                procs_alive   = len(procs)

                baseline.feed(main_rss)
                growth_pct = baseline.growth_pct(main_rss) if baseline.done else 0.0

                # DIAG 로그 파싱
                log_path = _detection_log_path()
                rd, cd, log_offset = _parse_diag_log(log_path, log_offset)
                if rd > 0:
                    cumulative_dropped = rd       # DIAG에서 읽은 값은 누적 절댓값
                if cd > 0:
                    cumulative_cmd_dropped = cd

                row = {
                    "timestamp":            sample_ts,
                    "elapsed_h":            f"{elapsed_h:.3f}",
                    "main_rss_mb":          f"{main_rss:.1f}",
                    "main_cpu_pct":         f"{main_cpu:.1f}",
                    "detect_rss_mb":        f"{det_rss:.1f}",
                    "detect_cpu_pct":       f"{det_cpu:.1f}",
                    "watchdog_rss_mb":      f"{wd_rss:.1f}",
                    "rss_growth_pct":       f"{growth_pct:.1f}",
                    "result_dropped_total": cumulative_dropped,
                    "cmd_dropped_total":    cumulative_cmd_dropped,
                    "procs_alive":          procs_alive,
                }
                writer.writerow(row)
                csvf.flush()

                if main_rss > 0:
                    hour_max_rss = max(hour_max_rss, main_rss)
                    if hour_min_rss == float("inf"):
                        hour_min_rss = main_rss
                    else:
                        hour_min_rss = min(hour_min_rss, main_rss)

                # 시간당 요약
                if time.time() >= next_hourly_report:
                    next_hourly_report += 3600
                    _print_hourly(elapsed_h, main_rss, growth_pct,
                                  cumulative_dropped, hour_min_rss, hour_max_rss,
                                  procs_alive)
                    hour_max_rss = 0.0
                    hour_min_rss = float("inf")
                else:
                    # 매 샘플 간단 출력
                    status = "OK" if procs_alive >= 2 else "경고: 프로세스 감소"
                    print(f"[{sample_ts}] "
                          f"main={main_rss:.0f}MB (+{growth_pct:.1f}%) "
                          f"det={det_rss:.0f}MB "
                          f"drop={cumulative_dropped} "
                          f"procs={procs_alive} {status}")

                time.sleep(interval_sec)

        except KeyboardInterrupt:
            print("\n[Monitor] 사용자 중단")

    # 최종 요약
    elapsed_h = (time.time() - start_time) / 3600.0
    print(f"\n{'='*60}")
    print(f"[Monitor] 완료 — 경과 {elapsed_h:.2f}h")
    print(f"[Monitor] CSV 저장: {csv_path}")

    # 합격/불합격 판정 (PROGRESS.md 기준: RSS 증가 < 5%)
    if baseline.done and main_rss > 0:
        final_growth = baseline.growth_pct(main_rss)
        if final_growth < 5.0:
            print(f"[Monitor] PASS — RSS 증가 {final_growth:.1f}% < 5%")
        else:
            print(f"[Monitor] FAIL — RSS 증가 {final_growth:.1f}% >= 5%")
    if cumulative_dropped > 0:
        print(f"[Monitor] 경고: result_queue drop 누적 {cumulative_dropped}건")
    else:
        print("[Monitor] result_queue drop 없음")


def _print_hourly(elapsed_h, current_rss, growth_pct,
                  dropped, hour_min, hour_max, procs_alive):
    print(f"\n{'─'*60}")
    print(f"[시간당 보고] 경과 {elapsed_h:.1f}h")
    print(f"  main RSS: {current_rss:.1f}MB (기준 대비 +{growth_pct:.1f}%)")
    print(f"  이 시간 RSS 범위: {hour_min:.1f} ~ {hour_max:.1f}MB")
    print(f"  result_queue drop 누적: {dropped}건")
    print(f"  생존 프로세스: {procs_alive}개")
    status = "PASS" if growth_pct < 5.0 else "WARN(RSS↑)"
    print(f"  판정: {status}")
    print(f"{'─'*60}\n")


def main():
    parser = argparse.ArgumentParser(description="KBS Monitoring 24시간 메모리 모니터")
    parser.add_argument("--interval",     type=int, default=60,
                        help="샘플링 주기(초), 기본 60")
    parser.add_argument("--duration",     type=int, default=86400,
                        help="총 관찰 시간(초), 기본 86400 (24h)")
    parser.add_argument("--baseline-min", type=int, default=5,
                        help="기준치 측정 기간(분), 기본 5")
    args = parser.parse_args()

    if not PSUTIL_OK:
        print("[오류] psutil이 필요합니다: pip install psutil")
        sys.exit(1)

    procs = _find_kbs_processes()
    if not procs:
        print("[경고] 실행 중인 KBS Monitoring 프로세스를 찾지 못했습니다.")
        print("  main.py를 먼저 실행하거나, 프로세스 이름/경로를 확인하세요.")
        print("  모니터링을 계속 진행합니다 (프로세스 시작을 기다립니다).")

    run_monitor(
        interval_sec=args.interval,
        duration_sec=args.duration,
        baseline_min=args.baseline_min,
    )


if __name__ == "__main__":
    main()
