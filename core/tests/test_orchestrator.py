"""Test per core/orchestrator.py (Cabina di Regia FastAPI).

Usa TestClient per i route handler + unit per gli helper. Tutti i moduli
lazy-importati nei handler (licensing/system/catalog_updates/ai_environment)
sono monkeypatchati per evitare rete e side-effect su ~/.givengine.
"""

from __future__ import annotations

import socket

import pytest
from fastapi.testclient import TestClient

from core import ai_environment, catalog_updates, licensing
from core import orchestrator as orch
from core import system as sysmod


@pytest.fixture
def client():
    return TestClient(orch.create_app())


# ---------- helper puri -------------------------------------------------------
class TestHelpers:
    def test_tier_allows(self):
        assert orch._tier_allows("all-access", "catalog") is True
        assert orch._tier_allows("starter", "catalog") is False
        assert orch._tier_allows("catalog", "catalog") is True
        assert orch._tier_allows("ignoto", "x") is True  # ValueError → permissivo

    def test_current_tier_ok(self, monkeypatch):
        monkeypatch.setattr(licensing, "current_tier", lambda: "catalog")
        assert orch._current_tier() == "catalog"

    def test_current_tier_exception_fallback(self, monkeypatch):
        def boom():
            raise RuntimeError("x")

        monkeypatch.setattr(licensing, "current_tier", boom)
        assert orch._current_tier() == "starter"

    def test_list_recipes_real_dir(self):
        recipes = orch._list_recipes()
        assert isinstance(recipes, list) and len(recipes) > 0
        assert all("id" in r and "tier" in r for r in recipes)

    def test_list_recipes_filter_starter(self):
        only = orch._list_recipes("starter")
        assert all(r["tier"] == "starter" for r in only)

    def test_load_ui_states_missing(self):
        with pytest.raises(FileNotFoundError):
            orch._load_ui_states("recipe-inesistente-zzz")

    def test_load_ui_states_real(self):
        states = orch._load_ui_states("spese-casalinghe")
        assert isinstance(states, list) and states

    def test_load_inject_missing(self):
        with pytest.raises(FileNotFoundError):
            orch._load_inject_module("recipe-inesistente-zzz")

    def test_state_delay(self):
        assert orch._state_delay({"stato": "caveman"}) == pytest.approx(1.4)
        assert orch._state_delay({"stato": "avanzamento"}) == pytest.approx(1.6)
        assert orch._state_delay({"stato": "altro"}) == pytest.approx(0.8)

    def test_port_available_and_busy(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        try:
            assert orch._port_available("127.0.0.1", port) is False  # occupata
        finally:
            s.close()
        assert orch._port_available("127.0.0.1", port) is True  # ora libera

    def test_default_streamlit_command_missing_app(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            orch._default_streamlit_command(str(tmp_path), 8501, False)

    def test_default_streamlit_command_ok(self, tmp_path):
        (tmp_path / "app.py").write_text("x")
        cmd = orch._default_streamlit_command(str(tmp_path), 8505, True)
        assert "streamlit" in cmd and "8505" in cmd
        assert "0.0.0.0" in cmd  # expose_lan

    def test_build_session(self):
        s = orch.BuildSession("spese-casalinghe")
        assert len(s.id) == 10 and s.recipe_id == "spese-casalinghe"
        assert s.answers == {} and s.report is None


# ---------- spawn / shutdown --------------------------------------------------
class TestSpawn:
    def test_spawn_app_mock(self, tmp_path, monkeypatch):
        (tmp_path / "app.py").write_text("x")

        class _Proc:
            pid = 4242

            def poll(self):
                return None

        monkeypatch.setattr(orch.subprocess, "Popen", lambda *a, **k: _Proc())
        monkeypatch.setattr(orch, "STREAMLIT_PROCS", [])
        info = orch._spawn_app({"output_dir": str(tmp_path), "porta_locale": 8888})
        assert info["pid"] == 4242 and "8888" in info["url"]

    def test_shutdown_children(self, monkeypatch):
        terminated = {"n": 0}

        class _P:
            def __init__(self):
                self._alive = True

            def poll(self):
                return None if self._alive else 0

            def terminate(self):
                terminated["n"] += 1
                self._alive = False

            def wait(self, timeout=None):
                return 0

        monkeypatch.setattr(orch, "STREAMLIT_PROCS", [_P(), _P()])
        orch._shutdown_streamlit_children()
        assert terminated["n"] == 2
        assert orch.STREAMLIT_PROCS == []


# ---------- browser fallback --------------------------------------------------
class TestFallback:
    def test_log_fallback(self, tmp_path, monkeypatch):
        monkeypatch.setattr(orch, "FALLBACK_LOG", tmp_path / "fb.log")
        orch._log_fallback("ciao")
        orch._log_fallback("due")
        assert "ciao" in (tmp_path / "fb.log").read_text()

    def test_print_fallback_box(self):
        from rich.console import Console

        orch._print_fallback_box("https://x", console=Console(quiet=True))

    def test_open_browser_async(self, monkeypatch):
        opened = {}
        monkeypatch.setattr(orch.webbrowser, "open", lambda u, new=0: opened.setdefault("u", u))
        monkeypatch.setattr(orch, "_log_fallback", lambda *a: None)
        orch._open_browser_async("https://x")
        import time as _t

        _t.sleep(0.05)
        assert opened.get("u") == "https://x"

    def test_browser_fallback_watcher(self, monkeypatch):
        monkeypatch.setattr(orch, "BROWSER_FALLBACK_SECONDS", 0.0)
        monkeypatch.setattr(orch, "CONNECTED_CLIENTS", 0)
        logged = []
        monkeypatch.setattr(orch, "_log_fallback", lambda m: logged.append(m))
        monkeypatch.setattr(orch, "_print_fallback_box", lambda *a, **k: None)
        orch._browser_fallback_watcher("https://x")
        assert any("fallback box" in m for m in logged)


# ---------- endpoint HTTP -----------------------------------------------------
class TestHttpEndpoints:
    def test_index(self, client):
        assert client.get("/").status_code == 200

    def test_recipes(self, client):
        r = client.get("/recipes")
        assert r.status_code == 200 and isinstance(r.json(), list)

    def test_catalog(self, client, monkeypatch):
        monkeypatch.setattr(orch, "_current_tier", lambda: "catalog")
        r = client.get("/catalog")
        assert r.status_code == 200
        assert r.json()["active_tier"] == "catalog"

    def test_tutorial_ok_and_404(self, client):
        assert client.get("/recipes/spese-casalinghe/tutorial").status_code == 200
        assert client.get("/recipes/nope-zzz/tutorial").status_code == 404

    def test_tos_status(self, client):
        r = client.get("/system/tos-status")
        assert r.status_code == 200 and r.json()["current_version"] == "0.9"

    def test_novita_risorse(self, client, monkeypatch):
        monkeypatch.setattr(sysmod, "set_pref", lambda *a, **k: None)
        assert client.get("/novita").status_code == 200
        assert client.get("/risorse-ia").status_code == 200

    def test_license_status(self, client, monkeypatch):
        monkeypatch.setattr(
            licensing, "current_status",
            lambda refresh=False: licensing.LicenseStatus(valid=False, tier="starter"),
        )
        assert client.get("/license/status").json()["tier"] == "starter"

    def test_license_activate_400(self, client):
        assert client.post("/license/activate", json={}).status_code == 400

    def test_license_activate_ok(self, client, monkeypatch):
        class _V:
            def activate(self, key, name):
                return licensing.ActivationResult(
                    success=True,
                    status=licensing.LicenseStatus(valid=True, tier="catalog"),
                    message="ok",
                )

        monkeypatch.setattr(licensing, "validator", lambda: _V())
        r = client.post("/license/activate", json={"license_key": "K"})
        assert r.json()["success"] is True

    def test_license_deactivate(self, client, monkeypatch):
        class _V:
            def deactivate(self):
                return True

        monkeypatch.setattr(licensing, "validator", lambda: _V())
        assert client.post("/license/deactivate").json()["success"] is True

    def test_system_status(self, client, monkeypatch):
        monkeypatch.setattr(sysmod, "snapshot", lambda: {"is_first_launch": False, "os": "linux"})
        assert client.get("/system/status").json()["os"] == "linux"

    def test_system_autostart(self, client, monkeypatch):
        monkeypatch.setattr(sysmod, "enable_autostart", lambda: (True, "on"))
        monkeypatch.setattr(sysmod, "autostart_is_enabled", lambda: True)
        r = client.post("/system/autostart", json={"enabled": True})
        assert r.json()["success"] is True and r.json()["autostart"] is True

    def test_system_expose_lan(self, client, monkeypatch):
        monkeypatch.setattr(sysmod, "set_expose_lan", lambda v: None)
        monkeypatch.setattr(sysmod, "expose_lan_pref", lambda: True)
        r = client.post("/system/expose-lan", json={"enabled": True})
        assert r.json()["requires_restart"] is True

    def test_catalog_updates_and_mark(self, client, monkeypatch):
        class _C:
            def get_updates_since_last_seen(self):
                return catalog_updates.UpdatesResult(has_updates=True, new_count=1)

            def mark_all_seen(self):
                return True

        monkeypatch.setattr(catalog_updates, "checker", lambda: _C())
        assert client.get("/catalog/updates").json()["new_count"] == 1
        assert client.post("/catalog/mark-seen").json()["success"] is True

    def test_ai_environment(self, client, monkeypatch):
        class _D:
            def load_cached(self):
                return {"platform": "linux"}

            def cache_is_fresh(self, max_age_s=0):
                return True

            def refresh(self):
                return {"platform": "linux", "refreshed": True}

        monkeypatch.setattr(ai_environment, "detector", lambda: _D())
        assert client.get("/ai-environment/status").json()["platform"] == "linux"
        assert client.post("/ai-environment/refresh").json()["refreshed"] is True

    def test_dismiss_and_byok(self, client, monkeypatch):
        store = {}
        monkeypatch.setattr(sysmod, "get_pref", lambda k, d=None: store.get(k, d))
        monkeypatch.setattr(sysmod, "set_pref", lambda k, v: store.__setitem__(k, v))
        assert client.post("/system/ai-setup-dismiss").json()["ok"] is True
        assert client.post("/system/byok-interest").json()["ok"] is True

    def test_build_and_answer(self, client):
        assert client.post("/build/nope-zzz").status_code == 404
        bid = client.post("/build/spese-casalinghe").json()["build_id"]
        assert client.post(f"/answer/{bid}", json={}).status_code == 400
        assert client.post("/answer/nope", json={"id_domanda": "q", "risposta": "r"}).status_code == 404
        ok = client.post(f"/answer/{bid}", json={"id_domanda": "q", "risposta": "r"})
        assert ok.json()["ok"] is True


# ---------- WebSocket ---------------------------------------------------------
class TestWebSocket:
    def test_heartbeat(self, client):
        with client.websocket_connect("/heartbeat") as ws:
            assert ws.receive_json() == {"ok": True}
            ws.send_text("ping")
            assert ws.receive_text() == "pong"

    def test_stream_build_not_found(self, client):
        with client.websocket_connect("/stream/nonexistent") as ws:
            msg = ws.receive_json()
            assert msg["stato"] == "errore"


# ---------- main() (mockato) --------------------------------------------------
class TestMain:
    def test_port_busy_returns_1(self, monkeypatch):
        monkeypatch.setenv("GIVE_NO_UPDATE", "1")  # niente auto-update in test
        monkeypatch.setattr(orch, "_port_available", lambda h, p: False)
        monkeypatch.setattr(sysmod, "expose_lan_pref", lambda: False)
        assert orch.main(["--no-browser", "--port", "5999"]) == 1

    def test_main_runs_and_returns_0(self, monkeypatch):
        monkeypatch.setenv("GIVE_NO_UPDATE", "1")  # niente auto-update in test
        monkeypatch.setattr(orch, "_port_available", lambda h, p: True)
        monkeypatch.setattr(orch, "_install_signal_handlers", lambda: None)
        monkeypatch.setattr(sysmod, "expose_lan_pref", lambda: False)

        class _C:
            def check_async(self):
                return None

        monkeypatch.setattr(catalog_updates, "checker", lambda: _C())

        class _D:
            def cache_is_fresh(self, max_age_s=0):
                return True

        monkeypatch.setattr(ai_environment, "detector", lambda: _D())
        monkeypatch.setattr(orch.uvicorn.Server, "run", lambda self: None)
        assert orch.main(["--no-browser"]) == 0


# ---------- cache headers -----------------------------------------------------
class TestNoCacheHtml:
    """Le pagine HTML non devono essere cacheabili: dopo un update il browser
    deve rifare il fetch (altrimenti Firefox mostra la UI vecchia in cache)."""

    def test_html_routes_are_no_store(self, client):
        r = client.get("/")
        assert r.headers["content-type"].startswith("text/html")
        assert r.headers["cache-control"] == "no-store, must-revalidate"

    def test_json_routes_not_forced_no_store(self, client):
        r = client.get("/recipes")
        assert r.headers["content-type"].startswith("application/json")
        assert "no-store" not in r.headers.get("cache-control", "")


# ---------- BYOK --------------------------------------------------------------
class TestByokEndpoints:
    def test_save_ok(self, client, monkeypatch):
        saved = {}
        monkeypatch.setattr(sysmod, "save_byok_key", lambda k: saved.__setitem__("k", k))
        monkeypatch.setattr(sysmod, "byok_status", lambda: {"configured": True, "masked": "sk-ant-…WXYZ"})
        r = client.post("/system/byok", json={"api_key": "sk-ant-secret-WXYZ"})
        assert r.json()["ok"] is True
        assert r.json()["status"]["configured"] is True
        assert saved["k"] == "sk-ant-secret-WXYZ"
        # la chiave intera non deve mai comparire nella risposta
        assert "secret" not in r.text

    def test_save_empty_400(self, client, monkeypatch):
        def _raise(_):
            raise ValueError("chiave vuota")

        monkeypatch.setattr(sysmod, "save_byok_key", _raise)
        assert client.post("/system/byok", json={"api_key": ""}).status_code == 400

    def test_delete(self, client, monkeypatch):
        monkeypatch.setattr(sysmod, "clear_byok_key", lambda: True)
        monkeypatch.setattr(sysmod, "byok_status", lambda: {"configured": False, "masked": None})
        r = client.delete("/system/byok")
        assert r.json()["ok"] is True and r.json()["removed"] is True

    def test_test_ok(self, client, monkeypatch):
        from core import llm as _llm

        class _Client:
            def complete(self, **kw):
                return "x"

        monkeypatch.setattr(_llm, "anthropic_client", lambda: _Client())
        r = client.post("/system/byok/test")
        assert r.json()["ok"] is True

    def test_test_no_key(self, client, monkeypatch):
        from core import llm as _llm
        from core.shared.rag.exceptions import LLMError

        def _raise():
            raise LLMError("nessuna chiave")

        monkeypatch.setattr(_llm, "anthropic_client", _raise)
        r = client.post("/system/byok/test")
        assert r.json()["ok"] is False
        assert "Verifica fallita" in r.json()["message"]


# ---------- ui_states fallback (ricette "ready app") --------------------------
class TestUiStatesFallback:
    """Le ricette con app.py ma senza ui_states.json (la maggioranza) non devono
    più bloccare il build con FileNotFoundError: si sintetizza una sequenza."""

    def test_generator_recipe_detected(self):
        assert orch._is_generator_recipe("spese-casalinghe") is True
        assert orch._is_generator_recipe("bollette-watcher") is False

    def test_ready_app_gets_synth_states(self):
        states = orch._load_ui_states("bollette-watcher")
        assert [s["stato"] for s in states][-1] == "consegna"
        assert all("messaggio" in s for s in states)

    def test_generator_states_unchanged(self):
        states = orch._load_ui_states("spese-casalinghe")
        assert any(s["stato"] == "human_in_loop" for s in states)

    def test_ready_app_report_points_to_recipe_dir(self):
        rep = orch._ready_app_report("bollette-watcher")
        assert rep["output_dir"].endswith("bollette-watcher")
        assert rep["recipe_id"] == "bollette-watcher"
        assert isinstance(rep["porta_locale"], int)

    def test_missing_everything_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(orch, "RECIPES_DIR", tmp_path)
        (tmp_path / "ghost").mkdir()
        with pytest.raises(FileNotFoundError):
            orch._load_ui_states("ghost")


# ---------- spawn app: errori visibili + porta ------------------------------
class TestSpawnApp:
    """L'app ricetta che non parte (es. dipendenza mancante) non deve più dare
    un link morto silenzioso: _spawn_app solleva con le ultime righe di log."""

    def test_spawn_failure_raises_with_log(self, tmp_path, monkeypatch):
        import socket
        import sys as _sys
        monkeypatch.setattr(orch, "LOGS_DIR", tmp_path)
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        report = {
            "output_dir": str(tmp_path),
            "porta_locale": port,
            "recipe_id": "selftest",
            "launch_command": [_sys.executable, "-c",
                               "import sys; sys.stderr.write('ModuleNotFoundError: streamlit\\n'); sys.exit(1)"],
        }
        with pytest.raises(RuntimeError) as ei:
            orch._spawn_app(report)
        assert "non si è avviata" in str(ei.value)
        assert "streamlit" in str(ei.value)  # tail del log incluso

    def test_free_port_noop_when_available(self):
        import socket
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        orch._free_port("127.0.0.1", port)  # porta libera → ritorna subito
