@echo off
REM ASCII-only content on purpose: chcp 65001 does not reliably take effect
REM before the batch parser reads this file on some Windows builds (real
REM case: Windows 11, admin-elevated run) -> non-ASCII bytes on the command
REM line itself get misdecoded and cmd fails with "not recognized". %~dpn0
REM (drive+path+basename of THIS file) is resolved by cmd internally, not by
REM re-parsing text bytes, so it sidesteps the issue entirely even though the
REM actual filename is Korean. See fix/260526_...md for the failure history.
chcp 65001 >nul
powershell -ExecutionPolicy Bypass -File "%~dpn0.ps1"
echo.
echo [python313 setup] If this window is paused here, that is normal - check the output above.
pause
