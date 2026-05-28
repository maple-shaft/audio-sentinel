#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Registers audio-sentinel as a Windows Service using sc.exe.

.DESCRIPTION
    Creates (or recreates) the AudioSentinel Windows Service, pointing at the
    pythonw.exe inside the project's virtual environment.

    IMPORTANT — microphone access from a Windows Service:
    -------------------------------------------------------
    Windows services run in Session 0 (isolated from the interactive desktop).
    Audio capture via WASAPI (used by sounddevice/PortAudio) works from Session 0
    provided that:

      1. The "Windows Audio" service (audiosrv) is running — this script adds it
         as a dependency automatically.
      2. The service runs under a user account (or LocalSystem) that has been
         granted microphone access in Windows Privacy settings:
             Settings > Privacy & Security > Microphone
             > Let desktop apps access your microphone  [ON]
         LocalSystem (SYSTEM) is not subject to per-app restrictions but IS
         subject to the master "Microphone access" toggle.
      3. LocalService / NetworkService accounts do NOT have microphone access —
         use LocalSystem or a dedicated named user account instead.

.PARAMETER InstallDir
    Root directory of the audio-sentinel project. Defaults to the parent folder
    of this script.

.PARAMETER ConfigPath
    Path to config.yaml. Defaults to <InstallDir>\audio_sentinel\config\config.yaml.

.PARAMETER ServiceAccount
    Account the service runs under. Use "LocalSystem" (default) or a UPN such as
    ".\MyUser" with -ServicePassword for a named account with microphone access.

.PARAMETER ServicePassword
    Password for -ServiceAccount when using a named account. Ignored for built-in
    accounts.

.EXAMPLE
    # Install with defaults (LocalSystem, auto-start)
    .\install-service.ps1

.EXAMPLE
    # Install under a named user account
    .\install-service.ps1 -ServiceAccount ".\AudioSvc" -ServicePassword "P@ssw0rd!"

.EXAMPLE
    # Remove the service
    .\install-service.ps1 -Uninstall
#>

param(
    [string]$ServiceName    = "AudioSentinel",
    [string]$DisplayName    = "Audio Sentinel",
    [string]$Description    = "Monitors microphone input and triggers configurable actions on detected sound events.",
    [string]$InstallDir     = (Split-Path $PSScriptRoot -Parent),
    [string]$ConfigPath     = "",
    [string]$StartupType    = "auto",
    [string]$ServiceAccount = "LocalSystem",
    [SecureString]$ServicePassword = $null,
    [switch]$Uninstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Write-Step([string]$msg) { Write-Host "  >> $msg" -ForegroundColor Cyan }
function Write-OK([string]$msg)   { Write-Host "  OK $msg" -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "  WARN $msg" -ForegroundColor Yellow }
function Abort([string]$msg)      { Write-Host "  ERROR $msg" -ForegroundColor Red; exit 1 }

# ---------------------------------------------------------------------------
# Uninstall path
# ---------------------------------------------------------------------------

if ($Uninstall) {
    Write-Step "Stopping service '$ServiceName' (if running)..."
    sc.exe stop $ServiceName 2>$null | Out-Null

    Write-Step "Deleting service '$ServiceName'..."
    $result = sc.exe delete $ServiceName
    if ($LASTEXITCODE -eq 0) {
        Write-OK "Service '$ServiceName' removed."
    } else {
        Abort "sc.exe delete failed: $result"
    }
    exit 0
}

# ---------------------------------------------------------------------------
# Locate pythonw.exe inside the venv
# ---------------------------------------------------------------------------

$venvPython = Join-Path $InstallDir ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $venvPython)) {
    # Fall back to python.exe (shows a console window but works)
    $venvPython = Join-Path $InstallDir ".venv\Scripts\python.exe"
}
if (-not (Test-Path $venvPython)) {
    Abort "Could not find python(w).exe in '$InstallDir\.venv\Scripts\'. Run 'python -m venv .venv && pip install -r requirements.txt' first."
}
Write-Step "Using Python: $venvPython"

# ---------------------------------------------------------------------------
# Resolve config path
# ---------------------------------------------------------------------------

if (-not $ConfigPath) {
    $ConfigPath = Join-Path $InstallDir "audio_sentinel\config\config.yaml"
}
if (-not (Test-Path $ConfigPath)) {
    Write-Warn "Config file not found at '$ConfigPath'. The service may fail to start."
}

# ---------------------------------------------------------------------------
# Build the binPath string
# sc.exe requires the entire command (including arguments) in the binPath.
# Paths with spaces must be quoted inside the binPath value.
# ---------------------------------------------------------------------------

$binPath = '"' + $venvPython + '" -m audio_sentinel --config "' + $ConfigPath + '"'

# ---------------------------------------------------------------------------
# Remove existing service if present
# ---------------------------------------------------------------------------

$existing = sc.exe query $ServiceName 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Step "Existing service found — stopping and removing before re-creating..."
    sc.exe stop $ServiceName 2>$null | Out-Null
    Start-Sleep -Seconds 2
    sc.exe delete $ServiceName | Out-Null
    Start-Sleep -Seconds 1
}

# ---------------------------------------------------------------------------
# Create service
# ---------------------------------------------------------------------------

Write-Step "Creating service '$ServiceName'..."

if ($ServiceAccount -eq "LocalSystem") {
    $createResult = sc.exe create $ServiceName `
        binPath= $binPath `
        DisplayName= $DisplayName `
        start= $StartupType `
        obj= LocalSystem
} else {
    if ($null -eq $ServicePassword -or $ServicePassword.Length -eq 0) {
        Abort "A -ServicePassword is required when using a named -ServiceAccount."
    }
    $plainPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($ServicePassword)
    )
    $createResult = sc.exe create $ServiceName `
        binPath= $binPath `
        DisplayName= $DisplayName `
        start= $StartupType `
        obj= $ServiceAccount `
        password= $plainPassword
}

if ($LASTEXITCODE -ne 0) {
    Abort "sc.exe create failed: $createResult"
}
Write-OK "Service created."

# ---------------------------------------------------------------------------
# Set description
# ---------------------------------------------------------------------------

sc.exe description $ServiceName $Description | Out-Null

# ---------------------------------------------------------------------------
# Add Windows Audio as a dependency
# Without audiosrv the microphone will not be accessible.
# ---------------------------------------------------------------------------

Write-Step "Setting dependency on Windows Audio service (audiosrv)..."
sc.exe config $ServiceName depend= audiosrv | Out-Null
Write-OK "Dependency set."

# ---------------------------------------------------------------------------
# Configure failure actions: restart on first two failures, then wait 1 min
# ---------------------------------------------------------------------------

Write-Step "Configuring failure/recovery actions..."
sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/10000/restart/60000 | Out-Null
Write-OK "Failure actions configured."

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "================================================================" -ForegroundColor Green
Write-Host "  Service '$ServiceName' registered successfully." -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Start :  Start-Service $ServiceName"
Write-Host "  Stop  :  Stop-Service $ServiceName"
Write-Host "  Remove:  .\install-service.ps1 -Uninstall"
Write-Host ""
Write-Host "  MICROPHONE ACCESS CHECKLIST:" -ForegroundColor Yellow
Write-Host "  [ ] Windows Audio service (audiosrv) is running"
Write-Host "  [ ] Settings - Privacy and Security - Microphone toggle is ON"
Write-Host "  [ ] 'Let desktop apps access your microphone' is ON"
if ($ServiceAccount -ne "LocalSystem") {
    Write-Host "  [ ] Account '$ServiceAccount' has 'Log on as a service' right secpol.msc"
}
Write-Host ""
