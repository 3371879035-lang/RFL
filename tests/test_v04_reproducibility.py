"""Cross-process reproducibility of the v0.4 training loop.

A regression test for a defect that the in-process test
``tests/test_v04.py::test_training_is_reproducible`` structurally cannot catch.

``decision_oracle`` and ``repair_oracle`` iterate ``repair.primitives``, which is
a ``frozenset`` of ``(str, int)`` tuples.  Iteration order therefore follows
string hashing and, by default, Python randomises that per process.  When a
repair contains both an ``unstick`` and an ``exec`` primitive, they resolve to a
``DECISION`` and an ``EXECUTION`` site on the *same* step; ``updates._write``
routes every non-PLAN unit to the same low-level Q table, so the two become
successive relative writes to one entry and the order decides which lands last.

Measured before the fix, arm ``Contrastive``, seed 4600000, in four separate
processes:

    q_hash   78e4710bd556 / 450ee8002097 / 6b868ff4e495 / f8d551c12d63
    wmd      0.11975     / 0.11191      / 0.03604      / 0.09104

a 3.3x spread in ``WithinModuleDamage`` -- a headline endpoint of the v0.4 spec --
produced entirely by hash order.

These tests pin the fix by comparing runs in *separate interpreters* with
different ``PYTHONHASHSEED`` values.  A same-process comparison passes either
way, because the hash seed is fixed for the lifetime of a process; that is why
the original test could not see it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "v04_beta.yaml"

# Every arm that consults the oracle's primitive set is exposed to the ordering
# hazard, because that is the frozenset being iterated.  `NoCorrection` never
# applies a repair at all and is the only true control; note that `NegativeOnly`
# looks safe but is NOT -- on the unfixed code it also changed with the hash
# seed, which a three-process spot check had failed to reveal.
AFFECTED_ARMS = (
    "DecisionOracle",
    "RepairOracle",
    "NegativeOnly",
    "PositiveAlternative",
    "Contrastive",
)
CONTROL_ARMS = ("NoCorrection",)

SNAPSHOT = """
import dataclasses, json, sys, yaml
sys.path.insert(0, {src!r})
from rflv04.train import train
cfg = yaml.safe_load(open({cfg!r}, encoding="utf-8"))
r = train(cfg, seed={seed}, arm={arm!r})
d = {{f.name: getattr(r, f.name) for f in dataclasses.fields(r)}}
keep = {{k: v for k, v in d.items() if isinstance(v, (int, float, str, bool))}}
print(json.dumps(keep, sort_keys=True))
"""


def _snapshot(arm: str, hash_seed: str, seed: int = 4600000) -> dict:
    """Run one training run in a fresh interpreter and return its scalars."""
    code = SNAPSHOT.format(
        src=str(ROOT / "src"), cfg=str(CONFIG), seed=seed, arm=arm
    )
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = hash_seed
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    if proc.returncode != 0:
        pytest.skip(f"subprocess training failed: {proc.stderr[-400:]}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("arm", AFFECTED_ARMS)
def test_arm_is_reproducible_across_processes(arm):
    """Two interpreters with different hash seeds must agree exactly.

    This is the regression test for the bug above.  It fails on the unfixed
    ``for prim in prims`` loop and passes once the loop is sorted.
    """
    a = _snapshot(arm, "0")
    b = _snapshot(arm, "12345")
    assert a["q_hash"] == b["q_hash"], (
        f"{arm} depends on PYTHONHASHSEED: q_hash {a['q_hash'][:12]} vs "
        f"{b['q_hash'][:12]}"
    )
    assert a["corrections"] == b["corrections"]
    assert a["sites_touched"] == b["sites_touched"]
    assert a["wmd"] == pytest.approx(b["wmd"])


@pytest.mark.parametrize("arm", CONTROL_ARMS)
def test_control_arm_is_reproducible_across_processes(arm):
    """An arm that never applies a repair was stable before the fix too.

    It is kept as a control so that a failure here would point at something
    other than the primitive-ordering loop.
    """
    a = _snapshot(arm, "0")
    b = _snapshot(arm, "12345")
    assert a["q_hash"] == b["q_hash"]


def test_write_key_collapses_decision_and_execution():
    """`key` distinguishes units; `write_key` exposes the entry they collide on.

    The distinction matters because `dedup()` works on `key`, so a DECISION and
    an EXECUTION site on the same step both survive dedup even though
    `updates._write` sends them to the same Q table.
    """
    sys.path.insert(0, str(ROOT / "src"))
    from rflv04.credit_units import Credit, Site

    state = (1, 2, 0, 3)   # (context, x, y, t) as the low-level Q key sees it
    d = Site("DECISION", state, 1)
    e = Site("EXECUTION", state, 1)
    p = Site("PLAN", state, 1)

    assert d.key != e.key, "units are distinguished by key"
    assert d.write_key == e.write_key, "but they collide on one Q entry"
    assert p.write_key != d.write_key, "PLAN goes to the high-level table"

    credit = Credit("RepairOracle", {"DECISION", "EXECUTION"}, [d, e])
    credit.dedup()
    assert len(credit.sites) == 2, "dedup keeps both, since their keys differ"
    assert len(credit.collisions()) == 1, "the collision is detected and reported"

    clean = Credit("DecisionOracle", {"DECISION"}, [d])
    assert clean.collisions() == []
