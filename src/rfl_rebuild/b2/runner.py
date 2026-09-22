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

**Shared training randomness is not evaluator truth.** CRN needs shared randomness, not shared routing
truth. Since A91 that randomness is the training instrument's keyed stream: the arms share one
`FutureTrainingProtocol` (one seed, one episode draw generator), whose declared inputs are $F_0$/$F_1$
quantities rather than anything this module may read from the world. The old closed-nominal
`ExogenousSetup` and the arbitrary `environment_factory` are retired --- after A91 neither fed a
measurement, and an unused callable on the production path is a side-effect surface, not a boundary.

**No conclusion can be produced here.** No cross-seed aggregation, no
$\mathrm{RMST} = \mathbb E[\text{restricted\_time}]$, no verdict, no Holm, no bootstrap; the record
keeps the three dimensions apart with the cost view beside them.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Sequence

from rfl_rebuild.b1.contract import fingerprint
from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b1.laws import DQ_LAWS, P_LAWS, X_LAWS
from rfl_rebuild.b1.process import resolve_process_addresses
from rfl_rebuild.b1.runner import run_controller_law, run_dq_law, run_process_law
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.b2.collateral import behavioral_collateral_scenes, measure_scene_map
from rfl_rebuild.b2.retention import select_form
from rfl_rebuild.b2.training import FutureTrainingProtocol, train_curve
from rfl_rebuild.b2.unaffected import (
    REFINEMENTS,
    CreditedSite,
    build_unaffected,
    credited_domain,
    pre_update_traces,
)
from rfl_rebuild.b2.utility import FutureUtility
from rfl_rebuild.learner.store import LearnerPersistentState

__all__ = ["ARCHITECTURES", "ArmSpec", "PairedRunner",
           "PairedSceneRecord"]

ARCHITECTURES = ("D_Q", "X", "P")

#: Each architecture's frozen law registry: an arm's law must be a member, which is what makes a
#: stand-in or a lambda impossible rather than merely discouraged. $D_Q$ is present because A85
#: §73.2.5 requires the measurement interface to be behaviourally load-bearing for all three, and B1
#: already ships the entry point -- the runner dispatches to it rather than inventing $D_Q$ semantics.
LAW_REGISTRIES = {"D_Q": DQ_LAWS, "P": P_LAWS, "X": X_LAWS}

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
    fingerprints_post: Mapping
    observations: tuple


