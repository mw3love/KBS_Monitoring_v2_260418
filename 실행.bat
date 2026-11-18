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

REM Create logs\ first: without it the stderr redirect below (and the venv
REM fallback notice) fail before python even starts. logs\ is .gitignore'd
REM so a fresh GitHub clone lacks it.
if not exist "%~dp0logs" mkdir "%~dp0logs"

REM [Round 2 - UI heap corruption incident] prefer local .venv313 (Python 3.13
REM downgrade experiment) if present, so switching to it is just "create the
REM venv" with no launcher edit needed on the incident PC. Absent -> unchanged
REM behavior (system python/py), so other stations are unaffected.
REM   NOT silent: a fresh git clone always drops .venv313 (gitignored) since
REM   it is untracked. That is exactly how this launcher silently regressed
REM   back to system Python 3.14 after the 2026-08-07 redeploy and led to
REM   the 2026-08-11 UI heap corruption recurrence (6th occurrence; see
REM   fix/260526_settings_dialog_typeerror.md sec.14). So the fallback now
REM   announces itself loudly instead of failing quietly.
REM [One-click setup, 2026-11-18] On a new PC (no .venv313) or after
REM requirements.txt changed, run the setup script with -Auto first: Python
REM 3.13 + .venv313 + pinned packages + ffmpeg, then launch as usual. The
REM setup script has a Korean filename, so it is found by an ASCII wildcard
REM (this file must stay ASCII-only). The stamp file is the copy of
REM requirements.txt the setup script leaves inside .venv313 on success.
REM Setup failure never blocks launch: monitoring starts with whatever
REM interpreter exists and the startup self-check lists missing parts.
set "NEED_SETUP="
if not exist "%~dp0.venv313\Scripts\python.exe" set "NEED_SETUP=.venv313 missing"
if not defined NEED_SETUP if not exist "%~dp0.venv313\requirements.installed.txt" set "NEED_SETUP=install stamp missing"
if defined NEED_SETUP goto find_setup
fc /b "%~dp0requirements.txt" "%~dp0.venv313\requirements.installed.txt" >nul 2>nul
if errorlevel 1 set "NEED_SETUP=requirements.txt changed"
if not defined NEED_SETUP goto setup_done
:find_setup
set "SETUP_PS1="
for %%F in ("%~dp0python313_*.ps1") do set "SETUP_PS1=%%~fF"
if defined SETUP_PS1 goto run_setup
echo [launcher] NOTICE: setup needed - %NEED_SETUP% - but setup script not found, skipping
echo [launcher] NOTICE: setup needed - %NEED_SETUP% - but setup script not found, skipping >> "%~dp0logs\stderr_debug.txt"
goto setup_done
:run_setup
echo [launcher] setup: %NEED_SETUP% - installing now. First time takes 5-10 min and needs internet.
echo [launcher] setup start: %NEED_SETUP% >> "%~dp0logs\stderr_debug.txt"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SETUP_PS1%" -Auto
set "SETUP_RC=%errorlevel%"
if not "%SETUP_RC%"=="0" goto setup_failed
echo [launcher] setup done >> "%~dp0logs\stderr_debug.txt"
goto setup_done
:setup_failed
echo [launcher] NOTICE: setup failed rc=%SETUP_RC% - continuing with the available interpreter
echo [launcher] NOTICE: setup failed rc=%SETUP_RC% - continuing with the available interpreter >> "%~dp0logs\stderr_debug.txt"
:setup_done
REM winget portable installs such as ffmpeg land in WinGet\Links; this
REM console's PATH predates a fresh install, so add it for this session.
set "PATH=%PATH%;%LOCALAPPDATA%\Microsoft\WinGet\Links"

set "PYEXE=python"
where py >nul 2>nul && set "PYEXE=py"
if exist "%~dp0.venv313\Scripts\python.exe" (
    set "PYEXE=%~dp0.venv313\Scripts\python.exe"
) else (
    echo [launcher] NOTICE: .venv313 not found - falling back to default interpreter: %PYEXE%
    echo [launcher] NOTICE: .venv313 not found - falling back to default interpreter: %PYEXE% >> "%~dp0logs\stderr_debug.txt"
)

:loop
"%PYEXE%" "%~dp0main.py" 2>> "%~dp0logs\stderr_debug.txt"
if %errorlevel%==42 (
    echo.
    echo [launcher] scheduled restart - relaunching in 2 seconds...
    timeout /t 2 /nobreak >nul
    goto loop
)
