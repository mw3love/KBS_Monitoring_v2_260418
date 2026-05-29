@echo off
chcp 65001 >nul
REM ── KBS Monitoring v2 자동 시작 해제 ─────────────────────────
REM "자동시작 등록.bat" 으로 만든 시작프로그램 바로가기를 제거합니다.

set "LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\KBS Monitoring v2.lnk"

if exist "%LNK%" (
    del "%LNK%"
    echo.
    echo  [완료] 자동 시작이 해제되었습니다.
    echo         다음 PC 로그인부터는 자동 실행되지 않습니다.
    echo.
) else (
    echo.
    echo  [안내] 등록된 자동 시작 항목이 없습니다. (이미 해제됨)
    echo.
)
pause
