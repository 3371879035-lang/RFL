"""Seedless proposal/row/tier engineering checks, NOT diagnostic efficacy.

Proposals are explicit constructed packets, not outputs of a scientific method.
Healthy traces are component fixtures only, never online SUCCESS reflections.
Actual owned P failures exercise the router -> closed packet -> native B1 link;
no future, population, environment key or collection authorization is created.
"""
from dataclasses import fields, replace
import inspect
import json
from pathlib import Path
import sys
from types import MappingProxyType, SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import credit_delivery_candidate as candidate
import factual_event_candidate as factual
import native_record_candidate as bridge
import readiness as ready
from rfl_rebuild.b1.contract import EVALUABLE_NOOP, fingerprint
from rfl_rebuild.b1.controller import resolve_controller_sites
from rfl_rebuild.b1.factual import factual_return_to_go
from rfl_rebuild.b1.process import AssistedInput
from rfl_rebuild.b1.targets import resolve_credited_units
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.b2.environment import learned_rollout
from rfl_rebuild.b2.runner import PairedRunner
from rfl_rebuild.b2.training import ExogenousEpisode
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.env import kernel as K
from rfl_rebuild.env.observation import learner_rows
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.learner.store import DECISION, PROCESS, Q, DecisionAddress, Edit, LearnerPersistentState, QAddress
from rfl_rebuild.method import credit as native
from rfl_rebuild.method.contract import FactualEvidence, FactualStep
from rfl_rebuild.method.runner import make_evidence
from rfl_rebuild.solve.dp import solve_reference

ERRORS = (ready.ProtocolError, native.ProtocolError)


class CreditDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent = ready.load_parent()
        cls.reference = ready.read_json(ready.ROOT / ready.FOLDER / "b2_prepare/healthy_reference_candidate.json")
        cls.q = reference_view_from(solve_reference())
        cls.trace = learned_rollout(LearnerPersistentState(), kappa=0,
            tape=EvaluationScene(0, 0, 0, 0, 0).tape, base_option=0, q_reference=cls.q)
        cls.evidence = make_evidence(learner_rows(cls.trace, 0, 0), cls.trace.option_in_force, 0, 0)

    def prep(self, units=("Decision_0",), *, kind="causal", evidence=None):
        return candidate.prepare_credit(evidence or self.evidence, kind=kind,
            proposal=candidate.PROPOSALS[kind](frozenset(units)))

    def cell(self, prepared=None, architecture="D_Q", tier=Tier.L0_FACTUAL,
             law="FactualReturnWrite", **kw):
        return candidate.prepare_cell(prepared or self.prep(), bridge.registered_pair(architecture, tier, law), **kw)

    def waiting(self, *, q_store=False, process=False):
        # Explicit engineering state, not C3/SCI initialization or population.
        state = LearnerPersistentState()
        edits = [Edit(PROCESS, 0, 1)] if process else []
        for t in range(K.HORIZON):
            s = K.State(*K.START, t, 0, 0)
            if q_store:
                edits.append(Edit(Q, QAddress(s, 1, 0, K.WAIT), max(self.q.row(s, 1, 0).values()) + 1.))
            else:
                edits.append(Edit(DECISION, DecisionAddress(s, 1, 0), K.WAIT))
        state.apply_transaction(edits, q_reference=self.q)
        return state

    def owned(self, state=None, *, base=1):
        return factual.prepare_factual_event(self.waiting() if state is None else state,
            scene=EvaluationScene(0, 0, 0, 0, base), regime="P", q_reference=self.q,
            parent=self.parent, reference=self.reference)

    def test_rows_match_original_closed_observation(self):
        rows, _, _, _, _ = candidate.factual_projection(self.evidence)
        self.assertEqual(rows, tuple(learner_rows(self.trace, 0, 0)))

    def test_shape_full_controller_wire_address_not_timestep_alias(self):
        _, shape, order, _, controllers = candidate.factual_projection(self.evidence)
        self.assertEqual(set(order), set(shape.gamma()))
        self.assertEqual(shape.sites, tuple(u.removeprefix("ControllerSite_") for u, _ in controllers))

    def test_all_native_expanders_are_reused(self):
        for kind, units in (("module", ("H", "L")), ("trajectory", ("Episode",)),
                            ("causal", ("Decision_0", "ExternalPlant"))):
            p = self.prep(units, kind=kind)
            self.assertEqual(set(p.expanded_units), native.expand(kind, p.proposal,
                candidate.factual_projection(self.evidence)[1]))

    def test_module_H_keeps_all_static_units_not_truth_best(self):
        self.assertEqual(self.prep(("H",), kind="module").expanded_units, native.GAMMA_STATIC)

    def test_module_L_keeps_all_D_and_X_addresses(self):
        p = self.prep(("L",), kind="module")
        self.assertEqual(len(p.expanded_units), 2 * len(self.evidence.steps))
        cell = self.cell(p)
        self.assertEqual(len(cell.addresses), len(self.evidence.steps))
        self.assertEqual(len(cell.audit["other_writeable_channels_retained_not_reclassified"]), len(self.evidence.steps))

    def test_trajectory_Episode_is_whole_domain_not_one_site(self):
        p = self.prep(("Episode",), kind="trajectory")
        self.assertEqual(set(p.expanded_units), set(candidate.factual_projection(self.evidence)[2]))
        with self.assertRaises(ready.ProtocolError):
            candidate.single_credited_site(self.cell(p))

    def test_empty_native_predictions_remain_abstentions(self):
        for kind in candidate.PROPOSALS:
            p = self.prep((), kind=kind)
            cell = self.cell(p)
            self.assertEqual(p.expanded_units, ())
            self.assertEqual(cell.addresses, ())
            self.assertEqual(cell.deliveries, (None, None))
            self.assertEqual(cell.audit["route"], "NO_CREDIT_IN_THIS_CELL_NOT_ZERO_FILLED")

    def test_unknown_is_not_abstention_or_writeable(self):
        p = self.prep(("Unknown/NoWrite",))
        c = self.cell(p)
        self.assertEqual(c.audit["nonwriteable_predictions_retained"], ["Unknown/NoWrite"])
        self.assertEqual(native.coverage(p.expanded_units, ("Unknown/NoWrite",)), 1.)
        self.assertEqual(native.coverage((), ("Unknown/NoWrite",)), 0.)

    def test_all_nonwriteable_predictions_preserved(self):
        c = self.cell(self.prep(candidate.NONWRITEABLE))
        self.assertEqual(set(c.audit["nonwriteable_predictions_retained"]), set(candidate.NONWRITEABLE))
        self.assertEqual(c.credited_units, ())

    def test_same_factual_and_proposal_same_cell_not_truth_dependent(self):
        one = self.owned(self.waiting(q_store=False))
        two = self.owned(self.waiting(q_store=True))
        self.assertEqual(one["method_evidence"], two["method_evidence"])
        a = self.cell(self.prep(evidence=one["method_evidence"]))
        b = self.cell(self.prep(evidence=two["method_evidence"]))
        self.assertEqual(a.audit_sha256, b.audit_sha256)
        self.assertNotEqual(one["evaluator_audit"]["fingerprint_pre"], two["evaluator_audit"]["fingerprint_pre"])

    def test_actual_success_router_never_reaches_credit_builder(self):
        with patch.object(candidate, "prepare_credit", side_effect=AssertionError("SUCCESS reflected")):
            got = factual.prepare_factual_event(LearnerPersistentState(), scene=EvaluationScene(0, 0, 0, 0, 0),
                regime="T", q_reference=self.q, parent=self.parent, reference=self.reference)
        self.assertIsNone(got["method_evidence"])
        with self.assertRaises(ready.ProtocolError):
            candidate.prepare_credit(None, kind="causal", proposal=native.CausalProposal(frozenset()))

    def test_domain_order_is_chronological_not_lexicographic(self):
        p = self.prep(("L",), kind="module", evidence=self.owned()["method_evidence"])
        self.assertEqual(p.expanded_units[:K.HORIZON], tuple(f"Decision_{t}" for t in range(K.HORIZON)))
        self.assertLess(p.expanded_units.index("Decision_2"), p.expanded_units.index("Decision_10"))

    def test_causal_stray_and_padded_or_wrong_controller_units_refused(self):
        for unit in ("Decision_999", "Decision_00", "ControllerSite_0", "ControllerSite_00_0_0_0",
                     "ControllerSite_999_0_0_0"):
            with self.subTest(unit=unit), self.assertRaises(ERRORS):
                self.prep((unit,))

    def test_exact_proposal_type_required_not_oracle_or_callable(self):
        for p in (native.OracleCreditAdapter(), lambda x: (), SimpleNamespace(units=frozenset()),
                  native.V02Input(self.evidence, (0,) * 5, candidate.factual_projection(self.evidence)[1])):
            with self.assertRaises(ERRORS):
                candidate.prepare_credit(self.evidence, kind="causal", proposal=p)

    def test_representation_kind_is_not_inferred_from_wrong_native_type(self):
        for kind in ("bad", None, 0, True, "module"):
            with self.assertRaises(ERRORS):
                candidate.prepare_credit(self.evidence, kind=kind, proposal=native.CausalProposal(frozenset()))

    def test_proposal_forged_mutable_units_refused(self):
        p = native.CausalProposal(frozenset(("Decision_0",)))
        object.__setattr__(p, "units", {"Decision_0"})
        with self.assertRaises(ERRORS):
            candidate.prepare_credit(self.evidence, kind="causal", proposal=p)

    def test_native_alphabet_revalidated_after_low_level_mutation(self):
        p = native.ModuleProposal(frozenset())
        object.__setattr__(p, "units", frozenset(("Decision_0",)))
        with self.assertRaises(ERRORS):
            candidate.prepare_credit(self.evidence, kind="module", proposal=p)

    def test_credit_packet_recomputed_not_trusted_cached_expansion(self):
        p = self.prep()
        for units in (("ProcessCommit",), (), ("Decision_0", "Decision_0"), ["Decision_0"]):
            with self.assertRaises(ERRORS):
                self.cell(replace(p, expanded_units=units))

    def test_evidence_and_step_subclasses_or_duck_types_refused(self):
        class ExtraEvidence(FactualEvidence):
            pass
        class ExtraStep(FactualStep):
            pass
        wrong = ExtraEvidence(self.evidence.steps, self.evidence.z_in_force, 0, 0)
        extra = ExtraStep(*(getattr(self.evidence.steps[0], f.name) for f in fields(FactualStep)))
        for e in (wrong, SimpleNamespace(steps=self.evidence.steps),
                  replace(self.evidence, steps=(extra,) + self.evidence.steps[1:])):
            with self.assertRaises(ERRORS):
                candidate.factual_projection(e)

    def test_outer_boolean_float_aliases_fail_before_equal_comparison(self):
        for name in ("kappa", "phi", "z_in_force"):
            for value in (False, 0.):
                with self.assertRaises(ERRORS):
                    candidate.factual_projection(replace(self.evidence, **{name: value}))

    def test_every_inner_integer_rejects_bool_float_aliases(self):
        for name in ("x", "y", "t", "kappa", "phi", "z", "m", "a_cmd", "a_realized"):
            original = getattr(self.evidence.steps[0], name)
            for value in (float(original), bool(original)):
                s = replace(self.evidence.steps[0], **{name: value})
                with self.assertRaises(ERRORS):
                    candidate.factual_projection(replace(self.evidence, steps=(s,) + self.evidence.steps[1:]))

    def test_empty_list_duplicate_reordered_step_rows_refused(self):
        for steps in ((), list(self.evidence.steps), self.evidence.steps[::-1],
                      (self.evidence.steps[0],) * 2):
            with self.assertRaises(ERRORS):
                candidate.factual_projection(replace(self.evidence, steps=steps))

    def test_reward_bool_nonfinite_nonreal_rejected_without_repair(self):
        for reward in (True, float("inf"), float("nan"), "1", 10 ** 500):
            s = replace(self.evidence.steps[0])
            object.__setattr__(s, "reward", reward)
            with self.assertRaises(ERRORS):
                candidate.factual_projection(replace(self.evidence, steps=(s,) + self.evidence.steps[1:]))

    def test_D_rows_resolution_equals_original_rho_D_on_real_trace(self):
        p = self.prep(("L",), kind="module")
        c = self.cell(p)
        self.assertEqual(c.addresses, resolve_credited_units(c.credited_units, self.trace, 0, 0))

    def test_X_rows_resolution_equals_original_rho_X_on_real_trace(self):
        p = self.prep(("L",), kind="module")
        c = self.cell(p, "X", Tier.L0_FACTUAL, "X_id")
        self.assertEqual(c.addresses, resolve_controller_sites(c.credited_units, self.trace, 0, 0))

    def test_D_and_X_resolutions_remain_distinct_not_timestep_aliases(self):
        p = self.prep(("L",), kind="module")
        d = self.cell(p); x = self.cell(p, "X", Tier.L0_FACTUAL, "X_id")
        self.assertTrue(all(type(a) is DecisionAddress for a in d.addresses))
        self.assertTrue(all(type(a) is K.ControllerSite for a in x.addresses))
        self.assertEqual(set(d.addresses) & set(x.addresses), set())

    def test_DQ_L0_exact_original_reverse_fold_no_new_summation(self):
        p = self.prep(("L",), kind="module", evidence=self.owned()["method_evidence"])
        c = self.cell(p)
        for i, a in enumerate(c.addresses):
            self.assertEqual(set(c.deliveries[0][a]), {"a_factual", "g_factual"})
            self.assertEqual(c.deliveries[0][a]["g_factual"].hex(), factual_return_to_go(c.b1_evidence["rows"], i).hex())

    def test_DQ_L0_reference_and_treatment_delivery_same_readonly_object(self):
        c = self.cell()
        self.assertIs(c.deliveries[0], c.deliveries[1])
        with self.assertRaises(TypeError):
            c.deliveries[0][c.addresses[0]]["g_cf"] = 7.
        with self.assertRaises(TypeError):
            c.b1_evidence["sol"] = "unauthorized"

    def test_X_L0_only_cmd_not_z_m_or_learner_u_delivered(self):
        c = self.cell(self.prep(("L",), kind="module"), "X", Tier.L0_FACTUAL, "X_id")
        for a in c.addresses:
            self.assertEqual(dict(c.deliveries[0][a]), {"a_cmd": a.cmd})

    def test_DQ_and_X_L3_construct_no_envelope_and_deliver_no_object(self):
        with patch.object(candidate, "build_factual_envelope", side_effect=AssertionError("L3 factual")), \
             patch.object(candidate, "build_controller_envelope", side_effect=AssertionError("L3 controller")):
            for arch in ("D_Q", "X"):
                c = self.cell(self.prep(("L",), kind="module"), arch, Tier.L3_ORACLE, "LocalOracleRestore")
                self.assertEqual(c.deliveries, (None, None))

    def test_nonempty_L2_cannot_silently_fallback_to_L0(self):
        with patch.object(candidate, "build_factual_envelope", side_effect=AssertionError("fallback")):
            with self.assertRaises(ready.ProtocolError):
                self.cell(self.prep(), "D_Q", Tier.L2_COUNTERFACTUAL, "CounterfactualReturnWrite")

    def test_pair_must_keep_architecture_tier_law_and_roles(self):
        arms = bridge.registered_pair("D_Q", Tier.L0_FACTUAL, "FactualReturnWrite")
        for pair in (arms[::-1], list(arms), (arms[0], bridge.registered_pair("X", Tier.L0_FACTUAL, "X_id")[1])):
            with self.assertRaises(ready.ProtocolError):
                candidate.prepare_cell(self.prep(), pair)

    def test_P_without_explicit_assisted_is_not_licensed_by_in_force_option(self):
        p = self.prep(("ProcessCommit",))
        for assisted in (None, self.evidence.z_in_force, SimpleNamespace(z_proposal=0)):
            with self.assertRaises(ready.ProtocolError):
                self.cell(p, "P", Tier.L1_CORRECTIVE, "P_id", assisted=assisted)

    def test_P_L1_original_rho_and_exact_same_tier_proposal_delivery(self):
        c = self.cell(self.prep(("ProcessCommit",)), "P", Tier.L1_CORRECTIVE, "P_id", assisted=AssistedInput(2))
        self.assertEqual(c.addresses, (2,))
        self.assertEqual(dict(c.deliveries[0][2]), {"z_proposal": 2})
        self.assertIs(c.deliveries[0], c.deliveries[1])

    def test_P_L3_requires_same_upstream_assisted_but_no_envelope(self):
        p = self.prep(("ProcessCommit",))
        with patch.object(candidate, "build_process_envelope", side_effect=AssertionError("L3 assisted envelope")):
            with self.assertRaises(ready.ProtocolError):
                self.cell(p, "P", Tier.L3_ORACLE, "LocalOracleRestore")
            c = self.cell(p, "P", Tier.L3_ORACLE, "LocalOracleRestore", assisted=AssistedInput(2))
        self.assertEqual(c.addresses, (2,))
        self.assertEqual(c.deliveries, (None, None))

    def test_P_assisted_type_before_option_equality(self):
        for value in (True, 1., -1, 4):
            with self.assertRaises(ready.ProtocolError):
                self.cell(self.prep(("ProcessCommit",)), "P", Tier.L1_CORRECTIVE, "P_id", assisted=AssistedInput(value))

    def test_ill_typed_or_unregistered_cell_dies_before_assisted_resolution(self):
        with patch.object(candidate, "resolve_process_addresses", side_effect=AssertionError("ill typed consumed assistance")):
            for tier in (Tier.L0_FACTUAL, Tier.L2_COUNTERFACTUAL, 1):
                with self.assertRaises(ready.ProtocolError):
                    self.cell(self.prep(("ProcessCommit",)), "P", tier, "P_id", assisted=AssistedInput(0))

    def test_extra_or_unused_assistance_refused(self):
        with self.assertRaises(ready.ProtocolError):
            self.cell(assisted=AssistedInput(0))
        with self.assertRaises(ready.ProtocolError):
            self.cell(self.prep(()), "P", Tier.L1_CORRECTIVE, "P_id", assisted=AssistedInput(0))

    def test_single_site_requires_whole_prediction_not_first_unit(self):
        one = self.cell()
        self.assertEqual(candidate.single_credited_site(one).address, one.addresses[0])
        for p in (self.prep(("Decision_0", "Decision_1")), self.prep(("Decision_0", "Unknown/NoWrite")),
                  self.prep(("Decision_0", "ProcessCommit")), self.prep(())):
            with self.assertRaises(ready.ProtocolError):
                candidate.single_credited_site(self.cell(p))

    def test_modified_cell_audit_or_b1_evidence_not_cached_authority(self):
        c = self.cell()
        with self.assertRaises(ready.ProtocolError):
            candidate.single_credited_site(replace(c, b1_evidence=MappingProxyType(dict(c.b1_evidence) | {"sol": "extra"})))
        c.audit["all_expanded_units"].append("Unknown/NoWrite")
        with self.assertRaises(ready.ProtocolError):
            candidate.single_credited_site(c)

    def test_fault_privileged_cmd_is_not_silently_granted_learner_write(self):
        s = self.evidence.steps[0]
        # A native transient observation may carry a command outside A_z. The
        # evidence expander preserves it; the cell must refuse learner writes.
        state = K.State(s.x, s.y, s.t, s.kappa, s.phi)
        allowed = K.option_actions(s.z, K.ControlState(s.z, s.m), state)
        bad = next(a for a in range(len(K.ACTIONS)) if a not in allowed)
        step = replace(s, a_cmd=bad)
        evidence = replace(self.evidence, steps=(step,) + self.evidence.steps[1:])
        p = self.prep(("L",), kind="module", evidence=evidence)
        for arch, tier, law in (("D_Q", Tier.L0_FACTUAL, "FactualReturnWrite"),
                ("X", Tier.L0_FACTUAL, "X_id"), ("X", Tier.L3_ORACLE, "LocalOracleRestore")):
            with self.assertRaises(ready.ProtocolError):
                self.cell(p, arch, tier, law)

    def test_pure_entry_points_cannot_request_truth_state_query_seed_or_population(self):
        self.assertEqual(tuple(inspect.signature(candidate.prepare_credit).parameters), ("evidence", "kind", "proposal"))
        self.assertEqual(tuple(inspect.signature(candidate.prepare_cell).parameters), ("prepared", "arms", "assisted"))
        with patch.object(K, "rollout", side_effect=AssertionError("adapter rollout")), \
             patch.object(ExogenousEpisode, "derive", side_effect=AssertionError("environment draw")), \
             patch.object(LearnerPersistentState, "apply_transaction", side_effect=AssertionError("adapter write")):
            self.cell()
        c = self.cell()
        for name in ("actual_failure_origin_authenticated", "assisted_source_authority_authenticated",
                     "B1_executed", "collection_authorized", "scientific_claim_authorized"):
            self.assertIs(c.audit[name], False)

    def test_owned_failure_expansion_all_D_addresses_original_native_B1_two_clones(self):
        pre = self.waiting(q_store=True); before = fingerprint(pre)
        event = self.owned(pre)
        self.assertEqual(event["evaluator_audit"]["factual_outcome"], K.Outcome.TIMEOUT)
        prepared = self.prep(("L",), kind="module", evidence=event["method_evidence"])
        c = self.cell(prepared)
        clones = (pre.clone(), pre.clone())
        results = tuple(PairedRunner._apply(a, clone, c.b1_evidence, self.q)
                        for a, clone in zip(c.arms, clones))
        self.assertEqual(len(results[0].ledger.receipts), K.HORIZON)
        self.assertEqual(len(results[1].ledger.receipts), K.HORIZON)
        self.assertEqual(tuple(r.address for r in results[0].ledger.receipts), c.addresses)
        self.assertEqual(tuple(r.address for r in results[1].ledger.receipts), c.addresses)
        self.assertTrue(all(r.status == EVALUABLE_NOOP for r in results[0].ledger.receipts))
        self.assertEqual(fingerprint(pre), before)
        self.assertEqual(fingerprint(clones[0]), before)
        self.assertIsNot(clones[0], clones[1])
        print("SEEDLESS_CREDIT_B1_COMPONENT_SUMMARY=" + json.dumps({
            "actual_factual_outcome": K.Outcome.TIMEOUT, "B1_credited_address_count_per_arm": len(c.addresses),
            "candidate_audit_sha256": c.audit_sha256, "source_prestate_unchanged": True,
            "diagnostic_algorithm_executed": False, "environment_seed_draws": 0,
            "future_training_episodes": 0, "collection_authorized": False}, sort_keys=True))

    def test_owned_process_failure_explicit_L1_B1_binding_without_audit_proposal(self):
        pre = self.waiting(process=True); before = fingerprint(pre)
        event = self.owned(pre, base=0)
        p = self.prep(("ProcessCommit",), evidence=event["method_evidence"])
        c = self.cell(p, "P", Tier.L1_CORRECTIVE, "P_id", assisted=AssistedInput(0))
        self.assertNotEqual(c.addresses[0], event["method_evidence"].z_in_force)
        clones = (pre.clone(), pre.clone())
        results = tuple(PairedRunner._apply(a, clone, c.b1_evidence, self.q)
                        for a, clone in zip(c.arms, clones))
        self.assertEqual(results[0].ledger.receipts[0].status, EVALUABLE_NOOP)
        self.assertEqual(fingerprint(pre), before)
        self.assertEqual(clones[1].snapshot().process_commit_provider()(0), 0)

    def test_invalid_prepared_cell_arms_fail_at_nominal_boundary(self):
        c = self.cell()
        for arms in ((), [], (None, None)):
            with self.assertRaises(ready.ProtocolError):
                candidate.single_credited_site(replace(c, arms=arms))

    def test_single_site_rejects_modified_delivery_even_with_unchanged_audit(self):
        c = self.cell()
        with self.assertRaises(ready.ProtocolError):
            candidate.single_credited_site(replace(c, deliveries=(None, None)))

    def test_single_site_refuses_reference_treatment_different_delivery_objects(self):
        c = self.cell()
        copied = MappingProxyType(dict(c.deliveries[1]))
        with self.assertRaises(ready.ProtocolError):
            candidate.single_credited_site(replace(c, deliveries=(c.deliveries[0], copied)))

    def test_same_numeric_reward_or_integer_alias_does_not_bind_B1_rows(self):
        c = self.cell()
        for row in (tuple(float(v) for v in c.b1_evidence["rows"][0][:-1]) + c.b1_evidence["rows"][0][-1:],
                    c.b1_evidence["rows"][0][:-1] + (int(c.b1_evidence["rows"][0][-1]),)):
            evidence = dict(c.b1_evidence) | {"rows": (row,) + c.b1_evidence["rows"][1:]}
            with self.assertRaises(ready.ProtocolError):
                candidate.single_credited_site(replace(c, b1_evidence=MappingProxyType(evidence)))

    def test_signed_zero_reward_or_delivery_cannot_substitute_bytes(self):
        step = replace(self.evidence.steps[0], reward=0.)
        evidence = FactualEvidence((step,), step.z, step.kappa, step.phi)
        c = self.cell(self.prep(evidence=evidence))
        row = c.b1_evidence["rows"][0][:-1] + (-0.,)
        altered = MappingProxyType(dict(c.b1_evidence) | {"rows": (row,)})
        with self.assertRaises(ready.ProtocolError):
            candidate.single_credited_site(replace(c, b1_evidence=altered))
        changed = MappingProxyType({c.addresses[0]: MappingProxyType({"a_factual": step.a_cmd, "g_factual": -0.})})
        with self.assertRaises(ready.ProtocolError):
            candidate.single_credited_site(replace(c, deliveries=(changed, changed)))

    def test_same_numeric_float_action_not_accepted_delivery(self):
        c = self.cell()
        row = dict(c.deliveries[0][c.addresses[0]])
        row["a_factual"] = float(row["a_factual"])
        changed = MappingProxyType({c.addresses[0]: MappingProxyType(row)})
        with self.assertRaises(ready.ProtocolError):
            candidate.single_credited_site(replace(c, deliveries=(changed, changed)))


if __name__ == "__main__":
    unittest.main()
