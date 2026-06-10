import core.installed_registry as reg


def test_register_and_query(monkeypatch):
    store: dict = {}
    monkeypatch.setattr(reg, "_get_pref", lambda k, d=None: store.get(k, d))
    monkeypatch.setattr(reg, "_set_pref", lambda k, v: store.__setitem__(k, v))

    reg.register_installed("vault-clienti", port=8521, version="1.5.0", output_dir="/tmp/v")
    assert reg.is_installed("vault-clienti") is True
    assert reg.get_port("vault-clienti") == 8521
    rows = reg.list_installed()
    assert rows[0]["slug"] == "vault-clienti"
    assert rows[0]["status"] == "installed"
    assert isinstance(rows[0]["installed_at"], str)
    assert rows[0]["installed_at"]
    assert "T" in rows[0]["installed_at"]


def test_legacy_flat_built_recipes_migrated(monkeypatch):
    store: dict = {"built_recipes": ["spese-casalinghe", "vault-clienti"]}
    monkeypatch.setattr(reg, "_get_pref", lambda k, d=None: store.get(k, d))
    monkeypatch.setattr(reg, "_set_pref", lambda k, v: store.__setitem__(k, v))

    assert reg.is_installed("spese-casalinghe") is True
    rows = {r["slug"] for r in reg.list_installed()}
    assert rows == {"spese-casalinghe", "vault-clienti"}
    # port unknown for legacy entries
    assert reg.get_port("spese-casalinghe") is None


def test_not_installed(monkeypatch):
    store: dict = {}
    monkeypatch.setattr(reg, "_get_pref", lambda k, d=None: store.get(k, d))
    monkeypatch.setattr(reg, "_set_pref", lambda k, v: store.__setitem__(k, v))
    assert reg.is_installed("ghost") is False
    assert reg.get_port("ghost") is None
