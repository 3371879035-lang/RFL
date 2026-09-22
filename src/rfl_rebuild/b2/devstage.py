r"""The development-stage harness: the three frozen commands of $F_0$ §7, as code.

$$\boxed{\text{a frozen command list that cannot run is not a protocol}}$$

This module is the *executable* half of $F_0$: `run_smoke.py`, `run_dev_baseline.py` and
`run_dev_lock.py` are thin CLIs over the functions here, so that the protocol's command surface is a
reviewable artifact rather than a plan. It draws **no seed** while nothing is authorised, and the
authorisation is read from the manifest rather than from a flag:

$$\boxed{\text{no stage runs unless the manifest's } \texttt{currently\_authorises} \text{ names it}}$$

Facts a later reader should not have to re-derive (they cost real time to establish):

* **scenes**: `unaffected.scene_domain()` returns all $5760$ `EvaluationScene`s *already* in A88 §76.2's
  lexicographic order, so the master evaluation sample of $F_0$ §3 is a prefix of that tuple -- the
  sample is deterministic and seed-free. `EvaluationScene.tape` gives the `SemanticTape`.
* **rollouts**: `environment.learned_rollout(learner, kappa=, tape=, base_option=, q_reference=)` takes
  the *learner state* first (not a `State`), and returns a `RolloutTrace` with `.steps` and `.outcome`.
* **the reference artifact**: `solve.dp.solve_reference()` -> `ReferenceSolution(.q, .v, .policy)`; a
  rollout needs `learner.reference.reference_view_from(solution)`, a `QReferenceView`. Passing the raw
  dict raises `ReferenceContractError` -- the boundary refuses duck-typed stand-ins (A77 §65.4).
* **a healthy pre-update learner** is `LearnerPersistentState()` with no arguments.
* **seeds**: in this rebuild line a seed maps to a stream through `SemanticTape.sample(seed)` (the
  legacy `rflnext.NoiseTape` does not exist here). One seed is one episode's tape, which is why the seed
  is the statistical unit.
* **cost**: a seedless pass over the first $1024$ scenes' rollouts measures `0.064 s` on the frozen
  instrument, i.e. ~`6e-5 s` per scene; that is the measurement $F_0$ §8's bound is derived from.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.environment import learned_rollout
from rfl_rebuild.b2.unaffected import scene_domain
from rfl_rebuild.env.kernel import SemanticTape
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.learner.store import LearnerPersistentState
from rfl_rebuild.solve.dp import solve_reference

__all__ = [
    "ARTIFACTS",
    "BENCHMARK_SCENES",
    "MANIFEST",
    "SMOKE_SEEDS_FILE",
    "DEV_SEEDS_FILE",
    "STAGE_AUTHORISATION",
    "SMOKE_REPORT_FIELDS",
    "authorisation",
    "benchmark_eval_sample",
    "dev_seeds_file",
    "load_seed_set",
    "plan",
    "require_authorised",
    "run_stage",
    "smoke_report",
    "smoke_seeds_file",
]

ROOT = Path(__file__).resolve().parents[3]

#: The declared artifact paths of $F_0$ §7. A stage writes to its own path and to nothing else.
ARTIFACTS = {
    "smoke": "experiments/v03r/smoke_report.json",
    "dev_baseline": "experiments/v03r/dev_baseline.json",
    "dev_lock": "experiments/v03r/dev_lock.json",
}

MANIFEST = "experiments/v03r/f0_manifest.json"
SMOKE_SEEDS_FILE = "experiments/v03r/smoke_seeds.txt"
DEV_SEEDS_FILE = "experiments/v03r/dev_seeds.txt"

#: Which manifest authorisation token unlocks which stage.
STAGE_AUTHORISATION = {"smoke": "smoke5", "dev_baseline": "dev32", "dev_lock": "dev32"}

#: $F_0$ §9: smoke's artifact surface is operational only -- no arm contrast, no interval, no effect size.
SMOKE_REPORT_FIELDS = frozenset({
    "stage", "seeds", "tree", "runtime_s", "gate_exit_codes", "artifact_paths",
    "artifact_digests", "errors", "fallbacks",
})

#: $F_0$ §3: the master evaluation sample size, and the benchmark's scene count.
BENCHMARK_SCENES = 1024

#: Declared seed-set sizes; a file that disagrees is an error, not a silent truncation.
_SEED_SET_SIZE = {"smoke": 5, "dev_baseline": 32}


def _path(rel: str) -> Path:
    return ROOT / rel


def smoke_seeds_file() -> Path:
    return _path(SMOKE_SEEDS_FILE)


def dev_seeds_file() -> Path:
    return _path(DEV_SEEDS_FILE)


def load_seed_set(path) -> tuple:
    r"""Read a seed set: one integer per line, `#` comments, and **the file is the set**.

    A range typed into a command line is a range again, so the sets live in files and this loader is the
    only reader. Duplicates, non-integers, an unsorted file and the two sets overlapping are all errors:
    each would silently change which streams a stage draws while every count still looked right.
    """
    path = Path(path)
    if not path.is_file():
        raise ProtocolError(f"seed set {path} does not exist")
    seeds = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        try:
            seeds.append(int(line))
        except ValueError:
            raise ProtocolError(f"{path.name}:{lineno}: {raw.strip()!r} is not an integer seed") from None
    if not seeds:
        raise ProtocolError(f"{path.name}: declares no seeds")
    if len(set(seeds)) != len(seeds):
        raise ProtocolError(f"{path.name}: declares a duplicate seed")
    if seeds != sorted(seeds):
        raise ProtocolError(f"{path.name}: seeds are not ascending; the file must be the set, in order")
    return tuple(seeds)


def _require_declared_sizes(smoke, dev) -> None:
    for name, seeds in (("smoke", smoke), ("dev_baseline", dev)):
        expected = _SEED_SET_SIZE[name]
        if len(seeds) != expected:
            raise ProtocolError(
                f"the {name} seed set declares {len(seeds)} seeds, and F0 section 1 declares {expected}; "
                "a set of another size would silently redefine the stage")
    overlap = sorted(set(smoke) & set(dev))
    if overlap:
        raise ProtocolError(f"the smoke and development seed sets overlap on {overlap[:5]}")


def authorisation(manifest_path=None) -> dict:
    """Read the manifest's authorisation fields, refusing a manifest that is not evidence."""
    path = Path(manifest_path) if manifest_path is not None else _path(MANIFEST)
    if not path.is_file():
        raise ProtocolError(f"no manifest at {path}, so no stage is authorised")
    data = json.loads(path.read_text(encoding="utf-8"))
    status = str(data.get("status", ""))
    if status.startswith("MUTATION-PROBE"):
        raise ProtocolError(
            f"{path.name} is a mutation probe ({status!r}), not evidence; it authorises nothing")
    now = data.get("currently_authorises", [])
    later = data.get("authorises_on_validity", [])
    if not isinstance(now, list) or not all(isinstance(t, str) for t in now):
        raise ProtocolError(f"{path.name}: currently_authorises must be a list of stage tokens")
    # A manifest that predates the split authorises nothing *here*: the old `authorises` field was the
    # grant-on-validity reading, and reading it as a live authorisation is exactly the conflation the
    # review asked to remove. Absent therefore means empty, while malformed is still an error.
    if not isinstance(later, list) or not all(isinstance(t, str) for t in later):
        raise ProtocolError(f"{path.name}: authorises_on_validity must be a list of stage tokens")
    stray = sorted(set(now) - set(later))
    if stray:
        raise ProtocolError(
            f"{path.name}: authorises {stray} which authorises_on_validity does not list; a manifest "
            "may not authorise more than its own validity grant")
    return {"currently_authorises": list(now), "authorises_on_validity": list(later),
            "has_authorisation_field": "currently_authorises" in data,
            "status": status, "execution_revision": (data.get("repo") or {}).get("execution_revision")}


