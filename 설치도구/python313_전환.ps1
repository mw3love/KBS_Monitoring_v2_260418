param(
    # 실행.bat이 부를 때: 멈춤(Read-Host) 없이 진행, 기존 venv는 지우지 않고 부품만 다시 설치,
    # ffmpeg가 없으면 winget으로 한 번 시도. 손으로 더블클릭하면(-Auto 없음) 예전처럼 venv를 새로 만든다.
    [switch]$Auto
)
$Host.UI.RawUI.WindowTitle = "KBS Monitoring v2 - Python 3.13 전환 (Round 2)"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Stop-Fail([string]$msg, [string]$hint) {
    Write-Host ""
    Write-Host "[오류] $msg" -ForegroundColor Red
    if ($hint) { Write-Host $hint -ForegroundColor White }
    if (-not $Auto) { Read-Host "엔터를 누르면 종료합니다" }
    exit 1
}

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

# 이 스크립트는 설치도구\ 안에 있다 — .venv313·requirements.txt·resources\는 한 단계 위(프로그램 폴더)
$appRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $appRoot ".venv313"
$venvPy = Join-Path $venvPath "Scripts\python.exe"
# 자동 모드이고 venv가 이미 있으면 시스템 Python 3.13은 필요 없다(부품만 다시 맞춘다)
$keepVenv = $Auto -and (Test-Path $venvPy)

# ── 1단계: Python 3.13 확인/설치 ───────────────────
Write-Host "[1/4] Python 3.13 확인 중..." -ForegroundColor Yellow
if ($keepVenv) {
    Write-Host "  기존 .venv313 사용 → 건너뜀" -ForegroundColor Gray
} else {
    $py313Version = py -3.13 --version 2>&1
    if ($LASTEXITCODE -ne 0 -or $py313Version -notmatch "Python 3\.13") {
        Write-Host "  Python 3.13 미설치 → winget으로 설치 중..." -ForegroundColor Gray
        winget install --id Python.Python.3.13 -e --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -ne 0) {
            Stop-Fail "Python 3.13 설치에 실패했습니다." "수동 설치: https://www.python.org/downloads/release/python-3130/ "
        }
        # 방금 설치한 py 런처는 이 창이 시작된 뒤 PATH에 들어갔다 → 레지스트리에서 PATH를 다시 읽는다
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                    [Environment]::GetEnvironmentVariable("Path", "User")
        $py313Version = py -3.13 --version 2>&1
        if ($LASTEXITCODE -ne 0 -or $py313Version -notmatch "Python 3\.13") {
            Stop-Fail "설치 후에도 'py -3.13' 이 확인되지 않습니다." "PC 재시작 후 다시 시도하거나 수동 설치를 확인하세요."
        }
    }
    Write-Host "  $py313Version 확인됨" -ForegroundColor Green
}
Write-Host ""

# ── 2단계: .venv313 생성 ────────────────────────────
Write-Host "[2/4] 가상환경(.venv313) 준비 중..." -ForegroundColor Yellow
if ($keepVenv) {
    Write-Host "  기존 .venv313 유지 → 부품만 다시 맞춥니다" -ForegroundColor Gray
} else {
    if (Test-Path $venvPath) {
        Write-Host "  기존 .venv313 발견 → 삭제 후 새로 생성" -ForegroundColor Gray
        Remove-Item -Recurse -Force $venvPath
    }
    py -3.13 -m venv $venvPath
    if ($LASTEXITCODE -ne 0) {
        Stop-Fail "가상환경 생성에 실패했습니다." ""
    }
    Write-Host "  생성 완료: $venvPath" -ForegroundColor Green
}
Write-Host ""

# ── 3단계: 패키지 설치 (requirements.txt 고정 버전 그대로) ──
Write-Host "[3/4] 패키지 설치 중 (requirements.txt 고정 버전)..." -ForegroundColor Yellow
$reqPath = Join-Path $appRoot "requirements.txt"
& $venvPy -m pip install -r $reqPath
if ($LASTEXITCODE -ne 0) {
    Stop-Fail "패키지 설치 중 문제가 발생했습니다." "위 오류 메시지를 확인한 후 담당자에게 문의하세요."
}
# 설치 도장: 실행.bat이 이 파일과 requirements.txt를 비교해 다르면 다시 설치한다
Copy-Item -Force $reqPath (Join-Path $venvPath "requirements.installed.txt")
Write-Host ""
Write-Host "  패키지 설치 완료" -ForegroundColor Green
Write-Host ""

# ── 4단계: ffmpeg (자동 모드만 — 손으로는 install_ffmpeg.bat) ──
if ($Auto) {
    Write-Host "[4/4] ffmpeg 확인 중 (녹화 영상에 소리 합성용)..." -ForegroundColor Yellow
    # detection/auto_recorder.py:_find_ffmpeg 와 같은 자리 + winget 설치 위치
    $ffLinks = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\ffmpeg.exe"
    $hasFf = (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or
             (Test-Path "C:\KBS_Tools\ffmpeg.exe") -or
             (Test-Path (Join-Path $appRoot "resources\bin\ffmpeg.exe")) -or
             (Test-Path $ffLinks)
    if ($hasFf) {
        Write-Host "  ffmpeg 있음" -ForegroundColor Green
    } elseif (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Host "  [주의] winget이 없어 ffmpeg를 설치하지 못했습니다(녹화에 소리 미포함)." -ForegroundColor DarkYellow
        Write-Host "  나중에 설치도구 폴더의 install_ffmpeg.bat 으로 설치할 수 있습니다." -ForegroundColor Gray
    } else {
        # 기다리지 않는다: 2026-11-18 실측 다운로드가 초당 ~13KB(257MB에 수 시간)라, 기다리면 첫 실행의
        # 감시 시작이 그만큼 늦어진다. 따로 작은 창에서 받게 두고 프로그램은 먼저 켠다. 실행.bat이 PATH에
        # WinGet\Links를 넣어 두고 녹화가 매번 ffmpeg를 찾으므로(auto_recorder._find_ffmpeg), 다 받으면
        # 다음 녹화부터 소리가 들어간다.
        Start-Process -FilePath "winget" -WindowStyle Minimized -ArgumentList @(
            "install", "-e", "--id", "Gyan.FFmpeg",
            "--accept-source-agreements", "--accept-package-agreements")
        Write-Host "  ffmpeg는 작업표시줄의 작은 창에서 따로 내려받는 중입니다(수 분~수 시간)." -ForegroundColor Gray
        Write-Host "  프로그램은 먼저 켭니다. 다 받으면 다음 녹화부터 소리가 들어갑니다." -ForegroundColor Gray
    }
    Write-Host ""
}

# ── 완료 ────────────────────────────────────────────
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  전환 완료!" -ForegroundColor Green
Write-Host ""
if ($Auto) {
    Write-Host "  이어서 프로그램을 켭니다..." -ForegroundColor White
    Write-Host "=============================================" -ForegroundColor Cyan
    exit 0
}
Write-Host "  이제 평소처럼  실행.bat  으로 실행하세요." -ForegroundColor White
Write-Host "  (.venv313 이 있으면 실행.bat 이 자동으로 그 Python을 씁니다)" -ForegroundColor Gray
Write-Host ""
Write-Host "  확인 방법: 기동 후 logs\YYYYMMDD_ui.txt 에서" -ForegroundColor White
Write-Host "    'SYSTEM - EXPERIMENT: ... python=3.13.x' 줄을 확인하세요." -ForegroundColor Gray
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""
Read-Host "엔터를 누르면 종료합니다"
