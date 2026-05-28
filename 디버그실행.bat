@echo off
chcp 65001 >nul
REM KBS Monitoring v2 디버그 실행 — stderr 를 debug_error.txt 로 캡처
where py >nul 2>nul
if %errorlevel%==0 (
    py "%~dp0main.py" 2> "%~dp0debug_error.txt"
) else (
    python "%~dp0main.py" 2> "%~dp0debug_error.txt"
)
echo.
echo === 오류 내용 ===
type "%~dp0debug_error.txt"
echo.
pause