def require_authorised(stage: str, manifest_path=None) -> dict:
    r"""$$\boxed{\text{unauthorised} \;\Longrightarrow\; \texttt{ProtocolError}, \text{ and nothing written}}$$"""
    if stage not in STAGE_AUTHORISATION:
        raise ProtocolError(f"unknown stage {stage!r}")
    state = authorisation(manifest_path)
    token = STAGE_AUTHORISATION[stage]
    if token not in state["currently_authorises"]:
        raise ProtocolError(
            f"stage {stage!r} is not authorised: the manifest's currently_authorises is "
            f"{state['currently_authorises']} and this stage needs {token!r}. Stage bodies run only "
            "after a reviewer marks F0 VALID and the manifest says so; --plan needs no authorisation.")
    return state


def plan(stage: str, *, seeds_path=None, design=None, manifest_path=None) -> dict:
    """What a stage *would* do, with no episode run and no artifact written. Needs no authorisation."""
    if stage == "smoke":
        seeds = load_seed_set(seeds_path or smoke_seeds_file())
        dev = load_seed_set(dev_seeds_file())
        _require_declared_sizes(seeds, dev)
    elif stage == "dev_baseline":
        seeds = load_seed_set(seeds_path or dev_seeds_file())
        smoke = load_seed_set(smoke_seeds_file())
        _require_declared_sizes(smoke, seeds)
    elif stage == "dev_lock":
        seeds = ()
        design_path = Path(design) if design else _path(ARTIFACTS["dev_baseline"])
        if not design_path.is_file():
            raise ProtocolError(
                f"the lock reads {design_path}, which does not exist yet: the lock is downstream of the "
                "baseline acquisition and cannot be planned before it")
    else:
        raise ProtocolError(f"unknown stage {stage!r}")
    state = authorisation(manifest_path)
    try:
        revision = state["execution_revision"]
    except KeyError:  # pragma: no cover - authorisation always returns the key
        revision = None
    return {
        "stage": stage,
        "authorises": STAGE_AUTHORISATION[stage],
        "currently_authorised": STAGE_AUTHORISATION[stage] in state["currently_authorises"],
        "execution_revision": revision,
        "seeds": list(seeds),
        "artifact": ARTIFACTS[stage],
        "writes_artifact": False,
        "runs_episodes": False,
        "gates_that_must_be_green": [
            "the full suite exits 0 at the execution revision",
            "the manifest's digests match the execution revision",
        ],
    }


