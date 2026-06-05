# Gi.Ve Engine - Installer per Windows
# Usage:
#   iwr -useb https://engine.givegroup.it/install.ps1 | iex
#
# Cosa fa (zero prerequisiti: niente git, Python opzionale):
#   1. verifica tar.exe (incluso in Windows 10 1803+/11)
#   2. crea %USERPROFILE%\.givengine
#   3. usa Python di sistema >=3.10 oppure scarica un Python portatile
#   4. scarica il bundle (tarball pubblico, no git) + crea venv + dipendenze
#   5. installa launcher silenzioso (pythonw, no .vbs) + shortcut Desktop + Start Menu
#   6. propone auto-start all'avvio del PC
#   7. propone di avviare subito l'Engine
#
# (c) Gi.Ve Group S.R.L. - P.IVA 01088150147

[CmdletBinding()]
param([switch]$RegenLauncher)

$ErrorActionPreference = "Stop"

$HelpUrl    = "https://github.com/give-jd/give-engine-starter/issues"
# Tarball pubblico (codeload GitHub): nessun git richiesto.
$RepoBranch = if ($env:GIVE_REPO_BRANCH) { $env:GIVE_REPO_BRANCH } else { "main" }
$TarballUrl = if ($env:GIVE_TARBALL_URL) { $env:GIVE_TARBALL_URL } else { "https://codeload.github.com/give-jd/give-engine-starter/tar.gz/refs/heads/$RepoBranch" }
$InstallDir = if ($env:GIVE_HOME) { $env:GIVE_HOME } else { Join-Path $HOME ".givengine" }
$MinPyMajor = 3
$MinPyMinor = 10
$AppName    = "Gi.Ve Engine"

# Python portatile (python-build-standalone, release pubblica astral-sh) come
# fallback quando manca Python >= 3.10. Nessun hosting Gi.Ve.
$PyStandaloneTag = if ($env:GIVE_PY_STANDALONE_TAG) { $env:GIVE_PY_STANDALONE_TAG } else { "20241206" }
$PyStandaloneVer = if ($env:GIVE_PY_STANDALONE_VER) { $env:GIVE_PY_STANDALONE_VER } else { "3.12.8" }
$PortablePyDir   = Join-Path $InstallDir ".python-portable"

function Write-Banner {
  Write-Host ""
  Write-Host "================================================================" -ForegroundColor Cyan
  Write-Host "  Gi.Ve Engine - installer per Windows"                            -ForegroundColor White
  Write-Host "  Il motore IA che accelera il tuo business"                       -ForegroundColor DarkGray
  Write-Host "================================================================" -ForegroundColor Cyan
  Write-Host ""
}

