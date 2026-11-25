# KBS Monitoring v2 다시 켜기 반복 — 실행.bat이 준비를 마친 뒤 부른다.
# main.py를 켜고, 끝나면 종료 코드로 가른다:
#   0  = 사람이 닫음(창 X·윈도우 종료·이미 실행 중) → 멈춤
#   42 = 예약 재시작·설정 불러오기 뒤 다시 켜기 → RestartDelaySec 뒤 다시 켬
#   그 밖 = 크래시 → 남은 자손 프로세스(Watchdog·Detection)가 끝나길 기다린 뒤 간격을 두고 다시 켬
# PowerShell은 시작할 때 이 파일을 통째로 읽으므로, 도는 중에 파일을 고쳐도 어긋나지 않는다
# (bat의 줄 책갈피 함정 — CLAUDE.md 「신규 빌드 배포 시 함정」).
# 계획 문서: docs/plan/20261125-0953-스스로-켜지고-크래시-뒤-다시-켜기.md
# 시험: tests/test_run_loop.py (인자로 가짜 UI·임시 기록 폴더·짧은 대기를 준다)
param(
    [Parameter(Mandatory = $true)][string]$Python,
    [string]$Main = '',
    [string]$LogDir = '',
    [string]$StderrPath = '',
    [int]$BaseDelaySec = 15,
    [int]$MaxDelaySec = 300,
    [int]$StableSec = 120,
    [int]$ChildWaitSec = 30,
    [int]$RestartDelaySec = 2,
    [int]$SnapshotSec = 5
)
$ErrorActionPreference = 'Continue'
# PowerShell 5.1은 param 기본값 안에서 $PSScriptRoot가 비어 있다 — 본문에서 채운다.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Main) { $Main = Join-Path $here 'main.py' }
if (-not $LogDir) { $LogDir = Join-Path $here 'logs' }
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
if (-not $StderrPath) { $StderrPath = Join-Path $LogDir 'stderr_debug.txt' }
$utf8 = New-Object System.Text.UTF8Encoding($false)

function Log([string]$msg) {
    $now = Get-Date
    Write-Host "[launcher] $msg"
    $path = Join-Path $LogDir ($now.ToString('yyyyMMdd') + '_launcher.txt')
    try { [IO.File]::AppendAllText($path, ('[{0}] {1}' -f $now.ToString('yyyy-MM-dd HH:mm:ss'), $msg) + "`r`n", $utf8) } catch { }
}

# 지금 떠 있는 프로세스: PID → 이름·생성 시각·부모 PID
function Get-ProcTable {
    $t = @{}
    foreach ($p in (Get-CimInstance Win32_Process -Property ProcessId, ParentProcessId, Name, CreationDate)) {
        $t[[int]$p.ProcessId] = @{ Name = $p.Name; Created = $p.CreationDate; Parent = [int]$p.ParentProcessId }
    }
    return $t
}

# $known(PID → 이름·생성 시각)에 $rootPid와 이미 아는 PID의 자손을 더한다(덮어쓰지 않고 쌓음).
# 부모가 죽은 고아도 부모 PID 값은 그대로 남으므로, 아는 PID에서 내려가면 찾힌다.
# 자식의 생성 시각이 부모보다 이르면 PID가 재사용된 남의 프로세스라 따라가지 않는다.
function Add-Descendants([int]$rootPid, [hashtable]$known, [hashtable]$table) {
    $kids = @{}
    foreach ($id in $table.Keys) {
        $pp = $table[$id].Parent
        if (-not $kids.ContainsKey($pp)) { $kids[$pp] = New-Object System.Collections.ArrayList }
        [void]$kids[$pp].Add($id)
    }
    $stack = New-Object System.Collections.Stack
    $stack.Push($rootPid)
    foreach ($k in @($known.Keys)) { $stack.Push([int]$k) }
    $seen = @{}
    while ($stack.Count -gt 0) {
        $id = [int]$stack.Pop()
        if ($seen.ContainsKey($id)) { continue }
        $seen[$id] = $true
        if (-not $kids.ContainsKey($id)) { continue }
        $parentCreated = if ($known.ContainsKey($id)) { $known[$id].Created } elseif ($table.ContainsKey($id)) { $table[$id].Created } else { $null }
        foreach ($cid in $kids[$id]) {
            if ($cid -eq $id) { continue }
            $c = $table[$cid]
            if ($parentCreated -and $c.Created -and $c.Created -lt $parentCreated) { continue }
            if (-not $known.ContainsKey($cid)) { $known[$cid] = @{ Name = $c.Name; Created = $c.Created } }
            $stack.Push($cid)
        }
    }
}

