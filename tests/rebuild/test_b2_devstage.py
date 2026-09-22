r"""The development-stage harness of $F_0$ §7: seed sets, authorisation, plan, and the smoke surface.

$$\boxed{\text{a refusal that cannot be lifted is not a gate, and a gate that cannot refuse is a lie}}$$

Every test here comes in the pair that makes it evidence. The authorisation tests assert both that an
empty `currently_authorises` refuses **and** that a manifest naming the stage lets the stage through --
otherwise "always refuse" would pass every refusal test. The surface tests assert the eight operational
fields **and** that the assertion guarding them goes red when the constant and the dict disagree. And the
benchmark is checked to be seedless by making the seed loader explode: if the benchmark read a seed set,
it would fail, so a passing benchmark proves it did not.

No test in this file runs a stage. `--plan` is the only mode exercised, which is what keeps the gates
themselves from drawing a seed.
"""

from __future__ import annotations

import ast
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b1.errors import ProtocolError  # noqa: E402
from rfl_rebuild.b2 import devstage  # noqa: E402


def _write_manifest(tmp_path, **payload) -> pathlib.Path:
    body = {"status": "PROPOSED", "repo": {"execution_revision": "0" * 40},
            "currently_authorises": [], "authorises_on_validity": ["smoke5", "dev32"]}
    body.update(payload)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(body), encoding="utf-8", newline="\n")
    return path


def _seed_file(tmp_path, name, values) -> pathlib.Path:
    path = tmp_path / name
    path.write_text("".join(f"{v}\n" for v in values), encoding="utf-8", newline="\n")
    return path


# --- seed sets -------------------------------------------------------------------------------------

def test_1_the_two_declared_seed_sets_load_as_sets():
    smoke = devstage.load_seed_set(devstage.smoke_seeds_file())
    dev = devstage.load_seed_set(devstage.dev_seeds_file())
    assert smoke == (0, 1, 2, 3, 4)
    assert dev == tuple(range(1000, 1032))
    assert len(dev) == 32 and set(smoke) & set(dev) == set()


def test_2_a_duplicate_seed_is_refused(tmp_path):
    path = _seed_file(tmp_path, "dup.txt", [1, 1, 2])
    with pytest.raises(ProtocolError, match="duplicate"):
        devstage.load_seed_set(path)


def test_3_a_non_integer_line_is_refused(tmp_path):
    path = tmp_path / "bad.txt"
    path.write_text("1\n2\nnot-a-seed\n", encoding="utf-8", newline="\n")
    with pytest.raises(ProtocolError, match="not an integer seed"):
        devstage.load_seed_set(path)


def test_4_a_missing_file_is_refused(tmp_path):
    with pytest.raises(ProtocolError, match="does not exist"):
        devstage.load_seed_set(tmp_path / "absent.txt")


def test_5_a_set_of_the_wrong_size_is_refused_rather_than_truncated(tmp_path):
    path = _seed_file(tmp_path, "smoke.txt", [0, 1, 2, 3])  # four, not five
    with pytest.raises(ProtocolError, match="declares 4 seeds"):
        devstage.plan("smoke", seeds_path=path)


def test_6_overlapping_sets_are_refused(tmp_path):
    # Five seeds, so the size check passes and the overlap check is what fires: a "smoke" set drawn from
    # the development range would let smoke burn streams that the development stage must see fresh.
    path = _seed_file(tmp_path, "smoke.txt", [1000, 1001, 1002, 1003, 1004])
    with pytest.raises(ProtocolError, match="overlap"):
        devstage.plan("smoke", seeds_path=path)


# --- authorisation ---------------------------------------------------------------------------------

@pytest.mark.parametrize("stage", ["smoke", "dev_baseline", "dev_lock"])
def test_7_an_empty_authorisation_refuses_every_stage(stage):
    with pytest.raises(ProtocolError, match="is not authorised"):
        devstage.require_authorised(stage)


def test_8_a_manifest_naming_the_stage_lets_it_through(tmp_path):
    path = _write_manifest(tmp_path, currently_authorises=["smoke5"])
    state = devstage.require_authorised("smoke", path)
    assert state["currently_authorises"] == ["smoke5"]
    with pytest.raises(ProtocolError, match="is not authorised"):
        devstage.require_authorised("dev_baseline", path)


def test_9_a_mutation_probe_manifest_authorises_nothing(tmp_path):
    path = _write_manifest(tmp_path, status="MUTATION-PROBE -- not evidence",
                           currently_authorises=["smoke5"])
    with pytest.raises(ProtocolError, match="mutation probe"):
        devstage.require_authorised("smoke", path)


def test_10_a_manifest_may_not_authorise_beyond_its_validity_grant(tmp_path):
    path = _write_manifest(tmp_path, currently_authorises=["dev32"],
                           authorises_on_validity=["smoke5"])
    with pytest.raises(ProtocolError, match="may not authorise more"):
        devstage.authorisation(path)


