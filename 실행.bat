@echo off
chcp 65001 >nul
REM KBS Monitoring v2 launcher - prefer py launcher, fallback to python.
REM On scheduled restart (exit code 42) auto-relaunch; otherwise exit loop.

REM [TEMP - heap corruption trace] identify UI interpreter corruption culprit.
REM   PYTHONMALLOC=debug: guard bytes around every alloc -> detect wild write
REM   immediately as fatal (faulthandler writes python stack to fault.log).
REM   The debug allocator's C-violation message goes to stderr -> captured in
REM   logs\stderr_debug.txt. Revert this block and the stderr redirect after
REM   the culprit is identified.
REM   (ASCII-only comments: non-ASCII REM lines break batch parsing on some
REM    PCs under chcp 65001 -> misparsed as commands.)
set "PYTHONMALLOC=debug"

REM [Round 2 - UI heap corruption incident] prefer local .venv313 (Python 3.13
REM downgrade experiment) if present, so switching to it is just "create the
REM venv" with no launcher edit needed on the incident PC. Absent -> unchanged
REM behavior (system python/py), so other stations are unaffected.
set "PYEXE=python"
where py >nul 2>nul && set "PYEXE=py"
if exist "%~dp0.venv313\Scripts\python.exe" set "PYEXE=%~dp0.venv313\Scripts\python.exe"

REM Create logs\ first: without it the stderr redirect below fails before
REM python even starts. logs\ is .gitignore'd so a fresh GitHub clone lacks it.
if not exist "%~dp0logs" mkdir "%~dp0logs"

:loop
"%PYEXE%" "%~dp0main.py" 2>> "%~dp0logs\stderr_debug.txt"
if %errorlevel%==42 (
    echo.
    echo [launcher] scheduled restart - relaunching in 2 seconds...
    timeout /t 2 /nobreak >nul
    goto loop
)
