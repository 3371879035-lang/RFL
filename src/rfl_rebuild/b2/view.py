r"""A75 §62.10 — B2's input types: dependency closure, two views, and the constructor gate.

$$\boxed{\text{the metric not seeing the truth} \;\not\Rightarrow\; \text{the metric's input
was not built from it}}$$

An evaluator can compute $c = \text{Collateral}(\Delta W, \Gamma_P^\ast)$ and place the
already-computed scalar into the view. The metric then imports nothing forbidden, and neither a
type boundary nor an AST scan sees it:

$$\boxed{\text{forbidden truth} \to \text{derived feature} \to
\texttt{FutureConsequenceView} \to \text{metric}}$$

So what must be clean is the **dependencies of the features**, not the metric's imports:

$$F \in \texttt{FutureConsequenceView} \;\Longrightarrow\;
\mathrm{Deps}(F) \cap \mathcal H_{\text{forbidden}} = \varnothing$$

$$\mathcal H_{\text{forbidden}} = \{Z^{\text{fire}},\ J^L,\ \Gamma_T^\ast,\ \Gamma_P^\ast,\
R^{\text{mech}},\ R^{\text{rescue}},\ \pi_{\text{credit}}\}$$

and the two views stay **separate objects**, because "what was written" and "what happened next"
must not travel together or the first cannot be checked against the second:

1. `FutureConsequenceView` — only genuinely external future rollout information: future rewards,
   outcomes, trajectories, actions/observations, plus the ordinary time indices needed to compute
   them. **Its constructor is itself truth-blind**;
2. `UpdateLedger` — cost accounting, which is B1's object and is **not** an external criterion.

**The four gate layers are implemented here, each as something that can go red:**

| layer | mechanism |
|---|---|
| type boundary | a view field is a `FutureField`, a nominal type that cannot be built from a bare value |
| AST / import allowlist | `assert_module_is_closed` reads this module's own AST and refuses a forbidden import or attribute load |
| constructor-flow | `FutureField.from_rollout` fixes $\mathrm{Deps}(F) = \{\text{the rollout}\}$; the rollout is **sealed** and only the audited producer can mint one (B2-2a), so provenance is not a claim; and the view re-derives every payload and the time index from that one rollout |
| mutation power | `tests/rebuild/test_b2_view.py::test_5` fabricates $1[\texttt{Decision}_t \in \Gamma_P^\ast]$ and requires the first three layers to kill it |

The fourth layer exists because the first three could all be present and *inert*. A gate that only
shows the metric does not import truth demonstrates nothing about the $\text{truth} \to
\text{metric input}$ path; the fabricated feature is what makes the closure observable.

**What is deliberately *not* here.** No estimator, no runner, no seed, and no development-stage
choice: $U_{\text{unaffected}}$'s construction, the Retention form, $T$, $N_{\text{eval}}$, the
checkpoint grid and every $\Delta_{\min}$ are decided under A83 §71.4 and none of them is named in
this module.
"""

from __future__ import annotations

import ast
import pathlib
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Callable, Mapping

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.learner.store import LearnerPersistentState

__all__ = [
    "H_FORBIDDEN",
    "IMPORT_ALLOWLIST",
    "SCENE_FORBIDDEN",
    "VIEW_FIELDS",
    "EvidenceOrigin",
    "FutureConsequenceView",
    "FutureConsequenceViewBuilder",
    "FutureField",
    "FutureRollout",
    "assert_module_is_closed",
    "assert_modules_are_closed",
    "require_learner_rollout",
]

#: $\mathcal H_{\text{forbidden}}$ (A75 §62.10), verbatim. Not a style list: a feature whose
#: dependencies meet any of these may not appear in the view, however indirect the path.
H_FORBIDDEN = (
    "Z_fire", "J_L", "Gamma_T_star", "Gamma_P_star", "R_mech", "R_rescue", "pi_credit",
)