def test_11_a_manifest_without_the_new_field_authorises_nothing(tmp_path):
    """The pre-split `authorises` field was the grant-on-validity reading, not a live grant."""
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"status": "PROPOSED", "authorises": ["smoke5"]}),
                    encoding="utf-8", newline="\n")
    state = devstage.authorisation(path)
    assert state["currently_authorises"] == [] and state["has_authorisation_field"] is False
    with pytest.raises(ProtocolError, match="is not authorised"):
        devstage.require_authorised("smoke", path)


# --- plan and the no-write guarantee ---------------------------------------------------------------

def _artifact_state():
    path = ROOT / devstage.ARTIFACTS["smoke"]
    return (path.exists(), path.stat().st_mtime_ns if path.exists() else None)


def test_12_plan_runs_without_authorisation_and_writes_nothing():
    before = _artifact_state()
    payload = devstage.plan("smoke")
    assert payload["currently_authorised"] is False
    assert payload["runs_episodes"] is False and payload["writes_artifact"] is False
    assert payload["seeds"] == [0, 1, 2, 3, 4]
    assert _artifact_state() == before


def test_13_the_dev_lock_refuses_to_plan_without_its_acquisition():
    with pytest.raises(ProtocolError, match="downstream of the baseline acquisition"):
        devstage.plan("dev_lock")


def test_14_every_cli_refuses_to_run_but_exits_zero_for_plan():
    for script, extra in (("run_smoke.py", ()), ("run_dev_baseline.py", ()),
                          ("run_dev_lock.py", ("--design", str(ROOT / devstage.ARTIFACTS["dev_baseline"])))):
        run = subprocess.run([sys.executable, str(ROOT / "scripts" / script), *extra],
                             cwd=ROOT, capture_output=True, text=True)
        assert run.returncode == 2 and "REFUSED" in run.stderr, script
    plan = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_smoke.py"), "--plan"],
                          cwd=ROOT, capture_output=True, text=True)
    assert plan.returncode == 0, plan.stderr
    assert json.loads(plan.stdout)["stage"] == "smoke"


# --- the smoke surface -----------------------------------------------------------------------------

def test_15_the_smoke_surface_is_exactly_the_operational_field_set():
    report = devstage.smoke_report(seeds=[0], runtime_s=0.0, tree="0" * 40,
                                   gate_exit_codes={}, artifact_digests={})
    assert set(report) == devstage.SMOKE_REPORT_FIELDS
    assert not any(word in k for k in report
                   for word in ("effect", "arm", "contrast", "interval", "p_value", "delta_min"))


def test_16_the_surface_guard_goes_red_when_the_field_set_drifts(monkeypatch):
    monkeypatch.setattr(devstage, "SMOKE_REPORT_FIELDS", frozenset({"stage"}))
    with pytest.raises(ProtocolError, match="surface drifted"):
        devstage.smoke_report(seeds=[0], runtime_s=0.0, tree="0" * 40,
                              gate_exit_codes={}, artifact_digests={})


# --- the seedless benchmark ------------------------------------------------------------------------

def test_17_the_benchmark_draws_no_seed(monkeypatch):
    def explode(*_args, **_kwargs):  # pragma: no cover - only reached if the benchmark reads seeds
        raise AssertionError("the benchmark read a seed set")

    monkeypatch.setattr(devstage, "load_seed_set", explode)
    result = devstage.benchmark_eval_sample(8)
    assert result["seedless"] is True and result["draws_no_seed"] is True
    assert result["n_scenes"] == 8 and result["runtime_s"] >= 0.0
    assert result["writes_artifact"] is False


def test_18_the_benchmark_refuses_a_scene_count_outside_the_domain():
    with pytest.raises(ProtocolError, match="outside"):
        devstage.benchmark_eval_sample(0)
    with pytest.raises(ProtocolError, match="outside"):
        devstage.benchmark_eval_sample(len(devstage.scene_domain()) + 1)


# --- structural: no treatment machinery on the smoke path ------------------------------------------

def test_19_the_harness_imports_no_arm_or_runner_machinery():
    forbidden = {"rfl_rebuild.b2.runner", "rfl_rebuild.b2.collateral", "rfl_rebuild.b2.calibration"}
    for rel in ("src/rfl_rebuild/b2/devstage.py", "scripts/run_smoke.py",
                "scripts/run_dev_baseline.py", "scripts/run_dev_lock.py"):
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
        assert not (imported & forbidden), f"{rel} imports {sorted(imported & forbidden)}"


def test_20_the_plan_never_claims_to_have_run_anything():
    payload = devstage.plan("smoke")
    assert payload["runs_episodes"] is False and payload["writes_artifact"] is False
    assert payload["artifact"] == devstage.ARTIFACTS["smoke"]
