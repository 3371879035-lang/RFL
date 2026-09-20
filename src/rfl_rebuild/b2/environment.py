r"""B2-2 — the real `LearnerEnvironment`: the future is endogenous to the **updated state**.

$$\boxed{Y^{\text{future}} = Y^{\text{future}}(W + \Delta W)}$$

This module closes the provenance gap B2-2a left open on purpose. There, a *nominal*
`LearnerEnvironment` was all the producer could require, and a nominal implementation whose records
came from somewhere else was still expressible. Here the production implementation exists, and it
joins `PRODUCTION_MODULES`: it is audited by the same AST/import/dependency layer as the view and
the producer, so "the environment read the truth and labelled the result as the learner's" has a
gate that can go red.

**What makes the rollout endogenous.** The kernel reads four learner channels, and the
environment wires **all four from the snapshot of the state it was handed**:

| channel | read path |
|---|---|
| $Q_D^L$ | `snapshot.q_decision_provider(q_reference)` — the decision read path |
| $P_D^L$ | `snapshot.decision_provider(...)`, which takes precedence over the Q path |
| $C_X^L$ | `snapshot.controller_mapping()` — the kernel's `controller=` |
| $C_P^L$ | `snapshot.process_commit_provider()` — the kernel's `learner_process_commit=` |

A version that used the reference policy directly, or a default/fresh state, or a hard-coded healthy
provider, would produce a *plausible* future and would be wrong in the one way that matters: the
whole point of B2 is what the write did to this learner's future. The endogeneity gates therefore
vary one channel at a time and require the future to move, and require it to stay put when an
irrelevant channel moves.

$$\boxed{\text{no channel may be bypassed by a reference shortcut}}$$
"""

from __future__ import annotations

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.env.kernel import Outcome, rollout
from rfl_rebuild.learner.store import LearnerPersistentState
from rfl_rebuild.b2.producer import ENVIRONMENT_INTERFACE, LearnerEnvironment

__all__ = ["KernelLearnerEnvironment", "PRODUCTION_MODULES"]

#: Every module in the audited production chain. The list lives here rather than in a test so the
#: audit and the gates read one source: adding a module to the chain is adding it here.
PRODUCTION_MODULES = (
    "rfl_rebuild/b2/view.py",
    "rfl_rebuild/b2/producer.py",
    "rfl_rebuild/b2/utility.py",
    "rfl_rebuild/b2/environment.py",
    "rfl_rebuild/b2/collateral.py",
    "rfl_rebuild/b2/retention.py",
)


class KernelLearnerEnvironment(LearnerEnvironment):
    r"""The learner's own environment: a kernel rollout that reads the passed learner state.

    Its inputs are the episode's structural parameters — the semantic tape, the option in force at
    the episode's start, the discount used by the *learner's* read path, and the injected reference
    view the $D_Q$ read path needs in order to define "no override" at all. None of them is a fact
    about the update: the update arrives only through the state.
    """

    __slots__ = ("_kappa", "_phi", "_tape", "_base_option", "_q_reference")

    def __init__(self, *, kappa: int, phi: int, tape, base_option: int, q_reference) -> None:
        if not isinstance(kappa, int) or isinstance(kappa, bool):
            raise ProtocolError(f"kappa={kappa!r} is not an integer")
        if not isinstance(phi, int) or isinstance(phi, bool):
            raise ProtocolError(f"phi={phi!r} is not an integer")
        if not isinstance(base_option, int) or isinstance(base_option, bool):
            raise ProtocolError(f"base_option={base_option!r} is not an integer")
        if q_reference is None:
            # The D_Q read path's healthy referent *is* the reference view, so without it "no
            # override" is undefined rather than defaulted. The substrate refuses a Q edit without
            # one for the same reason; the environment refuses to guess one.
            raise ProtocolError(
                "the Q read path needs the injected reference view: it supplies the healthy "
                "referent, so an environment without it would silently answer a different question")
        object.__setattr__(self, "_kappa", kappa)
        object.__setattr__(self, "_phi", phi)
        object.__setattr__(self, "_tape", tape)
        object.__setattr__(self, "_base_option", base_option)
        object.__setattr__(self, "_q_reference", q_reference)

    def future_records(self, state) -> tuple:
        r"""The learner's future from **this** post-update state, as five record sequences.

        $$\boxed{\text{state} \to \text{snapshot} \to \text{the three channels} \to
        \text{kernel rollout} \to \text{records}}$$

        The snapshot is taken once, from the state that was handed over, and every channel is read
        from it. Nothing here consults a reference policy, a default provider, or a fresh state.
        """
        if type(state) is not LearnerPersistentState:
            raise ProtocolError(
                f"the future is rolled out from a learner state, got {type(state).__name__}")
        snapshot = state.snapshot()
        # The decision read path: the decision store takes precedence, and its healthy referent is
        # the Q read path over the injected reference view.
        command_provider = snapshot.decision_provider(
            snapshot.q_decision_provider(self._q_reference))
        trace = rollout(
            kappa=self._kappa,
            tape=self._tape,
            command_provider=command_provider,
            base_option=self._base_option,
            controller=snapshot.controller_mapping(),
            learner_process_commit=snapshot.process_commit_provider(),
        )
        rewards, outcomes, trajectories, actions, observations = [], [], [], [], []
        previous = None
        for step in trace.steps:
            next_state = step.state
            rewards.append(float(step.reward))
            outcomes.append(1 if getattr(step, "outcome", None) == Outcome.SUCCESS else 0)
            trajectories.append((previous, next_state))
            actions.append(int(step.a_cmd))
            observations.append(getattr(step, "obs", None))
            previous = next_state
        return (tuple(rewards), tuple(outcomes), tuple(trajectories), tuple(actions),
                tuple(observations))


def audited_modules(root) -> tuple:
    r"""The production chain as paths, so a gate and the audit cannot disagree about the list."""
    import pathlib

    root = pathlib.Path(root)
    return tuple(root / name for name in PRODUCTION_MODULES)
