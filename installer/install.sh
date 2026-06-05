#!/usr/bin/env bash
# Gi.Ve Engine - Installer per macOS / Linux
# Usage:
#   curl -fsSL https://engine.givegroup.it/install.sh | bash
#
# Cosa fa (zero prerequisiti: niente git, Python opzionale):
#   1. verifica curl + tar (preinstallati su macOS/Linux moderni)
#   2. crea ~/.givengine/
#   3. usa Python di sistema >=3.10 oppure scarica un Python portatile
#   4. scarica il bundle (tarball pubblico, no git) + crea venv + dipendenze
#   5. installa launcher CLI + icona OS (Dock macOS / menu app Linux)
#   6. propone auto-start all'accensione
#   7. propone di avviare subito l'Engine
#
# (c) Gi.Ve Group S.R.L. - P.IVA 01088150147

set -euo pipefail

if [[ -t 1 ]]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; RESET=$'\033[0m'
  CYAN=$'\033[36m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; MAGENTA=$'\033[35m'
else
  BOLD=""; DIM=""; RESET=""; CYAN=""; GREEN=""; YELLOW=""; RED=""; MAGENTA=""
fi

HELP_URL="https://github.com/give-jd/give-engine-starter/issues"
# Tarball pubblico (codeload GitHub): nessun git richiesto. Override completo via
# GIVE_TARBALL_URL, oppure GIVE_REPO_BRANCH per cambiare ramo.
REPO_BRANCH="${GIVE_REPO_BRANCH:-main}"
TARBALL_URL="${GIVE_TARBALL_URL:-https://codeload.github.com/give-jd/give-engine-starter/tar.gz/refs/heads/${REPO_BRANCH}}"
INSTALL_DIR="${GIVE_HOME:-$HOME/.givengine}"
MIN_PY_MAJOR=3
MIN_PY_MINOR=10

# Python portatile (python-build-standalone, release pubblica astral-sh) usato
# come fallback quando il sistema non ha Python >= 3.10. Nessun hosting Gi.Ve.
PY_STANDALONE_TAG="${GIVE_PY_STANDALONE_TAG:-20241206}"
PY_STANDALONE_VER="${GIVE_PY_STANDALONE_VER:-3.12.8}"
PORTABLE_PY_DIR="$INSTALL_DIR/.python-portable"
PYBIN=""  # risolto da ensure_python_runtime (sistema o portatile)

banner() {
  echo
  echo "${CYAN}╔══════════════════════════════════════════════════════════════╗${RESET}"
  echo "${CYAN}║${RESET}  ${BOLD}Gi.Ve Engine${RESET} ${DIM}— installer per macOS / Linux${RESET}              ${CYAN}║${RESET}"
  echo "${CYAN}║${RESET}  ${DIM}Il motore IA che accelera il tuo business${RESET}                  ${CYAN}║${RESET}"
  echo "${CYAN}╚══════════════════════════════════════════════════════════════╝${RESET}"
  echo
}

step() { echo "${CYAN}›${RESET} ${BOLD}$1${RESET}"; }
ok()   { echo "  ${GREEN}✓${RESET} $1"; }
warn() { echo "  ${YELLOW}⚠${RESET} $1"; }
fail() {
  echo
  echo "${RED}✗ $1${RESET}"
  echo "${DIM}  Hai bisogno di aiuto? Vai su ${HELP_URL}${RESET}"
  echo
  exit 1
}

detect_os() {
  case "$(uname -s)" in
    Darwin) echo "macos" ;;
    Linux)  echo "linux" ;;
    *)      fail "Sistema non supportato dallo script: $(uname -s). Usa l'installer Windows se sei su Windows." ;;
  esac
}
ARCH="$(uname -m)"
OS="$(detect_os)"

_py_version_ok() {
  # $1 = eseguibile python; ritorna 0 se >= MIN_PY
  local exe="$1" ver major minor
  ver="$("$exe" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)" || return 1
  major="${ver%.*}"; minor="${ver#*.}"
  (( major > MIN_PY_MAJOR )) && return 0
  (( major == MIN_PY_MAJOR )) && (( minor >= MIN_PY_MINOR )) && return 0
  return 1
}

_py_standalone_triple() {
  case "${OS}/${ARCH}" in
    macos/arm64)         echo "aarch64-apple-darwin" ;;
    macos/x86_64)        echo "x86_64-apple-darwin" ;;
    linux/x86_64)        echo "x86_64-unknown-linux-gnu" ;;
    linux/aarch64|linux/arm64) echo "aarch64-unknown-linux-gnu" ;;
    *)                   echo "" ;;
  esac
}