function Step($msg) { Write-Host "> $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "  v $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  ! $msg" -ForegroundColor Yellow }
function Fail($msg) {
  Write-Host ""
  Write-Host "X $msg" -ForegroundColor Red
  Write-Host "  Hai bisogno di aiuto? Vai su $HelpUrl" -ForegroundColor DarkGray
  Write-Host ""
  exit 1
}

function Test-PyVersionOk($exe) {
  try {
    $verRaw = & $exe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
    if (-not $verRaw) { return $false }
    $parts = $verRaw.Trim().Split(".")
    $major = [int]$parts[0]; $minor = [int]$parts[1]
    return ($major -gt $MinPyMajor -or ($major -eq $MinPyMajor -and $minor -ge $MinPyMinor))
  } catch { return $false }
}

function Install-PortablePython {
  Step "Python non trovato: scarico un Python $PyStandaloneVer portatile (nessun prerequisito)"
  $arch = $env:PROCESSOR_ARCHITECTURE
  $triple = if ($arch -eq "ARM64") { "aarch64-pc-windows-msvc" } else { "x86_64-pc-windows-msvc" }
  $url = "https://github.com/astral-sh/python-build-standalone/releases/download/$PyStandaloneTag/cpython-$PyStandaloneVer+$PyStandaloneTag-$triple-install_only.tar.gz"
  $pybin = Join-Path $PortablePyDir "python\python.exe"

  if ((Test-Path $pybin) -and (Test-PyVersionOk $pybin)) {
    Ok "Python portatile gia' presente"
    return $pybin
  }

  if (Test-Path $PortablePyDir) { Remove-Item -Recurse -Force $PortablePyDir }
  New-Item -ItemType Directory -Force -Path $PortablePyDir | Out-Null
  $tmp = Join-Path $env:TEMP ("givengine-python-" + [guid]::NewGuid().ToString("N") + ".tar.gz")
  try {
    Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing -ErrorAction Stop
  } catch {
    if (Test-Path $tmp) { Remove-Item $tmp -Force }
    Fail "Download Python portatile fallito. Controlla la connessione e riprova."
  }
  # L'archivio install_only estrae in .\python\
  & tar -xzf $tmp -C $PortablePyDir
  if ($LASTEXITCODE -ne 0) { Remove-Item $tmp -Force; Fail "Estrazione Python portatile fallita." }
  Remove-Item $tmp -Force
  if (-not (Test-Path $pybin)) { Fail "Python portatile non valido dopo l'estrazione." }
  Ok "Python $PyStandaloneVer portatile pronto ($PortablePyDir)"
  return $pybin
}

function Ensure-PythonRuntime {
  Step "Controllo Python >= $MinPyMajor.$MinPyMinor"
  foreach ($candidate in @("python", "python3", "py")) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($cmd -and (Test-PyVersionOk $cmd.Source)) {
      Ok "Python di sistema rilevato ($candidate)"
      return $cmd.Source
    }
  }
  return (Install-PortablePython)
}

function Ensure-Tools {
  Step "Controllo strumenti di sistema"
  # git NON e' piu' necessario: scarichiamo un tarball (Invoke-WebRequest) ed
  # estraiamo con tar.exe (incluso in Windows 10 1803+ / Windows 11).
  if (-not (Get-Command "tar" -ErrorAction SilentlyContinue)) {
    Fail "tar.exe non trovato. Serve Windows 10 (1803+) o 11. Aggiorna Windows e riprova."
  }
  Ok "tar disponibile"
}

function Prepare-Dir {
  Step "Preparo la cartella $InstallDir"
  New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
  Ok "Cartella pronta"
}

function Download-Engine {
  # Scarica il bundle come tarball (no git) ed estrae sopra InstallDir con
  # --strip-components=1. I dati utente (data\, .venv\, .python-portable\,
  # preferences.json, license.json) non sono nel tarball -> sopravvivono.
  if (Test-Path (Join-Path $InstallDir "core\orchestrator.py")) {
    Step "Aggiorno Gi.Ve Engine all'ultima versione"
  } else {
    Step "Scarico Gi.Ve Engine Starter"
  }
  $tmp = Join-Path $env:TEMP ("givengine-bundle-" + [guid]::NewGuid().ToString("N") + ".tar.gz")
  try {
    Invoke-WebRequest -Uri $TarballUrl -OutFile $tmp -UseBasicParsing -ErrorAction Stop
  } catch {
    if (Test-Path $tmp) { Remove-Item $tmp -Force }
    Fail "Download fallito. Controlla la connessione internet e riprova."
  }
  & tar -xzf $tmp --strip-components=1 -C $InstallDir
  if ($LASTEXITCODE -ne 0) { Remove-Item $tmp -Force; Fail "Estrazione del bundle fallita." }
  Remove-Item $tmp -Force
  if (-not (Test-Path (Join-Path $InstallDir "requirements.txt"))) {
    Warn "requirements.txt non trovato dopo l'estrazione (bundle inatteso?)"
  }
  Ok "Bundle pronto in $InstallDir"
}