def benchmark_eval_sample(n: int = BENCHMARK_SCENES) -> dict:
    r"""Time the **seedless** evaluation-sample pass that $F_0$ §8's bound is derived from.

    Seedless is structural rather than a matter of restraint: the evaluation sample is a prefix of the
    frozen $U_2$ enumeration, so this workload is a property of the instrument and not of a sample, and
    it draws no stream from $\mathcal S_{\text{smoke}}$ or $\mathcal S_{\text{dev}}$. It writes nothing
    and needs no authorisation -- a benchmark is not a stage.
    """
    scenes = scene_domain()
    if not 0 < n <= len(scenes):
        raise ProtocolError(f"benchmark scene count {n} is outside 1..{len(scenes)}")
    solution = solve_reference()
    reference = reference_view_from(solution)
    learner = LearnerPersistentState()
    started = time.perf_counter()
    outcomes = {}
    for scene in scenes[:n]:
        trace = learned_rollout(learner, kappa=scene.kappa, tape=scene.tape,
                                base_option=scene.base_option, q_reference=reference)
        key = str(trace.outcome)
        outcomes[key] = outcomes.get(key, 0) + 1
    runtime = time.perf_counter() - started
    return {
        "n_scenes": n,
        "runtime_s": round(runtime, 6),
        "per_scene_s": round(runtime / n, 9),
        "outcomes": outcomes,
        "deterministic": True,
        "seedless": True,
        "draws_no_seed": True,
        "writes_artifact": False,
    }


def smoke_report(*, seeds, runtime_s, tree, gate_exit_codes, artifact_digests,
                 errors=(), fallbacks=()) -> dict:
    """Build smoke's artifact, asserting its surface is exactly the operational field set of $F_0$ §9."""
    report = {
        "stage": "smoke",
        "seeds": list(seeds),
        "tree": tree,
        "runtime_s": runtime_s,
        "gate_exit_codes": dict(gate_exit_codes),
        "artifact_paths": dict(ARTIFACTS),
        "artifact_digests": dict(artifact_digests),
        "errors": list(errors),
        "fallbacks": list(fallbacks),
    }
    if set(report) != SMOKE_REPORT_FIELDS:
        raise ProtocolError(
            f"the smoke surface drifted: {sorted(set(report) ^ SMOKE_REPORT_FIELDS)}; the boundary is "
            "drawn at running rather than at showing, so an extra field is a hole, not a convenience")
    return report