install_portable_python() {
  step "Python non trovato: scarico un Python ${PY_STANDALONE_VER} portatile (nessun prerequisito)"
  local triple url tmp pybin
  triple="$(_py_standalone_triple)"
  [[ -n "$triple" ]] || fail "Architettura non supportata per Python portatile: ${OS}/${ARCH}. Installa Python ≥ ${MIN_PY_MAJOR}.${MIN_PY_MINOR} manualmente."
  url="https://github.com/astral-sh/python-build-standalone/releases/download/${PY_STANDALONE_TAG}/cpython-${PY_STANDALONE_VER}+${PY_STANDALONE_TAG}-${triple}-install_only.tar.gz"

  pybin="$PORTABLE_PY_DIR/python/bin/python3"
  if [[ -x "$pybin" ]] && _py_version_ok "$pybin"; then
    PYBIN="$pybin"; ok "Python portatile già presente"; return
  fi

  rm -rf "$PORTABLE_PY_DIR"
  mkdir -p "$PORTABLE_PY_DIR"
  tmp="$(mktemp -t givengine-python-XXXXXX.tar.gz)"
  curl -fsSL "$url" -o "$tmp" || { rm -f "$tmp"; fail "Download Python portatile fallito. Controlla la connessione e riprova."; }
  # L'archivio install_only estrae in ./python/
  tar -xzf "$tmp" -C "$PORTABLE_PY_DIR" || { rm -f "$tmp"; fail "Estrazione Python portatile fallita."; }
  rm -f "$tmp"
  [[ -x "$pybin" ]] || fail "Python portatile non valido dopo l'estrazione."
  PYBIN="$pybin"
  ok "Python ${PY_STANDALONE_VER} portatile pronto (${DIM}${PORTABLE_PY_DIR}${RESET})"
}

ensure_python_runtime() {
  step "Controllo Python ≥ ${MIN_PY_MAJOR}.${MIN_PY_MINOR}"
  if command -v python3 >/dev/null 2>&1 && _py_version_ok "$(command -v python3)"; then
    PYBIN="$(command -v python3)"
    ok "Python di sistema rilevato"
    return
  fi
  # Assente o troppo vecchio → Python portatile, zero prerequisiti per l'utente.
  install_portable_python
}

ensure_tools() {
  step "Controllo strumenti di sistema"
  # git NON è più necessario: scarichiamo un tarball con curl + tar (entrambi
  # preinstallati su macOS e Linux moderni).
  for tool in curl tar; do
    command -v "$tool" >/dev/null 2>&1 || fail "Strumento mancante: ${tool}. Installalo e riprova."
  done
  ok "curl e tar disponibili"
}

prepare_dir() {
  step "Preparo la cartella ${INSTALL_DIR}"
  mkdir -p "$INSTALL_DIR"
  ok "Cartella pronta"
}

download_engine() {
  # Scarica il bundle come tarball (no git) e lo estrae sopra INSTALL_DIR.
  # --strip-components=1 toglie la dir radice del tarball; i dati utente
  # (data/, .venv/, .python-portable/, preferences.json, license.json) NON
  # sono nel tarball, quindi sopravvivono all'overlay → update sicuro.
  if [[ -e "$INSTALL_DIR/core/orchestrator.py" ]]; then
    step "Aggiorno Gi.Ve Engine all'ultima versione"
  else
    step "Scarico Gi.Ve Engine Starter"
  fi
  local tmp
  tmp="$(mktemp -t givengine-bundle-XXXXXX.tar.gz)"
  curl -fsSL "$TARBALL_URL" -o "$tmp" \
    || { rm -f "$tmp"; fail "Download fallito. Controlla la connessione internet e riprova."; }
  tar -xzf "$tmp" --strip-components=1 -C "$INSTALL_DIR" \
    || { rm -f "$tmp"; fail "Estrazione del bundle fallita."; }
  rm -f "$tmp"
  [[ -f "$INSTALL_DIR/requirements.txt" ]] \
    || warn "requirements.txt non trovato dopo l'estrazione (bundle inatteso?)"
  ok "Bundle pronto in ${INSTALL_DIR}"
}

