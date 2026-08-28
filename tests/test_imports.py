"""S00 验收：包可 import、目录存在。"""

import importlib


def test_import_rflcc():
    mod = importlib.import_module("rflcc")
    assert mod.__version__ == "0.1.0"


def test_package_layout():
    for sub in (
        "types",
        "noise",
        "env",
        "trace",
        "policies",
        "scenarios",
        "feedback",
        "sequence",
        "qtables",
        "replay",
        "counterfactual",
        "oracle",
        "attribution",
        "router",
        "metrics",
        "logging_io",
        "stats",
        "plots",
    ):
        assert importlib.util.find_spec(f"rflcc.{sub}") is not None, sub


def test_baselines_package():
    for sub in (
        "standard",
        "immediate",
        "er",
        "pe_seq",
        "cf_only",
        "full_rfl",
        "oracle_upper",
    ):
        assert importlib.util.find_spec(f"rflcc.baselines.{sub}") is not None, sub
