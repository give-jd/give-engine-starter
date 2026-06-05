"""Test per core/checker.py (hardware checker → raccomandazione local/cloud)."""

from __future__ import annotations

import json

import pytest

from core import checker


class TestDecide:
    def test_local_high_quando_ram_gpu_cpu_sufficienti(self):
        assert checker._decide(32.0, 8.0, 8) == ("local", "high")

    def test_local_light_senza_gpu_ma_ram_e_cpu_ok(self):
        assert checker._decide(12.0, None, 4) == ("local_light", "medium")

    def test_local_light_con_gpu_debole(self):
        # vram < soglia → non "local", ma ram/cpu ok → local_light
        assert checker._decide(16.0, 2.0, 8) == ("local_light", "medium")

    def test_cloud_quando_ram_bassa(self):
        assert checker._decide(4.0, None, 8) == ("cloud", "high")

    def test_cloud_low_confidence_se_ram_sconosciuta(self):
        assert checker._decide(0.0, None, None) == ("cloud", "low")

    def test_cloud_se_cpu_insufficiente(self):
        assert checker._decide(32.0, 8.0, 2) == ("cloud", "high")


class TestFriendlyMessage:
    def test_local_menziona_gpu(self):
        msg = checker._friendly_message("local", 32.0, "RTX 4070")
        assert "locale" in msg and "RTX 4070" in msg and "32.0 GB" in msg

    def test_local_light_senza_gpu(self):
        msg = checker._friendly_message("local_light", 12.0, None)
        assert "leggera" in msg and "Nessuna GPU" in msg

    def test_cloud(self):
        msg = checker._friendly_message("cloud", 4.0, None)
        assert "cloud" in msg and "4.0 GB" in msg


class TestRun:
    def test_run_costruisce_report(self, monkeypatch):
        monkeypatch.setattr(checker, "_detect_cpu", lambda: ("TestCPU", 4, 8))
        monkeypatch.setattr(checker, "_detect_ram_gb", lambda: (32.0, 20.0))
        monkeypatch.setattr(checker, "_detect_gpu", lambda: ("RTX 4070", 12.0))
        rep = checker.run()
        assert rep.recommendation == "local"
        assert rep.confidence == "high"
        assert rep.cpu_model == "TestCPU"
        assert rep.ram_total_gb == pytest.approx(32.0)
        assert rep.gpu_name == "RTX 4070"
        assert "RTX 4070" in rep.friendly_message

    def test_run_cloud_su_macchina_debole(self, monkeypatch):
        monkeypatch.setattr(checker, "_detect_cpu", lambda: ("Weak", 2, 2))
        monkeypatch.setattr(checker, "_detect_ram_gb", lambda: (4.0, 2.0))
        monkeypatch.setattr(checker, "_detect_gpu", lambda: (None, None))
        rep = checker.run()
        assert rep.recommendation == "cloud"


class TestMain:
    def test_main_stampa_json_e_ritorna_0(self, monkeypatch, capsys):
        monkeypatch.setattr(checker, "_detect_cpu", lambda: ("CPU", 4, 8))
        monkeypatch.setattr(checker, "_detect_ram_gb", lambda: (16.0, 8.0))
        monkeypatch.setattr(checker, "_detect_gpu", lambda: (None, None))
        rc = checker.main()
        assert rc == 0
        out = capsys.readouterr().out
        payload = json.loads(out.split("\n\n")[0])
        assert payload["recommendation"] in {"local", "local_light", "cloud"}
        assert "Check Hardware" in out


class TestDetectRam:
    def test_proc_meminfo_fallback(self, monkeypatch, tmp_path):
        import sys

        monkeypatch.setitem(sys.modules, "psutil", None)  # forza ImportError → /proc
        meminfo = tmp_path / "meminfo"
        meminfo.write_text("MemTotal: 16777216 kB\nMemAvailable: 8388608 kB\n")
        monkeypatch.setattr(checker.os.path, "exists", lambda p: p == "/proc/meminfo")
        real_open = open

        def fake_open(path, *a, **k):
            target = meminfo if path == "/proc/meminfo" else path
            return real_open(target, *a, **k)

        monkeypatch.setattr("builtins.open", fake_open)
        total, avail = checker._detect_ram_gb()
        assert total == pytest.approx(16.0)
        assert avail == pytest.approx(8.0)