_pip_install_with_progress() {
  # Esegue `pip install "$@"` mostrando spinner + conteggio pacchetti + tempo
  # trascorso (pip non espone una percentuale affidabile col download di wheel).
  # Output completo loggato; in caso di errore stampa le ultime righe.
  local pip="$INSTALL_DIR/.venv/bin/pip"
  local log; log="$(mktemp -t givengine-pip-XXXXXX.log)"
  "$pip" install --progress-bar off "$@" >"$log" 2>&1 &
  local pid=$! sp='|/-\' i=0 start=$SECONDS
  if [[ -t 1 ]]; then
    while kill -0 "$pid" 2>/dev/null; do
      local n elapsed
      n="$(grep -cE '^(Collecting|Downloading|Using cached) ' "$log" 2>/dev/null || echo 0)"
      elapsed=$((SECONDS - start))
      printf "\r  ${CYAN}%s${RESET} dipendenze: %s pacchetti · %ss      " "${sp:i++%4:1}" "$n" "$elapsed"
      sleep 0.2
    done
    printf "\r\033[K"
  else
    while kill -0 "$pid" 2>/dev/null; do printf "."; sleep 3; done
    echo
  fi
  wait "$pid"; local rc=$?
  if (( rc != 0 )); then
    echo "${DIM}--- ultime righe di pip ---${RESET}"
    tail -n 15 "$log" 2>/dev/null
    rm -f "$log"
    return 1
  fi
  rm -f "$log"
  return 0
}

setup_venv() {
  step "Creo l'ambiente Python isolato"
  : "${PYBIN:?PYBIN non risolto: chiamare ensure_python_runtime prima di setup_venv}"
  "$PYBIN" -m venv "$INSTALL_DIR/.venv" \
    || fail "Creazione venv fallita. Su Debian/Ubuntu: sudo apt install python3-venv"
  ok "Ambiente creato"

  step "Installo le dipendenze (prima volta: può richiedere qualche minuto)"
  "$INSTALL_DIR/.venv/bin/pip" install --upgrade --quiet pip
  # Engine/orchestrator: requirements-engine.txt (NON requirements.txt, che è
  # minimale per Vercel). Fallback a requirements.txt per bundle vecchi.
  _engine_reqs="$INSTALL_DIR/requirements-engine.txt"
  [[ -f "$_engine_reqs" ]] || _engine_reqs="$INSTALL_DIR/requirements.txt"
  if [[ -f "$_engine_reqs" ]]; then
    _pip_install_with_progress -r "$_engine_reqs" \
      || fail "Installazione dipendenze fallita. Controlla la connessione e riprova."
  else
    warn "requirements-engine.txt non trovato nel repo, skip dipendenze"
  fi
  # Dipendenze runtime delle ricette (streamlit, pandas, ...): le mette solo
  # l'installer (mai Vercel), così gli app.py delle ricette partono.
  if [[ -f "$INSTALL_DIR/requirements-recipes.txt" ]]; then
    _pip_install_with_progress -r "$INSTALL_DIR/requirements-recipes.txt" \
      || warn "Alcune dipendenze delle ricette non sono state installate."
  fi
  ok "Dipendenze installate"
}

