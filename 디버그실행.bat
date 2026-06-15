@echo off
chcp 65001 >nul
REM KBS Monitoring v2 debug run - capture stderr to debug_error.txt
where py >nul 2>nul
if %errorlevel%==0 (
    py "%~dp0main.py" 2> "%~dp0debug_error.txt"
) else (
    python "%~dp0main.py" 2> "%~dp0debug_error.txt"
)
echo.
echo === error output (debug_error.txt) ===
type "%~dp0debug_error.txt"
echo.
pause