#: The mint capability and the module allowed to hold it. The allowlist above says which modules a
#: production module may *import*; this says which names it may not **load at all** outside their
#: owner, because an allowlisted import is still an escalation if the name it brings is the ability
#: to mint evidence:
#:
#: $$\boxed{\texttt{\_mint\_rollout},\ \texttt{\_ROLLOUT\_SEAL}\ \text{may be loaded only
#: inside}\ \texttt{producer.py}}$$
#:
#: `testing.py` holds the capability too and is deliberately not on this list: it is test-only, the
#: audit refuses a production module that imports it, and a hostile fixture that escalates through
#: it is labelled as an escalation rather than mistaken for a production route.
CAPABILITY_OWNERS = {
    "_mint_rollout": "producer.py",
    "_ROLLOUT_SEAL": "producer.py",
}

#: The per-scene identifiers a **metric** may additionally not receive: the selector may use truth
#: to choose the report table, but the metric may not learn which table it is in.
SCENE_FORBIDDEN = (
    "S_T_plus", "S_T_minus", "S_P_plus", "S_P_minus", "world_id", "block_id",
)

#: `FutureConsequenceView`'s closed field surface. "Closed" is the operative word: a view carrying
#: one more field is a different view, and the extra field is how a derived feature would arrive.
VIEW_FIELDS = (
    "future_rewards",
    "future_outcomes",
    "future_trajectories",
    "future_actions",
    "future_observations",
)


class EvidenceOrigin(Enum):
    """Where a piece of evidence came from. The builder admits exactly one member.

    An enum and not a boolean flag: a flag invites `origin=True`-style call sites and folds
    `0`/`1`/`"truth"` into one branch, which is the coercion failure A77 §65.1 already had to
    close for tiers.
    """

    LEARNER_FUTURE_ROLLOUT = "learner_future_rollout"
    EVALUATOR_TRUTH = "evaluator_truth"
    SCENE_ROUTING = "scene_routing"


@dataclass(frozen=True, slots=True)
class FutureRollout:
    r"""The future, as the learner's own rollout observes it — and nothing else.

    This is the only admissible source of a view field. It carries the future record plus the
    ordinary time indices needed to read it, and it is **sealed**: only the audited producer can
    mint one, so its provenance is a fact about who could have built it rather than a field the
    caller filled in (B2-2a).
    """

    _seal: object
    origin: EvidenceOrigin
    future_rewards: tuple
    future_outcomes: tuple
    future_trajectories: tuple
    future_actions: tuple
    future_observations: tuple
    t_index: tuple

    def __post_init__(self) -> None:
        """Only the audited mint may produce a rollout.

        $$\boxed{\text{a source label} \neq \text{a proof of source}}$$

        B2-1 checked `origin`, and `origin` is a field the caller fills in -- so an injected
        callable could close over forbidden truth and return an object that *said* it came from
        the learner. The seal is what makes that impossible through the public constructor: the
        value is minted by `b2.producer`, and provenance is therefore answered by *who could have
        built it* rather than by what the object claims.
        """
        from rfl_rebuild.b2.producer import is_sealed

        if not is_sealed(self._seal):
            raise ProtocolError(
                "a FutureRollout may only be minted by the audited producer "
                "(rfl_rebuild.b2.producer); a directly constructed rollout reports its own "
                "provenance, which is exactly the claim B2-2a replaces with a mint")


def require_learner_rollout(rollout: object) -> FutureRollout:
    r"""The constructor-flow layer: only the learner's own future rollout may feed the view.

    $$\boxed{\mathrm{Deps}(F) = \{\text{the rollout}\} \;\Longrightarrow\;
    \mathrm{Deps}(F) \cap \mathcal H_{\text{forbidden}} = \varnothing}$$

    A rollout whose origin is evaluator truth or scene routing is refused *here*, at the only door
    a field can come through, rather than after the fact by inspecting the finished object.
    """
    if type(rollout) is not FutureRollout:
        raise ProtocolError(
            f"the future evidence {rollout!r} has type {type(rollout).__name__}, not "
            "FutureRollout; a view field is built from a rollout rather than from a value")
    if type(rollout.origin) is not EvidenceOrigin:
        # The error path must not be the thing that crashes: formatting `origin.value` on a string
        # that spells the right word raised `AttributeError` out of the guard, where the contract
        # promises a `PROTOCOL_ERROR`. A string equal to a member's value is not the member, which
        # is the same nominal rule A77 §65.1 put on tiers.
        raise ProtocolError(
            f"the future evidence carries origin={rollout.origin!r} of type "
            f"{type(rollout.origin).__name__}, not an EvidenceOrigin member; an origin must be the "
            "member itself, since a value-equal stand-in would answer the check without being the "
            "evidence it claims to describe")
    if rollout.origin is not EvidenceOrigin.LEARNER_FUTURE_ROLLOUT:
        raise ProtocolError(
            f"the future evidence originates from {rollout.origin.value!r}; only "
            f"{EvidenceOrigin.LEARNER_FUTURE_ROLLOUT.value!r} may feed a FutureConsequenceView. "
            "Evaluator truth and scene routing are exactly what the dependency closure "
            f"{H_FORBIDDEN!r} and {SCENE_FORBIDDEN!r} exist to keep out, however indirect the "
            "path from truth to a derived feature")
    return rollout


