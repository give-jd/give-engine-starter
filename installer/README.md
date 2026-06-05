# Gi.Ve Engine — Installer (interno)

Documentazione per il team su come funzionano e come si deployano gli
installer pubblici di Gi.Ve Engine Starter.

## File

| File | Target | Comando utente finale |
|---|---|---|
| `install.sh` | macOS / Linux (bash) | `curl -fsSL https://engine.givegroup.it/install.sh \| bash` |
| `install.ps1` | Windows (PowerShell ≥ 5.1) | `iwr -useb https://engine.givegroup.it/install.ps1 \| iex` |

## Cosa fa l'installer

1. **Verifica strumenti**: `curl` + `tar` (preinstallati su macOS/Linux moderni
   e Windows 10 1803+/11). **`git` NON è più richiesto.**
2. **Risolve Python**: usa il `python3 ≥ 3.10` di sistema se presente, altrimenti
   scarica un **Python portatile** (`python-build-standalone`, release pubblica
   astral-sh, per OS/arch) sotto `~/.givengine/.python-portable/`. Zero
   prerequisiti per l'utente.
3. **Scarica il bundle** come **tarball pubblico** (codeload GitHub, niente git)
   in `~/.givengine/` ed estrae con `--strip-components=1` (i dati utente —
   `data/`, `.venv/`, `.python-portable/`, `preferences.json`, `license.json` —
   non sono nel tarball, quindi sopravvivono all'update).
4. **Crea venv** `~/.givengine/.venv/` (dal Python risolto) e installa `requirements.txt`.
4. **Installa launcher** `givengine` (bash o `.cmd` su Windows) e prova ad
   aggiungerlo al PATH (`~/.local/bin` su unix, registry HKCU su Windows).
5. **Avvia opzionalmente** l'Engine (`givengine start`) con prompt
   interattivo (`s/n`). Skippa il prompt se stdin non è un TTY (modalità
   pipe non interattiva).

## Comandi del launcher

```
givengine               # alias di "givengine start"
givengine start [args]  # avvia core.orchestrator (passa args)
givengine update        # ri-scarica il tarball (no git) ed estrae sopra l'installazione
givengine path          # stampa $GIVE_HOME
```

## Variabili d'ambiente

| Var | Default | Scopo |
|---|---|---|
| `GIVE_HOME` | `~/.givengine` | Cartella di installazione |
| `GIVE_TARBALL_URL` | codeload `give-engine-starter` ramo `main` | URL tarball completo (mirror/fork/release) |
| `GIVE_REPO_BRANCH` | `main` | Ramo del tarball codeload (se non override URL completo) |
| `GIVE_PY_STANDALONE_TAG` | `20241206` | Release tag di python-build-standalone (Python portatile) |
| `GIVE_PY_STANDALONE_VER` | `3.12.8` | Versione CPython del Python portatile |
| `GIVE_AUTOSTART` | `0` | Se `1`, forza il prompt di avvio anche in pipe |

## Deploy su Vercel

I file vanno serviti come **root statico** di `engine.givegroup.it`. Vercel
prende `outputDirectory: "website"` da `vercel.json`, quindi gli installer
sono copiati direttamente lì:

```
website/install.sh        ← copia di installer/install.sh
website/install.ps1       ← copia di installer/install.ps1
```

Lo script `tools/build-starter.sh` non li sincronizza (deploy = lavoro
separato). Quando aggiorni `installer/install.sh`, copia a mano in
`website/install.sh` prima del commit, oppure usa il pre-commit hook.

## Test locale

```bash
# Linux/macOS — simula install in /tmp
GIVE_HOME=/tmp/give-test bash installer/install.sh
ls /tmp/give-test/
/tmp/give-test/bin/givengine start

# Windows PowerShell — simula install in %TEMP%
$env:GIVE_HOME = "$env:TEMP\give-test"
powershell -ExecutionPolicy Bypass -File installer/install.ps1
```

## Sicurezza

- `set -euo pipefail` su bash, `$ErrorActionPreference = "Stop"` su PS.
- Nessun `sudo` richiesto. L'installer scrive solo in `$HOME`.
- Download via **tarball pubblico** (codeload) + Python portatile da release
  GitHub `astral-sh/python-build-standalone`: niente git, niente endpoint Gi.Ve
  (coerente con Punto cardine 14). Integrità garantita da TLS (HTTPS).
- I checksum dello script vengono validati da TLS (HTTPS Vercel). Per
  un livello extra in futuro: GPG-sign + nota in README utente per
  verificare.

## Roadmap

- [x] Zero prerequisiti: download via tarball (no git) + Python portatile fallback.
- [ ] Pacchetto `.pkg` macOS firmato Apple Developer ID.
- [ ] Pacchetto MSIX per Windows (Microsoft Store).
- [ ] systemd unit file su Linux per autostart NUC.
- [ ] Mirror su `homebrew/cask` (`brew install --cask givengine`).

---

© Gi.Ve Group S.R.L. — P.IVA 01088150147