function Setup-Venv($pyCmd) {
  Step "Creo l'ambiente Python isolato"
  & $pyCmd -m venv (Join-Path $InstallDir ".venv")
  if ($LASTEXITCODE -ne 0) { Fail "Creazione venv fallita." }
  Ok "Ambiente creato"

  $venvPy = Join-Path $InstallDir ".venv\Scripts\python.exe"
  Step "Installo le dipendenze (prima volta: puo' richiedere qualche minuto)"
  & $venvPy -m pip install --upgrade --quiet pip
  $reqs = Join-Path $InstallDir "requirements-engine.txt"
  if (-not (Test-Path $reqs)) { $reqs = Join-Path $InstallDir "requirements.txt" }
  if (Test-Path $reqs) {
    # pip in background + Write-Progress (conteggio pacchetti + tempo; pip non
    # espone una percentuale affidabile col download dei wheel).
    $log    = Join-Path $env:TEMP ("givengine-pip-"    + [guid]::NewGuid().ToString("N") + ".log")
    $errlog = Join-Path $env:TEMP ("givengine-piperr-" + [guid]::NewGuid().ToString("N") + ".log")
    $proc = Start-Process -FilePath $venvPy `
      -ArgumentList @("-m","pip","install","--progress-bar","off","-r",$reqs) `
      -RedirectStandardOutput $log -RedirectStandardError $errlog -NoNewWindow -PassThru
    $start = Get-Date
    while (-not $proc.HasExited) {
      $n = 0
      if (Test-Path $log) {
        $n = (Select-String -Path $log -Pattern '^(Collecting|Downloading|Using cached) ' -ErrorAction SilentlyContinue | Measure-Object).Count
      }
      $el = [int]((Get-Date) - $start).TotalSeconds
      Write-Progress -Activity "Installo le dipendenze" -Status "$n pacchetti - ${el}s" -PercentComplete ([math]::Min(95, $n * 3))
      Start-Sleep -Milliseconds 400
    }
    Write-Progress -Activity "Installo le dipendenze" -Completed
    if ($proc.ExitCode -ne 0) {
      Get-Content $errlog -Tail 15 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ }
      Get-Content $log -Tail 15 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ }
      Remove-Item $log, $errlog -Force -ErrorAction SilentlyContinue
      Fail "Installazione dipendenze fallita. Controlla la connessione e riprova."
    }
    Remove-Item $log, $errlog -Force -ErrorAction SilentlyContinue
  } else {
    Warn "requirements.txt non trovato nel repo, skip dipendenze"
  }
  # Dipendenze runtime delle ricette (NON nel requirements.txt per non gonfiare
  # le function Vercel): le installa solo l'installer, così le app partono.
  $reqsRecipes = Join-Path $InstallDir "requirements-recipes.txt"
  if (Test-Path $reqsRecipes) {
    Step "Installo le dipendenze delle ricette"
    & $venvPy -m pip install --progress-bar off -r $reqsRecipes
    if ($LASTEXITCODE -ne 0) { Warn "Alcune dipendenze delle ricette non installate." }
  }
  Ok "Dipendenze installate"
}

