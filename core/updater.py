"""Auto-update all'avvio dell'Engine.

`maybe_self_update()` viene chiamato all'inizio di `orchestrator.main()`: se sul
repo Starter c'è un commit più recente di quello installato, scarica il bundle,
sovrascrive i file in GIVE_HOME, aggiorna le dipendenze e RI-ESEGUE l'orchestrator
col codice nuovo. Copre tutti i modi di avvio (icona/.app/.desktop/CLI), perché
sta nel processo Python.

Best-effort: offline o nessuna novità → non fa nulla e l'avvio prosegue normale.
Disattivabile con la variabile d'ambiente GIVE_NO_UPDATE=1.
"""

from __future__ import annotations

import hashlib
import io
import os
import subprocess
import sys
import tarfile

_REPO = "give-jd/give-engine-starter"
_BRANCH = os.environ.get("GIVE_REPO_BRANCH", "main")
_TARBALL = os.environ.get(
    "GIVE_TARBALL_URL",
    f"https://codeload.github.com/{_REPO}/tar.gz/refs/heads/{_BRANCH}",
)
_SHA_URL = f"https://api.github.com/repos/{_REPO}/commits/{_BRANCH}"


def _remote_sha(timeout: float = 4.0) -> str | None:
    """SHA dell'ultimo commit dello Starter (check leggero, 1 richiesta)."""
    try:
        import httpx
        r = httpx.get(_SHA_URL, timeout=timeout,
                      headers={"Accept": "application/vnd.github.sha"})
        if r.status_code == 200 and r.text.strip():
            return r.text.strip()[:40]
    except Exception:
        return None
    return None


def _download_and_extract(dest: str) -> None:
    """Scarica il tarball e lo estrae su `dest` (strip del dir radice), con
    guardia anti path-traversal; ignora symlink/special (sicurezza)."""
    import httpx
    r = httpx.get(_TARBALL, timeout=120.0, follow_redirects=True)
    r.raise_for_status()
    dest_real = os.path.realpath(dest)
    with tarfile.open(fileobj=io.BytesIO(r.content), mode="r:gz") as tar:
        for m in tar.getmembers():
            parts = m.name.split("/", 1)
            if len(parts) < 2 or not parts[1]:
                continue  # salta la dir radice del tarball
            target = os.path.realpath(os.path.join(dest, parts[1]))
            if target != dest_real and not target.startswith(dest_real + os.sep):
                continue  # path traversal → skip
            if m.isdir():
                os.makedirs(target, exist_ok=True)
            elif m.isreg():
                os.makedirs(os.path.dirname(target), exist_ok=True)
                src = tar.extractfile(m)
                if src is None:
                    continue
                with src, open(target, "wb") as out:
                    out.write(src.read())
            # symlink/fifo/etc. ignorati di proposito


def _req_files(home: str) -> list[str]:
    """Path dei requirements da installare (engine + ricette).

    NON il requirements.txt root (minimale per Vercel). Fallback al root se
    manca l'engine file (bundle vecchi). Ritorna solo i file esistenti.
    """
    names = ["requirements-engine.txt", "requirements-recipes.txt"]
    if not os.path.exists(os.path.join(home, "requirements-engine.txt")):
        names = ["requirements.txt", "requirements-recipes.txt"]
    return [os.path.join(home, n) for n in names if os.path.exists(os.path.join(home, n))]


def _deps_hash(home: str) -> str | None:
    """sha256 di path+contenuto dei requirements file. None se illeggibili.

    Identifica univocamente lo stato dichiarato delle dipendenze: se non cambia,
    rilanciare pip è inutile (risolve il reinstall ripetuto a ogni update).
    """
    h = hashlib.sha256()
    paths = _req_files(home)
    if not paths:
        return None
    for p in paths:
        try:
            with open(p, "rb") as fh:
                h.update(os.path.basename(p).encode("utf-8"))
                h.update(b"\0")
                h.update(fh.read())
        except OSError:
            return None
    return h.hexdigest()


def _pip_install(home: str, *, force: bool = False) -> None:
    """Installa engine + ricette SOLO se i requirements sono cambiati.

    Gate per hash: se i due requirements file sono byte-identici all'ultimo
    install riuscito, pip non viene rilanciato (evita di "reinstallare ogni
    volta gli stessi pacchetti"). `force=True` bypassa il gate.
    """
    from core import system as _sys
    current = _deps_hash(home)
    if not force and current and _sys.get_pref("deps_install_hash") == current:
        print("Gi.Ve Engine: dipendenze già aggiornate, salto pip.", flush=True)
        return
    ok = True
    for p in _req_files(home):
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q",
             "--disable-pip-version-check", "-r", p],
            check=False, timeout=600,
        )
        ok = ok and (r.returncode == 0)
    # Memorizza l'hash solo se tutti i pip sono andati a buon fine: un install
    # parziale non deve far saltare il retry al prossimo giro.
    if ok and current:
        _sys.set_pref("deps_install_hash", current)


def check_remote_update() -> str | None:
    """SHA remoto se più recente di quello installato, altrimenti None.

    Best-effort: None anche offline o se l'API non risponde.
    """
    from core import system as _sys
    last = _sys.get_pref("last_update_sha")
    sha = _remote_sha()
    if not sha or sha == last:
        return None
    return sha


def apply_update(*, force_pip: bool = False) -> dict:
    """Scarica l'ultima versione, sovrascrive i file e (se cambiate) aggiorna le
    dipendenze. NON ri-esegue il processo — il caller decide se/come riavviare.

    Returns:
        dict con ``updated`` (bool: codice nuovo scaricato), ``sha``, ``message``.
        Best-effort: non solleva, in errore ritorna ``updated=False``.
    """
    from core import system as _sys
    home = str(_sys.GIVE_HOME)
    try:
        sha = check_remote_update()
        if sha:
            print("Gi.Ve Engine: trovato un aggiornamento, lo applico…", flush=True)
            _download_and_extract(home)
        _pip_install(home, force=force_pip)
        if sha:
            _sys.set_pref("last_update_sha", sha)
        return {
            "updated": bool(sha),
            "sha": sha or _sys.get_pref("last_update_sha"),
            "message": ("Aggiornamento applicato."
                        if sha else "Sei già all'ultima versione."),
        }
    except Exception as e:  # noqa: BLE001 — l'update non deve mai propagare eccezioni
        print(f"[update] saltato ({type(e).__name__}: {e})", flush=True)
        return {"updated": False, "sha": None,
                "message": f"Update saltato ({type(e).__name__})."}


def maybe_self_update(already_updated: bool, reexec_args: list[str]) -> None:
    """Aggiorna+ri-esegue se c'è una versione nuova. No-op se già aggiornato in
    questo ciclo, se GIVE_NO_UPDATE è settata, se offline o se non ci sono novità.
    """
    if already_updated or os.environ.get("GIVE_NO_UPDATE"):
        return
    res = apply_update()
    if not res.get("updated"):
        return
    # ricarica col codice aggiornato (mantiene gli argomenti originali)
    os.execv(sys.executable,
             [sys.executable, "-m", "core.orchestrator", "--updated", *reexec_args])
