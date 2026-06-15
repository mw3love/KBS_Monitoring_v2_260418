@echo off
chcp 65001 >nul
REM KBS Monitoring v2 launcher - prefer py launcher, fallback to python.
REM On scheduled restart (exit code 42) auto-relaunch; otherwise exit loop.
set "PYEXE=python"
where py >nul 2>nul && set "PYEXE=py"

:loop
%PYEXE% "%~dp0main.py"
if %errorlevel%==42 (
    echo.
    echo [launcher] scheduled restart - relaunching in 2 seconds...
    timeout /t 2 /nobreak >nul
    goto loop
)
