@echo off
chcp 65001 >nul
REM KBS Monitoring v2 launcher - prefer py launcher, fallback to python.
REM On scheduled restart (exit code 42) auto-relaunch; otherwise exit loop.

REM ── [임시·힙손상 추적] UI 프로세스 인터프리터 손상 범인 특정용 ─────────────
REM   PYTHONMALLOC=debug: 모든 할당 앞뒤 가드바이트 검사 → wild write를 오염 직후
REM   fatal 검출(faulthandler가 fault.log에 파이썬 스택 기록). 디버그 할당자의 C 위반
REM   메시지(위반종류·주소)는 stderr로 나오므로 logs\stderr_debug.txt 에 캡처.
REM   범인 특정 후 이 블록과 stderr 리다이렉트를 원복할 것.
set "PYTHONMALLOC=debug"

set "PYEXE=python"
where py >nul 2>nul && set "PYEXE=py"

REM logs 폴더가 없으면 아래 stderr 리다이렉트가 실패해 python이 시작조차 못 함.
REM (GitHub 신규 다운로드 시 logs\ 는 .gitignore 라 존재하지 않음)
if not exist "%~dp0logs" mkdir "%~dp0logs"

:loop
%PYEXE% "%~dp0main.py" 2>> "%~dp0logs\stderr_debug.txt"
if %errorlevel%==42 (
    echo.
    echo [launcher] scheduled restart - relaunching in 2 seconds...
    timeout /t 2 /nobreak >nul
    goto loop
)
