"""Acceptance-filtered knowledge-shock scenarios for v0.2."""

from __future__ import annotations

from dataclasses import dataclass

from .qtables import QTables
from .scenarios import ScenarioGenerator, ScenarioSample
from .env import CausalChaseEnv
from .noise import NoiseTape
from .oracle import OracleEvaluator
from .policies import ScriptedRouteFollower, rollout_to_trace
from .types import ACT_WAIT, InterventionSet


@dataclass
class KnowledgeScenario:
    scenario_id: str
    trace: object
    oracle_r: dict[str, float]
    feedback: str
    q_snapshot: QTables
    correct_items: dict
    wrong_items: dict


def is_high_protection(r: dict[str, float]) -> bool:
    return r.get("L", 0.0) >= 0.8 and r.get("H", 0.0) <= 0.1


def is_low_protection(r: dict[str, float]) -> bool:
    return r.get("H", 0.0) >= 0.8 and r.get("L", 0.0) <= 0.1


def is_environment_mixed(r: dict[str, float]) -> bool:
    return r.get("E", 0.0) >= max(r.get("H", 0.0), r.get("L", 0.0)) and r.get("E", 0.0) >= 0.5


def is_hl_mixed(r: dict[str, float]) -> bool:
    return r.get("H", 0.0) >= 0.2 and r.get("L", 0.0) >= 0.2 and r.get("H", 0.0) + r.get("L", 0.0) >= 0.7


def _knowledge_snapshot(sample: ScenarioSample) -> tuple[QTables, dict, dict]:
    q = QTables()
    # A stable, known margin of 0.60 at both possible update sites.  The
    # snapshot is cloned for every algorithm and never contains evaluator R*.
    q.high[0] = {sample.trace.option: 0.60, 1 - sample.trace.option: 0.0}
    last = sample.trace.transitions[-1] if sample.trace.transitions else None
    low_state = last.state if last is not None else (0, 0, 0, 0, sample.trace.option, 0)
    low_action = last.action if last is not None else 0
    q.low[low_state] = [0.0] * q.n_actions
    q.low[low_state][low_action] = 0.60
    return q, {"H": (0, sample.trace.option), "L": (low_state, low_action)}, {"H": (0, 1 - sample.trace.option), "L": (low_state, (low_action + 1) % q.n_actions)}


def _wrap(sample: ScenarioSample, feedback: str) -> KnowledgeScenario:
    q, correct, wrong = _knowledge_snapshot(sample)
    return KnowledgeScenario(sample.scenario_id, sample.trace, dict(sample.oracle.responsibility or {}), feedback, q, correct, wrong)


def _make(kind: str, n: int, *, seed: int = 0, max_attempts: int = 120) -> list[KnowledgeScenario]:
    # H/L/E are the existing evaluator-accepted causal families.  The mixed
    # family is searched from all accepted candidates; no synthetic R* is
    # fabricated when the environment cannot realise the requested geometry.
    gen = ScenarioGenerator(max_attempts=max_attempts)
    candidates = []
    causes = ["L"] if kind == "high_protection" else ["H"] if kind == "low_protection" else ["E"] if kind == "environment_mixed" else ["H", "L", "E"]
    predicate = {"high_protection": is_high_protection, "low_protection": is_low_protection, "environment_mixed": is_environment_mixed, "hl_mixed": is_hl_mixed}[kind]
    for i in range(max(1, n)):
        found = None
        if kind == "hl_mixed":
            env = CausalChaseEnv()
            oracle_eval = OracleEvaluator(policy_for=lambda o: ScriptedRouteFollower(o), env=env)
            for attempt in range(max_attempts * 2):
                s = seed + i * 100003 + attempt * 7919
                tape = NoiseTape.from_seed(s)
                option = tape.monster_start_lane
                trace = rollout_to_trace(
                    env, tape=tape, option=option, policy=ScriptedRouteFollower(option),
                    seed=s, scenario_id=f"HL_{s:06d}", true_primary="H",
                    interventions=InterventionSet(action_override={3: ACT_WAIT, 4: ACT_WAIT}),
                )
                if trace.terminal_type != "COLLISION":
                    continue
                result = oracle_eval.evaluate(trace)
                if result.responsibility and predicate(result.responsibility):
                    trace.env_meta["r_star"] = result.responsibility
                    found = ScenarioSample("HL", s, trace.scenario_id, trace, result, attempt + 1)
                    break
            if found is None:
                raise RuntimeError(f"no evaluator-accepted {kind} scenario found")
        else:
            for cause in causes:
                try:
                    batch = gen.generate(cause, seed + i * 100003, 1)
                except RuntimeError:
                    continue
                if batch and batch[0].oracle.responsibility and predicate(batch[0].oracle.responsibility):
                    found = batch[0]
                    break
        if found is None:
            raise RuntimeError(f"no evaluator-accepted {kind} scenario found")
        feedback = "H" if kind in ("high_protection", "hl_mixed") else "L" if kind == "low_protection" else "E"
        candidates.append(_wrap(found, feedback))
    return candidates


def make_high_protection(n: int = 1, *, seed: int = 0, max_attempts: int = 120):
    return _make("high_protection", n, seed=seed, max_attempts=max_attempts)


def make_low_protection(n: int = 1, *, seed: int = 0, max_attempts: int = 120):
    return _make("low_protection", n, seed=seed, max_attempts=max_attempts)


def make_environment_mixed(n: int = 1, *, seed: int = 0, max_attempts: int = 120):
    return _make("environment_mixed", n, seed=seed, max_attempts=max_attempts)


def make_hl_mixed(n: int = 1, *, seed: int = 0, max_attempts: int = 120):
    return _make("hl_mixed", n, seed=seed, max_attempts=max_attempts)


def generate_update_scenarios(kind: str, n: int = 1, *, seed: int = 0, max_attempts: int = 120):
    aliases = {"high": "high_protection", "low": "low_protection", "environment": "environment_mixed", "mixed": "hl_mixed"}
    return _make(aliases.get(kind, kind), n, seed=seed, max_attempts=max_attempts)
