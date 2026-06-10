from core.shared.deps.models import Dependency, RecipeNode


def test_dependency_fields():
    dep = Dependency(slug="vault-clienti", kind="required", min_version="1.5.0", reason="r")
    assert dep.slug == "vault-clienti"
    assert dep.kind == "required"
    assert dep.min_version == "1.5.0"
    assert dep.reason == "r"


def test_recipe_node_groups_deps_by_kind():
    node = RecipeNode(
        slug="cartella-clinica-light",
        tier="catalog",
        version="1.0.0",
        deps=[
            Dependency("vault-clienti", "required", "1.5.0", "archivio"),
            Dependency("agenda-studio", "recommended", "1.2.0", "appuntamenti"),
            Dependency("scadenze-auto-casa", "optional", None, "promemoria"),
        ],
    )
    assert [d.slug for d in node.required] == ["vault-clienti"]
    assert [d.slug for d in node.recommended] == ["agenda-studio"]
    assert [d.slug for d in node.optional] == ["scadenze-auto-casa"]
