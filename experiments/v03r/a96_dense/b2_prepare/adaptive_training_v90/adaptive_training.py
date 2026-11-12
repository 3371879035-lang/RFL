"""Isolated revised ordinary learning. NOT the unchanged A77/A91 architecture.

DQ keeps the original Q update. Patch has an explicit value learner and a
learnable literal policy: after a complete TD sweep, previously patched VISITED
contexts take the value learner's greedy action. Unread patches and P/X remain.
This policy-improvement step can change D even when numeric TD is exactly zero;
it must never be reported as a numeric-TD gain or a qualified scientific result.
No original API, guard, provider, registry, key generator or source is patched.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, fields, is_dataclass
from fractions import Fraction
from hashlib import sha256
import json

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2 import training as original
from rfl_rebuild.env import kernel as K
from rfl_rebuild.learner.store import (
    DECISION, Edit, DecisionAddress, LearnerPersistentState, require_q_reference,
)


def require(ok, message):
    if not ok:
        raise ProtocolError(message)


def wire(value):
    if isinstance(value, Fraction):
        return {"rational": [value.numerator, value.denominator]}
    if is_dataclass(value):
        return {f.name: wire(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, float):
        return {"binary64_hex": value.hex()}
    if isinstance(value, (tuple, list)):
        return [wire(x) for x in value]
    if isinstance(value, dict):
        return {k: wire(v) for k, v in value.items()}
    return value


def stores(state):
    snap = state.snapshot()
    return {name: [{"address": wire(k), "value": wire(v)}
                   for k, v in sorted(mapping.items(), key=lambda item: repr(item[0]))]
            for name, mapping in (("D", snap.decision_overrides),
                                  ("P", snap.process_overrides),
                                  ("X", snap.controller_overrides),
                                  ("Q", snap.q_overrides))}


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True).encode("ascii")).hexdigest()


@dataclass(frozen=True, slots=True)
class LearningParameters:
    alpha: Fraction = Fraction(1, 2)
    epsilon: Fraction = Fraction(1, 10)

    def __post_init__(self):
        original._require_learning_constants(self.alpha, self.epsilon)


@dataclass(frozen=True, slots=True)
class ScriptedEpisode:
    """Explicit engineering inputs, not a seed or a fake ExogenousEpisode.

    Every real step has its own coin and rejection sequence. No RNG/key calls.
    This is deliberately NOT a production Xi generator or workload protocol.
    """
    label: str
    kappa: int
    proposal: int
    tape: K.SemanticTape
    coins: tuple
    action_draws: tuple

    def __post_init__(self):
        require(type(self.label) is str and bool(self.label), "episode label required")
        require(type(self.kappa) is int and self.kappa in (0, 1), "bad kappa")
        require(type(self.proposal) is int and self.proposal in K.option_ids(), "bad proposal")
        require(type(self.tape) is K.SemanticTape, "nominal tape required")
        require(type(self.coins) is tuple and len(self.coins) == K.HORIZON,
                "one coin for every possible actual step required")
        require(type(self.action_draws) is tuple and len(self.action_draws) == K.HORIZON,
                "one rejection sequence per actual step required")
        require(all(type(v) is int and 0 <= v <= original.M64 for v in self.coins),
                "coin outside uint64")
        require(all(type(seq) is tuple and seq and
                    all(type(v) is int and 0 <= v <= original.M64 for v in seq)
                    for seq in self.action_draws), "bad action draws")

    def coin(self, i):
        return self.coins[i]

    def chi(self, i, j, c):
        require(j == 1 and 0 <= i < K.HORIZON and 0 <= c < len(self.action_draws[i]),
                "scripted rejection exhausted; no retry or invented draw")
        return self.action_draws[i][c]


class AdaptiveTrainingState:
    """Explicit composite revision, never passed as LearnerPersistentState.

    Mode is bound at construction, NOT inferred from post D emptiness. A patch
    role with empty D remains a patch role. Original immediate post is cloned and
    protected. Internal value state is part of every complete fingerprint.
    In-process engineering ownership; NOT authenticated scientific B1 lineage.
    """
    __slots__ = ("mode", "role", "source_label", "reference", "_immediate",
                 "_current", "_values", "_attempted", "_completed", "_initial", "_binding")

    def __init__(self, immediate, *, mode, role, source_label, reference):
        require(type(immediate) is LearnerPersistentState, "nominal immediate post required")
        require(mode in ("dq", "patch-adaptive"), "explicit architecture mode required")
        require(role in ("reference", "treatment"), "explicit pair role required")
        require(type(source_label) is str and bool(source_label), "source label required")
        require_q_reference(reference)
        # Original construction guards remain operative. Never clean an invalid input.
        immediate.snapshot().q_decision_provider(reference)
        require(not immediate.decision_overrides if mode == "dq" else
                not immediate.q_overrides, "source architecture and full post disagree")
        self.mode, self.role, self.source_label, self.reference = mode, role, source_label, reference
        self._binding = (mode, role, source_label, reference.digest())
        self._immediate = immediate.clone()
        self._current = immediate.clone()
        self._values = LearnerPersistentState() if mode == "patch-adaptive" else None
        self._attempted, self._completed = set(), 0
        self._initial = stores(self._immediate)
        self._check()

    def _check(self):
        require((self.mode, self.role, self.source_label, self.reference.digest()) == self._binding,
                "architecture/source/role/reference binding changed")
        require(stores(self._immediate) == self._initial, "immediate measurement target changed")
        current = stores(self._current)
        require(current["P"] == self._initial["P"] and current["X"] == self._initial["X"],
                "ordinary learning changed P or X")
        self._current.snapshot().q_decision_provider(self.reference)
        if self.mode == "dq":
            require(self._values is None and not self._current.decision_overrides,
                    "DQ acquired a hidden layer or a D patch")
        else:
            require(type(self._values) is LearnerPersistentState and
                    not self._current.q_overrides, "invalid explicit patch composite")
            value_stores = stores(self._values)
            require(not value_stores["D"] and not value_stores["P"] and not value_stores["X"],
                    "numeric learning state contains non-Q channels")
            self._values.snapshot().q_decision_provider(self.reference)

    def payload(self):
        self._check()
        return deepcopy({"revision": "v90-policy-improvement-not-A77-A91-unchanged",
                "mode": self.mode, "role": self.role, "source_label": self.source_label,
                "reference_digest": self.reference.digest(), "immediate": self._initial,
                "current": stores(self._current),
                "learning_values": stores(self._values) if self._values is not None else None,
                "completed_episodes": self._completed,
                "attempted_labels": sorted(self._attempted)})

    def _greedy(self):
        self._check()
        snap = self._current.snapshot()
        numeric = self._current if self.mode == "dq" else self._values
        base = numeric.snapshot().q_decision_provider(self.reference)
        return base if self.mode == "dq" else snap.decision_provider(base)

    def evaluate(self, *, kappa, tape, proposal):
        """Same greedy composition as training exploitation, zero draws/writes."""
        before = self.payload()
        snap = self._current.snapshot()
        trace = K.rollout(kappa=kappa, tape=tape, base_option=proposal,
                          command_provider=self._greedy(), controller=snap.controller_mapping(),
                          learner_process_commit=snap.process_commit_provider(), reward_mode="A")
        require(self.payload() == before, "evaluation wrote a learner state")
        return {"before": before, "trace": wire(trace), "return_hex": trace.return_value.hex(),
                "after": self.payload(), "draws": [], "readonly": True}

    def train_episode(self, episode, *, parameters=LearningParameters()):
        require(type(episode) is ScriptedEpisode and type(parameters) is LearningParameters,
                "typed engineering episode and parameters required")
        self._check()
        require(episode.label not in self._attempted, "episode already attempted; no retry")
        self._attempted.add(episode.label)  # BEFORE any rollout; failure never completes.
        before = self.payload()
        greedy, draws = self._greedy(), []
        snap = self._current.snapshot()

        def provider(state, control):
            i = len(draws)
            admissible = tuple(K.option_actions(control.z, control, state))
            explore = original.is_explore(episode.coin(i), parameters.epsilon)
            a = original.uniform_action(episode, i, admissible) if explore else greedy(state, control)
            draws.append({"i": i, "explore": explore, "admissible": list(admissible), "a_cmd": a})
            return a

        trace = K.rollout(kappa=episode.kappa, tape=episode.tape, base_option=episode.proposal,
                          command_provider=provider, controller=snap.controller_mapping(),
                          learner_process_commit=snap.process_commit_provider(), reward_mode="A")
        numeric = self._current if self.mode == "dq" else self._values
        edits = original.sweep_edits(numeric, trace, episode, protocol=parameters,
                                     q_reference=self.reference)
        candidate_numeric = numeric.clone()
        candidate_numeric.apply_transaction(edits, q_reference=self.reference)
        actor_edits = []
        candidate_actor = self._current.clone() if self.mode == "patch-adaptive" else candidate_numeric
        if self.mode == "patch-adaptive":
            # Explicit generalized policy improvement, not TD writes into original D.
            # No truth target, original corruption mask or effect-selected action.
            improved = candidate_numeric.snapshot().q_decision_provider(self.reference)
            seen = set()
            for state, control, result in original.visited_order(
                    trace, kappa=episode.kappa, phi=episode.tape.phase):
                address = DecisionAddress(state, control.z, control.m)
                if address in self._current.decision_overrides and address not in seen:
                    actor_edits.append(Edit(DECISION, address, improved(state, control)))
                    seen.add(address)
            if actor_edits:
                candidate_actor.apply_transaction(tuple(actor_edits))
        # One composite publication after both candidates have validated.
        self._current, self._values = (candidate_actor,
                                      candidate_numeric if self.mode == "patch-adaptive" else None)
        self._completed += 1
        after = self.payload()
        return {"episode": wire(episode), "parameters": wire(parameters),
                "before": before, "trace": wire(trace), "draws": draws,
                "numeric_edits": wire(edits), "policy_improvement_edits": wire(actor_edits),
                "after": after, "return_hex": trace.return_value.hex(),
                "original_frozen_contract_unchanged": False,
                "scientific_qualification": False}
