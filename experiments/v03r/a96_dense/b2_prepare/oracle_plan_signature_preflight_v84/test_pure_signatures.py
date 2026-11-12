"""Four fresh SERIAL pure checks; real RFL plans/entrypoints/native never execute."""
import ast
from contextlib import ExitStack
import hashlib
import inspect
import json
from pathlib import Path
import sys
from types import MethodType
import unittest
from unittest.mock import patch
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / "src"))
from plan_capture import plan_capture
from rfl_rebuild.b1 import laws, runner
from rfl_rebuild.b1.tier import DQ_SLICE, PATCH_SLICE, Tier
from rfl_rebuild.env import kernel
from rfl_rebuild.learner.store import LearnerPersistentState

COUNTS = {"original_contract_calls": 0, "synthetic_original_calls": 0,
          "synthetic_observer_calls": 0, "blocked_calls": 0}
RECORDS = []
OUTPUT_BYTES = 0
def emit(tag, value):
    global OUTPUT_BYTES
    line = tag + "=" + json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    OUTPUT_BYTES += len((line + "\n").encode("utf8"))
    if OUTPUT_BYTES > 100000:
        raise RuntimeError("predeclared finite stdout budget; no retry")
    print(line, flush=True)
def blocked(*args, **kwargs):
    COUNTS["blocked_calls"] += 1
    raise AssertionError("pure signature preflight forbids original plan/native/store/reference/keys")
def roles():
    return [
        ("DQ_L3_NoWrite", laws.NoWriteRef(Tier.L3_ORACLE), DQ_SLICE),
        ("DQ_L3_LocalOracleRestore", laws.DQLocalOracleRestore(), DQ_SLICE),
        ("PATCH_L1_NoWrite", laws.NoWriteRef(Tier.L1_CORRECTIVE), PATCH_SLICE),
        ("PATCH_L1_SetAlternative", laws.SetAlternative(), PATCH_SLICE),
        ("PATCH_L3_NoWrite", laws.NoWriteRef(Tier.L3_ORACLE), PATCH_SLICE),
        ("PATCH_L3_LocalOracleRestore", laws.LocalOracleRestore(), PATCH_SLICE),
    ]
def checked_contract(label, law, spec, phase):
    COUNTS["original_contract_calls"] += 1
    if COUNTS["original_contract_calls"] > 12:
        raise RuntimeError("predeclared original pure contract budget; no retry")
    result, tier = runner._law_contract(law, spec)
    assert result is law and tier is law.tier
    # Check actual call syntax in addition to inspect's default view.
    bound = inspect.signature(law.plan, follow_wrapped=False)
    assert tuple(bound.parameters) == ("addresses", "targets")
    assert all(p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD and
               p.default is inspect.Parameter.empty for p in bound.parameters.values())
    assert "__signature__" not in law.plan.__func__.__dict__
    assert "__wrapped__" not in law.plan.__func__.__dict__
    record = {"label": label, "phase": phase, "law": law.name, "tier": tier.name,
              "slice": spec.name, "bound_names": list(bound.parameters),
              "kinds": [p.kind.name for p in bound.parameters.values()],
              "fields": sorted(spec.fields(tier)), "plan_executed": False}
    RECORDS.append(record); emit("ACTUAL_BOUND_SIGNATURE_AND_ORIGINAL_CONTRACT", record)

