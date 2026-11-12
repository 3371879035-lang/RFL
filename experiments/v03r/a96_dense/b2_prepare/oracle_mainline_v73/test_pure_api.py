"""New bounded pure API tests; NO actual source/rollout/B1/future execution."""
import ast
from contextlib import ExitStack
from fractions import Fraction
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

PREP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PREP))
import oracle_mainline_v73 as addon
from rfl_rebuild.b1.process import AssistedInput
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.b2 import training
from rfl_rebuild.env import kernel as K
from rfl_rebuild.learner.store import LearnerPersistentState
from rfl_rebuild.method.contract import FactualEvidence, FactualStep
from rfl_rebuild.method.credit import CausalProposal, OracleCreditAdapter
from rfl_rebuild.solve import dp

BLOCKED_CALLS = []
def blocked(*args, **kwargs):
    BLOCKED_CALLS.append(True)
    raise AssertionError("FORBIDDEN: actual rollout/update/key/RNG/training in pure API suite")


def packet():
    # Nominal sensor rows ONLY. Not a captured environment history/scientific event.
    steps = tuple(FactualStep(0, 2, t, 0, 0, 1, 0, 4, 4, -.02) for t in range(3))
    return FactualEvidence(steps, 1, 0, 0)


GAMMA = ("Decision_2", "ProcessCommit", "ControllerSite_0_2_2_4",
         "ExternalPlant", "Decision_0", "ControllerSite_0_2_0_4")


