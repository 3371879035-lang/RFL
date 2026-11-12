"""Versioned lazy episode entry; same v90 ordinary semantics, no old edits.

Engineering episodes are explicitly key-free. A real ExogenousEpisode is
delegated lazily by the keyed adapter, never prefetched or impersonated. Its
execution permit is deliberately unissued while collection remains closed.
"""
from copy import deepcopy
from dataclasses import dataclass
import math

import adaptive_training as A
import v105_floor_draw_td as TD
from rfl_rebuild.b2 import training as T
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.env import kernel as K
from rfl_rebuild.learner.store import DECISION, DecisionAddress, Edit, LearnerPersistentState


@dataclass(frozen=True, slots=True)
class EngineeringEpisode:
    epoch: int
    kappa: int
    proposal: int
    tape: K.SemanticTape
    coins: tuple
    rejections: tuple

    def __post_init__(self):
        A.require(type(self.epoch) is int and self.epoch >= 0, "invalid real epoch")
        A.require(type(self.kappa) is int and self.kappa in (0, 1), "invalid kappa")
        A.require(type(self.proposal) is int and self.proposal in K.option_ids(), "invalid proposal")
        A.require(type(self.tape) is K.SemanticTape, "nominal tape required")
        A.require(type(self.coins) is tuple and len(self.coins) == K.HORIZON and
                  all(type(x) is int and 0 <= x <= T.M64 for x in self.coins), "bad coins")
        A.require(type(self.rejections) is tuple and len(self.rejections) == K.HORIZON and
                  all(type(s) is tuple and s and all(type(x) is int and 0 <= x <= T.M64
                      for x in s) for s in self.rejections), "bad coordinate draws")

    def coin(self, i):
        A.require(type(i) is int and 0 <= i < K.HORIZON, "coin coordinate outside episode")
        return self.coins[i]

    def chi(self, i, j, c):
        A.require(j == 1 and type(i) is int and 0 <= i < K.HORIZON and
                  type(c) is int and 0 <= c < T.MAX_REJECTION, "draw coordinate outside domain")
        A.require(c < len(self.rejections[i]), "finite engineering rejection exhausted; no retry")
        return self.rejections[i][c]


@dataclass(frozen=True, slots=True)
class EngineeringPlan:
    episodes: tuple
    evaluation_sample: tuple
    v_pre: float
    parameters: A.LearningParameters
    lock_digest: str

    def __post_init__(self):
        A.require(type(self.episodes) is tuple and self.episodes and
                  all(type(e) is EngineeringEpisode for e in self.episodes), "typed stream required")
        A.require(tuple(e.epoch for e in self.episodes) == tuple(range(len(self.episodes))),
                  "stream must have each chronological epoch exactly once")
        sample = T._require_scene_sample(self.evaluation_sample, what="engineering evaluation sample")
        A.require(type(self.evaluation_sample) is tuple and sample == self.evaluation_sample,
                  "nominal ordered sample tuple required")
        A.require(type(self.v_pre) is float and math.isfinite(self.v_pre), "finite shared pre-level")
        A.require(type(self.parameters) is A.LearningParameters, "declared shared parameters required")
        A.require(type(self.lock_digest) is str and bool(self.lock_digest), "original lock binding required")

    @property
    def t_max(self):
        return len(self.episodes)

    @property
    def grid(self):
        return tuple(range(self.t_max + 1))

    def episode(self, e):
        A.require(type(e) is int and 0 <= e < self.t_max, "epoch outside declared stream")
        return EpisodeAdapter(self, e, self.episodes[e])


class FutureExecutionPermit:
    def __new__(cls):
        raise A.ProtocolError("formal execution permit is not issued by this engineering module")


_FORMAL_PERMITS = {}  # Separate committed once-gate must supply authority later; no grant factory here.


class KeyedPlan:
    """Code-only exact original protocol adapter; closed activation, not a fake seed stream."""
    def __init__(self, protocol, permit):
        A.require(type(protocol) is T.FutureTrainingProtocol, "exact original protocol required")
        A.require(type(permit) is FutureExecutionPermit and _FORMAL_PERMITS.get(id(permit)) is protocol,
                  "formal curve execution remains closed")
        self.protocol = protocol
        self.parameters = A.LearningParameters(protocol.alpha, protocol.epsilon)
        self.evaluation_sample, self.v_pre = protocol.evaluation_sample, protocol.v_pre
        self.t_max, self.grid = protocol.t_max, protocol.grid

    def episode(self, e):
        A.require(type(e) is int and 0 <= e < self.t_max, "keyed epoch outside horizon")
        return EpisodeAdapter(self, e, T.ExogenousEpisode.derive(self.protocol.seed, e))


class EpisodeAdapter:
    """Coordinates requested lazily at each actual command; audit calls are not policy state."""
    def __init__(self, plan, e, episode):
        A.require(type(plan) in (EngineeringPlan, KeyedPlan), "nominal owned plan required")
        A.require(type(episode) is (EngineeringEpisode if type(plan) is EngineeringPlan else
                                   T.ExogenousEpisode), "no duck-typed or impersonated episode")
        A.require((episode.epoch if type(episode) is EngineeringEpisode else episode.episode) == e,
                  "episode coordinate differs from plan")
        self.plan, self.epoch, self._input = plan, e, episode
        self.kappa, self.proposal, self.tape = episode.kappa, episode.proposal, episode.tape
        self.calls = []

    def coin(self, i):
        value = self._input.coin(i)
        self.calls.append((i, 0, 0, value))
        return value

    def chi(self, i, j, c):
        value = self._input.chi(i, j, c)
        self.calls.append((i, j, c, value))
        return value