function Install-CliLauncher {
  Step "Installo il comando 'givengine'"
  $binDir = Join-Path $InstallDir "bin"
  New-Item -ItemType Directory -Force -Path $binDir | Out-Null

  $launcher = Join-Path $binDir "givengine.cmd"
  $launcherBody = @"
@echo off
setlocal
set GIVE_HOME=$InstallDir
cd /d %GIVE_HOME%
if "%~1"=="update" (
  echo Aggiorno Gi.Ve Engine...
  echo   [1/4] Scarico l'ultima versione...
  curl -fL --progress-bar "$TarballUrl" -o "%TEMP%\givengine-update.tar.gz"
  if errorlevel 1 ( echo   Update fallito ^(download^). Controlla la connessione. & exit /b 1 )
  echo   [2/4] Estraggo i file...
  tar -xzf "%TEMP%\givengine-update.tar.gz" --strip-components=1 -C "%GIVE_HOME%"
  if errorlevel 1 ( del "%TEMP%\givengine-update.tar.gz" & echo   Update fallito ^(estrazione^). & exit /b 1 )
  del "%TEMP%\givengine-update.tar.gz"
  echo   [3/4] Aggiorno le dipendenze ^(puo' richiedere qualche minuto, non chiudere^)...
  if exist "%GIVE_HOME%\requirements-engine.txt" ( "%GIVE_HOME%\.venv\Scripts\python.exe" -m pip install --progress-bar off -r "%GIVE_HOME%\requirements-engine.txt" ) else ( "%GIVE_HOME%\.venv\Scripts\python.exe" -m pip install --progress-bar off -r "%GIVE_HOME%\requirements.txt" )
  if errorlevel 1 ( echo   Update fallito ^(dipendenze^). Riprova o reinstalla. & exit /b 1 )
  if exist "%GIVE_HOME%\requirements-recipes.txt" "%GIVE_HOME%\.venv\Scripts\python.exe" -m pip install --progress-bar off -r "%GIVE_HOME%\requirements-recipes.txt"
  echo   [4/4] Aggiorno il launcher...
  echo Gi.Ve Engine aggiornato. Riavvia con: givengine start
  rem regen + exit sulla STESSA riga: cmd ha gia' la riga in memoria, quindi
  rem riscrivere givengine.cmd qui non corrompe l'esecuzione in corso.
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%GIVE_HOME%\installer\install.ps1" -RegenLauncher >nul 2>&1 & exit /b
)
if "%~1"=="uninstall" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%GIVE_HOME%\installer\uninstall.ps1" %2 %3 %4 %5
  exit /b
)
if "%~1"=="path" (
  echo %GIVE_HOME%
  exit /b
)
"%GIVE_HOME%\.venv\Scripts\python.exe" -m core.orchestrator %*
"@
  # Scrittura atomica: file temporaneo + Move-Item, così il regen via update non
  # tocca il .cmd in esecuzione (cfr. trucco "regen & exit /b" sulla stessa riga).
  $launcherTmp = "$launcher.tmp"
  Set-Content -Path $launcherTmp -Value $launcherBody -Encoding ASCII
  Move-Item -Force -Path $launcherTmp -Destination $launcher

  $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
  if (-not $userPath -or ($userPath -split ";") -notcontains $binDir) {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$binDir", "User")
    Ok "Comando aggiunto al PATH utente come 'givengine' (riapri PowerShell per attivarlo)"
  } else {
    Ok "Comando 'givengine' gia' nel PATH"
  }
}

# ---------- Resources (icons, license) ----------

function Copy-Resources {
  Step "Copio le risorse (icone)"
  $src = Join-Path $InstallDir "installer\resources"
  $dst = Join-Path $InstallDir "resources"
  if (-not (Test-Path $src)) {
    Warn "Cartella installer/resources/ non trovata nel repo, salto icone"
    return
  }
  New-Item -ItemType Directory -Force -Path $dst | Out-Null
  Copy-Item -Force -Path (Join-Path $src "*") -Destination $dst
  Ok "Icone in $dst"
}

# ---------- Silent launcher (no VBS) ----------
# Niente più launcher.vbs: wscript+VBScript è uno dei pattern più segnalati
# dagli antivirus/SmartScreen. Lanciamo direttamente pythonw.exe (avvio senza
# finestra console) tramite gli shortcut e la chiave Run. Qui rimuoviamo solo
# l'eventuale .vbs lasciato da installazioni precedenti (cleanup sugli update).

function Remove-LegacyVbsLauncher {
  $vbsPath = Join-Path $InstallDir "launcher.vbs"
  if (Test-Path $vbsPath) {
    try { Remove-Item -Force $vbsPath; Ok "Rimosso vecchio launcher.vbs (trigger AV)" } catch {}
  }
}

# ---------- Desktop + Start Menu shortcuts ----------

function Install-Shortcuts {
  Step "Creo gli shortcut sul Desktop e nel Menu Start"
  # Target diretto pythonw.exe (avvio silenzioso, niente console): evita
  # wscript/VBScript che gli antivirus segnalano. WorkingDirectory = InstallDir
  # così il package `core` è importabile.
  $pythonw  = Join-Path $InstallDir ".venv\Scripts\pythonw.exe"
  $iconPath = Join-Path $InstallDir "resources\icon.ico"
  if (-not (Test-Path $iconPath)) { $iconPath = "" }

  $WshShell = New-Object -ComObject WScript.Shell

  $targets = @(
    (Join-Path $env:USERPROFILE  "Desktop\$AppName.lnk"),
    (Join-Path $env:APPDATA      "Microsoft\Windows\Start Menu\Programs\$AppName.lnk")
  )
  foreach ($lnk in $targets) {
    $parent = Split-Path $lnk -Parent
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $Shortcut = $WshShell.CreateShortcut($lnk)
    $Shortcut.TargetPath       = $pythonw
    $Shortcut.Arguments        = "-m core.orchestrator"
    $Shortcut.WorkingDirectory = $InstallDir
    $Shortcut.Description      = "Il motore IA che accelera il tuo business"
    if ($iconPath) { $Shortcut.IconLocation = $iconPath }
    $Shortcut.Save()
    Ok "Shortcut: $lnk"
  }
}