class PairedRunner:
    r"""Run one scene's paired arms, exposing the properties a gate has to be able to see."""

    __slots__ = ("_training", "_refinement", "_q_reference", "_form",
                 "_form_name", "_params", "_recorder")

    def __init__(self, *, refinement: str, q_reference, retention_form: str,
                 retention_params: Mapping, training, recorder=None) -> None:
        r"""A89 §77.8: the collateral dimension is $U_2$-native, and the refinement is the caller's.

        There is no default refinement and no construction registry to choose from: A79 §67.4 leaves
        that choice to the development stage, and an instrument that embodied one could not compare
        candidates. The reference artifact is the same single object for eligibility and for both arms.

        **`training` is required, and it is A91's.** The future curve used to be read off
        `view.fields["future_rewards"]` and indexed by `range(len(levels))` --- the *step* index of one
        kernel rollout. A91 §§79.4--79.9 retired that reading, so the level curve now comes from the
        training instrument and its index is the **training episode**. The protocol carries
        $(\alpha, \varepsilon, T^{*}, \mathcal G^{*}, \mathcal S_{\text{eval}}^{*},
        V_{\text{pre}}^{*})$ as declared inputs: the runner obeys them and chooses none of them.

        **What is no longer here.** The old `environment_factory` and `ExogenousSetup` used to be handed
        to this constructor and to `run`, and after A91 neither fed any measurement: the factory was an
        arbitrary callable whose return value was discarded, which left a side-effect and exception
        surface on the production path with no scientific role, and the exogenous setup's
        `q_reference` identity check guarded a field the future no longer read. Both are retired
        rather than kept as decoration; the shared-stream contract now lives on `training`, and the
        one-reference contract is asserted against the consumers that actually read it.
        """
        if not isinstance(training, FutureTrainingProtocol):
            raise ProtocolError(
                "the runner needs A91's training protocol: the future curve is indexed by training "
                "episode, and a step-indexed curve is refused rather than reinterpreted")
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
        object.__setattr__(self, "_training", training)
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
            credited_site: CreditedSite) -> PairedSceneRecord:
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

        # The ONE-reference contract is asserted against the consumers that actually read the
        # reference, not against a field on a discarded object: A89 §77.8 freezes one nominal artifact
        # for eligibility, both arms' collateral, the $D_Q$ write path and --- since A91 --- the training
        # instrument. `self._q_reference` is the single source, and no other reference object exists on
        # this path to pass in; a spy on the three consumers is what proves it (test_12).
        if self._q_reference is None:                          # pragma: no cover - constructor guards
            raise ProtocolError("the runner lost its reference artifact")

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

        # (3b) the IMMEDIATE post-B1 states, captured before any future training runs.
        #      A85 §73.2.2 freezes $V_{\text{unaffected,post}}$ as **that arm's own post-update state**,
        #      and A91's training learns in place, so the future must consume a clone while the collateral
        #      keeps measuring this state. Before A91 the future producer was read-only, which is why the
        #      old order was safe; it no longer is, and the order is now asserted rather than assumed.
        post_states = {arm.name: clone for arm, clone in zip(arms, clones)}
        post_fingerprints = {arm.name: fingerprint(post_states[arm.name]) for arm in arms}

        # (4) the paired futures on ONE shared training protocol: the same keyed episode stream for both
        #     arms (A91 §79.5/§79.8), so a between-arm difference can only come from the initial write.
        futures, curves, observations = {}, {}, []
        protocol_ids = set()
        for arm, clone in zip(arms, clones):
            # ONE protocol object for both arms: this is the binding the CRN gate reads, and the
            # assertion below is what makes "the arms share one episode stream" mechanical
            protocol = self._training
            protocol_ids.add(id(protocol))
            self._recorder("training_protocol", arm.name, id(protocol))
            # the observation records the TRAINING provenance, which is what now decides the future:
            # the old single-episode (kappa, phi, tape, base_option, checkpoints) tuple described an
            # object that no longer feeds any measurement
            observations.append((arm.name, protocol.seed, protocol.t_max, protocol.grid,
                                 len(protocol.evaluation_sample), protocol.v_pre))
            # the future learns on a CLONE of the post-B1 state; the post state itself is the
            # collateral's measurement target and must come out of this loop untouched. The identity
            # check comes first because it is decisive on its own: a value-level check passes vacuously
            # whenever training happens to leave the learner where it was, which is exactly what a
            # healthy fixture does.
            future_state = post_states[arm.name].clone()
            if future_state is post_states[arm.name]:
                raise ProtocolError(
                    "the future was handed the arm's own post-B1 state rather than a clone: A85 §73.2.2 "
                    "measures $V_{unaffected,post}$ on the immediate post-B1 state, so future training "
                    "must not run on it")
            curve = train_curve(future_state, protocol=protocol, q_reference=self._q_reference)
            curves[arm.name] = curve
            futures[arm.name] = FutureUtility.from_curve(
                curve.values, curve.episodes, pre_level=curve.pre_level, t_max=curve.t_max)
            self._recorder("future", arm.name, (curve.values, curve.episodes))

        if len(protocol_ids) != 1:
            raise ProtocolError(
                "the paired futures did not consume one shared training protocol: the arms would draw "
                "different episode streams and the contrast would no longer be paired")
        for arm in arms:
            if fingerprint(post_states[arm.name]) != post_fingerprints[arm.name]:
                raise ProtocolError(
                    f"arm {arm.name!r}'s post-update state moved during the future computation: A85 "
                    "§73.2.2 measures $V_{unaffected,post}$ on the immediate post-B1 state, so future "
                    "training must run on a clone")

        # (5) the three dimensions, separately. Collateral is V_unaffected,pre - V_unaffected,post(a)
        #     **per arm**, over the unit set, against the one shared pre map -- not a difference
        #     between the two arms, which is the paired contrast this dimension is not
        collateral, post_maps = {}, {}
        for arm in arms:
            measured = post_states[arm.name]
            self._recorder("collateral_state", arm.name, fingerprint(measured))
            post_maps[arm.name] = measure_scene_map(measured, unaffected.units,
                                                    q_reference=self._q_reference)
            collateral[arm.name] = behavioral_collateral_scenes(
                unaffected, values_pre=pre_map, values_post=post_maps[arm.name])
        retention = {}
        for arm in arms:
            curve = curves[arm.name]
            retention[arm.name] = self._form(curve.values, curve.episodes, **dict(self._params))
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
            fingerprints_post=MappingProxyType(post_fingerprints),
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


def _ledger_of(state) -> object:
    """The intervention-cost view, kept **beside** the dimensions rather than inside them."""
    return getattr(state, "_last_ledger", None)
