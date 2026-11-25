"""
로그인 때 자동 실행 — 시작프로그램 폴더의 바로가기(KBS Monitoring v2.lnk) 만들기·지우기·확인.

설정창 「알림설정 → 자동 재시작」의 「PC 로그인 때 자동 실행」 체크박스가 쓴다.
상태는 설정 파일이 아니라 실제 바로가기로 정한다(백업을 다른 PC에 불러와도 그 PC의 자동 실행이 안 바뀜).
바로가기 이름·값은 2026-11-25 전에 쓰던 등록 bat과 같다 — 그 bat으로 등록해 둔 PC도 체크로 보인다.
바로가기는 PowerShell의 WScript.Shell COM으로 만들고 읽는다(추가 패키지 없음).
시험은 시작프로그램 폴더를 인자로 넘겨 진짜 폴더를 건드리지 않는다(tests/test_autostart.py).
계획 문서: docs/plan/20261125-0953-스스로-켜지고-크래시-뒤-다시-켜기.md
"""
import os
import subprocess

LINK_NAME = "KBS Monitoring v2.lnk"
_DESCRIPTION = "KBS Monitoring v2 자동 실행"
_WINDOW_MINIMIZED = 7
_CREATE_NO_WINDOW = 0x08000000


def default_startup_dir() -> str:
    """현재 사용자의 시작프로그램 폴더."""
    return os.path.join(os.environ.get("APPDATA", ""),
                        "Microsoft", "Windows", "Start Menu", "Programs", "Startup")


def link_path(startup_dir: str | None = None) -> str:
    return os.path.join(startup_dir or default_startup_dir(), LINK_NAME)


def _ps(script: str, env_extra: dict) -> str:
    """PowerShell 한 토막 실행. 값은 환경 변수로 넘겨 따옴표·한글 경로 문제를 피한다."""
    env = dict(os.environ)
    env.update(env_extra)
    prefix = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $ErrorActionPreference = 'Stop'; "
    p = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-Command", prefix + script],
        capture_output=True, env=env, timeout=30, creationflags=_CREATE_NO_WINDOW,
    )
    out = p.stdout.decode("utf-8", errors="replace").strip()
    if p.returncode != 0:
        err = p.stderr.decode("utf-8", errors="replace").strip() or out
        raise RuntimeError(f"PowerShell 실패(코드 {p.returncode}): {err[:300]}")
    return out


def read_target(startup_dir: str | None = None) -> str | None:
    """바로가기가 가리키는 파일 경로. 바로가기가 없으면 None."""
    lnk = link_path(startup_dir)
    if not os.path.exists(lnk):
        return None
    out = _ps("(New-Object -ComObject WScript.Shell).CreateShortcut($env:KBS_LNK).TargetPath",
              {"KBS_LNK": lnk})
    return out or None


def is_enabled(bat_path: str, startup_dir: str | None = None) -> bool:
    """바로가기가 있고 그 대상이 bat_path와 같을 때만 True."""
    target = read_target(startup_dir)
    if not target:
        return False
    norm = lambda p: os.path.normcase(os.path.abspath(p))
    return norm(target) == norm(bat_path)


def enable(bat_path: str, startup_dir: str | None = None) -> None:
    """bat_path를 가리키는 바로가기를 만든다(있으면 덮어씀). 실패하면 RuntimeError."""
    lnk = link_path(startup_dir)
    os.makedirs(os.path.dirname(lnk), exist_ok=True)
    _ps(
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:KBS_LNK); "
        "$s.TargetPath = $env:KBS_TARGET; $s.WorkingDirectory = $env:KBS_WORKDIR; "
        f"$s.WindowStyle = {_WINDOW_MINIMIZED}; $s.Description = $env:KBS_DESC; $s.Save()",
        {"KBS_LNK": lnk, "KBS_TARGET": os.path.abspath(bat_path),
         "KBS_WORKDIR": os.path.dirname(os.path.abspath(bat_path)), "KBS_DESC": _DESCRIPTION},
    )
    if not os.path.exists(lnk):
        raise RuntimeError(f"바로가기가 만들어지지 않음: {lnk}")


def disable(startup_dir: str | None = None) -> None:
    """바로가기를 지운다. 없으면 아무것도 안 한다."""
    lnk = link_path(startup_dir)
    if os.path.exists(lnk):
        os.remove(lnk)