class CoordinateLearner:
    def __init__(self, immediate, *, mode, role, source_label, reference, plan):
        A.require(type(immediate) is LearnerPersistentState, "complete original immediate state required")
        A.require(type(plan) in (EngineeringPlan, KeyedPlan), "nominal shared plan required")
        A.require(mode in ("dq", "patch-adaptive") and role in ("reference", "treatment"),
                  "source mode and exact role required")
        immediate.snapshot().q_decision_provider(reference)
        A.require(not immediate.decision_overrides if mode == "dq" else not immediate.q_overrides,
                  "full immediate state disagrees with source mode")
        self.mode, self.role, self.reference, self.source_label, self.plan = mode, role, reference, source_label, plan
        self._binding = (mode, role, source_label, reference.digest(), id(plan))
        self._immediate, self._current = immediate.clone(), immediate.clone()
        self._values = LearnerPersistentState() if mode == "patch-adaptive" else None
        self._initial, self._attempted, self._completed = A.stores(self._immediate), set(), 0
        self._check()

    def _check(self):
        A.require((self.mode, self.role, self.source_label, self.reference.digest(), id(self.plan)) == self._binding,
                  "source/mode/role/reference/shared plan changed")
        A.require(A.stores(self._immediate) == self._initial, "protected immediate state changed")
        current = A.stores(self._current)
        A.require(current["P"] == self._initial["P"] and current["X"] == self._initial["X"],
                  "ordinary learning changed P/X")
        self._current.snapshot().q_decision_provider(self.reference)
        if self.mode == "dq":
            A.require(self._values is None and not self._current.decision_overrides, "invalid DQ state")
        else:
            A.require(type(self._values) is LearnerPersistentState and not self._current.q_overrides,
                      "invalid explicit R+L state")
            values = A.stores(self._values)
            A.require(not values["D"] and not values["P"] and not values["X"], "L contains nonnumeric channels")
            self._values.snapshot().q_decision_provider(self.reference)

    def payload(self):
        self._check()
        return deepcopy({"revision": "v95-lazy-coordinate-v90-ordinary-semantics",
                         "mode": self.mode, "role": self.role, "source_label": self.source_label,
                         "reference_digest": self._binding[3], "immediate": self._initial,
                         "current": A.stores(self._current),
                         "learning_values": A.stores(self._values) if self._values is not None else None,
                         "completed_episodes": self._completed, "attempted_epochs": sorted(self._attempted)})

    def _greedy(self):
        numeric = self._current if self.mode == "dq" else self._values
        base = numeric.snapshot().q_decision_provider(self.reference)
        return base if self.mode == "dq" else self._current.snapshot().decision_provider(base)

    def evaluate(self, scene):
        A.require(type(scene) is EvaluationScene, "original nominal evaluation scene required")
        before = self.payload()
        snap = self._current.snapshot()
        trace = K.rollout(kappa=scene.kappa, tape=scene.tape, base_option=scene.base_option,
                          command_provider=self._greedy(), controller=snap.controller_mapping(),
                          learner_process_commit=snap.process_commit_provider(), reward_mode="A")
        A.require(self.payload() == before, "checkpoint wrote composite state")
        return trace

    def train_episode(self, episode):
        A.require(type(episode) is EpisodeAdapter and episode.plan is self.plan, "exact shared coordinate plan required")
        A.require(episode.epoch == self._completed and episode.epoch not in self._attempted,
                  "chronological unattempted epoch required; no retry")
        self._attempted.add(episode.epoch)  # Before native; failure never publishes/completes.
        before = self.payload()
        snap, greedy, decisions = self._current.snapshot(), self._greedy(), []

        def provider(state, control):
            i = len(decisions)
            admissible = tuple(K.option_actions(control.z, control, state))
            explore = T.is_explore(episode.coin(i), self.plan.parameters.epsilon)
            action = TD.uniform_action(episode, i, admissible) if explore else greedy(state, control)
            decisions.append({"i": i, "explore": explore, "admissible": list(admissible), "a_cmd": action})
            return action

        trace = K.rollout(kappa=episode.kappa, tape=episode.tape, base_option=episode.proposal,
                          command_provider=provider, controller=snap.controller_mapping(),
                          learner_process_commit=snap.process_commit_provider(), reward_mode="A")
        numeric = self._current if self.mode == "dq" else self._values
        edits = TD.sweep_edits(numeric, trace, episode, protocol=self.plan.parameters, q_reference=self.reference)
        candidate_numeric = numeric.clone()
        candidate_numeric.apply_transaction(edits, q_reference=self.reference)
        candidate_actor = self._current.clone() if self.mode == "patch-adaptive" else candidate_numeric
        actor_edits = []
        if self.mode == "patch-adaptive":
            improved, seen = candidate_numeric.snapshot().q_decision_provider(self.reference), set()
            for state, control, _result in TD.visited_order(trace, kappa=episode.kappa, phi=episode.tape.phase):
                address = DecisionAddress(state, control.z, control.m)
                if address in self._current.decision_overrides and address not in seen:
                    actor_edits.append(Edit(DECISION, address, improved(state, control)))
                    seen.add(address)
            if actor_edits:
                candidate_actor.apply_transaction(tuple(actor_edits))
        self._current, self._values = candidate_actor, candidate_numeric if self.mode == "patch-adaptive" else None
        self._completed += 1
        return {"epoch": episode.epoch, "episode": A.wire(episode._input),
                "coordinates": A.wire(episode.calls), "parameters": A.wire(self.plan.parameters),
                "before": before, "trace": A.wire(trace), "draws": decisions,
                "numeric_edits": A.wire(edits), "policy_improvement_edits": A.wire(actor_edits),
                "after": self.payload(), "return_hex": trace.return_value.hex()}
