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


def _pip_install(home: str) -> None:
    # engine + ricette (NON il requirements.txt root, minimale per Vercel).
    # Fallback al root se manca l'engine file (bundle vecchi).
    files = ["requirements-engine.txt", "requirements-recipes.txt"]
    if not os.path.exists(os.path.join(home, "requirements-engine.txt")):
        files = ["requirements.txt", "requirements-recipes.txt"]
    for fn in files:
        p = os.path.join(home, fn)
        if os.path.exists(p):
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-q",
                 "--disable-pip-version-check", "-r", p],
                check=False, timeout=600,
            )


def maybe_self_update(already_updated: bool, reexec_args: list[str]) -> None:
    """Aggiorna+ri-esegue se c'è una versione nuova. No-op se già aggiornato in
    questo ciclo, se GIVE_NO_UPDATE è settata, se offline o se non ci sono novità.
    """
    if already_updated or os.environ.get("GIVE_NO_UPDATE"):
        return
    try:
        from core import system as _sys
        home = str(_sys.GIVE_HOME)
        last = _sys.get_pref("last_update_sha")
        sha = _remote_sha()
        if not sha or sha == last:
            return  # offline o già all'ultima versione
        print("Gi.Ve Engine: trovato un aggiornamento, lo applico…", flush=True)
        _download_and_extract(home)
        _pip_install(home)
        _sys.set_pref("last_update_sha", sha)
    except Exception as e:  # noqa: BLE001 — l'avvio non deve mai fallire per l'update
        print(f"[update] saltato ({type(e).__name__}: {e})", flush=True)
        return
    # ricarica col codice aggiornato (mantiene gli argomenti originali)
    os.execv(sys.executable,
             [sys.executable, "-m", "core.orchestrator", "--updated", *reexec_args])
