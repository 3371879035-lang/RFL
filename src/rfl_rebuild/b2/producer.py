r"""B2-2a — the trusted future-rollout producer: provenance as a mint, not a label.

$$\boxed{\text{a source label} \neq \text{a proof of source}}$$

B2-1's constructor-flow layer checked `origin`, and `origin` is a field the caller fills in. So
the closure it offered was the closure of a **claim**:

$$\Gamma_P^\ast \to \text{arbitrary injected callable} \to
\texttt{FutureRollout(origin=LEARNER)} \to \texttt{FutureConsequenceView}$$

and the injected callable could close over forbidden truth while `view.py`'s own AST scan saw
nothing. This module closes that path by moving provenance into the **mint**:

$$\boxed{\text{post-update learner state} \to \text{audited producer} \to
\texttt{FutureRollout} \to \texttt{FutureConsequenceViewBuilder}}$$

* a `FutureRollout` carries a **seal** that only this module can mint, so provenance cannot be
  self-reported through the public constructors at all;
* the producer is a **nominal type**, not a callable, and its only input is a
  `LearnerEnvironment` — a declared interface with no truth, no arm, no stratum, no world/block id
  and no ledger in it;
* this module joins `view.py` in the AST/import audit
  (`assert_modules_are_closed`), so "the producer reads forbidden truth and labels the result as
  the learner's" has a layer that can go red.

**Scope.** This is the provenance bridge only. The arithmetic of a future rollout — how the
learner's environment is stepped forward, what a record contains — is B2-2 and is **not**
implemented here: `LearnerEnvironment` declares the accessor surface and B2-2 supplies the
production implementation, which joins the same audit list when it lands.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from rfl_rebuild.b1.errors import ProtocolError

__all__ = [
    "ENVIRONMENT_INTERFACE",
    "FutureRolloutProducer",
    "LearnerEnvironment",
    "is_sealed",
]

#: The mint capability. **Private by name and by audit**: it is absent from `__all__`, absent from
#: the package's exports, and `framework.assert_modules_are_closed` refuses any audited production
#: module other than this one that loads `_ROLLOUT_SEAL` or `_mint_rollout`
#: (`CAPABILITY_OWNERS`). Python cannot make a module-private name unreachable and this does not
#: pretend otherwise; what it establishes is the property that matters:
#:
#: $$\boxed{\text{inside the audited production graph, only this module may mint}}$$
_ROLLOUT_SEAL = object()

#: The producer's whole input surface, declared as data so a gate can read it rather than trust it.
ENVIRONMENT_INTERFACE = ("future_records",)


class LearnerEnvironment(ABC):
    r"""The learner-visible environment, and nothing else about the world.

    Declared here rather than in B2-2 so that the producer's signature is frozen before the
    rollout arithmetic exists: the producer may read `future_records(state)` and it may read
    nothing else, because it is handed nothing else.

    A nominal ABC, not a duck-typed protocol: an object that merely *has* `future_records` is a
    stand-in, and a stand-in is how an evaluator-supplied truth table would arrive wearing the
    environment's method name.
    """

    __slots__ = ()

    @abstractmethod
    def future_records(self, state) -> tuple:
        """The learner's own future from a post-update state, as records.

        $$\boxed{\text{the only accessor, and it takes only the learner state}}$$
        """
        raise NotImplementedError


def is_sealed(value: object) -> bool:
    r"""Whether a value carries this module's mint. **Verification only** -- it cannot mint.

    `FutureRollout.__post_init__` needs to check the seal and lives in `view.py`, so the
    alternative was to hand `view.py` the capability itself. A verifier keeps the asymmetry: the
    view can ask "was this minted here" and cannot answer "yes" by making one.
    """
    return value is _ROLLOUT_SEAL


def _mint_rollout(origin, records, t_index):
    r"""Mint a sealed `FutureRollout`. The **only** production construction path.

    Called by `FutureRolloutProducer`, and by B2's test-only fixture module, which the AST audit
    keeps out of the production modules. `origin` is not a claim here: the mint belongs to the
    audited chain, so the question "where did this evidence come from" is answered by *who could
    have built it* rather than by a field the caller chose.
    """
    from rfl_rebuild.b2.view import EvidenceOrigin, FutureRollout

    if type(origin) is not EvidenceOrigin:
        raise ProtocolError(
            f"the rollout origin {origin!r} has type {type(origin).__name__}, not an EvidenceOrigin "
            "member")
    rewards, outcomes, trajectories, actions, observations = records
    return FutureRollout(
        _seal=_ROLLOUT_SEAL,
        origin=origin,
        future_rewards=tuple(rewards),
        future_outcomes=tuple(outcomes),
        future_trajectories=tuple(trajectories),
        future_actions=tuple(actions),
        future_observations=tuple(observations),
        t_index=tuple(t_index),
    )


class FutureRolloutProducer:
    r"""The audited producer: one nominal type, one declared input, one mint.

    $$\boxed{\text{producer}: \text{learner state} \times \texttt{LearnerEnvironment} \to
    \texttt{FutureRollout}}$$

    **Not a callable.** B2-1 accepted `future_rollout: Callable`, which made the closure
    unenforceable: a lambda can close over anything, and the module that would have had to be
    audited was the caller's. Here the producer is a class this module defines, the audit covers
    this module, and the builder refuses anything that is not an instance of it.

    Its constructor takes the environment and nothing else, so there is no parameter through which
    truth, a stratum, an arm, a world/block id or a ledger could be handed over.
    """

    __slots__ = ("_environment",)

    def __init__(self, environment: LearnerEnvironment) -> None:
        if not isinstance(environment, LearnerEnvironment):
            raise ProtocolError(
                f"the future environment {environment!r} has type "
                f"{type(environment).__name__}, not a LearnerEnvironment; the producer reads the "
                "learner's own future through the declared interface and through nothing else")
        object.__setattr__(self, "_environment", environment)

    @property
    def environment(self) -> LearnerEnvironment:
        return self._environment

    def produce(self, state):
        r"""Produce the learner's future from a post-update state.

        The state is typed nominally here as well: a `B1Result`, an `UpdateLedger` or a
        fingerprint is not a learner state, and accepting one would put "what was written" inside
        "what happened next" (A75 §62.10's two views).
        """
        from rfl_rebuild.b2.view import EvidenceOrigin
        from rfl_rebuild.learner.store import LearnerPersistentState

        if type(state) is not LearnerPersistentState:
            raise ProtocolError(
                f"the future rollout is produced from a learner state, got "
                f"{type(state).__name__}")
        records = self._environment.future_records(state)
        if not isinstance(records, tuple) or len(records) != 5:
            raise ProtocolError(
                f"the environment returned {records!r}; a future record set is a 5-tuple of "
                f"{ENVIRONMENT_INTERFACE!r} sequences (rewards, outcomes, trajectories, actions, "
                "observations)")
        *sequences, = records
        lengths = {len(s) for s in sequences}
        if len(lengths) != 1:
            raise ProtocolError(
                f"the future record sequences have lengths {sorted(lengths)}; the five sequences "
                "describe one horizon and must agree")
        horizon = lengths.pop()
        return _mint_rollout(EvidenceOrigin.LEARNER_FUTURE_ROLLOUT, records,
                             tuple(range(horizon)))
