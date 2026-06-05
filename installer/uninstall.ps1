# Gi.Ve Engine - Uninstaller per Windows
# Usage:
#   iwr -useb https://engine.givegroup.it/uninstall.ps1 | iex
#   powershell -ExecutionPolicy Bypass -File uninstall.ps1
#   powershell -File uninstall.ps1 -Purge -Yes
#
# Rimuove shortcut Desktop + Menu Start, entry HKCU\...\Run, comando CLI.
# Con -Purge rimuove anche %USERPROFILE%\.givengine.
#
# (c) Gi.Ve Group S.R.L. - P.IVA 01088150147

[CmdletBinding()]
param(
  [switch]$Purge,
  [switch]$Yes
)

$ErrorActionPreference = "Stop"

$HelpUrl    = "https://github.com/give-jd/give-engine-starter/issues"
$InstallDir = if ($env:GIVE_HOME) { $env:GIVE_HOME } else { Join-Path $HOME ".givengine" }
$AppName    = "Gi.Ve Engine"

function Banner {
  Write-Host ""
  Write-Host "================================================================" -ForegroundColor Yellow
  Write-Host "  Gi.Ve Engine - disinstalla"                                     -ForegroundColor White
  Write-Host "================================================================" -ForegroundColor Yellow
  Write-Host ""
}

function Step($msg) { Write-Host "> $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "  v $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  ! $msg" -ForegroundColor Yellow }
function Info($msg) { Write-Host "  $msg" -ForegroundColor DarkGray }

function Confirm-Action {
  if ($Yes) { return }
  if ($Purge) {
    Write-Host "Stai per RIMUOVERE anche $InstallDir (config + venv + ricette)." -ForegroundColor Yellow
  } else {
    Write-Host "Rimuovo icona + shortcut + auto-start. La cartella $InstallDir resta." -ForegroundColor White
    Write-Host "  Aggiungi -Purge se vuoi cancellarla." -ForegroundColor DarkGray
  }
  $resp = Read-Host "Procedere? [s/N]"
  if ($resp -notmatch '^(s|si|y|yes)$') {
    Write-Host "Annullato." -ForegroundColor DarkGray
    exit 1
  }
}

function Stop-RunningEngine {
  Step "Fermo l'Engine se e' in esecuzione"
  Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.ProcessName -match 'pythonw|wscript' } |
    ForEach-Object {
      try {
        $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)" -ErrorAction SilentlyContinue).CommandLine
        if ($cmd -and $cmd -match 'core\.orchestrator|givengine|launcher\.vbs') {
          Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
        }
      } catch {}
    }
  Ok "Processi chiusi (se presenti)"
}

function Remove-Shortcuts {
  Step "Rimuovo Desktop + Menu Start shortcut"
  $targets = @(
    (Join-Path $env:USERPROFILE  "Desktop\$AppName.lnk"),
    (Join-Path $env:APPDATA      "Microsoft\Windows\Start Menu\Programs\$AppName.lnk")
  )
  foreach ($lnk in $targets) {
    if (Test-Path $lnk) {
      Remove-Item -Force -Path $lnk -ErrorAction SilentlyContinue
      Ok "Rimosso: $lnk"
    }
  }
}

function Remove-AutoStart {
  Step "Rimuovo entry auto-start HKCU\\...\\Run"
  $runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
  if (Test-Path $runKey) {
    try {
      Remove-ItemProperty -Path $runKey -Name $AppName -ErrorAction SilentlyContinue
      Ok "Entry $AppName rimossa dal registry"
    } catch {}
  }
}

function Remove-CliFromPath {
  Step "Rimuovo 'givengine' dal PATH utente"
  $binDir = Join-Path $InstallDir "bin"
  $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
  if ($userPath) {
    $newPath = ($userPath -split ";") | Where-Object { $_ -ne $binDir } | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    [Environment]::SetEnvironmentVariable("Path", ($newPath -join ";"), "User")
    Ok "PATH utente ripulito (riavvia PowerShell)"
  }
}

function Remove-InstallDir {
  if (-not $Purge) {
    Info "Cartella conservata: $InstallDir"
    Info "(rilancia con -Purge per cancellarla)"
    return
  }
  if (Test-Path $InstallDir) {
    Remove-Item -Recurse -Force -Path $InstallDir
    Ok "Rimossa cartella: $InstallDir"
  }
}

function Final-Summary {
  Write-Host ""
  Write-Host "================================================================" -ForegroundColor Green
  Write-Host "  v Gi.Ve Engine disinstallato"                                   -ForegroundColor White
  Write-Host ""
  if (-not $Purge) {
    Write-Host "  La cartella $InstallDir e' rimasta (ricette + licenza)."     -ForegroundColor White
    Write-Host "  Per cancellarla manualmente:"                                  -ForegroundColor DarkGray
    Write-Host "    Remove-Item -Recurse -Force `"$InstallDir`""                -ForegroundColor DarkGray
  }
  Write-Host ""
  Write-Host "  Per reinstallare in futuro:"                                    -ForegroundColor White
  Write-Host "    iwr -useb https://engine.givegroup.it/install.ps1 | iex" -ForegroundColor Cyan
  Write-Host ""
  Write-Host "  Domande: $HelpUrl"                                              -ForegroundColor DarkGray
  Write-Host "================================================================" -ForegroundColor Green
  Write-Host ""
}

try {
  Banner
  Confirm-Action
  Stop-RunningEngine
  Remove-Shortcuts
  Remove-AutoStart
  Remove-CliFromPath
  Remove-InstallDir
  Final-Summary
} catch {
  Write-Host ""
  Write-Host "X $($_.Exception.Message)" -ForegroundColor Red
  Write-Host "  Aiuto: $HelpUrl" -ForegroundColor DarkGray
  exit 1
}
