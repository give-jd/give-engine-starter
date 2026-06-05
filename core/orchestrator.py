"""Gi.Ve Engine — Cabina di Regia (orchestrator).

FastAPI server on http://localhost:5000 with:
  GET  /                    -> serves templates/ui.html
  GET  /recipes             -> JSON list of available recipes
  GET  /recipes/{id}/tutorial -> raw markdown of recipe tutorial
  POST /build/{id}          -> kicks off a build (recipe injection)
  WS   /stream/{build_id}   -> pushes ui_states.json entries with realistic timing
  POST /answer/{build_id}   -> receives a human-in-the-loop answer

At startup it tries to open the user's browser. If no WebSocket client
appears within 3 seconds the elegant rich-ASCII fallback box is printed
to the terminal (only sanctioned terminal output in this app).
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import uvicorn
import yaml
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, PlainTextResponse
from rich.console import Console
from rich.panel import Panel
from rich.text import Text


# ---- Paths -----------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
CORE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = CORE_DIR / "templates"
RECIPES_DIR = CORE_DIR / "recipes"
LOGS_DIR = CORE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)
FALLBACK_LOG = LOGS_DIR / "browser_fallback.log"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5000
BROWSER_FALLBACK_SECONDS = 3.0


# ---- Recipe loading --------------------------------------------------------

# Tier is now read at request time from core/licensing.py (Lemon Squeezy).
TIER_ORDER = ["starter", "catalog", "all-access"]


def _current_tier() -> str:
    try:
        from core import licensing  # local import to avoid startup cycles
        return licensing.current_tier()
    except Exception:
        return "starter"


def _tier_allows(user_tier: str, recipe_tier: str) -> bool:
    """Return True iff a user on user_tier can use a recipe tagged recipe_tier."""
    try:
        ui = TIER_ORDER.index(user_tier)
        ri = TIER_ORDER.index(recipe_tier)
    except ValueError:
        return True
    return ui >= ri


def _list_recipes(filter_tier: Optional[str] = None) -> list[dict]:
    """Return recipe catalog. If filter_tier given, return only what that tier
    is allowed to consume."""
    out: list[dict] = []
    if not RECIPES_DIR.exists():
        return out
    try:
        from core import system as _sys
        built_set = set(_sys.get_pref("built_recipes", []) or [])
    except Exception:
        built_set = set()
    for recipe_dir in sorted(RECIPES_DIR.iterdir()):
        yaml_path = recipe_dir / "recipe.yaml"
        if not yaml_path.exists():
            continue
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        recipe_tier = data.get("tier", "starter")
        if filter_tier and filter_tier != "all" and not _tier_allows(filter_tier, recipe_tier):
            continue
        rid = data.get("id", recipe_dir.name)
        out.append({
            "id": rid,
            "tier": recipe_tier,
            "badge": data.get("badge"),
            "nome_visualizzato": data.get("nome_visualizzato", recipe_dir.name),
            "descrizione_breve": data.get("descrizione_breve", ""),
            "tempo_stimato_secondi": data.get("tempo_stimato_costruzione_secondi", 30),
            "moduli_attivati": data.get("moduli_attivati", []),
            "porta_locale": data.get("porta_locale", 8501),
            "built": rid in built_set,
        })
    return out


def _catalog_only_entries(local_ids: set) -> list[dict]:
    """Ricette presenti nel manifest del catalogo ma NON installate localmente.

    Permette alla Cabina di mostrare l'intero catalogo (es. su Starter le
    ricette premium non installate) come card bloccate con CTA di sblocco.
    """
    try:
        from core import catalog_updates as cu
        manifest = cu.checker().get_manifest(allow_fetch=True)
    except Exception:
        manifest = None
    if not manifest:
        return []
    extras: list[dict] = []
    for r in manifest.get("recipes", []) or []:
        rid = r.get("id")
        if not rid or rid in local_ids:
            continue
        extras.append({
            "id": rid,
            "tier": r.get("tier_richiesto", "catalog"),
            "badge": r.get("badge"),
            "nome_visualizzato": r.get("nome_visualizzato", rid),
            "descrizione_breve": r.get("descrizione_breve", ""),
            "tempo_stimato_secondi": r.get("tempo_stimato_secondi", 30),
            "moduli_attivati": [],
            "porta_locale": 0,
            "built": False,
            "installed": False,
        })
    return extras


def _mark_built(recipe_id: str) -> None:
    """Segna una ricetta come 'già costruita' (per la CTA Avvia in Cabina)."""
    try:
        from core import system as _sys
        built = list(_sys.get_pref("built_recipes", []) or [])
        if recipe_id not in built:
            built.append(recipe_id)
            _sys.set_pref("built_recipes", built)
    except Exception:
        pass


def _recipe_yaml(recipe_id: str) -> dict:
    """Leggi recipe.yaml di una ricetta (dict vuoto se mancante/illeggibile)."""
    path = RECIPES_DIR / recipe_id / "recipe.yaml"
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}


def _is_generator_recipe(recipe_id: str) -> bool:
    """Ricetta "generator" (spese/landing/vetrina): genera l'app da template via
    inject.py. Le altre sono "ready app": hanno già app.py e si lanciano dirette."""
    return (RECIPES_DIR / recipe_id / "inject.py").exists()


def _synth_ready_states(recipe_id: str) -> list[dict]:
    """Sequenza di build minima per le ricette "ready app" prive di
    ui_states.json: nessuna Q&A (l'app è statica), solo avanzamento + consegna.
    Evita il blocco "ui_states.json missing" su tutte le ricette non-generator."""
    nome = _recipe_yaml(recipe_id).get("nome_visualizzato", "la tua app")
    return [
        {"stato": "avanzamento", "messaggio": f"Avvio {nome}…",
         "percentuale": 25, "tempo_rimasto_sec": 4, "kanji_background": "起動"},
        {"stato": "avanzamento", "messaggio": "Preparo l'ambiente locale",
         "percentuale": 70, "tempo_rimasto_sec": 2, "kanji_background": "準備"},
        {"stato": "consegna", "messaggio": f"{nome} è pronta, sul tuo PC!",
         "tutorial_path": "README.md"},
    ]


def _ready_app_report(recipe_id: str) -> dict:
    """Report di lancio per una ricetta "ready app": si esegue il suo app.py
    in loco (la dir della ricetta), senza generazione/inject."""
    from core import system as _sys
    data = _recipe_yaml(recipe_id)
    return {
        "output_dir": str(RECIPES_DIR / recipe_id),
        "porta_locale": int(data.get("porta_locale", 8501)),
        "expose_lan": _sys.expose_lan_pref(),
        "recipe_id": recipe_id,
    }


def _load_ui_states(recipe_id: str) -> list[dict]:
    path = RECIPES_DIR / recipe_id / "ui_states.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    # Fallback per le ricette "ready app" (hanno app.py ma non ui_states.json):
    # sintetizza una sequenza minima invece di bloccare il build.
    if (RECIPES_DIR / recipe_id / "app.py").exists():
        return _synth_ready_states(recipe_id)
    raise FileNotFoundError(f"ui_states.json/app.py mancanti per {recipe_id}")


def _load_inject_module(recipe_id: str):
    inject_path = RECIPES_DIR / recipe_id / "inject.py"
    if not inject_path.exists():
        raise FileNotFoundError(f"inject.py missing for {recipe_id}")
    spec = importlib.util.spec_from_file_location(
        f"recipe_{recipe_id}_inject", inject_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# ---- State (in-memory) -----------------------------------------------------

class BuildSession:
    """Tracks a single recipe build and bridges the WebSocket conversation."""

    def __init__(self, recipe_id: str) -> None:
        self.id = uuid.uuid4().hex[:10]
        self.recipe_id = recipe_id
        self.answers: dict[str, str] = {}
        self.answer_events: dict[str, asyncio.Event] = {}
        self.report: Optional[dict] = None
        self.created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "")


BUILDS: dict[str, BuildSession] = {}
CONNECTED_CLIENTS = 0  # WebSocket clients (any path)
STREAMLIT_PROCS: list[subprocess.Popen] = []


# ---- Browser fallback ------------------------------------------------------

def _log_fallback(reason: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat().replace("+00:00", "")}Z  {reason}\n"
    try:
        FALLBACK_LOG.write_text(
            (FALLBACK_LOG.read_text(encoding="utf-8") if FALLBACK_LOG.exists() else "") + line,
            encoding="utf-8",
        )
    except OSError:
        pass


def _print_fallback_box(url: str, console: Optional[Console] = None) -> None:
    console = console or Console()
    body = Text()
    body.append("Il browser non si è aperto automaticamente\n", style="bold")
    body.append("Apri tu questo indirizzo:\n", style="dim")
    body.append(f"→ {url}", style="bold cyan")
    console.print(
        Panel(
            body,
            title="Gi.Ve Engine — Cabina di Regia",
            border_style="cyan",
            padding=(1, 4),
        )
    )


def _browser_fallback_watcher(url: str) -> None:
    """Run in a background thread. After N seconds, if no WS client showed up,
    print the fallback box and log the event."""
    time.sleep(BROWSER_FALLBACK_SECONDS)
    if CONNECTED_CLIENTS == 0:
        _print_fallback_box(url)
        _log_fallback(f"browser did not connect within {BROWSER_FALLBACK_SECONDS}s — printed fallback box")
    else:
        _log_fallback("browser connected within timeout — no fallback needed")


def _open_browser_async(url: str) -> None:
    def _go():
        try:
            webbrowser.open(url, new=2)
            _log_fallback(f"webbrowser.open invoked for {url}")
        except Exception as e:
            _log_fallback(f"webbrowser.open failed: {e!r}")
    threading.Thread(target=_go, daemon=True).start()


# ---- App factory -----------------------------------------------------------

def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Banner + browser open + fallback watcher are set up by main() before
    # uvicorn.run; lifespan stays focused on graceful shutdown.
    yield
    _shutdown_streamlit_children()


def create_app() -> FastAPI:
    app = FastAPI(title="Gi.Ve Engine — Cabina di Regia", lifespan=lifespan)

    @app.middleware("http")
    async def _no_cache_html(request, call_next):
        """Forza il re-fetch delle pagine HTML dopo un update.

        La Cabina è servita su un URL stabile (localhost:5000). Senza header di
        cache, i browser (Firefox in particolare) possono riusare la versione in
        cache: dopo `givengine update` l'utente vedrebbe la UI vecchia finché non
        fa un hard-refresh. `no-store` sulle risposte text/html elimina il
        problema; gli asset esterni (CDN, versionati) restano cacheabili.
        """
        response = await call_next(request)
        if response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Cache-Control"] = "no-store, must-revalidate"
        return response

    # --- HTML ---
    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        ui = TEMPLATES_DIR / "ui.html"
        if not ui.exists():
            raise HTTPException(500, "ui.html not found in core/templates/")
        return ui.read_text(encoding="utf-8")

    # --- Recipes ---
    @app.get("/recipes")
    async def get_recipes() -> list[dict]:
        # Return the full catalog = ricette installate localmente + tutte le
        # altre dal manifest (non installate, mostrate come bloccate/da
        # sbloccare). La UI mostra lock badge + upsell sui tier bloccati.
        local = _list_recipes()
        for r in local:
            r["installed"] = True
        extras = _catalog_only_entries({r["id"] for r in local})
        return local + extras

    @app.get("/catalog")
    async def get_catalog(tier: Optional[str] = None) -> dict:
        """Tier-filtered recipe catalog.

        ?tier=starter|catalog|all-access|all  (default: all-access licensed tier)
        """
        active_tier = tier or _current_tier()
        return {
            "active_tier": active_tier,
            "available_tiers": TIER_ORDER,
            "recipes": _list_recipes(active_tier),
        }

    @app.get("/recipes/{recipe_id}/tutorial", response_class=PlainTextResponse)
    async def get_tutorial(recipe_id: str) -> str:
        path = RECIPES_DIR / recipe_id / "tutorial.md"
        if not path.exists():
            raise HTTPException(404, "tutorial.md not found for recipe")
        return path.read_text(encoding="utf-8")

    # --- License management ---
    @app.get("/license/status")
    async def license_status(refresh: bool = False) -> dict:
        from core import licensing
        status = licensing.current_status(refresh=refresh)
        return status.to_dict()

    @app.post("/license/activate")
    async def license_activate(body: dict) -> dict:
        from core import licensing
        key = (body or {}).get("license_key", "").strip()
        instance_name = (body or {}).get("instance_name") or None
        if not key:
            raise HTTPException(400, "license_key richiesto")
        result = licensing.validator().activate(key, instance_name)
        return {
            "success": result.success,
            "message": result.message,
            "error_code": result.error_code,
            "status": result.status.to_dict(),
        }

    @app.post("/license/deactivate")
    async def license_deactivate() -> dict:
        from core import licensing
        ok = licensing.validator().deactivate()
        return {"success": ok, "message": "Licenza disattivata da questo PC." if ok else "Disattivazione fallita ma stato locale resettato."}

    # --- System (first-launch + auto-start) ---
    @app.get("/system/status")
    async def system_status(mark_seen: bool = False) -> dict:
        from core import system as _sys
        snap = _sys.snapshot()
        if mark_seen and snap["is_first_launch"]:
            _sys.mark_first_launch_done()
        return snap

    @app.get("/system/tos-status")
    async def system_tos_status() -> dict:
        """Returns the published ToS version + any pending changes.

        Used by the Cabina di Regia banner/modal to show the user when a
        new ToS revision is on the horizon. See LEGAL_COMPLIANCE.md §B2.

        Schema:
          - current_version  (str)    — version live on engine.givegroup.it/legal/termini.html
          - effective_from   (date)   — when current_version went live
          - in_legal_review  (bool)   — True until v1.0 is signed by legal
          - pending_version  (str?)   — next planned version, null if none
          - pending_kind     (str?)   — "ordinary" | "substantial_worse"
          - pending_effective_from (date?) — when the pending version takes effect
          - notice_url       (str)    — link to the public ToS archive
        """
        return {
            "current_version":        "0.9",
            "effective_from":         "2026-05-22",
            "in_legal_review":        True,
            "pending_version":        None,
            "pending_kind":           None,
            "pending_effective_from": None,
            "notice_url":             "https://engine.givegroup.it/legal/terms-archive",
        }

    @app.post("/system/autostart")
    async def system_autostart(body: dict) -> dict:
        from core import system as _sys
        enabled = bool((body or {}).get("enabled"))
        if enabled:
            ok, msg = _sys.enable_autostart()
        else:
            ok, msg = _sys.disable_autostart()
        return {
            "success": ok,
            "message": msg,
            "autostart": _sys.autostart_is_enabled(),
        }

    @app.post("/system/autostart-shell")
    async def system_autostart_shell(body: dict) -> dict:
        """Autostart via ~/.bash_profile (per ambienti shell-login/headless)."""
        from core import system as _sys
        enabled = bool((body or {}).get("enabled"))
        if enabled:
            ok, msg = _sys.enable_autostart_shell()
        else:
            ok, msg = _sys.disable_autostart_shell()
        return {
            "success": ok,
            "message": msg,
            "autostart_shell": _sys.shell_autostart_is_enabled(),
        }

    @app.post("/system/expose-lan")
    async def system_expose_lan(body: dict) -> dict:
        """Persist the toggle. Effect requires a restart (the launcher reads
        the preference at boot to pick the bind address)."""
        from core import system as _sys
        enabled = bool((body or {}).get("enabled"))
        _sys.set_expose_lan(enabled)
        return {
            "success": True,
            "expose_lan": _sys.expose_lan_pref(),
            "requires_restart": True,
            "message": (
                "Accesso LAN attivato. Si applica al prossimo avvio. "
                "Verifica che il firewall accetti la porta 5000 dalla tua rete."
                if enabled else
                "Accesso LAN disattivato. Si applica al prossimo avvio."
            ),
        }

    # --- Catalog updates (manifest diff) ---
    @app.get("/catalog/updates")
    async def catalog_updates() -> dict:
        from core import catalog_updates as cu
        return cu.checker().get_updates_since_last_seen().to_dict()

    @app.post("/catalog/mark-seen")
    async def catalog_mark_seen() -> dict:
        from core import catalog_updates as cu
        ok = cu.checker().mark_all_seen()
        return {"success": ok}

    @app.get("/novita", response_class=HTMLResponse)
    async def novita() -> str:
        ui = TEMPLATES_DIR / "novita.html"
        if not ui.exists():
            raise HTTPException(500, "novita.html not found in core/templates/")
        return ui.read_text(encoding="utf-8")

    # --- AI environment (transparency about external AI tooling) ---
    @app.get("/ai-environment/status")
    async def ai_environment_status() -> dict:
        from core import ai_environment as _ai
        det = _ai.detector()
        cached = det.load_cached()
        if cached and det.cache_is_fresh(max_age_s=86400.0):
            return cached
        # Stale or missing: kick a background refresh but still answer the
        # request immediately. Return the stale cache if we have one,
        # otherwise run a synchronous (sub-5s) check inline.
        if cached:
            import threading
            threading.Thread(
                target=det.refresh, name="ai-env-refresh", daemon=True,
            ).start()
            return cached
        return det.check()

    @app.post("/ai-environment/refresh")
    async def ai_environment_refresh() -> dict:
        from core import ai_environment as _ai
        return _ai.detector().refresh()

    @app.post("/system/ai-setup-dismiss")
    async def system_ai_setup_dismiss() -> dict:
        """Tracks how many distinct days the user clicked 'Più tardi' on the
        AI-setup card so we can stop showing it after 3 dismissals."""
        try:
            from core import system as _sys
            from datetime import datetime, timezone
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            last = _sys.get_pref("ai_setup_last_dismissed_at") or ""
            count = int(_sys.get_pref("ai_setup_dismissed_count", 0) or 0)
            if last[:10] != today:
                count += 1
                _sys.set_pref("ai_setup_dismissed_count", count)
                _sys.set_pref("ai_setup_last_dismissed_at", today)
            return {"ok": True, "count": count}
        except Exception:
            return {"ok": False}

    @app.post("/system/byok-interest")
    async def system_byok_interest() -> dict:
        """Local-only telemetry: increment a counter when the user clicks
        "Notify me when BYOK is ready". No tracking pings, no PII."""
        try:
            from core import system as _sys
            cur = int(_sys.get_pref("byok_interest_clicks", 0) or 0)
            _sys.set_pref("byok_interest_clicks", cur + 1)
            return {"ok": True, "clicks": cur + 1}
        except Exception:
            return {"ok": False}

    @app.post("/system/byok")
    async def system_byok_save(body: dict) -> dict:
        """Salva la chiave API Anthropic dell'utente in locale (mai inviata a Gi.Ve).

        Body: {"api_key": "..."}. Non restituisce mai la chiave, solo lo stato
        mascherato.
        """
        from core import system as _sys

        try:
            _sys.save_byok_key((body or {}).get("api_key", ""))
        except ValueError as exc:
            raise HTTPException(400, "Chiave mancante o vuota.") from exc
        return {"ok": True, "status": _sys.byok_status()}

    @app.delete("/system/byok")
    async def system_byok_clear() -> dict:
        from core import system as _sys

        removed = _sys.clear_byok_key()
        return {"ok": True, "removed": removed, "status": _sys.byok_status()}

    @app.post("/system/byok/test")
    async def system_byok_test() -> dict:
        """Verifica la chiave salvata con una chiamata minima ad Anthropic.

        Dimostra il consumo end-to-end della chiave BYOK. Non solleva mai 500
        verso la UI: ogni errore diventa {ok: false, message}.
        """
        from core import llm as _llm
        from core.shared.rag.exceptions import LLMError

        try:
            client = _llm.anthropic_client()
            client.complete(system_prompt="", user_prompt="ping", max_tokens=1)
            return {"ok": True, "message": "Chiave valida — connessione ad Anthropic riuscita."}
        except LLMError as exc:
            return {"ok": False, "message": f"Verifica fallita: {exc}"}
        except Exception as exc:  # noqa: BLE001 — mai propagare 500 alla UI
            return {"ok": False, "message": f"Errore inatteso: {exc}"}

    @app.get("/risorse-ia", response_class=HTMLResponse)
    async def risorse_ia() -> str:
        ui = TEMPLATES_DIR / "risorse_ia.html"
        if not ui.exists():
            raise HTTPException(500, "risorse_ia.html not found in core/templates/")
        # Side-effect: clear the "missing" nav dot once the user lands here.
        try:
            from core import system as _sys
            _sys.set_pref("risorse_ia_seen", True)
        except Exception:
            pass
        return ui.read_text(encoding="utf-8")

    # --- Build kickoff ---
    @app.post("/build/{recipe_id}")
    async def start_build(recipe_id: str) -> dict:
        if not (RECIPES_DIR / recipe_id / "recipe.yaml").exists():
            raise HTTPException(404, f"Recipe '{recipe_id}' not found")
        session = BuildSession(recipe_id)
        BUILDS[session.id] = session
        return {"build_id": session.id, "recipe_id": recipe_id}

    # --- Answers ---
    @app.post("/answer/{build_id}")
    async def submit_answer(build_id: str, body: dict) -> dict:
        session = BUILDS.get(build_id)
        if not session:
            raise HTTPException(404, "build not found")
        qid = body.get("id_domanda")
        risposta = body.get("risposta")
        if not qid or risposta is None:
            raise HTTPException(400, "id_domanda + risposta richiesti")
        session.answers[qid] = risposta
        event = session.answer_events.get(qid)
        if event:
            event.set()
        return {"ok": True}

    # --- WebSocket stream ---
    @app.websocket("/stream/{build_id}")
    async def stream(ws: WebSocket, build_id: str) -> None:
        global CONNECTED_CLIENTS
        await ws.accept()
        CONNECTED_CLIENTS += 1
        session = BUILDS.get(build_id)
        if not session:
            await ws.send_json({"stato": "errore", "messaggio": "Build non trovata"})
            await ws.close()
            CONNECTED_CLIENTS -= 1
            return

        try:
            await _run_build_stream(ws, session)
        except WebSocketDisconnect:
            pass
        finally:
            CONNECTED_CLIENTS = max(0, CONNECTED_CLIENTS - 1)

    @app.websocket("/heartbeat")
    async def heartbeat(ws: WebSocket) -> None:
        global CONNECTED_CLIENTS
        await ws.accept()
        CONNECTED_CLIENTS += 1
        try:
            await ws.send_json({"ok": True})
            while True:
                msg = await ws.receive_text()
                if msg == "ping":
                    await ws.send_text("pong")
        except WebSocketDisconnect:
            pass
        finally:
            CONNECTED_CLIENTS = max(0, CONNECTED_CLIENTS - 1)

    return app


# ---- Build streaming logic -------------------------------------------------

async def _run_build_stream(ws: WebSocket, session: BuildSession) -> None:
    states = _load_ui_states(session.recipe_id)

    for entry in states:
        stato = entry.get("stato")

        if stato == "human_in_loop":
            qid = entry.get("id_domanda", "q?")
            session.answer_events[qid] = asyncio.Event()
            await ws.send_json(entry)
            try:
                await asyncio.wait_for(session.answer_events[qid].wait(), timeout=120)
            except asyncio.TimeoutError:
                await ws.send_json({
                    "stato": "errore",
                    "messaggio": "Nessuna risposta ricevuta in 2 minuti, interrompo.",
                })
                return
            continue

        if stato == "consegna":
            try:
                if _is_generator_recipe(session.recipe_id):
                    inject_mod = _load_inject_module(session.recipe_id)
                    session.report = inject_mod.build(answers=session.answers)
                else:
                    # ready app: lancia direttamente il suo app.py, niente inject
                    session.report = _ready_app_report(session.recipe_id)
                spawn_info = _spawn_app(session.report)
                _mark_built(session.recipe_id)
                payload = dict(entry)
                payload["link"] = spawn_info["url"]
                payload["output_dir"] = session.report["output_dir"]
                payload["recipe_id"] = session.recipe_id
                await ws.send_json(payload)
            except Exception as e:
                await ws.send_json({
                    "stato": "errore",
                    "messaggio": f"Errore durante la consegna: {e}",
                })
            return

        # Normal "avanzamento" / "caveman"
        await ws.send_json(entry)
        await asyncio.sleep(_state_delay(entry))


def _state_delay(entry: dict) -> float:
    stato = entry.get("stato")
    if stato == "caveman":
        return 1.4
    if stato == "avanzamento":
        return 1.6
    return 0.8


# ---- Spawned app process management ----------------------------------------

def _free_port(host: str, port: int, timeout_s: float = 3.0) -> None:
    """Se la porta è occupata, termina chi è in ascolto e attende il rilascio.

    Risolve il caso in cui un avvio precedente dell'app ricetta ha lasciato un
    processo Streamlit zombie sulla porta: senza questo, il nuovo `streamlit
    run` non riesce a fare il bind ed esce subito → "connessione rifiutata".
    Best-effort: psutil se disponibile, altrimenti fuser/lsof.
    """
    if _port_available(host, port):
        return
    killed = False
    try:
        import psutil  # type: ignore
        for c in psutil.net_connections(kind="inet"):
            if c.laddr and c.laddr.port == port and c.status == psutil.CONN_LISTEN and c.pid:
                try:
                    psutil.Process(c.pid).terminate()
                    killed = True
                except Exception:
                    pass
    except Exception:
        for tool in (["fuser", "-k", f"{port}/tcp"],
                     ["bash", "-c", f"lsof -ti tcp:{port} | xargs -r kill"]):
            try:
                subprocess.run(tool, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=5)
                killed = True
                break
            except Exception:
                continue
    if not killed:
        return
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _port_available(host, port):
            return
        time.sleep(0.2)


def _default_streamlit_command(output_dir: str, port: int, expose_lan: bool) -> list[str]:
    entry = Path(output_dir) / "app.py"
    if not entry.exists():
        raise FileNotFoundError(f"Entrypoint Streamlit mancante: {entry}")
    address = "0.0.0.0" if expose_lan else "127.0.0.1"
    return [
        sys.executable, "-m", "streamlit", "run", str(entry),
        "--server.address", address,
        "--server.port", str(port),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ]


def _spawn_app(report: dict) -> dict:
    """Launch the child process for a freshly injected recipe.

    Recipes can declare their own launch_command in the build report (any
    binary + args). If absent we fall back to the historical Streamlit
    invocation for spese-casalinghe.
    """
    output_dir = report["output_dir"]
    port = int(report.get("porta_locale", 8501))
    expose_lan = bool(report.get("expose_lan"))
    cmd = report.get("launch_command")
    if not cmd:
        cmd = _default_streamlit_command(output_dir, port, expose_lan)

    env = os.environ.copy()
    env.update(report.get("launch_env") or {})
    if expose_lan:
        env.setdefault("EXPOSE_LAN", "1")

    address = "0.0.0.0" if expose_lan else "127.0.0.1"
    # Preflight: libera la porta se occupata da un avvio precedente (richiesta
    # utente: controlla all'avvio e termina il processo zombie).
    _free_port(address, port)

    # Log su file invece di DEVNULL: altrimenti gli errori del child (es.
    # streamlit/dipendenza mancante) spariscono e l'utente vede solo
    # "connessione rifiutata" senza traccia nei log.
    recipe_id = report.get("recipe_id", "app")
    log_path = LOGS_DIR / f"recipe-{recipe_id}.log"
    logf = open(log_path, "w", encoding="utf-8")  # noqa: SIM115 (vive col processo)
    proc = subprocess.Popen(
        cmd,
        cwd=output_dir,
        env=env,
        stdout=logf,
        stderr=subprocess.STDOUT,
    )
    STREAMLIT_PROCS.append(proc)

    # Healthcheck: attendi che il bind avvenga (porta non più libera) o che il
    # processo esca. Se non si avvia, solleva con le ultime righe di log così la
    # Cabina mostra l'errore vero invece di un link morto.
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            break
        if not _port_available(address, port):
            return {"pid": proc.pid, "url": f"http://localhost:{port}", "address": address}
        time.sleep(0.3)

    if proc.poll() is not None:
        try:
            logf.flush()
            tail = "\n".join(log_path.read_text(encoding="utf-8").splitlines()[-25:])
        except Exception:
            tail = "(log non leggibile)"
        raise RuntimeError(
            f"L'app non si è avviata (porta {port}). Probabile dipendenza "
            f"mancante nel venv. Ultime righe ({log_path}):\n{tail}"
        )
    # processo vivo ma porta non ancora pronta: ritorna comunque il link
    return {"pid": proc.pid, "url": f"http://localhost:{port}", "address": address}


def _shutdown_streamlit_children() -> None:
    for p in STREAMLIT_PROCS:
        if p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass
    deadline = time.time() + 3
    for p in STREAMLIT_PROCS:
        try:
            timeout = max(0.1, deadline - time.time())
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                p.kill()
            except Exception:
                pass
    STREAMLIT_PROCS.clear()


# ---- Entrypoint ------------------------------------------------------------

def _install_signal_handlers() -> None:
    def _handler(signum, frame):
        console = Console()
        console.print()
        console.print(Panel(
            "Sto chiudendo Gi.Ve Engine. Le tue app rimangono salvate.",
            border_style="yellow",
            padding=(0, 2),
        ))
        _shutdown_streamlit_children()
        sys.exit(0)

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Gi.Ve Engine — Cabina di Regia")
    parser.add_argument("--host", default=None,
                        help="Bind host (default 127.0.0.1, o 0.0.0.0 se preferenza expose_lan=true)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true",
                        help="Non aprire il browser automaticamente")
    parser.add_argument("--updated", action="store_true",
                        help="Interno: impostato dopo l'auto-update per evitare loop")
    args = parser.parse_args(argv)

    # Auto-update all'avvio: se c'è una versione nuova, aggiorna e ri-esegue col
    # codice aggiornato (no-op se offline / già aggiornato / GIVE_NO_UPDATE=1).
    try:
        from core import updater
        reexec = []
        if args.host:
            reexec += ["--host", args.host]
        reexec += ["--port", str(args.port)]
        if args.no_browser:
            reexec.append("--no-browser")
        updater.maybe_self_update(args.updated, reexec)
    except Exception:
        pass

    # When --host is omitted, honour the persisted "expose LAN" preference so
    # the UI toggle alone is enough to flip the bind address at next start.
    if not args.host:
        try:
            from core import system as _sys
            args.host = "0.0.0.0" if _sys.expose_lan_pref() else DEFAULT_HOST
        except Exception:
            args.host = DEFAULT_HOST

    if not _port_available(args.host, args.port):
        Console().print(Panel(
            f"La porta {args.port} è già in uso. Chiudi l'altra istanza o riprova.",
            border_style="red",
        ))
        return 1

    _install_signal_handlers()
    url = f"http://localhost:{args.port}"

    # Fire the catalog manifest fetch as soon as we know we'll boot. Bounded
    # 3s timeout inside the checker; runs in its own daemon thread so it never
    # blocks browser-open or uvicorn startup.
    try:
        from core import catalog_updates as _cu
        _cu.checker().check_async()
    except Exception:
        pass

    # Same pattern for the AI tooling detector: don't re-scan every boot if
    # the cache is fresh, otherwise refresh in background.
    try:
        from core import ai_environment as _ai
        import threading
        _det = _ai.detector()
        if not _det.cache_is_fresh(max_age_s=86400.0):
            threading.Thread(
                target=_det.refresh, name="ai-env-boot-refresh", daemon=True,
            ).start()
    except Exception:
        pass

    Console().print(Panel(
        Text.from_markup(
            "[bold]Gi.Ve Engine[/bold] — Cabina di Regia in avvio\n"
            f"In ascolto su [cyan]{url}[/cyan]"
        ),
        border_style="cyan",
        padding=(1, 4),
    ))

    if not args.no_browser:
        _open_browser_async(url)
        threading.Thread(
            target=_browser_fallback_watcher, args=(url,), daemon=True
        ).start()

    app = create_app()
    config = uvicorn.Config(app, host=args.host, port=args.port, log_level="warning")
    server = uvicorn.Server(config)
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
