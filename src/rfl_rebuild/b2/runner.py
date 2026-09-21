r"""B2-4 — the paired runner: one pre-scene, one shared object, two arms, three dimensions.

$$\boxed{\text{pre-scene} \to \text{shared design material} \to \text{paired updates} \to
\text{paired futures} \to \text{three separate dimensions}}$$

The instrument's last arrow. It aggregates nothing across seeds and chooses no candidate: the
collateral construction, the Retention form and their horizons are **required arguments**, because
A79 §67.4/§67.5 and A83 §71.4 leave those to the development stage and an instrument that embodies a
choice cannot compare candidates.

**No arbitrary callable on the update side.** B2-1's hole was
`FutureConsequenceViewBuilder(callable)`, and B2-4 must not re-open it as `Arm(name, apply)`: a
closure over $\Gamma^\ast$, a future or the other arm would arrive as an update while every audited
module stayed clean. An arm is a nominal `ArmSpec` naming a **frozen registry law**, and the runner
dispatches to the existing B1 entry points itself.

**Shared exogenous configuration is not evaluator truth.** CRN needs shared randomness, not shared
routing truth: `ExogenousSetup` is a closed nominal type with no `world_id`, no `block_id`, no
stratum and none of $\mathcal H_{\text{forbidden}}$.

**No conclusion can be produced here.** No cross-seed aggregation, no
$\mathrm{RMST} = \mathbb E[\text{restricted\_time}]$, no verdict, no Holm, no bootstrap; the record
keeps the three dimensions apart with the cost view beside them.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import fields as dataclass_fields
from types import MappingProxyType
from typing import Mapping, Sequence

from rfl_rebuild.b1.contract import fingerprint
from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b1.laws import DQ_LAWS, P_LAWS, X_LAWS
from rfl_rebuild.b1.process import resolve_process_addresses
from rfl_rebuild.b1.runner import run_controller_law, run_dq_law, run_process_law
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.b2.collateral import behavioral_collateral_scenes, measure_scene_map
from rfl_rebuild.b2.producer import FutureRolloutProducer
from rfl_rebuild.b2.retention import select_form
from rfl_rebuild.b2.unaffected import (
    REFINEMENTS,
    CreditedSite,
    build_unaffected,
    credited_domain,
    pre_update_traces,
)
from rfl_rebuild.b2.utility import FutureUtility
from rfl_rebuild.b2.view import SCENE_FORBIDDEN, FutureConsequenceViewBuilder
from rfl_rebuild.learner.store import LearnerPersistentState

__all__ = ["ARCHITECTURES", "EXOGENOUS_FIELDS", "ArmSpec", "ExogenousSetup", "PairedRunner",
           "PairedSceneRecord"]

ARCHITECTURES = ("D_Q", "X", "P")

#: Each architecture's frozen law registry: an arm's law must be a member, which is what makes a
#: stand-in or a lambda impossible rather than merely discouraged. $D_Q$ is present because A85
#: §73.2.5 requires the measurement interface to be behaviourally load-bearing for all three, and B1
#: already ships the entry point -- the runner dispatches to it rather than inventing $D_Q$ semantics.
LAW_REGISTRIES = {"D_Q": DQ_LAWS, "P": P_LAWS, "X": X_LAWS}

#: The exact field surface of `ExogenousSetup`. Shared exogenous configuration is not routing truth.
EXOGENOUS_FIELDS = ("kappa", "phi", "tape", "base_option", "q_reference", "checkpoints")


def _is_frozen_law(law, registry) -> bool:
    r"""Whether a law is one the registry froze.

    Class entries match by identity. Instance entries -- A77 §65.3's per-cell `NoWriteRef(L0)`
    references -- match by **(type, tier)**: the reference law is a value object, and demanding the
    registry's own instance would make the contract about object identity rather than about which
    frozen law runs. A lambda, a stand-in or another architecture's law matches nothing.
    """
    for entry in registry:
        if law is entry:
            return True
        if isinstance(entry, type):
            continue
        if type(law) is type(entry) and getattr(law, "tier", None) is getattr(entry, "tier", None):
            return True
    return False


@dataclass(frozen=True, slots=True)
class ExogenousSetup:
    r"""The shared exogenous future: tape, structural option, reference view, checkpoint grid.

    $$\boxed{\text{shared exogenous randomness} \neq \text{forbidden evaluator truth}}$$

    A closed nominal type: its field surface is exactly `EXOGENOUS_FIELDS`, so routing truth cannot
    ride along "and simply not be read". The arms may differ in $\Delta W$ and in nothing else.
    """

    kappa: int
    phi: int
    tape: object
    base_option: int
    q_reference: object
    checkpoints: tuple

    def __post_init__(self) -> None:
        names = {f.name for f in dataclass_fields(self)}
        if names != set(EXOGENOUS_FIELDS):
            raise ProtocolError(
                f"the exogenous setup's fields are {sorted(names)!r} but its surface is frozen as "
                f"{sorted(EXOGENOUS_FIELDS)!r}")
        leaked = names & (set(SCENE_FORBIDDEN) | {"stratum", "arm", "world", "block"})
        if leaked:                                             # pragma: no cover - unreachable
            raise ProtocolError(f"the exogenous setup carries routing truth {sorted(leaked)!r}")
        for name in ("kappa", "phi", "base_option"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ProtocolError(f"{name}={value!r} is not an integer")
        if not self.checkpoints or any(
                isinstance(t, bool) or not isinstance(t, int) for t in self.checkpoints):
            raise ProtocolError(
                "the checkpoint schedule is an explicit non-empty tuple of integer episodes; the "
                "runner has no default schedule")
        object.__setattr__(self, "checkpoints", tuple(self.checkpoints))


@dataclass(frozen=True, slots=True)
class ArmSpec:
    r"""One arm: a name, an architecture, a tier, and a law **from that architecture's registry**.

    Not `Arm(name, apply)`: an arbitrary callable on the update side would let the update close over
    forbidden truth, a future view or the other arm's ledger while the audited modules stayed clean.
    """

    name: str
    architecture: str
    tier: Tier
    law: object

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ProtocolError(f"the arm name {self.name!r} is not a non-empty string")
        if self.architecture not in ARCHITECTURES:
            raise ProtocolError(
                f"the arm architecture {self.architecture!r} is not one of {ARCHITECTURES!r}")
        if type(self.tier) is not Tier:
            raise ProtocolError(
                f"the arm tier {self.tier!r} is not a Tier member; a tier is not inferred")
        if not _is_frozen_law(self.law, LAW_REGISTRIES[self.architecture]):
            raise ProtocolError(
                f"the law {self.law!r} is not in the {self.architecture} registry; an arm runs a "
                "frozen law, not whatever callable it was handed")
        declared = getattr(self.law, "tier", None)
        if declared is not None and declared is not self.tier:
            raise ProtocolError(
                f"the arm declares tier {self.tier.name} but its law {self.law!r} declares "
                f"{declared!r}")


@dataclass(frozen=True, slots=True)
class PairedSceneRecord:
    r"""One scene's instrument record: three dimensions, kept apart, cost beside them.

    $$\boxed{Y^{\text{future}} = \{\text{FutureUtility},\ \text{Collateral},\ \text{Retention}\}}$$

    `unaffected_construction` names the **evaluation-scene** set the collateral was taken over, and
    `unaffected_size` is kept beside it: A89 §77.8 re-typed this dimension onto the surviving unit, so a
    record that named a decision-context construction would be describing a different instrument.
    """

    arm_names: tuple
    architecture: str
    unaffected_construction: str
    unaffected_size: int
    retention_form: str
    future_utility: Mapping
    collateral: Mapping
    retention: Mapping
    ledgers: Mapping
    fingerprints_pre: Mapping
    observations: tuple


class PairedRunner:
    r"""Run one scene's paired arms, exposing the properties a gate has to be able to see."""

    __slots__ = ("_environment_factory", "_refinement", "_q_reference", "_form",
                 "_form_name", "_params", "_recorder")

    def __init__(self, *, environment_factory, refinement: str, q_reference, retention_form: str,
                 retention_params: Mapping, recorder=None) -> None:
        r"""A89 §77.8: the collateral dimension is $U_2$-native, and the refinement is the caller's.

        There is no default refinement and no construction registry to choose from: A79 §67.4 leaves
        that choice to the development stage, and an instrument that embodied one could not compare
        candidates. The reference artifact is the same single object for eligibility and for both arms.
        """
        if not callable(environment_factory):
            raise ProtocolError("the environment factory is not callable")
        if refinement not in REFINEMENTS:
            raise ProtocolError(
                f"{refinement!r} is not one of the six frozen refinements {REFINEMENTS!r}; the runner "
                "has no default and does not choose one")
        if q_reference is None:
            raise ProtocolError(
                "the runner needs the injected nominal reference artifact: eligibility and both arms "
                "read one shared object")
        form = select_form(retention_form)
        if not isinstance(retention_params, Mapping) or not retention_params:
            raise ProtocolError(
                "the Retention horizons must be given explicitly: H, or H1 and H2, are "
                "development-stage quantities and the runner has no default for them")
        object.__setattr__(self, "_environment_factory", environment_factory)
        object.__setattr__(self, "_refinement", refinement)
        object.__setattr__(self, "_q_reference", q_reference)
        object.__setattr__(self, "_form", form)
        object.__setattr__(self, "_form_name", retention_form)
        object.__setattr__(self, "_params", MappingProxyType(dict(retention_params)))
        object.__setattr__(self, "_recorder", recorder or (lambda *a, **k: None))

    def pre_update_source(self, state: LearnerPersistentState, credited_site: CreditedSite):
        r"""$$\boxed{W_{\text{pre}} \to \text{traces} \to E(c) \to C_i(c)}$$

        The design material is built from **the pair's own pre-update learner** -- not a minted healthy
        state -- and from the credited unit, before any arm exists. A89 §77.2 is explicit about why the
        old path cannot simply be re-pointed: `decision_contexts()` and a `contexts`-typed set are the
        superseded ontology, and the old algorithms reading scene tuples would run and mean nothing.
        """
        if type(state) is not LearnerPersistentState:
            raise ProtocolError(
                f"the pre-update source is read from a learner state, got {type(state).__name__}")
        if type(credited_site) is not CreditedSite:
            raise ProtocolError(
                f"the credited unit {credited_site!r} has type {type(credited_site).__name__}; the "
                "unaffected region is defined relative to a credited site, not to a bare domain")
        traces = pre_update_traces(learner=state, q_reference=self._q_reference)
        # A89 §77.4: the credited unit must be a member of the executable production extent for this
        # learner -- the same domain the Gate C enumeration defines, not merely a well-typed address.
        domain = credited_domain(credited_site.channel, traces)
        if credited_site not in domain:
            raise ProtocolError(
                f"the credited unit {credited_site.render()} is not in "
                f"{credited_site.channel}'s production credited domain for this W_pre "
                f"({len(domain)} units); a well-typed address outside the extent would build "
                "E(c) for a unit the runner was never entitled to credit")
        return build_unaffected(credited_site, traces, self._refinement)

    def run(self, state: LearnerPersistentState, *, arms: Sequence[ArmSpec], evidence: Mapping,
            exogenous: ExogenousSetup, credited_site: CreditedSite) -> PairedSceneRecord:
        r"""$$\boxed{\text{unaffected set} \to \text{clone per arm} \to \text{updates} \to
        \text{futures} \to \text{metrics}}$$

        The order is the whole content: a set built after an arm ran, or a future that existed before
        an update was applied, makes the record uninterpretable in a way no downstream number can
        repair. Every step emits a recorder event, so a gate reads the order, not the intent.
        """
        if type(state) is not LearnerPersistentState:
            raise ProtocolError(f"the scene runs from a learner state, got {type(state).__name__}")
        arms = tuple(arms)
        if len(arms) != 2:
            raise ProtocolError(
                f"a paired scene has exactly two arms, got {len(arms)}; B2's contrasts are "
                "tier-matched pairs")
        for arm in arms:
            if type(arm) is not ArmSpec:
                raise ProtocolError(
                    f"the arm {arm!r} has type {type(arm).__name__}, not ArmSpec; an arbitrary "
                    "callable on the update side is the B2-1 hole, and it stays closed here")
        if arms[0].name == arms[1].name:
            raise ProtocolError(f"the two arms share the name {arms[0].name!r}")
        if arms[0].architecture != arms[1].architecture:
            raise ProtocolError(
                f"the arms belong to different architectures ({arms[0].architecture!r}, "
                f"{arms[1].architecture!r}); a tier-matched pair is one architecture")
        if arms[0].tier is not arms[1].tier:
            raise ProtocolError(
                f"the arms are at different tiers ({arms[0].tier.name}, {arms[1].tier.name}); "
                "B2's contrast is same-cell")
        if type(exogenous) is not ExogenousSetup:
            raise ProtocolError(
                f"the exogenous setup has type {type(exogenous).__name__}, not ExogenousSetup")

        if type(credited_site) is not CreditedSite:
            raise ProtocolError(
                f"the credited unit {credited_site!r} has type {type(credited_site).__name__}, not "
                "CreditedSite")
        if credited_site.channel != arms[0].architecture:
            raise ProtocolError(
                f"the credited unit belongs to {credited_site.channel!r} but the arms are "
                f"{arms[0].architecture!r}; the region and the write are about one architecture")

        # The credited unit must be the one B1 will actually credit, resolved by that architecture's
        # own resolver from the very evidence the arms run on. Membership in the credited domain is not
        # enough: a legal-but-unrelated $c$ would define the region for a pair that writes elsewhere,
        # which is the failure A89's "the credited unit the pair is testing" exists to prevent. The
        # ontology carries a single $c$, so the resolved population must be exactly a singleton.
        resolved = self._resolved_credit(arms[0].architecture, evidence)
        if resolved != (credited_site.address,):
            raise ProtocolError(
                f"this pair's B1 credit resolves to {resolved!r}, but the unaffected region was asked "
                f"for {credited_site.render()}; the region would describe a pair that writes somewhere "
                "else")

        if exogenous.q_reference is not self._q_reference:
            raise ProtocolError(
                "the exogenous setup carries a different reference artifact than the runner's: A89 "
                "§77.8 freezes ONE nominal artifact for eligibility, both arms' collateral and the $D_Q$ "
                "write path, and a second object would let the dimensions disagree while looking equal")

        # (1) the shared design material, built from the RAW pre-update state BEFORE any arm exists
        unaffected = self.pre_update_source(state, credited_site)
        self._recorder("unaffected", unaffected, id(unaffected))

        # (1b) ONE pre measurement from the RAW pre state, taken once and shared: A85 §73.2.2 fixes
        #      that the two arms' pre values are the same measurement rather than two that happen to
        #      agree, so the map is measured here and handed to both collateral computations
        pre_map = measure_scene_map(state, unaffected.units, q_reference=self._q_reference)
        self._recorder("pre_map", id(pre_map), len(pre_map))

        # (2) independent clones from ONE pre-update state
        clones = [state.clone() for _ in arms]
        pre_fingerprints = {arm.name: fingerprint(clone) for arm, clone in zip(arms, clones)}
        if len(set(pre_fingerprints.values())) != 1:
            raise ProtocolError(
                "the two arms did not start from one pre-update state: fingerprints "
                f"{pre_fingerprints!r}; a serial chain from one arm into the other is not a pair")

        # (3) the updates, each on its own clone, before any future exists
        for arm, clone in zip(arms, clones):
            self._apply(arm, clone, evidence, self._q_reference)
            self._recorder("update_applied", arm.name, id(clone))

        # (4) the paired futures on ONE shared exogenous setup
        futures, views, observations = {}, {}, []
        for arm, clone in zip(arms, clones):
            environment = self._environment_factory(exogenous)
            self._recorder("exogenous", arm.name, id(exogenous))
            observations.append((arm.name, exogenous.kappa, exogenous.phi, exogenous.base_option,
                                 exogenous.tape, exogenous.checkpoints))
            view = FutureConsequenceViewBuilder(FutureRolloutProducer(environment)).build(clone)
            views[arm.name] = view
            levels = _levels(view)
            grid = _episode_grid(levels)
            futures[arm.name] = FutureUtility.from_curve(
                levels, grid, pre_level=_baseline_level(levels), t_max=grid[-1])
            self._recorder("future", arm.name, view)

        # (5) the three dimensions, separately. Collateral is V_unaffected,pre - V_unaffected,post(a)
        #     **per arm**, over the unit set, against the one shared pre map -- not a difference
        #     between the two arms, which is the paired contrast this dimension is not
        collateral, post_maps = {}, {}
        for arm, clone in zip(arms, clones):
            post_maps[arm.name] = measure_scene_map(clone, unaffected.units,
                                                    q_reference=self._q_reference)
            collateral[arm.name] = behavioral_collateral_scenes(
                unaffected, values_pre=pre_map, values_post=post_maps[arm.name])
        retention = {}
        for arm in arms:
            levels = _levels(views[arm.name])
            retention[arm.name] = self._form(levels, _episode_grid(levels), **dict(self._params))
        return PairedSceneRecord(
            arm_names=tuple(a.name for a in arms),
            architecture=arms[0].architecture,
            unaffected_construction=unaffected.construction,
            unaffected_size=unaffected.size,
            retention_form=self._form_name,
            future_utility=MappingProxyType(futures),
            collateral=MappingProxyType(collateral),
            retention=MappingProxyType(retention),
            ledgers=MappingProxyType({arm.name: _ledger_of(clone)
                                      for arm, clone in zip(arms, clones)}),
            fingerprints_pre=MappingProxyType(pre_fingerprints),
            observations=tuple(observations),
        )

    @staticmethod
    def _resolved_credit(architecture: str, evidence: Mapping) -> tuple:
        r"""The unit B1 will actually credit, from the architecture's own resolver.

        $D_Q$ and $X$ are handed resolved addresses, so the binding is the tuple the caller declared;
        $P$ is resolved here through the frozen $\rho_P$ (`resolve_process_addresses`) rather than by
        reading a field out of `AssistedInput` and re-implementing it.
        """
        if architecture == "D_Q":
            if "addresses" not in evidence:
                raise ProtocolError("the D_Q credit cannot be resolved without 'addresses'")
            return tuple(evidence["addresses"])
        if architecture == "X":
            if "sites" not in evidence:
                raise ProtocolError("the X credit cannot be resolved without 'sites'")
            return tuple(evidence["sites"])
        for key in ("units", "assisted"):
            if key not in evidence:
                raise ProtocolError(f"the P credit cannot be resolved without {key!r}")
        return tuple(resolve_process_addresses(evidence["units"], evidence["assisted"]))

    @staticmethod
    def _apply(arm: ArmSpec, clone: LearnerPersistentState, evidence: Mapping,
               q_reference=None) -> None:
        """Dispatch to the architecture's **existing B1 entry point**. No new update path."""
        if arm.architecture == "D_Q":
            for key in ("addresses", "rows"):
                if key not in evidence:
                    raise ProtocolError(f"the D_Q arm needs {key!r} in the evidence")
            run_dq_law(arm.law, clone, evidence["addresses"], evidence["rows"], q_reference,
                       sol=evidence.get("sol"), episode=evidence.get("episode"))
        elif arm.architecture == "P":
            for key in ("units", "assisted"):
                if key not in evidence:
                    raise ProtocolError(f"the P arm needs {key!r} in the evidence")
            run_process_law(arm.law, clone, evidence["units"], evidence["assisted"])
        else:
            for key in ("sites", "rows"):
                if key not in evidence:
                    raise ProtocolError(f"the X arm needs {key!r} in the evidence")
            run_controller_law(arm.law, clone, evidence["sites"], evidence["rows"])


def _episode_grid(levels) -> tuple:
    r"""The observed future as a checkpoint grid spanning $[0, T_{\max}]$ (A84 §72)."""
    if len(levels) < 2:
        raise ProtocolError(
            f"the future view carries {len(levels)} level(s); a curve needs at least two "
            "checkpoints to span a horizon")
    return tuple(range(len(levels)))


def _levels(view) -> tuple:
    return tuple(view.fields["future_rewards"].value)


def _baseline_level(levels) -> float:
    return max(abs(v) for v in levels) if levels else 1.0


def _ledger_of(state) -> object:
    """The intervention-cost view, kept **beside** the dimensions rather than inside them."""
    return getattr(state, "_last_ledger", None)