# 아는 PID 가운데 아직 살아 있는 것(이름·생성 시각이 같아야 — PID 재사용 가드)
function Get-Alive([hashtable]$known, [hashtable]$table) {
    $alive = @()
    foreach ($id in $known.Keys) {
        if ($table.ContainsKey($id) -and $table[$id].Name -eq $known[$id].Name -and $table[$id].Created -eq $known[$id].Created) { $alive += [int]$id }
    }
    return , $alive
}

function Wait-Descendants([int]$rootPid, [hashtable]$known) {
    $deadline = (Get-Date).AddSeconds($ChildWaitSec)
    while ($true) {
        $table = Get-ProcTable
        if ($table.Count -eq 0) {
            # 프로세스 목록 읽기 실패 — 「다 끝남」으로 치지 않고 다시 본다
            if ((Get-Date) -ge $deadline) { Log '프로세스 목록을 읽지 못해 자손 확인 없이 진행'; return }
            Start-Sleep -Seconds 1
            continue
        }
        Add-Descendants $rootPid $known $table
        $alive = Get-Alive $known $table
        if ($alive.Count -eq 0) { return }
        if ((Get-Date) -ge $deadline) {
            # 이름으로 끄지 않는다 — 이 실행이 띄운 PID만(같은 PC의 다른 python.exe 보호)
            foreach ($id in $alive) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }
            Log ("남은 자손 프로세스 {0}초 넘게 안 끝남 — PID로 끔: {1}" -f $ChildWaitSec, ($alive -join ', '))
            Start-Sleep -Seconds 1
            return
        }
        Start-Sleep -Seconds 1
    }
}

Log ("반복 시작 — python={0} main={1}" -f $Python, $Main)
$lastDelay = 0
while ($true) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $env:ComSpec
    # cmd /c 안에서 2>> 로 stderr를 덧붙인다(지금까지의 logs\stderr_debug.txt 그대로).
    $psi.Arguments = '/d /c ""' + $Python + '" "' + $Main + '" 2>> "' + $StderrPath + '""'
    $psi.UseShellExecute = $false
    $psi.WorkingDirectory = Split-Path -Parent $Main
    $started = Get-Date
    try {
        $proc = [System.Diagnostics.Process]::Start($psi)
    } catch {
        Log ("main.py를 켜지 못함: {0}" -f $_.Exception.Message)
        exit 1
    }
    $rootPid = $proc.Id
    Log ("켬 — PID {0}" -f $rootPid)
    $known = @{}
    # 처음 30초는 1초마다 모은다 — main이 Watchdog을 띄운 직후 죽어도 그 Watchdog을 놓치지 않게
    while (-not $proc.WaitForExit($(if (((Get-Date) - $started).TotalSeconds -lt 30) { 1000 } else { [Math]::Max(1, $SnapshotSec) * 1000 }))) {
        try { Add-Descendants $rootPid $known (Get-ProcTable) } catch { }
    }
    $proc.WaitForExit()
    $code = $proc.ExitCode
    $ran = [int]((Get-Date) - $started).TotalSeconds
    $proc.Dispose()

    if ($code -eq 0) {
        Log ("사람이 닫음(코드 0) — 멈춤 ({0}초 돌았음)" -f $ran)
        exit 0
    }
    if ($code -eq 42) {
        Log ("예약 재시작(코드 42) — {0}초 뒤 다시 켬" -f $RestartDelaySec)
        Wait-Descendants $rootPid $known
        Start-Sleep -Seconds $RestartDelaySec
        continue
    }
    if ($ran -gt $StableSec -or $lastDelay -le 0) { $delay = $BaseDelaySec }
    else { $delay = [Math]::Min($lastDelay * 2, $MaxDelaySec) }
    if ($delay -le 0) { $lastDelay = 0 } else { $lastDelay = $delay }
    Log ("크래시(코드 {0}, {1}초 돌았음) — {2}초 뒤 다시 켬" -f $code, $ran, $delay)
    Wait-Descendants $rootPid $known
    Start-Sleep -Seconds $delay
}
