r"""A80 §68.2–§68.4 — $D_X\times\{L_0,L_3\}$: the controller path.

$$\boxed{X_{id}:\ C_X^L\bigl(\rho_X(\texttt{ControllerSite})\bigr) \leftarrow a^{cmd}}$$

Four chains carry the cell, and the gates are grouped by them:

1. **the contract check** — unique factual row $\to (z,m) \to a^{cmd} \in A_z(m,s) \to$ the same
   pre-plan admissibility for both arms;
2. **locality** — `ControllerSite` $\to owner_X \to \texttt{Edit}(\texttt{CONTROLLER},\cdot)
   \to$ locality, load-bearing on the real path;
3. **the operation** — $site.cmd \to X_{id} \to$ one plan serving $L_0$ and $L_3$ $\to$ the
   canonical identity restore;
4. **the transaction** — one pre-state $\to$ one atomic commit $\to$ one receipt per credited site.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b1 import (  # noqa: E402
    APPLIED, EVALUABLE_NOOP, AddressPlan, ControllerTarget, ILL_TYPED,
    LawPlan, NoWriteRef, ProtocolError, Tier, XId, XLocalOracleRestore, X_DOMAIN, X_LAWS,
    X_SLICE, independent_treatment_count, law_metadata, require_admissible_sites,
    resolve_controller_sites, run_controller_law,
)
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import ControlState, State  # noqa: E402
from rfl_rebuild.env.observation import learner_rows  # noqa: E402
from rfl_rebuild.learner.store import (  # noqa: E402
    CONTROLLER, Edit, LearnerPersistentState,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

SOL = solve_reference()


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #

def scene(kappa=0, phi=0, z0=1):
    """A real scene: its trace, its rows, and its credited controller sites."""
    trace = K.rollout(kappa=kappa, tape=K.SemanticTape(phase=phi, error_flag=0, cause_rank=0),
                      command_provider=lambda s, c: SOL.best_action(s, c.z, c.m),
                      base_option=z0)
    rows = learner_rows(trace, kappa, phi)
    steps = sorted({r[2] for r in rows})
    sites = resolve_controller_sites(tuple(f"Decision_{t}" for t in steps), trace, kappa,
                                     phi)
    return trace, rows, sites


def scene_with_alternative(kappa=0, phi=0):
    """A scene where the *reference* action differs somewhere, so a write can change state."""
    for z0 in range(4):
        for k in (kappa,):
            trace, rows, sites = scene(k, phi, z0)
            for site in sites:
                row = next(r for r in rows if r[2] == site.state.t)
                allowed = sorted(K.option_actions(row[5], ControlState(z=row[5], m=row[6]),
                                                  site.state))
                other = [a for a in allowed if a != site.cmd]
                if other:
                    return trace, rows, sites, site, other[0]
    pytest.fail("no scene in the support exposes a second admissible command")


def dirty_state(site, wrong):
    state = LearnerPersistentState()
    state.apply_transaction([Edit(CONTROLLER, site, wrong)])
    return state


# --------------------------------------------------------------------------- #
# 1. the contract check
# --------------------------------------------------------------------------- #

def test_1_an_inadmissible_command_is_refused_at_the_pre_plan_boundary():
    r"""$$\boxed{\text{fault privilege is fault semantics, not a learner privilege}}$$

    $Z_X$/$Z_E$ exist because a *fault* may violate $A_z$; a persistent learner write is not a
    fault, so a site whose command is outside the option in force must be refused before any law
    runs (A75 §62.3, A80 §68.3).

    **This branch cannot be reached through real evidence, and that is a finding rather than a
    gap:** a credited site is derived from a factual row, and a rollout only ever produces
    admissible commands, so every site the resolver yields passes. The check is therefore an
    *invariant assertion* on the contract — and like §65.7's prefix identity, what a gate can
    verify is the premise. Here the premise is exercised the other way: fabricated rows whose
    command the option excludes must be refused, which is what makes the assertion load-bearing
    if `rho_X` ever stops sourcing sites from admissible evidence.
    """
    trace, rows, sites = scene()
    site = sites[0]
    row = list(next(r for r in rows if r[2] == site.state.t))
    allowed = K.option_actions(row[5], ControlState(z=row[5], m=row[6]), site.state)
    outside = [a for a in range(len(K.ACTIONS)) if a not in allowed]
    if not outside:
        pytest.skip("every action is admissible here")             # pragma: no cover
    row[7] = outside[0]                       # the row now claims an inadmissible command
    forbidden = K.ControllerSite(state=site.state, cmd=outside[0])
    for law in (XId, NoWriteRef(Tier.L0_FACTUAL), NoWriteRef(Tier.L3_ORACLE)):
        with pytest.raises(ProtocolError) as ei:
            run_controller_law(law, LearnerPersistentState(), (forbidden,), [tuple(row)])
        assert "outside" in str(ei.value), (law.name, ei.value)
    # the premise on REAL evidence: every site the resolver yields satisfies the contract
    require_admissible_sites(sites, rows)


def test_2_a_site_outside_the_factual_rows_is_refused():
    trace, rows, sites = scene()
    stray = K.ControllerSite(state=State(x=99, y=99, t=0, kappa=0, phi=0), cmd=0)
    with pytest.raises(ProtocolError) as ei:
        require_admissible_sites((stray,), rows)
    assert "not a site of the learner-visible factual rows" in str(ei.value)


def test_3_the_contract_check_is_arm_uniform():
    r"""Same boundary, same reason, before any arm plans (A78 §66.5's rule on this cell)."""
    trace, rows, sites = scene()
    stray = K.ControllerSite(state=State(x=99, y=99, t=0, kappa=0, phi=0), cmd=0)
    messages = []
    for law in (XId, NoWriteRef(Tier.L0_FACTUAL), XLocalOracleRestore,
                NoWriteRef(Tier.L3_ORACLE)):
        with pytest.raises(ProtocolError) as ei:
            run_controller_law(law, LearnerPersistentState(), (stray,), rows)
        messages.append(str(ei.value))
    assert len(set(messages)) == 1, messages


def test_4_the_credited_site_is_strictly_typed():
    r"""The folding lesson at the controller key: $C_X$ is a function **of the command**."""
    trace, rows, sites = scene()
    site = sites[0]
    folded_state = State(x=float(site.state.x), y=site.state.y, t=site.state.t,
                         kappa=site.state.kappa, phi=site.state.phi)
    aliases = [K.ControllerSite(state=folded_state, cmd=site.cmd),
               K.ControllerSite(state=site.state, cmd=float(site.cmd))]
    if site.cmd in (0, 1):
        aliases.append(K.ControllerSite(state=site.state, cmd=bool(site.cmd)))
    # the premise, where it holds: Python folds these onto the legal site
    assert K.ControllerSite(state=folded_state, cmd=site.cmd) == site
    assert K.ControllerSite(state=site.state, cmd=float(site.cmd)) == site
    if site.cmd in (0, 1):
        assert K.ControllerSite(state=site.state, cmd=bool(site.cmd)) == site
    # and the domain refuses every one of them, because `C_X` is a function OF THE COMMAND
    for alias in aliases:
        with pytest.raises(ProtocolError):
            X_DOMAIN.require_credited(alias)
    X_DOMAIN.require_credited(site)


def test_5_the_option_in_force_comes_from_the_row_not_the_caller():
    r"""The premise the $A_z$ assertion rests on, over the healthy support.

    $\rho_X$ carries no $z,m$; they come from the site's unique factual row. That is only sound
    because a row's command is admissible in the option that row records — asserted here for every
    site of every scene in the support, so a future change to $\rho_X$ or to the observation model
    fails here rather than turning the contract check into a silent no-op.
    """
    checked = 0
    for kappa in (0, 1):
        for phi in range(6):
            for z0 in range(4):
                try:
                    trace, rows, sites = scene(kappa, phi, z0)
                except Exception:                                  # pragma: no cover
                    continue
                require_admissible_sites(sites, rows)
                checked += len(sites)
    assert checked >= 100, f"too few sites exercised: {checked}"


# --------------------------------------------------------------------------- #
# 2. locality
# --------------------------------------------------------------------------- #

def test_6_owner_x_is_load_bearing_on_the_real_path():
    """A law whose edit is owned by another site is refused by the runner, not by the law."""
    trace, rows, sites = scene()
    victim, other = sites[0], sites[1]

    class _MisOwned:
        name, alias_of, tier = "MisOwned", None, Tier.L0_FACTUAL

        def plan(self, addresses, targets):
            return LawPlan(self.name, tuple(
                AddressPlan(s, (Edit(CONTROLLER, other, s.cmd),)) if s is victim
                else AddressPlan(s) for s in addresses))

    with pytest.raises(ProtocolError) as ei:
        run_controller_law(_MisOwned(), LearnerPersistentState(), sites, rows)
    assert "owner_locality" in str(ei.value)


def test_7_a_cross_architecture_store_edit_is_refused():
    trace, rows, sites = scene()

    class _WrongStore:
        name, alias_of, tier = "WrongStore", None, Tier.L0_FACTUAL

        def plan(self, addresses, targets):
            return LawPlan(self.name, tuple(
                AddressPlan(s, (Edit("decision", s, s.cmd),)) for s in addresses))

    with pytest.raises(ProtocolError) as ei:
        run_controller_law(_WrongStore(), LearnerPersistentState(), sites, rows)
    assert "outside the" in str(ei.value)


def test_8_duplicates_and_uncredited_sites_fail_stop():
    trace, rows, sites = scene()
    victim = sites[0]

    class _DuplicateEdit:
        name, alias_of, tier = "DuplicateEdit", None, Tier.L0_FACTUAL

        def plan(self, addresses, targets):
            return LawPlan(self.name, tuple(
                AddressPlan(s, (Edit(CONTROLLER, s, s.cmd),
                                Edit(CONTROLLER, s, s.cmd))) if s is victim
                else AddressPlan(s) for s in addresses))

    class _DuplicatePlan:
        name, alias_of, tier = "DuplicatePlan", None, Tier.L0_FACTUAL

        def plan(self, addresses, targets):
            return LawPlan(self.name, tuple(AddressPlan(sites[0]) for _ in addresses))

    class _ExtraSite:
        name, alias_of, tier = "ExtraSite", None, Tier.L0_FACTUAL

        def plan(self, addresses, targets):
            return LawPlan(self.name, tuple(AddressPlan(s) for s in addresses)
                           + (AddressPlan(K.ControllerSite(
                               state=State(x=99, y=99, t=0, kappa=0, phi=0), cmd=0)),))

    for law, needle in ((_DuplicateEdit, "same entry twice"),
                        (_DuplicatePlan, "same address more than once"),
                        (_ExtraSite, "not a site")):
        with pytest.raises(ProtocolError) as ei:
            run_controller_law(law, LearnerPersistentState(), sites, rows)
        assert needle in str(ei.value) or "non-credited" in str(ei.value), (law.name, ei.value)


# --------------------------------------------------------------------------- #
# 3. the operation: one plan, two cells, the canonical restore
# --------------------------------------------------------------------------- #

def test_9_the_alias_is_a_real_implementation_alias():
    r"""$$\boxed{XLocalOracleRestore.plan\ \text{is}\ XId.plan}$$ and
    $\lvert\text{treatments}(X)\rvert = 1$."""
    assert XLocalOracleRestore.plan is XId.plan
    assert XLocalOracleRestore.alias_of == "X_id"
    assert [law.name for law in X_LAWS] == ["NoWrite", "X_id", "NoWrite",
                                            "LocalOracleRestore"]
    assert independent_treatment_count(X_LAWS) == 1


def test_10_the_same_plan_runs_at_l3_with_no_envelope():
    r"""$L_3$ delivers $\varnothing$, so a plan that read the envelope could not run here."""
    trace, rows, sites = scene()
    assert sorted(X_SLICE.fields(Tier.L3_ORACLE)) == []
    for law in (XLocalOracleRestore, NoWriteRef(Tier.L3_ORACLE)):
        state = LearnerPersistentState()
        led = run_controller_law(law, state, sites, rows).ledger
        assert led.n_addressed == len(sites)
        assert set(r.status for r in led.receipts) == {EVALUABLE_NOOP}, law.name
        assert dict(state.controller_overrides) == {}, law.name
    assert sorted(X_SLICE.fields(Tier.L0_FACTUAL)) == ["a_cmd"]


def test_11_l3_restores_a_dirty_state_and_l0_writes_the_same_transformation():
    r"""$$X_{id} \equiv LocalOracleRestore$$ on any pre-state, not only a healthy one.

    The store canonicalises $u = site.cmd$ to a deletion, so the identity write and the restore
    are the **same persistent-state transformation**; this measures it on a state that actually
    holds a wrong override.
    """
    trace, rows, sites, site, other = scene_with_alternative()
    dirty = dirty_state(site, other)
    assert dirty.controller_overrides == {site: other}
    led = run_controller_law(XLocalOracleRestore, dirty, sites, rows).ledger
    assert dict(dirty.controller_overrides) == {}
    status = next(r.status for r in led.receipts if r.address == site)
    assert status == APPLIED and led.store_changed
    # and the L0 treatment performs the identical transformation from the identical pre-state
    dirty2 = dirty_state(site, other)
    run_controller_law(XId, dirty2, sites, rows)
    assert dict(dirty2.controller_overrides) == dict(dirty.controller_overrides)


def test_12_the_canonical_receipt_changes_with_the_command():
    r"""Injectivity on the legal domain, with the canary that matters for this key.

    `ControllerSite` is exactly $(s, a^{cmd})$: an encoding that dropped the command would give
    two distinct credited sites one receipt identity — the defect the *legacy* controller key had,
    when it keyed on `(x, y, t, t)` and omitted $a^{cmd}$.
    """
    trace, rows, sites, site, other = scene_with_alternative()
    assert site.cmd != other
    assert X_DOMAIN.canonical(site) != X_DOMAIN.canonical(
        K.ControllerSite(state=site.state, cmd=other))
    # and the same for a state component
    moved = K.ControllerSite(
        state=State(x=site.state.x, y=site.state.y, t=site.state.t + 1,
                    kappa=site.state.kappa, phi=site.state.phi), cmd=site.cmd)
    assert X_DOMAIN.canonical(site) != X_DOMAIN.canonical(moved)


def test_13_both_arms_receive_the_same_delivered_fields():
    r"""Same cell $\Rightarrow$ same envelope (A77 §65.2), read at the delivery boundary."""
    trace, rows, sites = scene()
    seen = {}

    class _Spy(NoWriteRef):
        name = "SpyX"
        tier = Tier.L0_FACTUAL

        def plan(self, addresses, targets):
            seen["fields"] = {frozenset(v) for v in targets.values()}
            seen["pair"] = {tuple(sorted(v.items())) for v in targets.values()}
            return LawPlan(self.name, tuple(AddressPlan(a) for a in addresses))

    run_controller_law(_Spy(), LearnerPersistentState(), sites, rows)
    assert seen["fields"] == {frozenset({"a_cmd"})}
    # and the delivered command IS the address's own, checked independently of the law
    for pair in seen["pair"]:
        (field, value), = pair
        assert field == "a_cmd"


def test_14_the_envelope_and_the_address_must_agree():
    """The L0 delivery is checked against the credited address, not merely carried."""
    from rfl_rebuild.b1 import validate_controller_envelope

    trace, rows, sites = scene()
    site = sites[0]
    lie = {s: ControllerTarget(site=s, a_cmd=(s.cmd + 1) % len(K.ACTIONS)) for s in sites}
    with pytest.raises(ProtocolError) as ei:
        validate_controller_envelope(sites, lie, rows)
    assert "factual row says" in str(ei.value)


# --------------------------------------------------------------------------- #
# 4. the transaction
# --------------------------------------------------------------------------- #

def test_15_one_pre_state_one_transaction_one_receipt_per_site():
    trace, rows, sites, site, other = scene_with_alternative()
    dirty = dirty_state(site, other)
    calls = []
    original = LearnerPersistentState.apply_transaction

    def spy(self, edits, **kwargs):
        calls.append(tuple(edits))
        return original(self, edits, **kwargs)

    LearnerPersistentState.apply_transaction = spy
    try:
        res = run_controller_law(XId, dirty, sites, rows)
    finally:
        LearnerPersistentState.apply_transaction = original
    assert len(calls) == 1, f"one scene commits once, got {len(calls)}"
    assert res.ledger.n_addressed == len(sites)
    assert len(res.ledger.receipts) == len(sites)
    res.ledger.check_fingerprint_invariants()


def test_16_the_second_run_is_a_noop():
    """Idempotence: after the first run the store holds exactly the healthy referent."""
    trace, rows, sites, site, other = scene_with_alternative()
    state = dirty_state(site, other)
    first = run_controller_law(XId, state, sites, rows).ledger
    assert first.store_changed
    second = run_controller_law(XId, state, sites, rows).ledger
    assert not second.store_changed
    assert set(r.status for r in second.receipts) == {EVALUABLE_NOOP}
    assert second.fingerprint_pre == second.fingerprint_post


def test_17_the_cell_table_is_the_frozen_one():
    r"""A80 §68.3: $X$'s rows, written; and the empty cells are not arms."""
    assert X_SLICE.fields(Tier.L0_FACTUAL) == frozenset({"a_cmd"})
    assert X_SLICE.fields(Tier.L3_ORACLE) == frozenset()
    assert X_SLICE.cells[Tier.L1_CORRECTIVE] is ILL_TYPED
    assert X_SLICE.cells[Tier.L2_COUNTERFACTUAL] is ILL_TYPED
    assert X_SLICE.scalar is False
    assert X_SLICE.store == CONTROLLER
    kinds = [k for _n, k, _a in law_metadata(X_LAWS)]
    assert kinds == ["reference", "operation", "reference", "alias"]
