$Host.UI.RawUI.WindowTitle = "KBS Monitoring v2 - 설치 프로그램"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  KBS Monitoring v2  설치 프로그램" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

# ── 1단계: Python 확인 ──────────────────────────────
Write-Host "[1/3] Python 확인 중..." -ForegroundColor Yellow
# py 런처 우선, 없으면 python 시도 (Windows Store 스텁 제외)
$pyCmd = $null
$pythonVersion = $null
$pyVersion = py --version 2>&1
if ($LASTEXITCODE -eq 0 -and $pyVersion -match "Python") {
    $pyCmd = "py"
    $pythonVersion = $pyVersion
} else {
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -eq 0 -and $pythonVersion -match "Python") {
        $pyCmd = "python"
    }
}
if (-not $pyCmd) {
    Write-Host ""
    Write-Host "[오류] Python이 설치되어 있지 않습니다." -ForegroundColor Red
    Write-Host "Python 3.11 이상을 먼저 설치하세요." -ForegroundColor Red
    Write-Host "다운로드: https://www.python.org/downloads/" -ForegroundColor White
    Write-Host ""
    Write-Host "설치 후 이 파일을 다시 실행하세요."
    Read-Host "엔터를 누르면 종료합니다"
    exit 1
}
Write-Host "  $pythonVersion 확인됨  (명령어: $pyCmd)" -ForegroundColor Green
Write-Host ""

# ── 2단계: Python 패키지 설치 ───────────────────────
Write-Host "[2/3] Python 패키지 설치 중..." -ForegroundColor Yellow
Write-Host "  (PySide6, OpenCV, NumPy 등 - 처음 설치 시 수 분 소요)" -ForegroundColor Gray
Write-Host ""
$reqPath = Join-Path $PSScriptRoot "requirements.txt"
& $pyCmd -m pip install -r $reqPath
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[오류] 패키지 설치 중 문제가 발생했습니다." -ForegroundColor Red
    Write-Host "위 오류 메시지를 확인한 후 관리자에게 문의하세요." -ForegroundColor Red
    Read-Host "엔터를 누르면 종료합니다"
    exit 1
}
Write-Host ""
Write-Host "  패키지 설치 완료" -ForegroundColor Green
Write-Host ""

# ── 3단계: ffmpeg 설치 ──────────────────────────────
Write-Host "[3/3] ffmpeg 설치 중... (자동 녹화 오디오 합성용)" -ForegroundColor Yellow
Write-Host "  미설치 시에도 비디오 전용 녹화로 동작합니다." -ForegroundColor Gray
Write-Host ""
winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [주의] ffmpeg 설치 실패 또는 이미 설치되어 있습니다." -ForegroundColor DarkYellow
    Write-Host "  수동 설치: PowerShell에서  winget install ffmpeg  실행" -ForegroundColor Gray
} else {
    Write-Host "  ffmpeg 설치 완료" -ForegroundColor Green
}
Write-Host ""

# ── 완료 ────────────────────────────────────────────
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  설치 완료!" -ForegroundColor Green
Write-Host ""
Write-Host "  실행 방법:  py main.py" -ForegroundColor White
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""
Read-Host "엔터를 누르면 종료합니다"