@dataclass(frozen=True, slots=True)
class FutureField:
    r"""One view field: a value **and** the evidence it was derived from.

    $$\boxed{\text{a field is its dependency, not just its number}}$$

    A bare float would satisfy a type boundary and could still be
    $1[\texttt{Decision}_t \in \Gamma_P^\ast]$: the forbidden truth would have been consumed one
    step earlier, by whoever computed it. Binding the value to the rollout it came from makes the
    dependency checkable instead of inferable — the field's `rollout` is the *only* thing the value
    is allowed to depend on, and `from_rollout` is the only constructor.
    """

    name: str
    rollout: FutureRollout
    value: tuple

    @staticmethod
    def from_rollout(name: str, rollout: object) -> "FutureField":
        """Build a field **from the rollout itself**, projecting a declared field name."""
        require_learner_rollout(rollout)
        if name not in VIEW_FIELDS:
            raise ProtocolError(
                f"{name!r} is not a declared view field; the field surface is exactly "
                f"{VIEW_FIELDS!r}, and a field outside it is how a derived feature would arrive")
        return FutureField(name=name, rollout=rollout, value=tuple(getattr(rollout, name)))


@dataclass(frozen=True, slots=True)
class FutureConsequenceView:
    r"""A75 §62.10's first view: the future, and the ordinary time indices needed to read it.

    **Closed on two axes.** The field names are exactly `VIEW_FIELDS`, and every value is a
    `FutureField` rather than a bare value. Both closures are load-bearing and both are checked at
    construction: an extra field name is how a fabricated feature would be smuggled in, and a bare
    value is how an already-computed scalar would.

    **Separate from the ledger.** $N_{\text{addresses}}$, $N_{\text{scalar}}$,
    $\sum|\Delta\theta|$, $\max|\Delta\theta|$ and the pre/post fingerprints are B1's
    `UpdateLedger`, which is cost accounting rather than an external criterion. A view that carried
    them would be the merge §62.10 forbids, so they are not members here and a ledger is not
    accepted as this view's input.
    """

    fields: Mapping
    t_index: tuple

    def __post_init__(self) -> None:
        if not isinstance(self.fields, Mapping):
            raise ProtocolError(
                f"the view's fields are {type(self.fields).__name__}, not a mapping")
        keys = set(self.fields)
        expected = set(VIEW_FIELDS)
        if keys != expected:
            extra = sorted(keys - expected)
            missing = sorted(expected - keys)
            raise ProtocolError(
                f"the view's field surface is {sorted(keys)!r}, but it is frozen as "
                f"{sorted(expected)!r} (extra {extra!r}, missing {missing!r}); a view carrying one "
                "more field is a different view, and the extra field is how a derived feature "
                "arrives (A75 §62.10)")
        for name in VIEW_FIELDS:
            field = self.fields[name]
            if type(field) is not FutureField:
                raise ProtocolError(
                    f"the view field {name!r} has type {type(field).__name__}, not FutureField; a "
                    "bare value could be a scalar computed from forbidden truth, and its "
                    "dependencies would then be invisible")
            if field.name != name:
                raise ProtocolError(
                    f"the view field {name!r} carries the name {field.name!r}")
            require_learner_rollout(field.rollout)
        # The payload is re-derived, not trusted. A clean rollout with a forged value, or fields
        # drawn from several futures, would satisfy every check above and still carry a
        # truth-derived feature inside a legitimate-looking shell.
        rollouts = {id(self.fields[name].rollout) for name in VIEW_FIELDS}
        if len(rollouts) != 1:
            raise ProtocolError(
                "the view's fields come from more than one rollout; \"what happened next\" is one "
                "future, so a view assembled from several futures cannot be read as one horizon "
                "(A75 §62.10)")
        rollout = self.fields[VIEW_FIELDS[0]].rollout
        for name in VIEW_FIELDS:
            field = self.fields[name]
            if tuple(field.value) != tuple(getattr(rollout, name)):
                raise ProtocolError(
                    f"the view field {name!r} carries a value that is not the projection of its "
                    "own rollout; a clean rollout with a forged payload is how a truth-derived "
                    "feature still arrives inside a legitimate-looking shell (A75 §62.10)")
        if tuple(self.t_index) != tuple(rollout.t_index):
            raise ProtocolError(
                "the view's t_index is not its rollout's t_index; the ordinary time indices belong "
                "to the same future rather than being a second quantity that can be supplied "
                "separately")
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))
        object.__setattr__(self, "t_index", tuple(self.t_index))