install_launcher() {
  step "Installo il comando ${BOLD}givengine${RESET}"
  local bin_dir="$INSTALL_DIR/bin"
  mkdir -p "$bin_dir"
  # Scrittura atomica: scrivo su un file temporaneo e poi mv. Così se il launcher
  # rigenera sé stesso (givengine update → --regen-launcher), il processo in corso
  # mantiene l'fd sul vecchio inode e non legge byte corrotti.
  local launcher_tmp="$bin_dir/.givengine.$$.tmp"
  cat > "$launcher_tmp" <<EOF
#!/usr/bin/env bash
# Gi.Ve Engine launcher
set -e
GIVE_HOME="${INSTALL_DIR}"
cd "\$GIVE_HOME"
case "\${1:-start}" in
  start|"")  exec "\$GIVE_HOME/.venv/bin/python" -m core.orchestrator "\${@:2}" ;;
  update)
    echo "Aggiorno Gi.Ve Engine…"
    echo "  [1/4] Scarico l'ultima versione…"
    tmp="\$(mktemp -t givengine-bundle-XXXXXX.tar.gz)"
    if [ -t 1 ]; then DLFLAGS="-fL --progress-bar"; else DLFLAGS="-fsSL"; fi
    curl \$DLFLAGS "${TARBALL_URL}" -o "\$tmp" || { echo "  ✗ Update fallito (download). Controlla la connessione."; rm -f "\$tmp"; exit 1; }
    echo "  [2/4] Estraggo i file…"
    tar -xzf "\$tmp" --strip-components=1 -C "\$GIVE_HOME" || { echo "  ✗ Update fallito (estrazione)."; rm -f "\$tmp"; exit 1; }
    rm -f "\$tmp"
    _eng="\$GIVE_HOME/requirements-engine.txt"; [ -f "\$_eng" ] || _eng="\$GIVE_HOME/requirements.txt"
    if [ -f "\$_eng" ]; then
      echo "  [3/4] Aggiorno le dipendenze (può richiedere qualche minuto, non chiudere)…"
      if ! "\$GIVE_HOME/.venv/bin/pip" install --progress-bar off -r "\$_eng"; then
        echo "  ✗ Update fallito (dipendenze). Riprova o reinstalla."; exit 1
      fi
      [ -f "\$GIVE_HOME/requirements-recipes.txt" ] && \
        "\$GIVE_HOME/.venv/bin/pip" install --progress-bar off -r "\$GIVE_HOME/requirements-recipes.txt" || true
    fi
    # Rigenera il launcher stesso dal nuovo install.sh appena scaricato, così le
    # migliorie all'installer arrivano via 'update' senza ri-eseguire l'one-liner.
    # install_launcher scrive in modo atomico (temp+mv): l'fd di questo processo
    # resta sul vecchio inode, nessuna corruzione dello script in esecuzione.
    echo "  [4/4] Aggiorno il launcher…"
    if [ -f "\$GIVE_HOME/installer/install.sh" ]; then
      GIVE_HOME="\$GIVE_HOME" bash "\$GIVE_HOME/installer/install.sh" --regen-launcher >/dev/null 2>&1 \
        || echo "  ⚠ launcher non rigenerato; se necessario ri-esegui l'installer."
    fi
    echo "✓ Gi.Ve Engine aggiornato. Riavvia la Cabina con: givengine start"
    ;;
  uninstall) exec bash "\$GIVE_HOME/installer/uninstall.sh" "\${@:2}" ;;
  path)      echo "\$GIVE_HOME" ;;
  -h|--help|help)
    echo "Gi.Ve Engine - comandi disponibili:"
    echo "  givengine start         avvia la Cabina di Regia (default)"
    echo "  givengine update        aggiorna all'ultima versione"
    echo "  givengine uninstall     rimuove icone + launcher (--purge per rimuovere anche i dati)"
    echo "  givengine path          stampa il path di installazione"
    ;;
  *)         exec "\$GIVE_HOME/.venv/bin/python" -m core.orchestrator "\$@" ;;
esac
EOF
  chmod +x "$launcher_tmp"
  mv -f "$launcher_tmp" "$bin_dir/givengine"

  for candidate in "$HOME/.local/bin" "/usr/local/bin"; do
    if [[ -d "$candidate" && -w "$candidate" ]]; then
      ln -sf "$bin_dir/givengine" "$candidate/givengine"
      ok "Comando disponibile come ${BOLD}givengine${RESET} (link in ${candidate})"
      return
    fi
  done
  warn "Aggiungi questa riga al tuo profilo shell per usare il comando 'givengine':"
  echo "  ${MAGENTA}export PATH=\"${bin_dir}:\$PATH\"${RESET}"
}

# ---------- Shared: copy resources/ next to the user installation ----------

