r"""The mutation tables' own preconditions, as unit tests.

Twice now a self-check reported `MUTATION_NOT_APPLIED` for a reason that had nothing to do
with the code under test: an anchor went stale when the line it quoted was rewritten, and —
four times — a helper script rewrote a source file through ``Path.write_text``, which
translates ``\n`` to ``os.linesep`` on Windows. Anchors compare **working-tree bytes**, so
a newline translation is indistinguishable from a source change to them.

Both are mechanical, and both used to surface only after running eight pytest subprocesses
inside a mutation self-check. Here they are two loops:

$$\boxed{\text{every mutation's site is LF} \quad\land\quad
\text{every anchor matches exactly once}}$$

A stale anchor is then a red unit test rather than a mystery in a summary table.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

SELF_CHECKS = ("b1_interface_gate_selfcheck", "q_substrate_gate_selfcheck",
               "l0_factual_gate_selfcheck", "l2_counterfactual_gate_selfcheck",
               "l3_row_restore_gate_selfcheck",
               "address_domain_gate_selfcheck")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _all_mutations():
    out = []
    for name in SELF_CHECKS:
        module = _load(name)
        for entry in module.MUTATIONS:
            out.append((name, entry[0], pathlib.Path(entry[2]), entry[3], entry[5]))
    return out


def test_1_every_mutation_site_is_in_the_source_tree():
    missing = [str(p.relative_to(ROOT)) for _n, _k, p, _a, _g in _all_mutations()
               if not p.is_file()]
    assert not missing, f"mutation sites that do not exist: {missing}"


def test_2_every_mutation_site_uses_lf_line_endings():
    r"""$$\boxed{\text{a CRLF working tree makes every multi-line anchor unmatchable}}$$

    ``core.autocrlf=true`` with no ``.gitattributes`` means the index is always LF while
    the working-tree bytes depend on whoever wrote the file last. Editing source through
    ``Path.read_text``/``write_text`` therefore silently converts a file, and the next
    self-check reports ``MUTATION_NOT_APPLIED`` on every multi-line anchor in it — which
    looks like a broken harness rather than a newline.
    """
    crlf = []
    for name, key, path, _anchor, _gate in _all_mutations():
        if b"\r\n" in path.read_bytes():
            crlf.append(f"{name}:{key} -> {path.relative_to(ROOT)}")
    assert not crlf, (
        "these mutation sites have CRLF in the working tree, so their anchors cannot "
        f"match: {sorted(set(crlf))}. Normalize with newline=\"\" reads and writes")


def test_3_every_anchor_matches_exactly_once():
    """A stale anchor is a red test here instead of a `MUTATION_NOT_APPLIED` later."""
    bad = []
    for name, key, path, anchor, _gate in _all_mutations():
        with open(path, "r", encoding="utf-8", newline="") as fh:
            text = fh.read()
        count = text.count(anchor)
        if count != 1:
            bad.append(f"{name}:{key} matched {count} times in "
                       f"{path.relative_to(ROOT)}")
    assert not bad, bad


def test_4_every_gate_node_exists():
    """The same pre-flight the self-checks run, so a rename is caught without them."""
    bad = []
    for name, key, _path, _anchor, gate in _all_mutations():
        rel, _, test = gate.partition("::")
        try:
            with open(ROOT / rel, "r", encoding="utf-8", newline="") as fh:
                src = fh.read()
        except OSError:
            bad.append(f"{name}:{key} -> {rel} is missing")
            continue
        if f"def {test}(" not in src:
            bad.append(f"{name}:{key} -> {gate} has no such test")
    assert not bad, bad


def test_5_the_self_check_tables_are_not_empty():
    """A table that lost its entries would make every loop above vacuous."""
    for name in SELF_CHECKS:
        module = _load(name)
        assert len(module.MUTATIONS) >= 6, f"{name} has {len(module.MUTATIONS)} mutations"