class FutureConsequenceViewBuilder:
    r"""A75 §62.10's constructor gate: **the builder itself cannot access forbidden truth**.

    $$\boxed{\texttt{FutureConsequenceViewBuilder} \text{ itself cannot access forbidden truth}}$$

    The builder holds one injected callable and nothing else. It is handed no world id, no block
    id, no stratum, no arm, no update ledger and no truth: its `build` method takes the learner
    state, and the view it returns is assembled from a rollout that the constructor-flow layer
    already vetted.

    **Arm-blindness by signature.** `build` takes exactly `("state",)`. An arm tag could not be
    ignored safely — a builder that *can* be told which arm it is in is a builder that may one day
    branch on it — so the parameter does not exist, and a gate asserts the parameter list rather
    than the intent.
    """

    __slots__ = ("_producer",)

    def __init__(self, producer) -> None:
        """Accept the **audited producer**, never an arbitrary callable.

        B2-1 took `Callable`, and that made the closure unenforceable: a lambda can close over
        forbidden truth, and the module that would then need auditing is the caller's. A nominal
        producer is a class the audited module defines, so the chain
        `state -> producer -> rollout -> view` is inside the audit rather than outside it.
        """
        from rfl_rebuild.b2.producer import FutureRolloutProducer

        if type(producer) is not FutureRolloutProducer:
            raise ProtocolError(
                f"the future rollout producer {producer!r} has type {type(producer).__name__}, not "
                "FutureRolloutProducer; an injected callable answers the provenance question by "
                "assertion, and the audited producer answers it by construction (B2-2a)")
        object.__setattr__(self, "_producer", producer)

    def build(self, state) -> FutureConsequenceView:
        r"""Build the view for one post-update learner state.

        $$\boxed{\text{learner state} \to \text{future rollout} \to
        \text{one field per declared name}}$$

        The state is typed nominally: a `B1Result`, an `UpdateLedger` or a fingerprint is not a
        learner state, and accepting one would put "what was written" inside "what happened next".
        """
        if type(state) is not LearnerPersistentState:
            raise ProtocolError(
                f"the view is built from a learner state, got {type(state).__name__}; the update "
                "ledger and the fingerprints belong to the other view (A75 §62.10)")
        rollout = self._producer.produce(state)
        require_learner_rollout(rollout)
        fields = {name: FutureField.from_rollout(name, rollout) for name in VIEW_FIELDS}
        return FutureConsequenceView(fields=fields, t_index=rollout.t_index)


#: Modules this one may import. Kept as data so the AST gate and its mutation read the same list:
#: an allowlist that lives in the checker but not in the check's subject is a comment.
IMPORT_ALLOWLIST = (
    "__future__", "abc", "ast", "pathlib", "dataclasses", "enum", "types", "typing",
    "rfl_rebuild.b1.errors", "rfl_rebuild.learner.store", "rfl_rebuild.env.kernel",
    # B2's own audited chain: the producer and the view are one closure, so each may import the
    # other, and a module outside this list is a dependency the audit has not seen.
    "rfl_rebuild.b2.producer", "rfl_rebuild.b2.view", "rfl_rebuild.b2.utility",
    "rfl_rebuild.b2.environment", "rfl_rebuild.b2.continuation",
    "rfl_rebuild.b2.screening",
    "rfl_rebuild.b2.collateral",
    "rfl_rebuild.b2.retention", "rfl_rebuild.b2.runner",
    "rfl_rebuild.b1.contract", "rfl_rebuild.b1.laws", "rfl_rebuild.b1.runner",
    "rfl_rebuild.b1.tier", "rfl_rebuild.env.domain",
)


