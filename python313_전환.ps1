$Host.UI.RawUI.WindowTitle = "KBS Monitoring v2 - Python 3.13 전환 (Round 2)"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  KBS Monitoring v2  Python 3.13 전환 (Round 2)" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  이 스크립트는 UI 손상(설정창 무반응) 사고의 근본원인 후보를" -ForegroundColor Gray
Write-Host "  좁히기 위한 실험입니다 — Python 3.13 전용 가상환경(.venv313)을" -ForegroundColor Gray
Write-Host "  새로 만들고, 실행.bat 이 자동으로 그걸 쓰도록 전환합니다." -ForegroundColor Gray
Write-Host "  기존 시스템 Python·다른 프로젝트는 건드리지 않습니다." -ForegroundColor Gray
Write-Host ""

# ── 1단계: Python 3.13 확인/설치 ───────────────────
Write-Host "[1/3] Python 3.13 확인 중..." -ForegroundColor Yellow
$py313Version = py -3.13 --version 2>&1
if ($LASTEXITCODE -ne 0 -or $py313Version -notmatch "Python 3\.13") {
    Write-Host "  Python 3.13 미설치 → winget으로 설치 중..." -ForegroundColor Gray
    winget install --id Python.Python.3.13 -e --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "[오류] Python 3.13 설치에 실패했습니다." -ForegroundColor Red
        Write-Host "수동 설치: https://www.python.org/downloads/release/python-3130/ " -ForegroundColor White
        Read-Host "엔터를 누르면 종료합니다"
        exit 1
    }
    $py313Version = py -3.13 --version 2>&1
    if ($LASTEXITCODE -ne 0 -or $py313Version -notmatch "Python 3\.13") {
        Write-Host ""
        Write-Host "[오류] 설치 후에도 'py -3.13' 이 확인되지 않습니다." -ForegroundColor Red
        Write-Host "PC 재시작 후 다시 시도하거나 수동 설치를 확인하세요." -ForegroundColor Red
        Read-Host "엔터를 누르면 종료합니다"
        exit 1
    }
}
Write-Host "  $py313Version 확인됨" -ForegroundColor Green
Write-Host ""

# ── 2단계: .venv313 생성 ────────────────────────────
Write-Host "[2/3] 가상환경(.venv313) 생성 중..." -ForegroundColor Yellow
$venvPath = Join-Path $PSScriptRoot ".venv313"
if (Test-Path $venvPath) {
    Write-Host "  기존 .venv313 발견 → 삭제 후 새로 생성" -ForegroundColor Gray
    Remove-Item -Recurse -Force $venvPath
}
py -3.13 -m venv $venvPath
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[오류] 가상환경 생성에 실패했습니다." -ForegroundColor Red
    Read-Host "엔터를 누르면 종료합니다"
    exit 1
}
Write-Host "  생성 완료: $venvPath" -ForegroundColor Green
Write-Host ""

# ── 3단계: 패키지 설치 (requirements.txt 고정 버전 그대로) ──
Write-Host "[3/3] 패키지 설치 중 (requirements.txt 고정 버전)..." -ForegroundColor Yellow
$venvPy = Join-Path $venvPath "Scripts\python.exe"
$reqPath = Join-Path $PSScriptRoot "requirements.txt"
& $venvPy -m pip install -r $reqPath
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[오류] 패키지 설치 중 문제가 발생했습니다." -ForegroundColor Red
    Write-Host "위 오류 메시지를 확인한 후 담당자에게 문의하세요." -ForegroundColor Red
    Read-Host "엔터를 누르면 종료합니다"
    exit 1
}
Write-Host ""
Write-Host "  패키지 설치 완료" -ForegroundColor Green
Write-Host ""

# ── 완료 ────────────────────────────────────────────
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  전환 완료!" -ForegroundColor Green
Write-Host ""
Write-Host "  이제 평소처럼  실행.bat  으로 실행하세요." -ForegroundColor White
Write-Host "  (.venv313 이 있으면 실행.bat 이 자동으로 그 Python을 씁니다)" -ForegroundColor Gray
Write-Host ""
Write-Host "  확인 방법: 기동 후 logs\YYYYMMDD_ui.txt 에서" -ForegroundColor White
Write-Host "    'SYSTEM - EXPERIMENT: ... python=3.13.x' 줄을 확인하세요." -ForegroundColor Gray
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""
Read-Host "엔터를 누르면 종료합니다"
