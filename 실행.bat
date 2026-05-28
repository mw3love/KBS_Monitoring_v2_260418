@echo off
chcp 65001 >nul
REM KBS Monitoring v2 실행 — py 런처 우선, 없으면 python 폴백 (이식성)
where py >nul 2>nul
if %errorlevel%==0 (
    py "%~dp0main.py"
) else (
    python "%~dp0main.py"
)