class PureSignatureTests(unittest.TestCase):
    def test_01_original_six_roles_then_new_hooks_same_API_and_alias_restored(self):
        # The saved functions are inspected, never dispatched; patched parent preserves alias.
        classes = (laws.NoWriteRef, laws.DQLocalOracleRestore,
                   laws.SetAlternative, laws.DeleteFactualPatch)
        originals = {cls: cls.plan for cls in classes}
        registry_objects = (laws.DQ_LAWS, laws.LAWS, laws.P_LAWS, laws.X_LAWS)
        alias_local_before = "plan" in laws.LocalOracleRestore.__dict__
        self.assertFalse(alias_local_before)
        self.assertIs(laws.LocalOracleRestore.plan, laws.DeleteFactualPatch.plan)
        for label, law, spec in roles():
            checked_contract(label, law, spec, "original")
        with ExitStack() as hooks:
            for cls, fn in originals.items():
                hooks.enter_context(patch.object(cls, "plan", plan_capture(fn, blocked)))
            self.assertIs(laws.LocalOracleRestore.plan, laws.DeleteFactualPatch.plan)
            self.assertFalse("plan" in laws.LocalOracleRestore.__dict__)
            for label, law, spec in roles():
                checked_contract(label, law, spec, "new_hook")
        for cls, fn in originals.items():
            self.assertIs(cls.plan, fn)
        self.assertIs(laws.LocalOracleRestore.plan, laws.DeleteFactualPatch.plan)
        self.assertFalse("plan" in laws.LocalOracleRestore.__dict__)
        for current, before in zip((laws.DQ_LAWS,laws.LAWS,laws.P_LAWS,laws.X_LAWS), registry_objects):
            self.assertIs(current, before)
        emit("ALIAS_AND_RUNTIME_RESTORATION", {"same_parent_plan_before_during_after": True,
            "alias_never_has_own_plan_attribute": True, "all_four_original_function_identities_restored": True,
            "all_original_registry_tuple_identities_retained": True})

    def test_02_synthetic_forwarding_same_objects_return_once_empty_and_nonempty(self):
        # These sentinels are NOT State, DecisionAddress, a target envelope or LawPlan.
        events = []
        law = object(); addresses = object(); result = object()
        def synthetic(self, addresses, targets):
            COUNTS["synthetic_original_calls"] += 1
            self_test.assertIs(self,law); self_test.assertIs(addresses,address_object)
            self_test.assertIs(targets,target_object)
            events.append("original");return result_object
        def observer(self, addresses, targets, output):
            COUNTS["synthetic_observer_calls"] += 1
            self_test.assertIs(self,law);self_test.assertIs(addresses,address_object)
            self_test.assertIs(targets,target_object);self_test.assertIs(output,result_object)
            events.append("observer")
        self_test=self;address_object=addresses;result_object=result
        for target_object in (None, object()):
            events.clear()
            fn=plan_capture(synthetic,observer)
            self.assertIs(MethodType(fn,law)(addresses,target_object),result)
            self.assertEqual(events,["original","observer"])
        emit("SYNTHETIC_FORWARDING_NOT_NATIVE", {"cases":2,"targets_none_and_nonempty_sentinel":True,
            "same_input_output_object_identities":True,"order":["original","observer"],"not_real_plan":True})

    def test_03_synthetic_failures_no_retry_and_no_false_completed_record(self):
        # New synthetic callbacks only; no old failure fixture/hook/checker is executed.
        events=[]
        expected=RuntimeError("predeclared synthetic original failure")
        def synthetic(self,addresses,targets):
            COUNTS["synthetic_original_calls"]+=1
            events.append("original");raise expected
        def observer(*args):
            COUNTS["synthetic_observer_calls"]+=1
            events.append("observer")
        with self.assertRaises(RuntimeError) as got:
            MethodType(plan_capture(synthetic,observer),object())(object(),None)
        self.assertIs(got.exception,expected);self.assertEqual(events,["original"])
        expected2=RuntimeError("predeclared synthetic observer failure")
        result=object();events.clear()
        def synthetic2(self,addresses,targets):
            COUNTS["synthetic_original_calls"]+=1
            events.append("original");return result
        def observer2(*args):
            COUNTS["synthetic_observer_calls"]+=1
            events.append("observer");raise expected2
        with self.assertRaises(RuntimeError) as got2:
            MethodType(plan_capture(synthetic2,observer2),object())(object(),None)
        self.assertIs(got2.exception,expected2);self.assertEqual(events,["original","observer"])
        emit("SYNTHETIC_EXCEPTION_PROPAGATION_NOT_NATIVE", {"original_failure_same_exception":True,
            "observer_failure_same_exception":True,"no_repeat_no_completed_return":True})

    def test_04_full_AST_failure_pin_and_new_hook_source_no_signature_mask(self):
        contract=json.loads((HERE/"contract.json").read_bytes())
        p=ROOT/contract["old_failure_source"]["path"];raw=p.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),contract["old_failure_source"]["sha256"])
        tree=ast.parse(raw.decode("utf8"))
        factories=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=="plan_capture"]
        self.assertEqual(len(factories),1)
        captures=[n for n in ast.walk(factories[0]) if isinstance(n,ast.FunctionDef) and n.name=="capture"]
        self.assertEqual(len(captures),1)
        old_args=[n.arg for n in captures[0].args.args]
        self.assertEqual(old_args,["law","addresses","delivery"])
        new_raw=(HERE/"plan_capture.py").read_bytes();new_tree=ast.parse(new_raw.decode("utf8"))
        new_capture=[n for n in ast.walk(new_tree) if isinstance(n,ast.FunctionDef) and n.name=="capture"]
        self.assertEqual(len(new_capture),1)
        new_args=[n.arg for n in new_capture[0].args.args]
        self.assertEqual(new_args,["law","addresses","targets"])
        self.assertEqual(new_capture[0].decorator_list,[])
        self.assertFalse(any(isinstance(n,ast.Attribute) and n.attr in ("__signature__","__wrapped__") for n in ast.walk(new_tree)))
        self.assertFalse(any(isinstance(n,(ast.Import,ast.ImportFrom)) and
            (getattr(n,"module","") or "").startswith("rfl_rebuild") for n in ast.walk(new_tree)))
        emit("READ_ONLY_AST_PIN_NO_OLD_EXECUTION", {"old_source_sha256":contract["old_failure_source"]["sha256"],
            "old_unbound_names":old_args,"new_unbound_names":new_args,
            "old_fixture_import_or_exec":False,"hook_no_signature_mask_or_production_import":True})

