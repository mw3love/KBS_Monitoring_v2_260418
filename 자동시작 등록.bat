@echo off
chcp 65001 >nul
REM ── KBS Monitoring v2 자동 시작 등록 ─────────────────────────
REM 시작프로그램 폴더(shell:startup)에 실행.bat 바로가기를 만들어
REM PC 로그인 시 프로그램이 자동으로 켜지도록 합니다.
REM 관리자 권한 불필요. 해제하려면 "자동시작 해제.bat" 실행.

set "TARGET=%~dp0실행.bat"
set "WORKDIR=%~dp0"
set "LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\KBS Monitoring v2.lnk"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$lnk = $ws.CreateShortcut('%LNK%');" ^
  "$lnk.TargetPath = '%TARGET%';" ^
  "$lnk.WorkingDirectory = '%WORKDIR%';" ^
  "$lnk.WindowStyle = 7;" ^
  "$lnk.Description = 'KBS Monitoring v2 자동 시작';" ^
  "$lnk.Save()"

if %errorlevel%==0 (
    echo.
    echo  [완료] 자동 시작이 등록되었습니다.
    echo         다음 PC 로그인부터 프로그램이 자동으로 실행됩니다.
    echo.
) else (
    echo.
    echo  [실패] 등록 중 오류가 발생했습니다. 담당자에게 문의하세요.
    echo.
)
pause
