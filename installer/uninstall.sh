#!/usr/bin/env bash
# Gi.Ve Engine - Uninstaller per macOS / Linux
# Usage:
#   bash ~/.givengine/installer/uninstall.sh             # safe: keeps your data
#   bash ~/.givengine/installer/uninstall.sh --purge     # also removes ~/.givengine
#   curl -fsSL https://engine.givegroup.it/uninstall.sh | bash
#
# Rimuove:
#   - app / icona dal sistema operativo (Dock macOS, menu Linux)
#   - auto-start (LaunchAgent / autostart .desktop)
#   - launcher CLI 'givengine' nei PATH standard
# Con --purge rimuove anche la cartella ~/.givengine (config + venv + ricette).
#
# (c) Gi.Ve Group S.R.L. - P.IVA 01088150147

set -euo pipefail

if [[ -t 1 ]]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; RESET=$'\033[0m'
  CYAN=$'\033[36m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'
else
  BOLD=""; DIM=""; RESET=""; CYAN=""; GREEN=""; YELLOW=""; RED=""
fi

HELP_URL="https://github.com/give-jd/give-engine-starter/issues"
INSTALL_DIR="${GIVE_HOME:-$HOME/.givengine}"

PURGE=0
ASSUME_YES=0
for arg in "$@"; do
  case "$arg" in
    --purge) PURGE=1 ;;
    --yes|-y) ASSUME_YES=1 ;;
    -h|--help)
      cat <<HELP
Gi.Ve Engine uninstaller.

  --purge     Rimuovi anche ~/.givengine (config, venv, ricette generate).
              Senza questa flag la cartella resta intatta.
  --yes, -y   Salta la conferma interattiva.
  -h, --help  Mostra questo messaggio.
HELP
      exit 0
      ;;
  esac
done

step() { echo "${CYAN}›${RESET} ${BOLD}$1${RESET}"; }
ok()   { echo "  ${GREEN}✓${RESET} $1"; }
warn() { echo "  ${YELLOW}⚠${RESET} $1"; }
info() { echo "  ${DIM}$1${RESET}"; }

detect_os() {
  case "$(uname -s)" in
    Darwin) echo "macos" ;;
    Linux)  echo "linux" ;;
    *)      echo "unsupported" ;;
  esac
}
OS="$(detect_os)"

banner() {
  echo
  echo "${YELLOW}╔══════════════════════════════════════════════════════════════╗${RESET}"
  echo "${YELLOW}║${RESET}  ${BOLD}Gi.Ve Engine — disinstalla${RESET}                                    ${YELLOW}║${RESET}"
  echo "${YELLOW}╚══════════════════════════════════════════════════════════════╝${RESET}"
  echo
}

confirm() {
  if [[ "$ASSUME_YES" == "1" ]]; then return 0; fi
  if [[ ! -r /dev/tty ]]; then
    echo "${YELLOW}Nessun TTY: usa --yes per confermare senza prompt.${RESET}"
    exit 2
  fi
  if [[ "$PURGE" == "1" ]]; then
    echo "${YELLOW}Stai per RIMUOVERE anche ~/.givengine (config + venv + ricette).${RESET}"
  else
    echo "Rimuovo icona/app/auto-start. La tua cartella ${BOLD}${INSTALL_DIR}${RESET} ${BOLD}resta${RESET}."
    echo "  Aggiungi ${DIM}--purge${RESET} se vuoi cancellarla."
  fi
  local ans
  read -r -p "${BOLD}Procedere? [s/N]${RESET} " ans </dev/tty || ans="n"
  case "${ans,,}" in
    s|si|sì|y|yes) return 0 ;;
    *) echo "${DIM}Annullato.${RESET}"; exit 1 ;;
  esac
}

stop_running_engine() {
  step "Fermo l'Engine se è in esecuzione"
  if command -v pkill >/dev/null 2>&1; then
    pkill -f 'core.orchestrator' 2>/dev/null || true
  fi
  ok "Processi orchestrator chiusi (se presenti)"
}

