@echo off
chcp 65001 >nul
powershell -ExecutionPolicy Bypass -File "%~dp0python313_전환.ps1"
echo.
echo [python313_전환.bat] 창이 여기서 멈춰 있으면 정상입니다. 위 내용을 확인하세요.
pause