def assert_modules_are_closed(paths) -> None:
    r"""The AST/import layer over the **whole production chain**, not one module.

    B2-1 scanned `view.py` alone, and the path it therefore could not see was the one that
    mattered: the evidence producer. The chain is
    `state -> producer -> rollout -> view`, so the audit covers producer and view together.

    It also refuses a production module that imports `rfl_rebuild.b2.testing`: the fixture mint
    exists so that gates can build clean rollouts through the real seal, and a production module
    reaching it would be production code imported from the fixtures rather than the other way
    round.
    """
    for path in paths:
        # The specific refusal comes first: "you imported the test-only fixture module" is a more
        # useful diagnostic than "that module is not on the allowlist", and both would fire.
        path = pathlib.Path(path)
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        # Capability ownership, before the import allowlist: a module may import the owner and
        # still not be allowed to take the mint out of it.
        if path.name not in set(CAPABILITY_OWNERS.values()):
            for node in ast.walk(tree):
                loaded = None
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    loaded = node.id
                elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
                    loaded = node.attr
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        if alias.name in CAPABILITY_OWNERS:
                            raise ProtocolError(
                                f"{path}: imports the mint capability {alias.name!r} from "
                                f"{node.module!r}; {CAPABILITY_OWNERS[alias.name]!r} is its only "
                                "holder inside the audited production graph, and an allowlisted "
                                "import is still an escalation when the name it brings is the "
                                "ability to mint evidence")
                if loaded in CAPABILITY_OWNERS:
                    raise ProtocolError(
                        f"{path}: loads the mint capability {loaded!r}, which only "
                        f"{CAPABILITY_OWNERS[loaded]!r} may hold; minting is what makes a rollout "
                        "trusted, so a second holder makes the trust boundary decorative")
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                # `from rfl_rebuild.b2 import testing` names the package in `module` and the
                # submodule in the alias, so the module alone would miss it.
                names = [f"{node.module or ''}.{a.name}" for a in node.names]
            for name in names:
                if name.startswith("rfl_rebuild.b2.testing"):
                    raise ProtocolError(
                        f"{path}: imports the test-only fixture module {name!r}; fixtures may "
                        "import production, not the reverse")
        assert_module_is_closed(path)


def assert_module_is_closed(path: str | pathlib.Path) -> None:
    r"""The AST / import allowlist layer, applied to a module's own source.

    Imports are checked against `IMPORT_ALLOWLIST`, and every `Name`/`Attribute` **load** is
    checked against $\mathcal H_{\text{forbidden}} \cup$ `SCENE_FORBIDDEN`: importing nothing
    forbidden while reading `truth.gamma_P_star` through a local alias would otherwise pass.

    A **layer**, not the whole gate — §62.10 lists four, and this one alone demonstrates only that
    this module's *text* is clean, not that the $\text{truth} \to \text{feature}$ path is closed.
    That is what the fabricated-feature mutation is for.
    """
    source = pathlib.Path(path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = set(H_FORBIDDEN) | set(SCENE_FORBIDDEN)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in IMPORT_ALLOWLIST:
                    raise ProtocolError(
                        f"{path}: imports {alias.name!r}, which is not on the allowlist "
                        f"{IMPORT_ALLOWLIST!r}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module not in IMPORT_ALLOWLIST:
                raise ProtocolError(
                    f"{path}: imports from {module!r}, which is not on the allowlist "
                    f"{IMPORT_ALLOWLIST!r}")
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id in forbidden:
                raise ProtocolError(
                    f"{path}: reads {node.id!r}, which is in the forbidden dependency set; the "
                    "view's constructor must not reach it even through a local alias")
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            if node.attr in forbidden:
                raise ProtocolError(
                    f"{path}: reads the attribute {node.attr!r}, which is in the forbidden "
                    "dependency set")
