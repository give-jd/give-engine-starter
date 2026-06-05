"""Test per core/caveman_optimizer.py (KanjiCompressor + folder bundler)."""

from __future__ import annotations

import pytest

from core import caveman_optimizer as cm


class TestKanjiCompressor:
    def test_compress_roundtrip_custom_mapping(self):
        kc = cm.KanjiCompressor(mapping={"utente": "用"})
        out = kc.compress("Il utente accede", aggressive=False)
        assert "用" in out
        assert "utente" in kc.decompress(out)

    def test_compress_aggressive_strips_stopwords(self):
        kc = cm.KanjiCompressor()
        full = kc.compress("questo è un testo di prova lungo", aggressive=True)
        light = kc.compress("questo è un testo di prova lungo", aggressive=False)
        assert len(full) <= len(light)

    def test_estimate_tokens(self):
        assert cm.KanjiCompressor._estimate_tokens("") == 1
        assert cm.KanjiCompressor._estimate_tokens("abcd" * 4) >= 1

    def test_stats(self):
        kc = cm.KanjiCompressor()
        s = kc.stats("autenticazione utente applicazione " * 5)
        assert s.tokens_original >= s.tokens_compressed
        assert isinstance(s.asdict(), dict)
        assert "saved_pct" in s.asdict()

    def test_stats_with_explicit_compressed(self):
        kc = cm.KanjiCompressor()
        s = kc.stats("testo", compressed="x")
        assert s.chars_original == 5


class TestBundleStats:
    def test_filestat_saved_pct(self):
        assert cm.FileStat("a", 100, 40).saved_pct == pytest.approx(60.0)
        assert cm.FileStat("a", 0, 0).saved_pct == pytest.approx(0.0)

    def test_bundle_stats(self):
        b = cm.Bundle(text="x", files=[cm.FileStat("a", 100, 40), cm.FileStat("b", 100, 60)])
        st = b.stats
        assert st["files"] == 2 and st["original_chars"] == 200
        assert st["saved_chars"] == 100

    def test_bundle_stats_empty(self):
        assert cm.Bundle(text="").stats["saved_pct"] == pytest.approx(0.0)


class TestCavemanOptimizer:
    def test_root_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            cm.CavemanOptimizer(tmp_path / "nope")

    def test_build_bundle(self, tmp_path):
        (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "skip.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "big.py").write_text("# " + "x" * 300_000, encoding="utf-8")
        (tmp_path / "bin.py").write_bytes(b"\xff\xfe\x00bad")
        opt = cm.CavemanOptimizer(tmp_path, max_bytes=200_000)
        bundle = opt.build_bundle()
        assert "### FILE: a.py" in bundle.text
        assert "skip.py" not in bundle.text  # exclude dir
        assert "big.py" not in bundle.text  # oltre max_bytes
        assert any(f.path == "a.py" for f in bundle.files)

    def test_generate_agents_md_from_human(self, tmp_path):
        recipes = tmp_path / "recipes"
        (recipes / "r1").mkdir(parents=True)
        (recipes / "r1" / "caveman_human.md").write_text("autenticazione utente", encoding="utf-8")
        opt = cm.CavemanOptimizer(tmp_path)
        out = opt.generate_agents_md("r1", recipes_root=recipes)
        assert "AGENTS.md" in out and "r1" in out

    def test_generate_agents_md_from_compressed(self, tmp_path):
        recipes = tmp_path / "recipes"
        (recipes / "r2").mkdir(parents=True)
        (recipes / "r2" / "caveman.md").write_text("用 contenuto", encoding="utf-8")
        opt = cm.CavemanOptimizer(tmp_path)
        out = opt.generate_agents_md("r2", recipes_root=recipes)
        assert "用 contenuto" in out

    def test_generate_agents_md_missing_recipe(self, tmp_path):
        opt = cm.CavemanOptimizer(tmp_path)
        with pytest.raises(FileNotFoundError):
            opt.generate_agents_md("ignota", recipes_root=tmp_path / "recipes")

    def test_generate_agents_md_no_source(self, tmp_path):
        recipes = tmp_path / "recipes"
        (recipes / "r3").mkdir(parents=True)
        opt = cm.CavemanOptimizer(tmp_path)
        with pytest.raises(FileNotFoundError):
            opt.generate_agents_md("r3", recipes_root=recipes)
