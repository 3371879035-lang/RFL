r"""A87 §75.6 — the $U_1$ continuation instrument, and its closure gates G1--G5.

$$\boxed{\text{Continuation CLOSED} = G1 \land G2 \land G3 \land G4 \land G5 \land
\text{a clean kernel/B1 regression suite}}$$

Each gate answers exactly one question, and the split matters because the failure modes are
different:

| gate | what it proves |
|---|---|
| G1 | the $D_Q$ and $X$ **post-update** learner channels reach a continuation the same way they reach an ordinary rollout, on the frozen projection images |
| G2 | a continuation entered at the post-commit state is the *suffix* of the ordinary rollout of the frozen $\mathcal C_P$ scene |
| G3 | the continuation does **not** re-execute $C_P^{L}$ |
| G4 | the equality is not a $\texttt{START}$-only accident: every pre-action context with $t > 0$ on the frozen canary healthy traces |
| G5 | the scalar semantics hold on the whole of $\mathcal X_D$, against the frozen exact solve |

Nothing here is the structural screening: no behaviour on $\mathcal X_D$ or $U_2$ is measured against
a candidate, no $\Delta V^{meas}$ is formed, and no seed is drawn. The canary scenes are the
instrument's calibration scenes -- A86 §74.4 requires per-architecture synthetic calibration, and a
gate that never exercised its own edit could not tell instrument blindness from candidate blindness.
"""

from __future__ import annotations

