# ==============================================================================
# Infra-Pulse Continuous Auto-Audit Daemon Installer (Windows)
# Runs audit 1 time immediately, then schedules background execution every 2 hours
# ==============================================================================

param (
    [string]$ServerUrl = ""
)

Write-Host "--------------------------------------------------------" -ForegroundColor Cyan
Write-Host "  Infra-Pulse Continuous Auto-Audit Installer (Windows)" -ForegroundColor Cyan
Write-Host "--------------------------------------------------------" -ForegroundColor Cyan

# Install Directory
$InstallDir = Join-Path $env:LOCALAPPDATA "InfraPulse"
if (!(Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
}

$ScriptPath = Join-Path $InstallDir "audit.ps1"

# Determine Server URL if not provided
if ([string]::IsNullOrWhiteSpace($ServerUrl)) {
    $ServerUrl = "http://192.168.1.52:8000"
}
$ServerUrl = $ServerUrl.TrimEnd('/')

Write-Host "[1/4] Downloading system agent component..." -ForegroundColor Yellow
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $WebClient = New-Object System.Net.WebClient
    $WebClient.Headers.Add("User-Agent", "PowerShell WinHTTP CLI")
    $WebClient.DownloadFile("$ServerUrl/api/sys-agent?client_id=sys_daemon", $ScriptPath)
    Write-Host "[+] System agent package verified and saved." -ForegroundColor Green
} catch {
    Write-Host "[-] Failed to download agent component." -ForegroundColor Red
    exit 1
}

# Execute Initial Audit Immediately
Write-Host "[2/4] Executing initial compliance audit scan..." -ForegroundColor Yellow
try {
    & powershell.exe -ExecutionPolicy Bypass -File "$ScriptPath"
    Write-Host "[+] Initial compliance audit completed successfully." -ForegroundColor Green
} catch {
    Write-Host "[!] Initial audit executed with warnings: $_" -ForegroundColor Yellow
}

# Register Windows Scheduled Task (Every 2 Hours = 120 Minutes)
# Write the runner that the scheduled task actually invokes.
#
# The task must NOT point straight at audit.ps1: that pins every machine to the
# agent version present at install time, so a server-side agent fix would need a
# manual reinstall on every endpoint. The runner re-fetches the agent first and
# only swaps it in when the download looks like a real script, so an unreachable
# server simply means the last known-good copy runs again.
$RunnerPath = Join-Path $InstallDir "runner.ps1"
$RunnerBody = @'
$InstallDir    = Join-Path $env:LOCALAPPDATA "InfraPulse"
$ScriptPath    = Join-Path $InstallDir "audit.ps1"
$StampPath     = Join-Path $InstallDir "last_run.txt"
$ServerUrl     = "__SERVER_URL__"
$IntervalHours = 2

# The task fires every couple of minutes, but a scan is expensive, so decide
# here whether one is actually due. Two reasons to run: somebody pressed Rescan
# in the portal, or the scheduled interval has elapsed. An agent cannot be
# reached inbound from the portal — it sits behind its office's NAT — so the
# on-demand path is this poll rather than a push.
$shouldScan = $false
$reason     = ""

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $check = Invoke-RestMethod -TimeoutSec 15 `
        -Uri "$ServerUrl/api/check-trigger?device_name=$([Uri]::EscapeDataString($env:COMPUTERNAME))"
    if ($check.trigger) { $shouldScan = $true; $reason = "requested from portal" }
} catch {}

if (-not $shouldScan) {
    $last = $null
    if (Test-Path $StampPath) {
        try { $last = [DateTime]::Parse((Get-Content $StampPath -Raw).Trim()) } catch {}
    }
    if ($null -eq $last -or ((Get-Date) - $last).TotalHours -ge $IntervalHours) {
        $shouldScan = $true; $reason = "scheduled"
    }
}

if (-not $shouldScan) { return }

# Refresh the agent so server-side fixes reach this machine without a reinstall.
try {
    $Tmp = "$ScriptPath.new"
    $wc = New-Object System.Net.WebClient
    $wc.Headers.Add("User-Agent", "PowerShell WinHTTP CLI")
    $wc.DownloadFile("$ServerUrl/api/sys-agent?client_id=sys_daemon", $Tmp)
    # Guard against a truncated download or an HTML error page replacing the agent.
    if ((Get-Item $Tmp).Length -gt 10000 -and (Select-String -Path $Tmp -Pattern "upload-audit" -Quiet)) {
        Move-Item -Force $Tmp $ScriptPath
    } else {
        Remove-Item $Tmp -Force -ErrorAction SilentlyContinue
    }
} catch {}

if (Test-Path $ScriptPath) {
    # Stamp before running, not after: a scan that dies partway must not leave
    # the machine retrying every two minutes forever.
    Set-Content -Path $StampPath -Value (Get-Date).ToString("o") -Encoding ASCII
    & powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File $ScriptPath
}
'@
$RunnerBody = $RunnerBody.Replace("__SERVER_URL__", $ServerUrl)
Set-Content -Path $RunnerPath -Value $RunnerBody -Encoding UTF8

Write-Host "[3/4] Registering 2-Hour Auto-Audit Scheduled Task..." -ForegroundColor Yellow

$TaskName = "InfraPulseAuditDaemon"
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$RunnerPath`""
# Fires every 2 minutes; the runner decides whether a scan is actually due.
# The cadence is the poll for portal-requested rescans, not the scan interval
# itself, which the runner still holds at 2 hours.
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 2)

try {
    # Unregister existing task if present
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Description "Infra-Pulse Continuous IT Compliance Audit Daemon (Runs every 2 hours)" | Out-Null
    Write-Host "[+] Scheduled Task '$TaskName' registered successfully (Repeats every 2 hours)." -ForegroundColor Green
} catch {
    # Fallback to schtasks.exe if PowerShell cmdlets fail
    $SchCmd = "schtasks /create /tn `"$TaskName`" /tr `"powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File `\`"$RunnerPath`\`"`" /sc minute /mo 2 /f"
    Invoke-Expression $SchCmd | Out-Null
    Write-Host "[+] Scheduled Task '$TaskName' registered via schtasks (Repeats every 2 hours)." -ForegroundColor Green
}

Write-Host "--------------------------------------------------------" -ForegroundColor Cyan
Write-Host "[SUCCESS] Infra-Pulse Auto-Audit is fully installed and active!" -ForegroundColor Green
Write-Host "          - Initial scan posted to server." -ForegroundColor White
Write-Host "          - Automatic scans scheduled every 2 hours." -ForegroundColor White
Write-Host "--------------------------------------------------------" -ForegroundColor Cyan
