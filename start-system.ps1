param(
    [string]$PiHost = "192.168.122.183",
    [string]$PiUser = "pi",
    [string]$PiPassword = "raspberry",
    [string]$PiServiceName = "iot-face-client.service",
    [int]$DashboardPort = 3000,
    [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DashboardDir = Join-Path $RepoRoot "dashboard"
$RuntimeDir = Join-Path $RepoRoot "tmp"
$PidFile = Join-Path $RuntimeDir "dashboard.pid"
$OutLog = Join-Path $DashboardDir "tmp-start-out.log"
$ErrLog = Join-Path $DashboardDir "tmp-start-err.log"

function Invoke-PiCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [int]$TimeoutSeconds = 120
    )

    $env:PI_HOST = $PiHost
    $env:PI_USER = $PiUser
    $env:PI_PASSWORD = $PiPassword
    $env:PI_COMMAND = $Command
    $env:PI_TIMEOUT = "$TimeoutSeconds"

    @'
import os
import sys
import paramiko

host = os.environ["PI_HOST"]
user = os.environ["PI_USER"]
password = os.environ["PI_PASSWORD"]
command = os.environ["PI_COMMAND"]
timeout = int(os.environ["PI_TIMEOUT"])

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    client.connect(
        hostname=host,
        username=user,
        password=password,
        timeout=10,
        auth_timeout=10,
        banner_timeout=10,
    )
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    status = stdout.channel.recv_exit_status()
    if out:
        sys.stdout.write(out)
    if err:
        sys.stderr.write(err)
    raise SystemExit(status)
finally:
    client.close()
'@ | python -

    if ($LASTEXITCODE -ne 0) {
        throw "Pi command failed: $Command"
    }
}

function Wait-ForDashboard {
    param([int]$Port)

    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing "http://localhost:$Port" -TimeoutSec 3
            if ($response.StatusCode -eq 200) {
                return
            }
        } catch {
        }
        Start-Sleep -Seconds 1
    }

    $stdout = if (Test-Path $OutLog) { Get-Content $OutLog -ErrorAction SilentlyContinue | Out-String } else { "" }
    $stderr = if (Test-Path $ErrLog) { Get-Content $ErrLog -ErrorAction SilentlyContinue | Out-String } else { "" }
    throw "Dashboard did not start on port $Port.`nSTDOUT:`n$stdout`nSTDERR:`n$stderr"
}

if (-not (Test-Path $RuntimeDir)) {
    New-Item -ItemType Directory -Path $RuntimeDir | Out-Null
}

Write-Host "Starting Raspberry Pi service..." -ForegroundColor Cyan
Invoke-PiCommand "echo $PiPassword | sudo -S systemctl start $PiServiceName"
Invoke-PiCommand "systemctl is-active $PiServiceName"

if (-not (Test-Path (Join-Path $DashboardDir ".next\BUILD_ID"))) {
    Write-Host "Building dashboard..." -ForegroundColor Cyan
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) {
        throw "Dashboard build failed."
    }
}

$existingListener = Get-NetTCPConnection -LocalPort $DashboardPort -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique

if ($existingListener) {
    Write-Host "Dashboard already listening on port $DashboardPort (PID $existingListener)." -ForegroundColor Yellow
    Set-Content -Path $PidFile -Value $existingListener
} else {
    if (Test-Path $OutLog) { Remove-Item $OutLog -Force }
    if (Test-Path $ErrLog) { Remove-Item $ErrLog -Force }

    Write-Host "Starting dashboard on http://localhost:$DashboardPort ..." -ForegroundColor Cyan
    $proc = Start-Process `
        -FilePath "npm.cmd" `
        -ArgumentList @("run", "start", "--", "--hostname", "0.0.0.0") `
        -WorkingDirectory $DashboardDir `
        -RedirectStandardOutput $OutLog `
        -RedirectStandardError $ErrLog `
        -PassThru

    Set-Content -Path $PidFile -Value $proc.Id
    Wait-ForDashboard -Port $DashboardPort
}

if ($OpenBrowser) {
    Start-Process "http://localhost:$DashboardPort"
}

Write-Host "System started successfully." -ForegroundColor Green
Write-Host "Pi service: $PiServiceName" -ForegroundColor Green
Write-Host "Dashboard: http://localhost:$DashboardPort" -ForegroundColor Green
