"""The three competing credit-unit representations.

These are the arms of Pilot Alpha.  They differ **only** in which entries they
are allowed to touch; the update rule itself is held fixed at negative-only, so
Alpha measures credit granularity and nothing else.

    ModuleOracle     coarse: blame the plan unit if the plan was wrong,
                     otherwise the execution unit; touch every entry the unit
                     used this episode
    DecisionOracle   exact: touch only the oracle's minimal critical site(s)
    RepairOracle     the factual (bad) site of the selected repair candidate
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .env import ACT, PLAN, reference_action


@dataclass
class Site:
    """One state-action entry targeted for update."""

    unit: str      # "PLAN" | "DECISION" | "EXECUTION"
    state: tuple
    action: int
    is_factual: bool = True

    @property
    def key(self) -> tuple:
        return (self.unit, self.state, self.action)


@dataclass
class Credit:
    representation: str
    blamed_units: set = field(default_factory=set)
    sites: list = field(default_factory=list)

    def dedup(self) -> "Credit":
        seen = set()
        out = []
        for s in self.sites:
            if s.key not in seen:
                seen.add(s.key)
                out.append(s)
        self.sites = out
        return self


def _plan_state(trace) -> tuple:
    s = trace.steps[0].state
    return (s[0], s[1], s[2])


def _q_key(step) -> tuple:
    """The low-level Q key for a step: (x, y, o, t).

    The environment's state carries the context lane in slot 0, which is not
    part of the Q_L key.  Using the raw state as a key silently writes to
    entries the agent never reads.
    """
    return (step.state[1], step.state[2], step.state[3], step.t)


def _act_states(trace) -> list:
    return [_q_key(s) for s in trace.steps
            if s.state[4] == ACT and s.intent >= 0]


def module_oracle(trace, oracle_res) -> Credit:
    """Coarse representation: one unit blamed, every entry it used."""
    blamed = set()
    sites: list = []
    if oracle_res.family in ("Plan", "WholeProcess"):
        blamed.add("PLAN")
        sites.append(Site("PLAN", _plan_state(trace), trace.scene.plan))
    if oracle_res.family != "Plan":
        blamed.add("EXECUTION")
        for st in _act_states(trace):
            sites.append(Site("EXECUTION", st, reference_action(st[1], st[2], st[3])))
    if not blamed:
        blamed.add("EXECUTION")
        for st in _act_states(trace):
            sites.append(Site("EXECUTION", st, reference_action(st[1], st[2], st[3])))
    return Credit("ModuleOracle", blamed, sites).dedup()


def decision_oracle(trace, oracle_res) -> Credit:
    """Exact representation: only the oracle's minimal critical sites."""
    blamed = set()
    sites: list = []
    best = oracle_res.best
    prims = best.primitives if best is not None else frozenset()
    if not prims:
        prims = frozenset().union(*[r.primitives for r in oracle_res.sufficient]) \
            if oracle_res.sufficient else frozenset()
    for prim in prims:
        if prim[0] == "plan":
            blamed.add("PLAN")
            sites.append(Site("PLAN", _plan_state(trace), trace.scene.plan))
        elif prim[0] == "unstick":
            blamed.add("DECISION")
            step = next((s for s in trace.steps if s.t == prim[1]), None)
            if step is not None:
                sites.append(Site("DECISION", _q_key(step), step.intent))
        elif prim[0] == "exec":
            blamed.add("EXECUTION")
            step = next((s for s in trace.steps if s.t == prim[1]), None)
            if step is not None:
                sites.append(Site("EXECUTION", _q_key(step), step.intent))
    if not sites:
        return module_oracle(trace, oracle_res)
    return Credit("DecisionOracle", blamed, sites).dedup()


def repair_oracle(trace, oracle_res, selected) -> Credit:
    """Repair representation: the factual site of the selected candidate."""
    blamed = set()
    sites: list = []
    prims = selected.primitives if selected is not None else frozenset()
    if not prims:
        return module_oracle(trace, oracle_res)
    for prim in prims:
        if prim[0] == "plan":
            blamed.add("PLAN")
            sites.append(Site("PLAN", _plan_state(trace), trace.scene.plan))
        elif prim[0] == "unstick":
            blamed.add("DECISION")
            step = next((s for s in trace.steps if s.t == prim[1]), None)
            if step is not None:
                sites.append(Site("DECISION", _q_key(step), step.intent))
        elif prim[0] == "exec":
            blamed.add("EXECUTION")
            step = next((s for s in trace.steps if s.t == prim[1]), None)
            if step is not None:
                sites.append(Site("EXECUTION", _q_key(step), step.intent))
    if not sites:
        return module_oracle(trace, oracle_res)
    return Credit("RepairOracle", blamed, sites).dedup()


REPRESENTATIONS = {
    "ModuleOracle": module_oracle,
    "DecisionOracle": decision_oracle,
    "RepairOracle": repair_oracle,
}


def responsible_units(oracle_res) -> set:
    """Which units the oracle holds responsible, read off its best repair."""
    out = set()
    for repair in ([oracle_res.best] if oracle_res.best else oracle_res.sufficient):
        if repair is None:
            continue
        for prim in repair.primitives:
            if prim[0] == "plan":
                out.add("PLAN")
            elif prim[0] == "unstick":
                out.add("DECISION")
            elif prim[0] == "exec":
                out.add("EXECUTION")
    return out


def selected_repair(trace, oracle_res, *, pick: str = "best"):
    """Which sufficient repair the learner adopts.

    ``best`` uses the evaluator's long-term ranking.  Alpha is an Oracle-truth
    pilot, so it is allowed to use it; a learned arm in Delta is not.
    """
    if not oracle_res.sufficient:
        return None
    if pick == "best" and oracle_res.best is not None:
        return oracle_res.best
    return sorted(oracle_res.sufficient, key=lambda r: (r.size, r.describe()))[0]
