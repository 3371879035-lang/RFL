import importlib
import sys


def test_new_package_imports_without_old_package():
    for name in ("rflnext", "rflnext.qtables", "rflnext.stats", "rflnext.knowledge"):
        sys.modules.pop(name, None)
    sys.modules.pop("rflcc", None)
    for name in ("rflnext", "rflnext.qtables", "rflnext.stats", "rflnext.knowledge"):
        importlib.import_module(name)
    assert "rflcc" not in sys.modules


def test_forbidden_old_semantics_absent():
    import rflnext

    forbidden = (
        "normalize_responsibility",
        "UpdateRouter",
        "responsibility_to_rho",
        "is_low_protection",
        "is_high_protection",
        "ScenarioGenerator",
        "OracleEvaluator",
    )
    for name in forbidden:
        assert not hasattr(rflnext, name), f"forbidden v0.2 symbol leaked: {name}"


def test_vendored_qtables_is_generic():
    from rflnext.qtables import QTables

    q = QTables(n_actions=4, options=(0, 1))
    q.low_update((0, 0, 1), 2, 1.0, 1.0)
    assert q.low_get((0, 0, 1), 2) == 1.0
    q.high_update((1, 0), 1, 0.5, 1.0)
    assert q.high_get((1, 0), 1) == 0.5
    assert isinstance(q.deep_hash(), str)


def test_vendored_stats_and_knowledge_importable():
    from rflnext.knowledge import correct_knowledge_damage
    from rflnext.stats import cohens_dz

    assert cohens_dz.__name__ == "cohens_dz"
    assert correct_knowledge_damage({"a": 0.6, "b": 0.0}, {"a": 0.5, "b": 0.0}, "a") > 0