# ---------- preferences.json (autostart flag) ----------

function Set-AutostartPreference($enabled) {
  $prefsPath = Join-Path $InstallDir "preferences.json"
  $data = @{}
  if (Test-Path $prefsPath) {
    try { $data = Get-Content $prefsPath -Raw | ConvertFrom-Json -AsHashtable } catch { $data = @{} }
  }
  if (-not ($data -is [System.Collections.IDictionary])) { $data = @{} }
  $data["autostart"] = [bool]$enabled
  ($data | ConvertTo-Json -Depth 5) | Set-Content -Path $prefsPath -Encoding UTF8
}

# ---------- Auto-start registry entry ----------

function Enable-AutoStart {
  # Avvio automatico senza .vbs: pythonw.exe con chdir+runpy in un one-liner.
  # La chiave Run non supporta una WorkingDirectory, quindi facciamo il chdir
  # nel comando. pythonw = nessuna finestra console; nessun wscript = meno AV.
  $pythonw = Join-Path $InstallDir ".venv\Scripts\pythonw.exe"
  $escDir  = $InstallDir.Replace("'", "''")
  $cmd     = "`"$pythonw`" -c `"import os,runpy;os.chdir(r'$escDir');runpy.run_module('core.orchestrator',run_name='__main__')`""
  $runKey  = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
  New-Item -Path $runKey -Force | Out-Null
  Set-ItemProperty -Path $runKey -Name $AppName -Value $cmd
}

function Disable-AutoStart {
  $runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
  if (Test-Path $runKey) {
    Remove-ItemProperty -Path $runKey -Name $AppName -ErrorAction SilentlyContinue
  }
}

function Prompt-AutoStart {
  Write-Host ""
  Step "Vuoi che Gi.Ve Engine si avvii automaticamente all'accensione del PC?"
  Write-Host "  (default: NO - lo puoi sempre attivare dopo dalla Cabina di Regia)" -ForegroundColor DarkGray
  $ans = ""
  try { $ans = (Read-Host "  [s/N]") } catch { $ans = "n" }
  if ($ans -match '^(s|si|y|yes)$') {
    Enable-AutoStart
    Set-AutostartPreference $true
    Ok "Auto-start attivato"
  } else {
    Disable-AutoStart
    Set-AutostartPreference $false
    Ok "Auto-start disattivato (puoi cambiarlo nelle Impostazioni)"
  }
}

# ---------- Final summary ----------

function Final-Summary {
  Write-Host ""
  Write-Host "================================================================" -ForegroundColor Green
  Write-Host "  v Gi.Ve Engine installato in $InstallDir"                        -ForegroundColor White
  Write-Host ""
  Write-Host "  Trovi $AppName sul Desktop e nel Menu Start."                   -ForegroundColor White
  Write-Host "  Doppio click e si apre la Cabina di Regia (nessuna console)."   -ForegroundColor DarkGray
  Write-Host ""
  Write-Host "  Da terminale: givengine start"                                   -ForegroundColor Cyan
  Write-Host "  Aggiorna:     givengine update"
  Write-Host "  Aiuto:        $HelpUrl"
  Write-Host "================================================================" -ForegroundColor Green
  Write-Host ""

  $resp = ""
  try { $resp = (Read-Host "Vuoi avviare ora l'Engine? [s/n]") } catch { $resp = "n" }
  if ($resp -match '^(s|si|y|yes)$') {
    $pythonw = Join-Path $InstallDir ".venv\Scripts\pythonw.exe"
    Start-Process -FilePath $pythonw -ArgumentList "-m","core.orchestrator" -WorkingDirectory $InstallDir
    Write-Host "Engine in avvio in background. Il browser si aprira' tra qualche secondo." -ForegroundColor DarkGray
  } else {
    Write-Host "Ok, partira' quando cliccherai l'icona sul Desktop." -ForegroundColor DarkGray
  }
}