class PureOracleAdapterTests(unittest.TestCase):
    def test_complete_multi_decision_projection_and_residuals(self):
        p = addon._project(packet(), GAMMA, "D_Q")
        self.assertEqual(p.cell_units, ("Decision_0", "Decision_2"))
        self.assertEqual(tuple(a.state.t for a in p.addresses), (0, 2))
        self.assertEqual(set(p.whole_units), set(GAMMA))
        self.assertEqual(set(p.residual_units), set(GAMMA) - set(p.cell_units))
        self.assertEqual(len(p.whole_units), 6)

    def test_patch_preserves_same_extensional_owners_without_scalar_content(self):
        a = addon._project(packet(), GAMMA, "D_Q")
        b = addon._project(packet(), GAMMA, "D_patch")
        self.assertEqual(a.addresses, b.addresses)
        self.assertEqual(a.whole_units, b.whole_units)
        self.assertFalse(addon.SLICES["D_patch"].scalar)
        self.assertTrue(addon.SLICES["D_Q"].scalar)

    def test_controller_owners_do_not_merge_with_decisions(self):
        p = addon._project(packet(), GAMMA, "X")
        self.assertEqual(p.cell_units, ("ControllerSite_0_2_0_4", "ControllerSite_0_2_2_4"))
        self.assertEqual(tuple(a.state.t for a in p.addresses), (0, 2))
        self.assertEqual(tuple(a.cmd for a in p.addresses), (4, 4))
        self.assertIn("Decision_0", p.residual_units)

    def test_process_requires_explicit_assisted_input(self):
        with self.assertRaises(addon.ready.ProtocolError):
            addon._project(packet(), GAMMA, "P")
        p = addon._project(packet(), GAMMA, "P", AssistedInput(1))
        self.assertEqual(p.cell_units, ("ProcessCommit",))
        self.assertEqual(p.addresses, (1,))
        self.assertEqual(len(p.residual_units), 5)

    def test_process_rejects_boolean_address_alias(self):
        with self.assertRaises(addon.ready.ProtocolError):
            addon._project(packet(), GAMMA, "P", AssistedInput(True))

    def test_foreign_and_unused_assistance_rejected(self):
        for architecture, gamma in (("D_Q", GAMMA), ("X", GAMMA), ("P", ("ExternalPlant",))):
            with self.subTest(architecture=architecture):
                with self.assertRaises(addon.ready.ProtocolError):
                    addon._project(packet(), gamma, architecture, AssistedInput(1))

    def test_nonwriteable_truth_not_deleted_or_zero_filled(self):
        for architecture in addon.SLICES:
            p = addon._project(packet(), ("ExternalPlant", "Unknown/NoWrite"), architecture)
            self.assertEqual(p.cell_units, ())
            self.assertEqual(p.addresses, ())
            self.assertEqual(p.whole_units, p.residual_units)

    def test_empty_truth_not_relabelled_unknown(self):
        with self.assertRaises(addon.ready.ProtocolError):
            addon._ordered_oracle(packet(), ())

    def test_duplicate_truth_rejected_before_frozenset(self):
        with self.assertRaises(addon.ready.ProtocolError):
            addon._ordered_oracle(packet(), ("Decision_0", "Decision_0"))

    def test_wrong_truth_type_or_episode_domain_rejected(self):
        for gamma in ([*GAMMA], frozenset(GAMMA), ("Decision_3",), ("Decision_0", 0),
                      CausalProposal(frozenset({"Decision_0"}))):
            with self.subTest(value=repr(gamma)):
                with self.assertRaises(addon.ready.ProtocolError):
                    addon._ordered_oracle(packet(), gamma)

    def test_no_ordinary_method_or_proposal_path(self):
        tree = ast.parse(Path(addon.__file__).read_text(encoding="utf-8"))
        imports = [ast.unparse(n) for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
        self.assertFalse(any(s in " ".join(imports) for s in (
            "ordinary_methods_candidate", "diagnostic_source_candidate",
            "pair_source_candidate", "single_map_source_candidate", "future_inputs_candidate")))
        calls = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        self.assertNotIn("projection.prepare_credit", calls)
        self.assertNotIn("projection.prepare_cell", calls)
        self.assertIn("OracleCreditAdapter.evaluate", calls)
        self.assertNotIn("CausalProposal", calls)

    def test_only_existing_original_B1_entrypoints(self):
        tree = ast.parse(Path(addon.__file__).read_text(encoding="utf-8"))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_apply_original")
        calls = {ast.unparse(n.func) for n in ast.walk(fn) if isinstance(n, ast.Call)}
        self.assertEqual({c for c in calls if c.startswith("native_b1.")}, {
            "native_b1.run_dq_law", "native_b1.run_patch_law",
            "native_b1.run_controller_law", "native_b1.run_process_law"})
        self.assertFalse(any(isinstance(n, (ast.For, ast.While, ast.ListComp)) for n in ast.walk(fn)))

    def test_whole_pair_loops_roles_not_owners(self):
        tree = ast.parse(Path(addon.__file__).read_text(encoding="utf-8"))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_oracle_pair")
        loops = [ast.unparse(n.iter) for n in ast.walk(fn) if isinstance(n, ast.For)]
        self.assertEqual(loops, ["zip(originals, clones)"])
        self.assertIn("_CONSUMED[source].add(key)", ast.unparse(fn))

    def test_no_trainer_key_or_scientific_endpoint_dispatch(self):
        tree = ast.parse(Path(addon.__file__).read_text(encoding="utf-8"))
        calls = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        for c in ("training.train_curve", "train_curve", "FutureTrainingProtocol",
                  "training.key", "ExogenousEpisode.derive", "random.Random",
                  "native_b1._run", "measure_scene_map", "build_unaffected"):
            self.assertNotIn(c, calls)

    def test_original_same_tier_pairs_without_registration_mutation(self):
        original = (addon.laws.DQ_LAWS, addon.laws.X_LAWS, addon.laws.P_LAWS, addon.laws.LAWS)
        for a, t, name in (
            ("D_Q", Tier.L0_FACTUAL, "FactualReturnWrite"),
            ("D_Q", Tier.L3_ORACLE, "LocalOracleRestore"),
            ("D_patch", Tier.L0_FACTUAL, "DeleteFactualPatch"),
            ("X", Tier.L0_FACTUAL, "X_id"), ("X", Tier.L3_ORACLE, "LocalOracleRestore"),
            ("P", Tier.L1_CORRECTIVE, "P_id"), ("P", Tier.L3_ORACLE, "LocalOracleRestore")):
            ref, treatment = addon._registered(a, t, name)
            self.assertIs(ref.tier, treatment.tier)
            self.assertEqual(ref.name, "NoWrite")
            self.assertEqual(treatment.name, name)
        self.assertEqual(original, (addon.laws.DQ_LAWS, addon.laws.X_LAWS, addon.laws.P_LAWS, addon.laws.LAWS))

    def test_missing_tiers_fail_closed_not_relabelled(self):
        for a, t, name in (
            ("D_Q", Tier.L2_COUNTERFACTUAL, "DualReturnWrite"),
            ("D_patch", Tier.L1_CORRECTIVE, "SetAlternative"),
            ("D_patch", Tier.L3_ORACLE, "LocalOracleRestore"),
            ("D_Q", Tier.L1_CORRECTIVE, "FactualReturnWrite"),
            ("P", Tier.L0_FACTUAL, "P_id")):
            with self.subTest(cell=(a, t.name, name)):
                with self.assertRaises(addon.ready.ProtocolError):
                    addon._registered(a, t, name)

    def test_foreign_or_untyped_law_cell_rejected(self):
        for args in (("D_Q", True, "FactualReturnWrite"), ("D_Q", Tier.L0_FACTUAL, lambda: None),
                     ("X", Tier.L0_FACTUAL, "FactualReturnWrite"), ("bad", Tier.L0_FACTUAL, "X_id")):
            with self.assertRaises(addon.ready.ProtocolError):
                addon._registered(*args)

    def test_owned_handles_cannot_be_constructed_or_replaced_by_json(self):
        for cls in (addon.OwnedOracleSource, addon.OwnedOraclePair, addon.OwnedOracleFutureInputs):
            with self.assertRaises(addon.ready.ProtocolError):
                cls()
        for fn, args in ((addon._checked_source, ({},)), (addon._checked_pair, ({}, {})),
                         (addon._checked_future, ({}, {}))):
            with self.assertRaises(addon.ready.ProtocolError):
                fn(*args)

    def test_locked_seedfree_template_exact_dense_axis_and_bank(self):
        parent = addon.ready.load_parent()  # Byte/proof reads only, no native reruns.
        reference = addon.ready.read_json(PREP / "healthy_reference_candidate.json")
        t = addon._template(parent, reference)
        wire = addon._template_wire(t)
        self.assertIsInstance(t["alpha"], Fraction)
        self.assertEqual(t["alpha"], Fraction(1, 2))
        self.assertEqual(t["epsilon"], Fraction(1, 10))
        self.assertEqual(t["grid"], tuple(range(parent["design"]["T"] + 1)))
        self.assertEqual(len(t["sample"]), parent["design"]["N_eval"])
        self.assertEqual(wire["seed"], None)
        self.assertEqual(wire["v_pre_hex"], float(reference["v_pre"]).hex())
        with self.assertRaises(TypeError):
            t["T"] = 1

    def test_full_store_export_representation_not_effect_or_hash_only(self):
        state = LearnerPersistentState()
        self.assertEqual(addon._store_wire(state), {"D": [], "P": [], "X": [], "Q": []})
        clone = state.clone()
        self.assertIsNot(state, clone)
        self.assertEqual(addon._stores(state), addon._stores(clone))

    def test_nonfinite_seal_cannot_encode_nan(self):
        with self.assertRaises(ValueError):
            addon._sha({"bad": float("nan")})


if __name__ == "__main__":
    with ExitStack() as stack:
        for obj, name in (
            (K, "rollout"), (K, "step"), (LearnerPersistentState, "apply_transaction"),
            (addon.native_b1, "_run"), (addon.native_b1, "run_dq_law"),
            (addon.native_b1, "run_patch_law"), (addon.native_b1, "run_controller_law"),
            (addon.native_b1, "run_process_law"), (training, "train_curve"),
            (training, "episode_rollout"), (training, "key"),
            (training.ExogenousEpisode, "derive"), (dp, "solve_reference"),
            (addon.ready, "build_reference"), (addon.ready, "solve_reference")):
            stack.enter_context(patch.object(obj, name, blocked))
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(PureOracleAdapterTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        print(json.dumps({"role": "PURE_NEW_ADAPTER_API_TESTS_NOT_NATIVE_MECHANISM_OR_SCIENCE",
            "tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
            "skipped": len(result.skipped), "blocked_native_or_key_calls": len(BLOCKED_CALLS),
            "actual_source_capture_calls": 0, "actual_B1_execution_calls": 0,
            "future_training": 0, "keys_allocated": False, "scientific_PASS": False,
            "research_complete": False}, sort_keys=True))
        sys.exit(0 if result.wasSuccessful() and not BLOCKED_CALLS else 1)

