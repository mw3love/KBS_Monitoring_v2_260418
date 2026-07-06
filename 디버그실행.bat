@echo off
chcp 65001 >nul
REM KBS Monitoring v2 debug run - capture stderr to debug_error.txt
REM [임시·힙손상 추적] PYTHONMALLOC=debug 로 wild write 즉시 검출 (범인 특정 후 원복)
set "PYTHONMALLOC=debug"
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