copy_resources() {
  step "Copio le risorse (icone)"
  local src dst
  src="$INSTALL_DIR/installer/resources"
  dst="$INSTALL_DIR/resources"
  if [[ -d "$src" ]]; then
    mkdir -p "$dst"
    cp -f "$src"/* "$dst/" 2>/dev/null || true
    ok "Icone in ${DIM}${dst}${RESET}"
  else
    warn "Cartella installer/resources/ non trovata nel repo, salto icone"
  fi
}

# ---------- macOS: /Applications/Gi.Ve Engine.app ----------

install_macos_app() {
  step "Creo l'app ${BOLD}Gi.Ve Engine${RESET} in Applicazioni"
  local app_dir
  app_dir="/Applications/Gi.Ve Engine.app"
  if [[ ! -w "/Applications" ]]; then
    mkdir -p "$HOME/Applications"
    app_dir="$HOME/Applications/Gi.Ve Engine.app"
    warn "/Applications non scrivibile, uso ${DIM}${app_dir}${RESET}"
  fi

  rm -rf "$app_dir"
  mkdir -p "$app_dir/Contents/MacOS" "$app_dir/Contents/Resources"

  cat > "$app_dir/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>            <string>Gi.Ve Engine</string>
    <key>CFBundleDisplayName</key>     <string>Gi.Ve Engine</string>
    <key>CFBundleIdentifier</key>      <string>it.givegroup.engine</string>
    <key>CFBundleVersion</key>         <string>0.1.0</string>
    <key>CFBundleShortVersionString</key> <string>0.1.0</string>
    <key>CFBundleExecutable</key>      <string>launcher</string>
    <key>CFBundleIconFile</key>        <string>icon</string>
    <key>CFBundlePackageType</key>     <string>APPL</string>
    <key>LSMinimumSystemVersion</key>  <string>10.13</string>
    <key>LSUIElement</key>             <false/>
    <key>NSHumanReadableCopyright</key><string>© Gi.Ve Group S.R.L.</string>
</dict>
</plist>
PLIST

  cat > "$app_dir/Contents/MacOS/launcher" <<LAUNCHER
#!/usr/bin/env bash
# Gi.Ve Engine .app launcher — kicks off the orchestrator detached.
INSTALL_DIR="${INSTALL_DIR}"
cd "\$INSTALL_DIR" || exit 1
mkdir -p "\$INSTALL_DIR/core/logs"
nohup "\$INSTALL_DIR/.venv/bin/python" -m core.orchestrator \\
    >>"\$INSTALL_DIR/core/logs/engine.out" 2>&1 < /dev/null &
disown
exit 0
LAUNCHER
  chmod +x "$app_dir/Contents/MacOS/launcher"

  if [[ -f "$INSTALL_DIR/resources/icon.icns" ]]; then
    cp -f "$INSTALL_DIR/resources/icon.icns" "$app_dir/Contents/Resources/icon.icns"
  fi

  # App non firmata/notarizzata: rimuovi la quarantena così Gatekeeper non
  # blocca il primo avvio (finché non abbiamo l'Apple Developer ID per la
  # notarization). Un'app creata in locale di norma non è in quarantena, ma lo
  # facciamo per sicurezza su eventuali file copiati.
  xattr -dr com.apple.quarantine "$app_dir" 2>/dev/null || true

  ok "App pronta in ${DIM}${app_dir}${RESET}"

  if [[ -d "$HOME/Desktop" ]]; then
    ln -sfn "$app_dir" "$HOME/Desktop/Gi.Ve Engine"
    ok "Alias creato sul Desktop"
  fi
}

# ---------- Linux: .desktop ----------

install_linux_desktop() {
  step "Aggiungo Gi.Ve Engine al menu applicazioni"
  local apps_dir="$HOME/.local/share/applications"
  local desk_file="$apps_dir/givengine.desktop"
  mkdir -p "$apps_dir"

  cat > "$desk_file" <<DESKTOP
[Desktop Entry]
Version=1.0
Type=Application
Name=Gi.Ve Engine
GenericName=Motore IA
Comment=Il motore IA che accelera il tuo business
Exec=bash -c 'source "$INSTALL_DIR/.venv/bin/activate" && cd "$INSTALL_DIR" && exec python -m core.orchestrator'
Icon=$INSTALL_DIR/resources/icon.png
Terminal=false
Categories=Development;Utility;Office;
StartupNotify=true
StartupWMClass=givengine
DESKTOP
  chmod +x "$desk_file"

  if [[ -d "$HOME/Desktop" ]]; then
    cp -f "$desk_file" "$HOME/Desktop/Gi.Ve Engine.desktop"
    chmod +x "$HOME/Desktop/Gi.Ve Engine.desktop"
    if command -v gio >/dev/null 2>&1; then
      gio set "$HOME/Desktop/Gi.Ve Engine.desktop" \
        metadata::trusted true 2>/dev/null || true
    fi
  fi

  update-desktop-database "$apps_dir" >/dev/null 2>&1 || true

  ok "Icona disponibile nel menu applicazioni e sul Desktop"
}

# ---------- preferences.json helpers ----------

prefs_path() { echo "$INSTALL_DIR/preferences.json"; }

prefs_set_autostart() {
  local val="$1"  # true / false
  python3 - "$(prefs_path)" "$val" <<'PY'
import json, os, sys
path, val = sys.argv[1], sys.argv[2]
data = {}
if os.path.exists(path):
    try:
        data = json.load(open(path))
    except Exception:
        data = {}
data['autostart'] = (val.lower() == 'true')
json.dump(data, open(path, 'w'), indent=2)
PY
}

# ---------- auto-start enablement ----------

enable_autostart_macos() {
  local plist="$HOME/Library/LaunchAgents/it.givegroup.engine.plist"
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>it.givegroup.engine</string>
  <key>ProgramArguments</key>
  <array>
    <string>${INSTALL_DIR}/.venv/bin/python</string>
    <string>-m</string>
    <string>core.orchestrator</string>
  </array>
  <key>WorkingDirectory</key><string>${INSTALL_DIR}</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><false/>
  <key>StandardOutPath</key><string>${INSTALL_DIR}/core/logs/engine.out</string>
  <key>StandardErrorPath</key><string>${INSTALL_DIR}/core/logs/engine.err</string>
</dict>
</plist>
PLIST
  launchctl load -w "$plist" 2>/dev/null || true
}

disable_autostart_macos() {
  local plist="$HOME/Library/LaunchAgents/it.givegroup.engine.plist"
  [[ -f "$plist" ]] && launchctl unload "$plist" 2>/dev/null || true
  rm -f "$plist"
}

enable_autostart_linux() {
  local autostart_dir="$HOME/.config/autostart"
  mkdir -p "$autostart_dir"
  cp -f "$HOME/.local/share/applications/givengine.desktop" "$autostart_dir/givengine.desktop" 2>/dev/null || true
}

disable_autostart_linux() {
  rm -f "$HOME/.config/autostart/givengine.desktop"
}

prompt_autostart() {
  echo
  step "Vuoi che Gi.Ve Engine si avvii automaticamente all'accensione del PC?"
  echo "  ${DIM}(default: NO — lo puoi sempre attivare dopo dalla Cabina di Regia)${RESET}"

  local ans="n"
  if [[ -t 0 ]] && [[ -r /dev/tty ]]; then
    read -r -p "  [s/N]: " ans </dev/tty || ans="n"
  fi

  case "${ans,,}" in
    s|si|sì|y|yes)
      case "$OS" in
        macos) enable_autostart_macos ;;
        linux) enable_autostart_linux ;;
      esac
      prefs_set_autostart true
      ok "Auto-start attivato"
      ;;
    *)
      case "$OS" in
        macos) disable_autostart_macos ;;
        linux) disable_autostart_linux ;;
      esac
      prefs_set_autostart false
      ok "Auto-start disattivato (puoi cambiarlo nelle Impostazioni)"
      ;;
  esac
}

# ---------- final summary + interactive launch ----------

final_summary() {
  echo
  echo "${GREEN}╔══════════════════════════════════════════════════════════════╗${RESET}"
  echo "${GREEN}║${RESET}  ${BOLD}✓ Gi.Ve Engine installato in ${INSTALL_DIR}${RESET}"
  echo "${GREEN}║${RESET}  ${DIM}OS: ${OS}/${ARCH}${RESET}"
  echo "${GREEN}║${RESET}"
  case "$OS" in
    macos)
      echo "${GREEN}║${RESET}  Trovi l'app in ${BOLD}/Applications/Gi.Ve Engine.app${RESET}"
      echo "${GREEN}║${RESET}  Cliccaci sopra per avviare (anche dal Dock o dal Desktop)."
      ;;
    linux)
      echo "${GREEN}║${RESET}  Trovi l'icona nel ${BOLD}menu applicazioni${RESET} e sul ${BOLD}Desktop${RESET}."
      echo "${GREEN}║${RESET}  Doppio click e si apre la Cabina di Regia."
      ;;
  esac
  echo "${GREEN}║${RESET}"
  echo "${GREEN}║${RESET}  Da terminale: ${BOLD}${CYAN}givengine start${RESET}"
  echo "${GREEN}║${RESET}  Aggiorna:     ${BOLD}givengine update${RESET}"
  echo "${GREEN}║${RESET}  Aiuto:        ${HELP_URL}"
  echo "${GREEN}╚══════════════════════════════════════════════════════════════╝${RESET}"
  echo

  if [[ -t 0 ]] || [[ "${GIVE_AUTOSTART:-}" == "1" ]]; then
    local ans="n"
    if [[ -r /dev/tty ]]; then
      read -r -p "${BOLD}Vuoi avviare ora l'Engine? [s/n]${RESET} " ans </dev/tty || ans="n"
    fi
    case "${ans,,}" in
      s|si|sì|y|yes) exec "$INSTALL_DIR/bin/givengine" start ;;
      *) echo "${DIM}Ok, partirà quando lancerai 'givengine start' o cliccherai l'icona.${RESET}" ;;
    esac
  else
    echo "${DIM}Per avviarlo manualmente: ${INSTALL_DIR}/bin/givengine start${RESET}"
  fi
}

# ---------- recipe download (license-gated) ----------

# API endpoint che gestisce auth + tarball stream.
RECIPES_API="${GIVE_RECIPES_API:-https://engine.givegroup.it/api/recipes-download}"

# Elenco ricette Catalog/All-Access offerte dopo license check.
# Mantenuto statico per semplicità v1 (no manifest discovery client-side).
KNOWN_CATALOG_RECIPES=(
  "vetrina-vendite-completa"
  "landing-saas-premium"
)

download_recipe() {
  local recipe_id="$1"
  local license_key="${2:-}"
  local out_dir="$INSTALL_DIR/core/recipes"
  local tmp
  tmp="$(mktemp -t givengine-recipe-XXXXXX.tar.gz)"

  local http_code
  if [[ -n "$license_key" ]]; then
    http_code=$(curl -sS -o "$tmp" -w "%{http_code}" \
      -X POST "$RECIPES_API" \
      -H "Authorization: Bearer ${license_key}" \
      -H "Content-Type: application/json" \
      -d "{\"recipe_id\":\"${recipe_id}\"}" || echo "000")
  else
    http_code=$(curl -sS -o "$tmp" -w "%{http_code}" \
      "${RECIPES_API}?id=${recipe_id}" || echo "000")
  fi

  if [[ "$http_code" != "200" ]]; then
    rm -f "$tmp"
    warn "Download ${recipe_id} fallito (HTTP ${http_code})"
    return 1
  fi

  mkdir -p "$out_dir"
  if tar -xzf "$tmp" -C "$out_dir" 2>/dev/null; then
    ok "Ricetta '${recipe_id}' installata"
    rm -f "$tmp"
    return 0
  else
    rm -f "$tmp"
    warn "Tarball ${recipe_id} corrotto"
    return 1
  fi
}

prompt_catalog_recipes() {
  if [[ ! -r /dev/tty ]]; then
    return 0
  fi
  echo
  step "Ricette Catalog/All-Access"
  local ans="n"
  read -r -p "${BOLD}Hai una license key Catalog o All-Access? [s/n]${RESET} " ans </dev/tty || ans="n"
  case "${ans,,}" in
    s|si|sì|y|yes) ;;
    *) return 0 ;;
  esac

  local key=""
  read -r -p "${BOLD}Incolla la tua license key:${RESET} " key </dev/tty || return 0
  key="${key// /}"
  if [[ -z "$key" ]]; then
    warn "License key vuota, salto download Catalog"
    return 0
  fi

  echo
  step "Scarico ricette Catalog/All-Access disponibili"
  local installed=0
  for r in "${KNOWN_CATALOG_RECIPES[@]}"; do
    if download_recipe "$r" "$key"; then
      installed=$((installed + 1))
    fi
  done
  if [[ $installed -gt 0 ]]; then
    ok "${installed}/${#KNOWN_CATALOG_RECIPES[@]} ricette Catalog installate"
  else
    warn "Nessuna ricetta Catalog installata. Verifica la license key."
  fi
}

# ---------- main ----------

main() {
  banner
  ensure_tools
  prepare_dir
  ensure_python_runtime
  download_engine
  setup_venv
  install_launcher
  copy_resources

  case "$OS" in
    macos) install_macos_app ;;
    linux) install_linux_desktop ;;
  esac

  prompt_catalog_recipes
  prompt_autostart
  final_summary
}

# Modalità leggera usata da `givengine update`: rigenera SOLO il launcher e le
# scorciatoie OS dal codice appena scaricato, senza ri-scaricare runtime/deps.
regen_launcher_only() {
  install_launcher
  copy_resources
  case "$OS" in
    macos) install_macos_app ;;
    linux) install_linux_desktop ;;
  esac
}

case "${1:-}" in
  --regen-launcher) regen_launcher_only ;;
  *)                main "$@" ;;
esac