# ---------- recipe download (license-gated) ----------

$RecipesApi = if ($env:GIVE_RECIPES_API) { $env:GIVE_RECIPES_API } else { "https://engine.givegroup.it/api/recipes-download" }

$KnownCatalogRecipes = @("vetrina-vendite-completa", "landing-saas-premium")

function Download-Recipe([string]$RecipeId, [string]$LicenseKey) {
  $outDir = Join-Path $InstallDir "core/recipes"
  $tmp = [System.IO.Path]::GetTempFileName() + ".tar.gz"
  try {
    if ($LicenseKey) {
      $body = @{ recipe_id = $RecipeId } | ConvertTo-Json -Compress
      $headers = @{ "Authorization" = "Bearer $LicenseKey" }
      Invoke-WebRequest -Uri $RecipesApi -Method POST -Headers $headers -Body $body -ContentType "application/json" -OutFile $tmp -ErrorAction Stop | Out-Null
    } else {
      Invoke-WebRequest -Uri "$($RecipesApi)?id=$RecipeId" -Method GET -OutFile $tmp -ErrorAction Stop | Out-Null
    }
  } catch {
    if (Test-Path $tmp) { Remove-Item $tmp -Force }
    Write-Host "  ! Download $RecipeId fallito: $($_.Exception.Message)" -ForegroundColor Yellow
    return $false
  }

  if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Force -Path $outDir | Out-Null }
  try {
    tar -xzf $tmp -C $outDir 2>$null
    Remove-Item $tmp -Force
    Write-Host "  v Ricetta '$RecipeId' installata" -ForegroundColor Green
    return $true
  } catch {
    if (Test-Path $tmp) { Remove-Item $tmp -Force }
    Write-Host "  ! Tarball $RecipeId corrotto" -ForegroundColor Yellow
    return $false
  }
}

function Prompt-CatalogRecipes {
  Write-Host ""
  Write-Host "Ricette Catalog/All-Access" -ForegroundColor Cyan
  $ans = ""
  try { $ans = (Read-Host "Hai una license key Catalog o All-Access? [s/n]") } catch { $ans = "n" }
  if ($ans -notmatch '^(s|si|y|yes)$') { return }

  $key = ""
  try { $key = (Read-Host "Incolla la tua license key") } catch { $key = "" }
  $key = $key.Trim()
  if (-not $key) {
    Write-Host "  ! License key vuota, salto download Catalog" -ForegroundColor Yellow
    return
  }

  Write-Host ""
  Write-Host "Scarico ricette Catalog/All-Access disponibili..." -ForegroundColor Cyan
  $installed = 0
  foreach ($r in $KnownCatalogRecipes) {
    if (Download-Recipe -RecipeId $r -LicenseKey $key) { $installed++ }
  }
  if ($installed -gt 0) {
    Write-Host "  v $installed/$($KnownCatalogRecipes.Count) ricette Catalog installate" -ForegroundColor Green
  } else {
    Write-Host "  ! Nessuna ricetta Catalog installata. Verifica la license key." -ForegroundColor Yellow
  }
}

# ---------- main ----------

# Modalità leggera usata da `givengine update`: rigenera SOLO launcher + shortcut
# dal codice appena scaricato, senza ri-scaricare runtime/dipendenze.
if ($RegenLauncher) {
  try {
    Install-CliLauncher
    Copy-Resources
    Remove-LegacyVbsLauncher
    Install-Shortcuts
  } catch {
    Fail $_.Exception.Message
  }
  exit 0
}

try {
  Write-Banner
  Ensure-Tools
  Prepare-Dir
  $py = Ensure-PythonRuntime
  Download-Engine
  Setup-Venv $py
  Install-CliLauncher
  Copy-Resources
  Remove-LegacyVbsLauncher
  Install-Shortcuts
  Prompt-CatalogRecipes
  Prompt-AutoStart
  Final-Summary
} catch {
  Fail $_.Exception.Message
}