def _smoke_body(seeds, *, manifest_path=None) -> dict:
    """The operational smoke workload: one episode per authorised seed, operational fields only."""
    solution = solve_reference()
    reference = reference_view_from(solution)
    learner = LearnerPersistentState()
    scenes = scene_domain()
    started = time.perf_counter()
    errors, fallbacks = [], []
    for seed in seeds:
        scene = scenes[seed % len(scenes)]
        try:
            learned_rollout(learner, kappa=scene.kappa, tape=SemanticTape.sample(seed),
                            base_option=scene.base_option, q_reference=reference)
        except Exception as exc:  # noqa: BLE001 - smoke records operational failures, it does not hide them
            errors.append(f"seed {seed}: {type(exc).__name__}: {exc}")
    state = authorisation(manifest_path)
    return smoke_report(
        seeds=seeds,
        runtime_s=round(time.perf_counter() - started, 6),
        tree=state["execution_revision"],
        gate_exit_codes={},
        artifact_digests={},
        errors=errors,
        fallbacks=fallbacks,
    )


def _dev_baseline_body(seeds, *, manifest_path=None) -> dict:
    r"""The baseline acquisition: the seedless evaluation-scene bank plus one baseline episode per seed.

    $$\boxed{\text{baseline and static material only; the treatment arms of this seed set are not run}}$$

    The envelope carries the scene bank for the first $N_{\max}$ scenes and the per-seed baseline
    outcomes. It deliberately records **no** episode-indexed convergence curve: which mechanism indexes
    those episodes in this rebuild line is not frozen, and a harness that invented one would be choosing
    a design quantity. The field is present and `null` so the gap is visible rather than absent.
    """
    solution = solve_reference()
    reference = reference_view_from(solution)
    learner = LearnerPersistentState()
    scenes = scene_domain()[:BENCHMARK_SCENES]
    started = time.perf_counter()
    bank = {}
    for scene in scenes:
        trace = learned_rollout(learner, kappa=scene.kappa, tape=scene.tape,
                                base_option=scene.base_option, q_reference=reference)
        key = str(trace.outcome)
        bank[key] = bank.get(key, 0) + 1
    per_seed, errors = {}, []
    for seed in seeds:
        scene = scene_domain()[seed % len(scene_domain())]
        try:
            trace = learned_rollout(learner, kappa=scene.kappa, tape=SemanticTape.sample(seed),
                                    base_option=scene.base_option, q_reference=reference)
            per_seed[str(seed)] = {"scene": list(scene.key), "outcome": str(trace.outcome),
                                   "steps": len(trace.steps)}
        except Exception as exc:  # noqa: BLE001
            errors.append(f"seed {seed}: {type(exc).__name__}: {exc}")
    return {
        "stage": "dev_baseline",
        "seeds": list(seeds),
        "envelope_scenes": len(scenes),
        "envelope_outcomes": bank,
        "per_seed_baseline": per_seed,
        "convergence_sample": None,
        "pending": ("the episode-indexed baseline curve semantics are [PROPOSED] in F0 section 3 and not "
                    "ratified, so f_T/f_N/f_G cannot be evaluated and the lock refuses"),
        "runtime_s": round(time.perf_counter() - started, 6),
        "errors": errors,
        "treatment_arms_run": False,
    }


def run_stage(stage: str, *, seeds_path=None, design=None, manifest_path=None) -> dict:
    r"""Execute a stage: authorisation first, then the workload, then its declared artifact."""
    require_authorised(stage, manifest_path)
    if stage == "smoke":
        report = _smoke_body(load_seed_set(seeds_path or smoke_seeds_file()),
                             manifest_path=manifest_path)
    elif stage == "dev_baseline":
        report = _dev_baseline_body(load_seed_set(seeds_path or dev_seeds_file()),
                                    manifest_path=manifest_path)
    else:
        raise ProtocolError(
            "the design lock evaluates the frozen rules of F0 section 4, and the episode-indexed "
            "baseline curve they read is not ratified yet; it refuses rather than inventing one")
    out = _path(ARTIFACTS[stage])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8", newline="\n")
    return report
