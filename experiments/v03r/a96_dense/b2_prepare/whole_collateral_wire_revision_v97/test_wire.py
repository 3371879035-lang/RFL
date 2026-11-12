"""Necessary pure serialization check. No old test/checker/RFL execution."""
import ast
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import time
import unittest

from wire_boundary import encode, seal

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
CONTRACT=json.loads((HERE/'contract.json').read_bytes())
STARTED=time.monotonic()


@dataclass(frozen=True)
class OwnerWireShape:
    channel: str
    key: tuple


@dataclass(frozen=True)
class PreRecordWireShape:
    scene: dict
    trace: dict


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')).hexdigest()


class WireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=ROOT/CONTRACT['preserved_failed_capture']['path']
        assert sha(source)==CONTRACT['preserved_failed_capture']['sha256']
        cls.owners=None;cls.rows=[]
        with source.open(encoding='utf-8') as stream:
            for line in stream:
                r=json.loads(line)
                if r['tag']=='BANK_BEGIN' and r['payload']['stage']=='pre':
                    cls.owners=r['payload']['sanitized_owners']
                elif r['tag']=='RAW_ROLLOUT' and r['payload']['stage']=='pre':
                    s=dict(zip(('kappa','phase','error_flag','cause_rank','base_option'),r['payload']['scene']))
                    cls.rows.append({'scene':s,'trace':r['payload']['trace']})
        assert len(cls.rows)==5760 and len(cls.owners)==7
        cls.typed=tuple(OwnerWireShape(x['channel'],tuple(x['key'])) for x in cls.owners)
        print(json.dumps({'tag':'STORED_PRIMITIVES_READ_ONLY','full_pre_records':5760,'owner_wire_shapes':7,
                          'issued_handle_reconstruction':False,'old_native_reexecution':False},sort_keys=True),flush=True)

    def test_01_exact_failure_shape_and_repaired_owner_wire(self):
        with self.assertRaises(TypeError):json.dumps({'owners':self.typed})
        self.assertEqual(encode(self.typed),self.owners)
        self.assertEqual(seal({'owners':self.typed}),expected({'owners':self.owners}))

    def test_02_all_stored_pre_records_canonical_wire(self):
        records=tuple(PreRecordWireShape(x['scene'],x['trace']) for x in self.rows)
        self.assertEqual(seal((records,self.typed)),expected([self.rows,self.owners]))
        # The bytes are already wire data; encoding again must NOT reinterpret
        # binary64 markers as new learner values or convert their identity.
        self.assertEqual(encode(encode((records,self.typed))),encode((records,self.typed)))

    def test_03_binary64_rational_and_signed_zero(self):
        value={'x':(0.0,-0.0,0.1,Fraction(1,2)), 'already_wire':{'binary64_hex':(-0.0).hex()}}
        wanted={'x':[{'binary64_hex':0.0.hex()},{'binary64_hex':(-0.0).hex()},
                     {'binary64_hex':0.1.hex()},{'rational':[1,2]}],
                'already_wire':{'binary64_hex':(-0.0).hex()}}
        self.assertEqual(encode(value),wanted)
        self.assertEqual(seal(value),expected(wanted))
        self.assertNotEqual(seal(0.0),seal(-0.0))

    def test_04_revision_changes_only_six_wire_seal_calls(self):
        prior=ast.parse((ROOT/CONTRACT['preserved_failed_ruler']['path']).read_text(encoding='utf-8'))
        newer=ast.parse((HERE/'ruler.py').read_text(encoding='utf-8'))
        calls=0
        class Restore(ast.NodeTransformer):
            def visit_Call(self,node):
                nonlocal calls
                self.generic_visit(node)
                if isinstance(node.func,ast.Name) and node.func.id=='seal':
                    calls+=1;node.func=ast.Attribute(value=ast.Name(id='A',ctx=ast.Load()),attr='digest',ctx=ast.Load())
                return node
        newer=Restore().visit(newer)
        newer.body=[n for n in newer.body if not isinstance(n,ast.ImportFrom) or n.module!='wire_boundary']
        prior.body=prior.body[1:];newer.body=newer.body[1:]  # explicit explanatory docstrings differ
        self.assertEqual(calls,6)
        self.assertEqual(ast.dump(prior,include_attributes=False),ast.dump(newer,include_attributes=False))


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(WireTests))
    assert time.monotonic()-STARTED<CONTRACT['budget']['seconds']
    print(json.dumps({'tag':'RESULT','tests':result.testsRun,'failures':len(result.failures),
          'errors':len(result.errors),'skips':len(result.skipped),'seconds':time.monotonic()-STARTED,
          'RFL_or_old_checker_execution':False,'new_ruler_runtime_executed':False,
          'rollout':0,'step':0,'B1':0,'transaction':0,'scientific_qualification':False},sort_keys=True),flush=True)
    raise SystemExit(0 if result.wasSuccessful() else 1)
