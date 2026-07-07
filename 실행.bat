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

set "PYEXE=python"
where py >nul 2>nul && set "PYEXE=py"

REM Create logs\ first: without it the stderr redirect below fails before
REM python even starts. logs\ is .gitignore'd so a fresh GitHub clone lacks it.
if not exist "%~dp0logs" mkdir "%~dp0logs"

:loop
%PYEXE% "%~dp0main.py" 2>> "%~dp0logs\stderr_debug.txt"
if %errorlevel%==42 (
    echo.
    echo [launcher] scheduled restart - relaunching in 2 seconds...
    timeout /t 2 /nobreak >nul
    goto loop
)
