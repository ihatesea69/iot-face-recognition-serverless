param(
    [string]$PiHost = "192.168.122.183",
    [string]$PiUser = "pi",
    [string]$PiPassword = "raspberry",
    [string]$PiServiceName = "iot-face-client.service",
    [int]$DashboardPort = 3000
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimeDir = Join-Path $RepoRoot "tmp"
$PidFile = Join-Path $RuntimeDir "dashboard.pid"

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

function Stop-LocalDashboard {
    $stopped = $false

    if (Test-Path $PidFile) {
        $pidValue = Get-Content $PidFile | Select-Object -First 1
        if ($pidValue -and ($pidValue -as [int])) {
            $trackedPid = [int]$pidValue
            $process = Get-Process -Id $trackedPid -ErrorAction SilentlyContinue
            if ($process) {
                Stop-Process -Id $trackedPid -Force
                Write-Host "Stopped dashboard PID $trackedPid from pid file." -ForegroundColor Green
                $stopped = $true
            }
        }
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }

    $listeners = Get-NetTCPConnection -LocalPort $DashboardPort -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique

    foreach ($listenerPid in $listeners) {
        $process = Get-Process -Id $listenerPid -ErrorAction SilentlyContinue
        if ($process) {
            Stop-Process -Id $listenerPid -Force
            Write-Host "Stopped dashboard listener PID $listenerPid on port $DashboardPort." -ForegroundColor Green
            $stopped = $true
        }
    }

    if (-not $stopped) {
        Write-Host "No dashboard process was running on port $DashboardPort." -ForegroundColor Yellow
    }
}

Write-Host "Stopping Raspberry Pi service..." -ForegroundColor Cyan
Invoke-PiCommand "echo $PiPassword | sudo -S systemctl stop $PiServiceName"
Invoke-PiCommand "systemctl is-active $PiServiceName || true"

Write-Host "Stopping local dashboard..." -ForegroundColor Cyan
Stop-LocalDashboard

Write-Host "System stopped." -ForegroundColor Green
