@echo off
setlocal

echo ================================================
echo  KBS Monitoring v2 - ffmpeg 설치 스크립트
echo ================================================
echo.

where winget >nul 2>&1
if errorlevel 1 (
    echo [오류] winget이 설치되어 있지 않습니다.
    echo.
    echo Windows 10/11에서 Microsoft Store의 "앱 설치 관리자"를 업데이트하거나
    echo 아래 페이지에서 수동으로 ffmpeg를 설치하세요:
    echo   https://www.gyan.dev/ffmpeg/builds/
    echo.
    pause
    exit /b 1
)

echo [1/2] winget으로 ffmpeg 설치 중...
echo.
winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
set INSTALL_RC=%errorlevel%
echo.

if not "%INSTALL_RC%"=="0" (
    echo [참고] winget 종료 코드 %INSTALL_RC% - 이미 설치되어 있을 수 있습니다.
    echo 아래 검증 결과를 확인하세요.
    echo.
)

echo [2/2] 설치 검증 (ffmpeg -version)
echo ------------------------------------------------
cmd /c "ffmpeg -version"
set VERIFY_RC=%errorlevel%
echo ------------------------------------------------
echo.

if "%VERIFY_RC%"=="0" (
    echo [완료] ffmpeg 설치가 확인되었습니다.
    echo 새로 여는 터미널/앱부터 ffmpeg를 사용할 수 있습니다.
) else (
    echo [안내] 현재 창에서는 ffmpeg가 인식되지 않습니다.
    echo 새 명령 프롬프트를 열어 'ffmpeg -version' 으로 다시 확인하세요.
    echo 그래도 인식되지 않으면 재로그인 또는 재부팅이 필요할 수 있습니다.
)

echo.
pause
endlocal