remove_macos_app() {
  for dir in "/Applications/Gi.Ve Engine.app" "$HOME/Applications/Gi.Ve Engine.app"; do
    if [[ -d "$dir" ]]; then
      rm -rf "$dir"
      ok "Rimossa app: ${DIM}${dir}${RESET}"
    fi
  done
  if [[ -L "$HOME/Desktop/Gi.Ve Engine" ]]; then
    rm -f "$HOME/Desktop/Gi.Ve Engine"
    ok "Rimosso alias Desktop"
  fi
}

remove_linux_desktop() {
  local apps_dir="$HOME/.local/share/applications"
  for f in "$apps_dir/givengine.desktop" \
           "$HOME/Desktop/Gi.Ve Engine.desktop" \
           "$HOME/.config/autostart/givengine.desktop"; do
    if [[ -f "$f" ]]; then
      rm -f "$f"
      ok "Rimosso: ${DIM}${f}${RESET}"
    fi
  done
  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$apps_dir" >/dev/null 2>&1 || true
  fi
}

remove_macos_autostart() {
  local plist="$HOME/Library/LaunchAgents/it.givegroup.engine.plist"
  if [[ -f "$plist" ]]; then
    launchctl unload "$plist" 2>/dev/null || true
    rm -f "$plist"
    ok "Auto-start macOS rimosso"
  fi
}

remove_cli_launcher() {
  step "Rimuovo il comando ${BOLD}givengine${RESET}"
  local removed=0
  for candidate in "$HOME/.local/bin/givengine" "/usr/local/bin/givengine"; do
    if [[ -L "$candidate" ]] || [[ -f "$candidate" ]]; then
      if rm -f "$candidate" 2>/dev/null; then
        ok "Rimosso ${DIM}${candidate}${RESET}"; removed=1
      else
        warn "Permessi insufficienti per ${candidate} (esegui con sudo se serve)."
      fi
    fi
  done
  if [[ "$removed" == "0" ]]; then
    info "Nessun symlink CLI trovato"
  fi
}

remove_install_dir() {
  if [[ "$PURGE" != "1" ]]; then
    info "Cartella conservata: ${DIM}${INSTALL_DIR}${RESET}"
    info "(usa ${DIM}--purge${RESET} per rimuoverla)"
    return
  fi
  if [[ -d "$INSTALL_DIR" ]]; then
    rm -rf "$INSTALL_DIR"
    ok "Rimossa cartella: ${DIM}${INSTALL_DIR}${RESET}"
  fi
}

final_summary() {
  echo
  echo "${GREEN}╔══════════════════════════════════════════════════════════════╗${RESET}"
  echo "${GREEN}║${RESET}  ${BOLD}✓ Gi.Ve Engine disinstallato${RESET}"
  echo "${GREEN}║${RESET}"
  if [[ "$PURGE" != "1" ]]; then
    echo "${GREEN}║${RESET}  La tua cartella ${BOLD}${INSTALL_DIR}${RESET} è rimasta:"
    echo "${GREEN}║${RESET}  contiene le ricette generate e la licenza."
    echo "${GREEN}║${RESET}  Per cancellarla manualmente: ${DIM}rm -rf ${INSTALL_DIR}${RESET}"
  fi
  echo "${GREEN}║${RESET}"
  echo "${GREEN}║${RESET}  Per reinstallare in futuro:"
  echo "${GREEN}║${RESET}  ${CYAN}curl -fsSL https://engine.givegroup.it/install.sh | bash${RESET}"
  echo "${GREEN}║${RESET}"
  echo "${GREEN}║${RESET}  Domande o feedback: ${HELP_URL}"
  echo "${GREEN}╚══════════════════════════════════════════════════════════════╝${RESET}"
  echo
}

main() {
  banner
  if [[ "$OS" == "unsupported" ]]; then
    echo "${RED}Sistema non supportato dallo script ($(uname -s)).${RESET}"
    exit 1
  fi
  confirm
  stop_running_engine
  case "$OS" in
    macos)
      remove_macos_app
      remove_macos_autostart
      ;;
    linux)
      remove_linux_desktop
      ;;
  esac
  remove_cli_launcher
  remove_install_dir
  final_summary
}

main "$@"
