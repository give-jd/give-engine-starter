from pathlib import Path

from core.shared.deps.resolver import load_graph


def _write_recipe(root: Path, slug: str, body: str) -> None:
    d = root / slug
    d.mkdir(parents=True)
    (d / "recipe.yaml").write_text(body, encoding="utf-8")


def test_load_graph_parses_dependencies(tmp_path: Path):
    _write_recipe(tmp_path, "vault-clienti", """
id: vault-clienti
tier: catalog
versione: "1.5.0"
""")
    _write_recipe(tmp_path, "cartella-clinica-light", """
id: cartella-clinica-light
tier: catalog
versione: "1.0.0"
dependencies:
  required:
    - {slug: vault-clienti, min_version: "1.5.0", reason: "archivio"}
  recommended:
    - {slug: agenda-studio, min_version: "1.2.0", reason: "appuntamenti"}
  optional:
    - {slug: scadenze-auto-casa, reason: "promemoria"}
""")
    graph = load_graph(tmp_path)
    assert set(graph.nodes) == {"vault-clienti", "cartella-clinica-light"}
    ccl = graph.nodes["cartella-clinica-light"]
    assert [d.slug for d in ccl.required] == ["vault-clienti"]
    assert ccl.required[0].min_version == "1.5.0"
    assert [d.slug for d in ccl.recommended] == ["agenda-studio"]
    assert [d.slug for d in ccl.optional] == ["scadenze-auto-casa"]
    assert ccl.optional[0].min_version is None


def test_load_graph_recipe_without_dependencies(tmp_path: Path):
    _write_recipe(tmp_path, "spese-casalinghe", """
id: spese-casalinghe
tier: starter
versione: "1.0.0"
""")
    graph = load_graph(tmp_path)
    assert graph.nodes["spese-casalinghe"].deps == []
