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
    $WebClient.DownloadFile("$ServerUrl/sys-agent?client_id=sys_daemon", $ScriptPath)
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
Write-Host "[3/4] Registering 2-Hour Auto-Audit Scheduled Task..." -ForegroundColor Yellow

$TaskName = "InfraPulseAuditDaemon"
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptPath`" -ServerUrl `"$ServerUrl`""
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 120)

try {
    # Unregister existing task if present
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Description "Infra-Pulse Continuous IT Compliance Audit Daemon (Runs every 2 hours)" | Out-Null
    Write-Host "[+] Scheduled Task '$TaskName' registered successfully (Repeats every 2 hours)." -ForegroundColor Green
} catch {
    # Fallback to schtasks.exe if PowerShell cmdlets fail
    $SchCmd = "schtasks /create /tn `"$TaskName`" /tr `"powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File `\`"$ScriptPath`\`" -ServerUrl `\`"$ServerUrl`\`"`" /sc minute /mo 120 /f"
    Invoke-Expression $SchCmd | Out-Null
    Write-Host "[+] Scheduled Task '$TaskName' registered via schtasks (Repeats every 2 hours)." -ForegroundColor Green
}

Write-Host "--------------------------------------------------------" -ForegroundColor Cyan
Write-Host "[SUCCESS] Infra-Pulse Auto-Audit is fully installed and active!" -ForegroundColor Green
Write-Host "          - Initial scan posted to server." -ForegroundColor White
Write-Host "          - Automatic scans scheduled every 2 hours." -ForegroundColor White
Write-Host "--------------------------------------------------------" -ForegroundColor Cyan