import ast
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b1.errors import ProtocolError  # noqa: E402
from rfl_rebuild.b2 import assert_modules_are_closed  # noqa: E402
from rfl_rebuild.b2.continuation import (  # noqa: E402
    ContinuationContractError,
    continuation,
    exogenous_lift,
    sigma_suffix,
    suffix_from,
)
from rfl_rebuild.b2.environment import (  # noqa: E402
    PRODUCTION_MODULES,
    audited_modules,
    learned_rollout,
    learner_channels,
)
from rfl_rebuild.env.domain import decision_contexts, is_decision_context  # noqa: E402
from rfl_rebuild.env.kernel import (  # noqa: E402
    HORIZON,
    START,
    ControlState,
    ControllerSite,
    SemanticTape,
    State,
    continue_rollout,
    initial_control,
    option_ids,
)
from rfl_rebuild.learner.reference import reference_view_from  # noqa: E402
from rfl_rebuild.learner.store import (  # noqa: E402
    CONTROLLER,
    PROCESS,
    Q,
    Edit,
    LearnerPersistentState,
    LearnerStateError,
    QAddress,
    StoreTransactionError,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

SOL = solve_reference()
REFERENCE = reference_view_from(SOL)
INSTRUMENT = ROOT / "src" / "rfl_rebuild" / "b2" / "continuation.py"

#: The frozen canary scene of §75.2, in the projection-image form the gates are bound to.
START_STATE = State(x=START[0], y=START[1], t=0, kappa=0, phi=0)
CANARY_TAPE = SemanticTape(phase=0, error_flag=0, cause_rank=0)
U2_BASE_OPTION = {"D_Q": 1, "X": 1, "P": 0}
CANARIES = ("D_Q", "X", "P")


def canary_edit(kind: str) -> Edit:
    r"""$\Delta W_A^{cal}$ of §75.2, in the substrate's own edit vocabulary."""
    if kind == "D_Q":
        # The healthy argmax at x* falls below the alternative: the read path is an argmax, so
        # selection moves to action 4 structurally, and 0.86 is the frozen row it moves to.
        return Edit(Q, QAddress(state=START_STATE, z=1, m=0, a=3), -0.14)
    if kind == "X":
        # The site the healthy learner actually queries: its command is 3, and 4 is inside A_z.
        return Edit(CONTROLLER, ControllerSite(state=START_STATE, cmd=3), 4)
    if kind == "P":
        return Edit(PROCESS, 0, 1)
    raise AssertionError(kind)


def learner_with(edits=()) -> LearnerPersistentState:
    r"""A learner state with the given persistent edits.

    A $Q$ edit must be handed the injected reference view: it supplies both the domain the entry
    must lie in and the value that canonicalises to a deletion (A77 §65.4), and nothing in the
    substrate fetches one for itself. The same reference the instrument reads is passed here, so
    an edit and its read path cannot disagree about the referent.
"""
    state = LearnerPersistentState()
    if edits:
        state.apply_transaction(list(edits), q_reference=REFERENCE)
    return state


def ordinary(kind: str, learner: LearnerPersistentState):
    r"""The ordinary rollout of the frozen $U_2$ image of canary ``kind``."""
    return learned_rollout(learner, kappa=0, tape=CANARY_TAPE,
                           base_option=U2_BASE_OPTION[kind], q_reference=REFERENCE)


def entry_image(kind: str) -> tuple:
    r"""$g_{U_1}(\xi_A^*)$ of §75.2: the load-bearing $P$ image is the **pre-update** option."""
    return (START_STATE, 1, 0) if kind in ("D_Q", "X") else (START_STATE, 0, 0)


def cont(learner: LearnerPersistentState, state: State, z: int, m: int):
    r"""The instrument, entered with the lift the screening will use."""
    return continuation(learner=learner, state=state, z=z, m=m, kappa=state.kappa,
                        tape=exogenous_lift(state, z, m), q_reference=REFERENCE)


def healthy_contexts(kind: str) -> list:
    r"""The pre-action contexts a rollout of the frozen scene actually used.

    Step $j$ was taken from ``(steps[j-1].state, steps[j-1].control)``, so enumerating
    $j = 1 \ldots \lvert\text{steps}\rvert - 1$ is **complete** by construction: it is exactly the
    set of contexts the loop acted on, and it excludes the post-terminal state, which no step
    consumed and which the kernel could not resume from.
    """
    learner = learner_with()
    trace = ordinary(kind, learner)
    return learner, trace, [(trace.steps[j - 1].state, trace.steps[j - 1].control)
                            for j in range(1, len(trace.steps))]


# --------------------------------------------------------------------------- #
# 1-3. the instrument's own contract
# --------------------------------------------------------------------------- #

def test_1_the_entry_must_be_a_legal_decision_context():
    r"""§75.6 (i): membership in $\mathcal X_D$ by the **frozen** enumerator, types first.

    An arbitrary `State`/`ControlState` pair is not accepted, so an instrument cannot quietly widen
    the unit's domain -- the image table of §75.2 would stop being well defined if it could.
    """
    learner = learner_with()
    bad = [
        State(x=4, y=2, t=0, kappa=0, phi=0),          # GOAL: never a decision point
        State(x=0, y=2, t=HORIZON, kappa=0, phi=0),    # past the horizon
        State(x=0.0, y=2, t=0, kappa=0, phi=0),        # float-typed field: numeric folding
    ]
    for state in bad:
        with pytest.raises(ContinuationContractError):
            cont(learner, state, 1, 0)
    for z, m in ((9, 0), (1, 2), (True, 0), (1, 0.0)):
        with pytest.raises(ContinuationContractError):
            cont(learner, START_STATE, z, m)
    with pytest.raises(ContinuationContractError):
        continuation(learner=object(), state=START_STATE, z=1, m=0, kappa=0,
                     tape=CANARY_TAPE, q_reference=REFERENCE)
    # the legal entry the gates use is accepted, so the refusals above are not a blanket refusal
    assert is_decision_context(START_STATE, 1, 0)
    assert sigma_suffix(cont(learner, START_STATE, 1, 0)).steps


def test_2_the_exogenous_continuation_must_agree_with_the_entry():
    r"""§75.6 (ii): the kernel derives the episode's phase from the tape, so a mismatch describes a
    suffix the frozen environment cannot produce."""
    learner = learner_with()
    with pytest.raises(ContinuationContractError):
        continuation(learner=learner, state=START_STATE, z=1, m=0, kappa=0,
                     tape=SemanticTape(phase=3, error_flag=0, cause_rank=0), q_reference=REFERENCE)
    wrong_kappa = State(x=START[0], y=START[1], t=0, kappa=1, phi=0)
    with pytest.raises(ContinuationContractError):
        continuation(learner=learner, state=wrong_kappa, z=1, m=0, kappa=0,
                     tape=SemanticTape(phase=0, error_flag=0, cause_rank=0), q_reference=REFERENCE)


def test_3_lambda_U1_is_a_deterministic_lift_and_not_unit_identity():
    r"""§75.4: one complete assignment per context, so that $u \mapsto V$ is a function.

    It depends on the state's phase and on nothing else -- not on $z$, not on $m$ -- and it never
    enters the domain or a cell's name.
    """
    for state in (START_STATE, State(x=1, y=3, t=4, kappa=1, phi=5)):
        tapes = {exogenous_lift(state, z, m)
                 for z in option_ids() for m in (0, 1)}
        assert tapes == {SemanticTape(phase=state.phi, error_flag=0, cause_rank=0)}
        assert exogenous_lift(state, 1, 0) == exogenous_lift(state, 1, 0)
    assert START_STATE in {s for (s, _z, _m) in decision_contexts()}


def test_4_the_instrument_cannot_recommit_and_uses_the_one_core():
    r"""§75.6 (iii), (iv) — checked on the source, because a comment cannot fail.

    The entry has no process-commit parameter at all: $z$ is taken as already in force. A version
    that reached for `rollout` or for `process_commit_provider` would re-execute $C_P^{L}$ and
    manufacture the sensitivity the screening exists to test for.
    """
    source = INSTRUMENT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = {node.func.id for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert "continue_rollout" in calls, "the instrument must call the shared core"
    assert "rollout" not in calls, "the instrument may not go back through the commit edge"
    assert "process_commit_provider" not in attributes
    assert "process_commit_provider" not in names
    assert "learner_process_commit" not in {a for a in attributes} | names
    # and it is inside the audited production chain, not beside it
    assert "rfl_rebuild/b2/continuation.py" in PRODUCTION_MODULES
    assert_modules_are_closed(audited_modules(ROOT / "src"))


# --------------------------------------------------------------------------- #
# G1-G5
# --------------------------------------------------------------------------- #

def test_g1_refactor_equivalence_bound_to_the_frozen_projection_images():
    r"""G1: $\Sigma_{\text{suffix}}$ agrees for every $W \in \mathcal W_{\text{gate}}$
    restricted to the two decision/controller canaries, on their own frozen images.

    The non-vacuity assertion is the point of the binding: the edit must be on the executed path, or
    a continuation that ignored the post-update learner would pass this gate as well.
    """
    assert START == (START_STATE.x, START_STATE.y)
    for kind in ("D_Q", "X"):
        state, z, m = entry_image(kind)
        assert (state, z, m) == (START_STATE, 1, 0)     # the frozen $U_1$ image
        pre, cal = learner_with(), learner_with([canary_edit(kind)])
        # non-vacuity: the scene actually executes the edited channel
        assert sigma_suffix(ordinary(kind, cal)) != sigma_suffix(ordinary(kind, pre))
        for learner in (pre, cal):
            assert sigma_suffix(cont(learner, state, z, m)) == sigma_suffix(ordinary(kind, learner))


def test_g2_decomposition_equivalence_at_the_frozen_p_scene():
    r"""G2: the ordinary rollout runs the frozen $\mathcal C_P$ scene and its **own** commit produces
    $z^{\text{in-force}} = C_P^{L}(0) = 1$; the continuation then enters from that post-commit state.

    Both sides therefore share the scene, the learner and the exogenous assignment, and differ only
    in whether the commit edge was traversed -- which is what decomposition equivalence means.
    """
    learner = learner_with([canary_edit("P")])
    trace = ordinary("P", learner)
    assert trace.option_in_force == 1                      # C_P^L(0) = 1
    assert trace.base_option == 0                          # the scene's proposal
    assert exogenous_lift(START_STATE, 1, 0) == CANARY_TAPE  # the lift is the P scene's own tape
    assert sigma_suffix(cont(learner, START_STATE, 1, 0)) == sigma_suffix(trace)
    assert sigma_suffix(cont(learner, START_STATE, 1, 0)) == suffix_from(trace, 0)


def test_g3_the_continuation_does_not_read_the_process_channel():
    r"""G3: a commit override that *would* change $z$ must not be read.

    $$\boxed{\Sigma^{\text{poison}}_{\text{suffix}} = \Sigma^{\text{clean}}_{\text{suffix}}$$

    The liveness half is witnessed by the **option in force** of the paired ordinary rollout, not by
    a return: the poison's only purpose is to show that the ordinary entry really does read
    $C_P^{L}$, and two different options could otherwise share a return and make the gate fail
    spuriously.
    """
    poison = [Edit(PROCESS, z, (z + 1) % len(option_ids())) for z in option_ids()]
    clean, poisoned = learner_with(), learner_with(poison)
    entry = (START_STATE, 1, 0)
    assert sigma_suffix(cont(poisoned, *entry)) == sigma_suffix(cont(clean, *entry))
    assert ordinary("P", poisoned).option_in_force != ordinary("P", clean).option_in_force


def test_g4_non_start_suffix_equality_over_the_frozen_canary_healthy_traces():
    r"""G4: equality on the interior of the frozen traces, not only at $\texttt{START}$.

    A wrapper that reset a non-zero $t$, dropped the passed $m$, or resumed with the wrong remaining
    horizon could satisfy G1--G3. The context set is complete by construction (see
    `healthy_contexts`), the tape is the lift of each context, and the $m = 1$ case is required when
    the frozen traces contain one -- they do, so the conditional is discharged here rather than
    deferred to G5.
    """
    seen = {0: 0, 1: 0}
    for kind in CANARIES:
        learner, trace, contexts = healthy_contexts(kind)
        eligible = [(s, c) for (s, c) in contexts if is_decision_context(s, c.z, c.m)]
        assert len(eligible) == len(contexts), "a context the loop used is outside X_D"
        assert eligible, "no interior context: the gate would be vacuous"
        for step, (state, control) in enumerate(eligible, start=1):
            assert exogenous_lift(state, control.z, control.m) == CANARY_TAPE
            assert sigma_suffix(cont(learner, state, control.z, control.m)) == suffix_from(trace, step)
            seen[control.m] += 1
    assert seen[0] >= 1, "no t > 0 context with m = 0"
    assert seen[1] >= 1, (
        "the frozen healthy traces contain no t > 0 context with m = 1, so the m = 1 half of G4 is "
        "not exercised; G5 still covers m = 1 on the whole domain")


def test_g5_full_domain_scalar_semantics_with_the_lift():
    r"""G5: $\forall (s,z,m) \in \mathcal X_D:\ V^{cont}_{W_{\text{pre}}}(s,z,m;\lambda_{U_1}) =
    V^{*}(s,z,m)$, with the existing DP gate's tolerance.

    Stated against the lift rather than a bare phase clause, so the object validated is the
    instrument the screening will use. This is not a measurement of a candidate: $W_{\text{pre}}$ is
    the unedited learner and the oracle is the frozen exact solve.
    """
    contexts = decision_contexts()
    assert len(contexts) == 13824
    learner = learner_with()
    checked = 0
    for (state, z, m) in contexts:
        trace = cont(learner, state, z, m)
        assert trace.return_value == pytest.approx(SOL.value(state, z, m), rel=1e-6, abs=1e-12)
        assert trace.option_in_force == z
        checked += 1
    assert checked == len(contexts)


# --------------------------------------------------------------------------- #
# 9. mutation power: the gates must be able to fail
# --------------------------------------------------------------------------- #

def test_9_the_gates_kill_a_divergent_instrument():
    r"""A gate that cannot fail is not a gate.

    Four deliberate defects, each one a plausible implementation of the same interface, each one
    killed by the gate that owns that failure mode -- and each kill is checked *through the gate's
    own comparison*, so the mutation table cannot drift away from the contracts it certifies.
    """
    state, z, m = entry_image("D_Q")
    learner = learner_with()
    reference_signature = sigma_suffix(cont(learner, state, z, m))

    def wrong_t_reset(entry_state: State, ez: int, em: int):
        provider, controller = learner_channels(learner.snapshot(), REFERENCE)
        return continue_rollout(
            state=State(x=entry_state.x, y=entry_state.y, t=0, kappa=entry_state.kappa,
                        phi=entry_state.phi),
            control=ControlState(z=ez, m=em), tape=exogenous_lift(entry_state, ez, em),
            command_provider=provider, base_option=ez, option_in_force=ez, controller=controller)

    def wrong_m_dropped(entry_state: State, ez: int, em: int):
        provider, controller = learner_channels(learner.snapshot(), REFERENCE)
        return continue_rollout(
            state=entry_state, control=ControlState(z=ez, m=0),
            tape=exogenous_lift(entry_state, ez, em), command_provider=provider,
            base_option=ez, option_in_force=ez, controller=controller)

    def wrong_reference_shortcut(entry_state: State, ez: int, em: int):
        return cont(learner_with(), entry_state, ez, em)      # the unedited learner's channels

    def wrong_recommit(entry_state: State, ez: int, em: int):
        snapshot = learner.snapshot()
        provider, controller = learner_channels(snapshot, REFERENCE)
        recommitted = snapshot.process_commit_provider()(ez)
        return continue_rollout(
            state=entry_state, control=initial_control(recommitted),
            tape=exogenous_lift(entry_state, ez, em), command_provider=provider,
            base_option=ez, option_in_force=recommitted, controller=controller)

    # (a) G4 owns the t / m surface: a reset t or a dropped m must change an interior suffix
    kills = {"t_reset": 0, "m_dropped": 0}
    for kind in CANARIES:
        _learner, trace, contexts = healthy_contexts(kind)
        for step, (ctx_state, control) in enumerate(
                [(s, c) for (s, c) in contexts if is_decision_context(s, c.z, c.m)], start=1):
            want = suffix_from(trace, step)
            if sigma_suffix(wrong_t_reset(ctx_state, control.z, control.m)) != want:
                kills["t_reset"] += 1
            if sigma_suffix(wrong_m_dropped(ctx_state, control.z, control.m)) != want:
                kills["m_dropped"] += 1
    assert kills["t_reset"] > 0, "G4 cannot see a reset t"
    assert kills["m_dropped"] > 0, "G4 cannot see a dropped m"

    # (b) G1 owns the learner-channel surface: a continuation that ignores the edited W must
    #     disagree with the ordinary rollout of the *same* edited W.
    for kind in ("D_Q", "X"):
        edited = learner_with([canary_edit(kind)])
        image, ez, em = entry_image(kind)
        assert sigma_suffix(wrong_reference_shortcut(image, ez, em)) != sigma_suffix(ordinary(kind, edited))

    # (c) G3 owns the commit surface: under a poison that *would* change z, a wrapper that recommits
    #     leaves the poisoned/clean equality that the real instrument satisfies.
    poison = [Edit(PROCESS, zz, (zz + 1) % len(option_ids())) for zz in option_ids()]
    poisoned = learner_with(poison)
    clean_signature = sigma_suffix(cont(learner_with(), state, z, m))
    assert sigma_suffix(cont(poisoned, state, z, m)) == clean_signature          # the real thing
    snapshot = poisoned.snapshot()
    provider, controller = learner_channels(snapshot, REFERENCE)
    recommitted = snapshot.process_commit_provider()(z)
    assert recommitted != z, "the poison must change the option, or liveness is untested"
    assert sigma_suffix(continue_rollout(
        state=state, control=initial_control(recommitted),
        tape=exogenous_lift(state, z, m), command_provider=provider,
        base_option=z, option_in_force=recommitted, controller=controller)) != clean_signature


def test_10_the_reference_oracle_the_gates_compare_against_is_the_frozen_solver():
    r"""G5's oracle is `solve_reference()`, and the two rows §75.7 cites come from it."""
    assert SOL.value(START_STATE, 0, 0) == pytest.approx(0.92, rel=1e-6)
    assert SOL.value(START_STATE, 1, 0) == pytest.approx(0.88, rel=1e-6)


def test_11_the_instrument_refuses_an_entry_outside_the_frozen_canary_images():
    r"""The images are frozen in §75.2, so the gates cannot be re-pointed at a friendlier scene.

    This is the regression that keeps G1/G2 honest: if a later revision moved an image -- say the
    $P$ image to the post-commit option, or the $D_Q$ image to $z = 0$ -- the gate would exercise a
    different scene while still printing `PASS`.
    """
    assert entry_image("D_Q") == entry_image("X") == (START_STATE, 1, 0)
    assert entry_image("P") == (START_STATE, 0, 0)
    assert U2_BASE_OPTION == {"D_Q": 1, "X": 1, "P": 0}
    assert CANARY_TAPE == SemanticTape(phase=0, error_flag=0, cause_rank=0)
    # the P image is pre-update by rule: the option the scene proposes, not the one the arm commits
    assert entry_image("P")[1] == 0 and learner_with([canary_edit("P")]).process_overrides
    with pytest.raises((ProtocolError, LearnerStateError, StoreTransactionError)):
        learner_with().apply_transaction([Edit(PROCESS, 0, 9)])