if __name__=="__main__":
    with ExitStack() as guards:
        # Bound law inspection doesn't execute plan. Guard every real defining plan,
        # native runner/entrypoint, kernel path and learner construction/clone/write.
        def profiler(frame,event,arg):
            if event=="call":
                module=frame.f_globals.get("__name__","")
                name=frame.f_code.co_name
                forbidden=(module.startswith("rfl_rebuild") and
                    ((module=="rfl_rebuild.b1.laws" and name=="plan") or
                     (module=="rfl_rebuild.b1.runner" and name in ("_run","_lower_row_ops","_scalar_accounting","_validate_plan")) or
                     (module.startswith("rfl_rebuild.b2")) or
                     (module.startswith("rfl_rebuild.solve"))))
                if forbidden:blocked()
        old_profile=sys.getprofile()
        for obj,name in ((kernel,"rollout"),(kernel,"step"),(LearnerPersistentState,"__init__"),
                         (LearnerPersistentState,"clone"),(LearnerPersistentState,"apply_transaction")):
            guards.enter_context(patch.object(obj,name,blocked))
        for name in runner.__all__:
            if name.startswith("run_"):guards.enter_context(patch.object(runner,name,blocked))
        sys.setprofile(profiler)
        try:
            result=unittest.TextTestRunner(verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(PureSignatureTests))
        finally:sys.setprofile(old_profile)
        exact=COUNTS=={"original_contract_calls":12,"synthetic_original_calls":4,
                      "synthetic_observer_calls":3,"blocked_calls":0}
        emit("FINAL", {"tests":result.testsRun,"failures":len(result.failures),
            "errors":len(result.errors),"skipped":len(result.skipped),"counts":COUNTS,
            "exact_predeclared_counts":exact,"all_real_law_plan_calls":0,"B1":0,"rollout":0,
            "step":0,"transaction":0,"source_capture":0,"bank":0,"DP":0,"training":0,"keys":False,
            "RNG":0,"native_calibration":0,"collector":False,"old_fixture_checker_native_reruns":0,
            "production_integration_validated":False,"scientific_PASS":False,"research_complete":False})
        sys.exit(0 if result.wasSuccessful() and exact else 1)

