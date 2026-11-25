"""run_loop.ps1(다시 켜기 반복)과 실행.bat 대체 길 시험.

가짜 UI(fake_ui.py — 이름에 main.py를 넣지 않음: 커밋 검사의 running 판정과
Win_Tweaks 살아 있음 판정에 안 걸리게)가 정해 둔 종료 코드 열을 차례로 돌려준다.
진짜 logs/는 건드리지 않는다(-LogDir 임시 폴더). 시계는 재지 않고 기록의 순서·값만 본다.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_LOOP = os.path.join(ROOT, "run_loop.ps1")
RUN_BAT = os.path.join(ROOT, "실행.bat")

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows 전용")

# 가짜 UI: plan.json의 n번째 항목대로 행동하고 runs.txt에 기록을 남긴다.
#   {"code": 1}                  바로 코드 1로 끝남
#   {"code": 1, "run": 5}        5초 돈 뒤 끝남
#   {"code": 1, "child": 3}      3초 사는 자식을 남기고 2초 뒤 끝남(자식은 끝날 때 기록)
FAKE_UI = r'''
import json, os, subprocess, sys, time
d = os.path.dirname(os.path.abspath(__file__))
plan = json.load(open(os.path.join(d, "plan.json"), encoding="utf-8"))
cnt_path = os.path.join(d, "count.txt")
n = int(open(cnt_path).read()) if os.path.exists(cnt_path) else 0
open(cnt_path, "w").write(str(n + 1))
step = plan[min(n, len(plan) - 1)]
def rec(s):
    with open(os.path.join(d, "runs.txt"), "a", encoding="utf-8") as f:
        f.write(s + "\n")
rec(f"start {n} {time.time():.3f}")
if step.get("child"):
    code = ("import time,sys;time.sleep(%s);"
            "open(sys.argv[1],'a').write('childend %%.3f\\n' %% time.time())") % step["child"]
    c = subprocess.Popen([sys.executable, "-c", code, os.path.join(d, "runs.txt")],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    rec(f"child {c.pid}")
    time.sleep(2)
time.sleep(step.get("run", 0))
sys.exit(step["code"])
'''


def _setup(tmp_path, plan):
    (tmp_path / "fake_ui.py").write_text(FAKE_UI, encoding="utf-8")
    (tmp_path / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    logs = tmp_path / "logs"
    logs.mkdir()
    return logs


def _run_loop(tmp_path, logs, **kw):
    args = {"BaseDelaySec": 1, "MaxDelaySec": 4, "StableSec": 3, "ChildWaitSec": 10,
            "RestartDelaySec": 0, "SnapshotSec": 1}
    args.update(kw)
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", RUN_LOOP,
           "-Python", sys.executable, "-Main", str(tmp_path / "fake_ui.py"),
           "-LogDir", str(logs)]
    for k, v in args.items():
        cmd += [f"-{k}", str(v)]
    # 자식이 출력 파이프를 물고 있으면 기다림이 길어지므로 파이프를 쓰지 않는다.
    p = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       stdin=subprocess.DEVNULL, timeout=180)
    return p.returncode


def _launcher_log(logs):
    files = [f for f in os.listdir(logs) if f.endswith("_launcher.txt")]
    assert files, "launcher 기록 파일이 없음"
    return "".join(open(os.path.join(logs, f), encoding="utf-8").read() for f in files)


def _runs(tmp_path):
    return (tmp_path / "runs.txt").read_text(encoding="utf-8").splitlines()


def test_exit_codes_1_42_0(tmp_path):
    logs = _setup(tmp_path, [{"code": 1}, {"code": 42}, {"code": 0}])
    assert _run_loop(tmp_path, logs) == 0
    starts = [r for r in _runs(tmp_path) if r.startswith("start")]
    assert len(starts) == 3
    log = _launcher_log(logs)
    assert "크래시(코드 1" in log
    assert "예약 재시작(코드 42)" in log
    assert "사람이 닫음(코드 0)" in log
    assert (logs / "stderr_debug.txt").exists()


def test_exit_0_runs_once(tmp_path):
    logs = _setup(tmp_path, [{"code": 0}, {"code": 1}])
    assert _run_loop(tmp_path, logs) == 0
    assert len([r for r in _runs(tmp_path) if r.startswith("start")]) == 1


def test_backoff_grows_caps_and_resets(tmp_path):
    plan = [{"code": 1}] * 5 + [{"code": 1, "run": 5}, {"code": 0}]
    logs = _setup(tmp_path, plan)
    assert _run_loop(tmp_path, logs) == 0
    delays = [int(x) for x in re.findall(r"크래시\(코드 1[^)]*\) — (\d+)초 뒤 다시 켬", _launcher_log(logs))]
    # 빠른 크래시 5번: 1, 2, 4, 4, 4 → 5초 돈 뒤(StableSec 3 넘김)의 크래시: 1
    assert delays == [1, 2, 4, 4, 4, 1]


def test_waits_for_child_before_relaunch(tmp_path):
    logs = _setup(tmp_path, [{"code": 1, "child": 3}, {"code": 0}])
    assert _run_loop(tmp_path, logs, BaseDelaySec=0) == 0
    runs = _runs(tmp_path)
    child_end = [i for i, r in enumerate(runs) if r.startswith("childend")]
    second = [i for i, r in enumerate(runs) if r.startswith("start 1")]
    assert child_end and second
    assert child_end[0] < second[0], runs


def test_kills_child_after_wait_limit(tmp_path):
    import psutil
    logs = _setup(tmp_path, [{"code": 1, "child": 120}, {"code": 0}])
    assert _run_loop(tmp_path, logs, BaseDelaySec=0, ChildWaitSec=2) == 0
    child_pid = int([r for r in _runs(tmp_path) if r.startswith("child ")][0].split()[1])
    log = _launcher_log(logs)
    assert re.search(rf"끔.*\b{child_pid}\b", log), log
    time.sleep(0.5)
    assert not psutil.pid_exists(child_pid) or psutil.Process(child_pid).status() == psutil.STATUS_ZOMBIE


def test_bat_falls_back_without_run_loop(tmp_path):
    """run_loop.ps1이 없으면 실행.bat이 NOTICE를 남기고 main.py를 한 번 직접 켠다."""
    shutil.copy(RUN_BAT, tmp_path / "실행.bat")
    (tmp_path / "main.py").write_text(
        "import os\nopen(os.path.join(os.path.dirname(os.path.abspath(__file__)),'runs.txt'),'a').write('start' + chr(10))\n",
        encoding="utf-8")
    # .venv313·설치 스크립트가 없으니 설치 단계는 NOTICE만 남기고 건너뛰고, 기본 파이썬(py/python)으로 켠다.
    p = subprocess.run(["cmd", "/c", str(tmp_path / "실행.bat")], cwd=str(tmp_path),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       stdin=subprocess.DEVNULL, timeout=120)
    runs = (tmp_path / "runs.txt").read_text(encoding="utf-8").splitlines() if (tmp_path / "runs.txt").exists() else []
    assert runs == ["start"], (p.returncode, runs)
    err = (tmp_path / "logs" / "stderr_debug.txt").read_text(encoding="utf-8", errors="replace")
    assert "run_loop" in err


def test_bat_runs_through_run_loop(tmp_path):
    """실행.bat → run_loop.ps1 → main.py(코드 0)면 한 번 켜고 끝나며 launcher 기록이 남는다."""
    shutil.copy(RUN_BAT, tmp_path / "실행.bat")
    shutil.copy(RUN_LOOP, tmp_path / "run_loop.ps1")
    (tmp_path / "main.py").write_text(
        "import os\nopen(os.path.join(os.path.dirname(os.path.abspath(__file__)),'runs.txt'),'a').write('start' + chr(10))\n",
        encoding="utf-8")
    subprocess.run(["cmd", "/c", str(tmp_path / "실행.bat")], cwd=str(tmp_path),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   stdin=subprocess.DEVNULL, timeout=120)
    assert (tmp_path / "runs.txt").read_text(encoding="utf-8").splitlines() == ["start"]
    assert "사람이 닫음(코드 0)" in _launcher_log(tmp_path / "logs")
