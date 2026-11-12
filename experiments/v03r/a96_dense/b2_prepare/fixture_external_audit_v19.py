"""Primary-agent stdlib byte/role audit, not an independent expert or gate."""
import ast
import hashlib
import json
from pathlib import Path
import re
import sys

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[3]
CORE = {
    "fixture_source_candidate.py": "fa5a2d4a8711c0d15fceb118da551ecfd8d82e536de2d5acab7a64e75e042831",
    "test_fixture_source_candidate.py": "fd68f6576e496cde387e2e7185d3197013b9763baeb8c732eba86e9adf32c8f7",
    "fixture_contract_candidate_v19.json": "67b98312d770a9cb50304f3a5a0e15c2b2a82a304ced0c37dc3f15c8fc5ce622",
    "fixture_integration_runner_v19.py": "6b3f47da7003b261f92b14469f017937853d5797e89fe5b0c9489c063673f2c3",
    "fixture_source_initial_v19.py.txt": "07d80ef0f7e65e0f2d3f7a495337ce8725609a6a2e8875cfb669e43b2254ce10",
    "test_fixture_source_initial_v19.py.txt": "e065f54cbef8101f18deaa8ba348d5f74a1ca285236552d5117c3b8db2f203a6",
    "fixture_source_revision2_v19.py.txt": "edb75f0e5d6f065870c3b0a755bb534edcc8ca8d39dc27779991d30ca9c895d8"
}
SNAPSHOT_SHA = "2ced68db677953320cb3c4f0ca5e9df5e8d3a6a8f37752a0a53abbe89c8eac5d"
PAYLOAD_SHA = "4d7e69de6edca5170a0ed784d33c9e23c248fb47279a222144eab9f0e0a1910f"
MODULES = ("test_fixture_source_candidate", "test_seed_plan_candidate",
           "test_history_seed_audit_candidate", "test_history_schedule_candidate")


def sha(raw): return hashlib.sha256(raw).hexdigest()
def canon(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=True,separators=(",",":"),allow_nan=False).encode("ascii")
def pair_hook(rows):
    answer={}
    for key,value in rows:
        assert key not in answer, "duplicate JSON member"
        answer[key]=value
    return answer
def read_json(raw):
    return json.loads(raw.decode("utf-8-sig"),object_pairs_hook=pair_hook,
        parse_constant=lambda x: (_ for _ in ()).throw(ValueError("nonfinite")))
def union(rows):
    out=[]
    for a,b in sorted(rows):
        assert 0 <= a <= b < (1<<64)
        if out and a<=out[-1][1]+1: out[-1][1]=max(out[-1][1],b)
        else: out.append([a,b])
    return [[str(a),str(b)] for a,b in out]


def audit():
    for name,wanted in CORE.items():
        assert sha((FOLDER/name).read_bytes())==wanted, name
    contract=read_json((FOLDER/"fixture_contract_candidate_v19.json").read_bytes())
    expected=contract["bound_parent_test_sources"]
    assert len(expected)==19
    raw=(FOLDER/"evidence_v19/fixture_source_snapshot_final.stdout.log").read_bytes()
    assert sha(raw)==SNAPSHOT_SHA
    wrapped=read_json(raw); payload=wrapped["payload"]
    assert wrapped["payload_sha256"]==PAYLOAD_SHA==sha(canon(payload))
    assert payload["parent_commit"]=="62ca6c5603bedc14e16882190432f5fc1f50a198"
    assert payload["core_before_after_sha256"]=={n:CORE[n] for n in (
        "fixture_source_candidate.py","fixture_contract_candidate_v19.json","test_fixture_source_candidate.py")}
    actual=[]; claims=0; gaps=0; envelopes=0; all_rows=[]; input_hashes={}
    for record in payload["records"]:
        relative=record["path"]; assert relative in expected
        p=ROOT/relative; original=p.read_bytes(); input_hashes[relative]=sha(original)
        assert input_hashes[relative]==expected[relative]==record["sha256"]
        assert len(original)==record["actual_bytes"]
        tree=ast.parse(original.decode("utf-8-sig")); nodes=list(ast.walk(tree))
        max_line=max(getattr(n,"lineno",0) for n in nodes)
        inspection=record["source_only_inspection"]
        assert inspection["parse_complete"] is True
        assert inspection["runtime_flows_complete"] is False
        assert inspection["runtime_key_use_proved"] is False
        rows=[]
        for claim in inspection["claims"]:
            assert 1<=claim["line"]<=max_line
            assert claim["environment_key_use_proved"] is False
            assert claim["role"] in ("DECLARED_LITERAL_FIXTURE","REJECTED_INPUT_FIXTURE_LABEL_NOT_ENVIRONMENT_USE")
            # Independently bind every reported expression to an actual same-line
            # AST subtree. This checks byte/expression identity, not unknown flows.
            expression=ast.dump(ast.parse(claim["expression"],mode="eval").body)
            owner=[n for n in nodes if getattr(n,"lineno",0)==claim["line"]]
            expressions={ast.dump(n) for o in owner for n in ast.walk(o)}
            assert expression in expressions, (relative,claim["line"])
            originals=claim["original_integers_decimal"]
            assert all(re.fullmatch(r"-?(0|[1-9][0-9]*)",x) for x in originals)
            integers=list(map(int,originals))
            assert integers==sorted(set(integers))
            aliases=sorted({x%(1<<64) for x in integers})
            assert claim["modulo64_aliases_decimal"]==[str(x) for x in aliases]
            assert claim["literal_occurrences"]>=len(originals)>0
            rows.extend((x,x) for x in aliases); claims+=1
        assert union(rows)==inspection["fixture_alias_intervals"]
        all_rows.extend(rows)
        for e in inspection["synthetic_range_envelopes"]:
            assert e["role"]=="SYNTHETIC_EXCLUSION_ENVELOPE_NOT_KEY_USE"
            assert e["intervals_inclusive_decimal"]
            for a,b in e["intervals_inclusive_decimal"]: assert 0<=int(a)<=int(b)<(1<<64)
            envelopes+=1
        gaps+=len(inspection["gaps"])
        actual.append(relative)
    assert actual==sorted(expected) and len(set(actual))==19
    assert payload["actual_scope_bytes"]==sum(r["actual_bytes"] for r in payload["records"])==330457
    assert union(all_rows)==payload["fixture_alias_intervals_inclusive_decimal"]
    assert [str(1<<63),str((1<<64)-1)] not in payload["fixture_alias_intervals_inclusive_decimal"]
    v14=ROOT/"experiments/v03r/a96_dense/b2_prepare/test_seed_plan_candidate.py"
    tree=ast.parse(v14.read_bytes()); f=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="proposal")
    assert len(f.body)==2 and isinstance(f.body[0],ast.Assign) and isinstance(f.body[1],ast.Return)
    assert ast.dump(f.body[0].value)==ast.dump(ast.parse("1<<63",mode="eval").body)
    values={k.value:v for k,v in zip(f.body[1].value.keys,f.body[1].value.values)}
    for name,text in {
        "primary_blocks":"[[base+b*100+i for i in range(100)] for b in range(4)]",
        "secondary_blocks":"[[base+400+b*100+i for i in range(100)] for b in range(2)]",
        "engineering_keys":"[base+1000,base+1001,base+1002]"}.items():
        assert ast.dump(values[name])==ast.dump(ast.parse(text,mode="eval").body)
    # Independent closed construction arithmetic (not invoking proposal).
    nominal=list(range(1<<63,(1<<63)+600))+[(1<<63)+1000+i for i in range(3)]
    v14result=next(r["source_only_inspection"] for r in payload["records"] if r["path"].endswith("/test_seed_plan_candidate.py"))
    nominal_claims=[r for r in v14result["claims"] if r["line"]<30]
    assert sum(r["literal_occurrences"] for r in nominal_claims)==603
    assert sorted(int(x) for r in nominal_claims for x in r["original_integers_decimal"])==nominal
    assert [[str(1<<62),str((1<<62)+100)]]==[
        row for row in payload["fixture_alias_intervals_inclusive_decimal"] if int(row[0])==1<<62]
    assert claims==35 and gaps==227 and envelopes==8
    # Complete final test IDs, not just trailing "OK" or case count.
    final_suites={}
    for stem,modules,n in (
        ("new_fixture_source_corrected_final",("test_fixture_source_candidate",),52),
        ("fixture_seed_history_integration_final",MODULES,186)):
        expected_ids=set()
        for module in modules:
            t=ast.parse((FOLDER/(module+".py")).read_bytes())
            for cls in t.body:
                if isinstance(cls,ast.ClassDef):
                    expected_ids.update(module+"."+cls.name+"."+method.name for method in cls.body
                        if isinstance(method,ast.FunctionDef) and method.name.startswith("test_"))
        assert len(expected_ids)==n
        log=(FOLDER/("evidence_v19/"+stem+".stderr.log")).read_bytes()
        text=log.decode("utf-8").replace("\r\n","\n")
        observed=[]
        for method,owner in re.findall(r"^(test_\w+) \(([^)]+)\) \.\.\. ok$",text,re.M):
            observed.append(".".join(owner.split(".")[-3:]))
        assert len(observed)==n and set(observed)==expected_ids and len(set(observed))==n
        assert re.search(r"Ran "+str(n)+r" tests in [0-9.]+s\n\nOK\n",text)
        assert not re.search(r"FAIL:|ERROR:|skipped |FAILED|unexpected success",text)
        final_suites[stem]={"count":n,"module_count":len(modules),"stderr_actual_sha256":sha(log),
            "full_case_ids_sha256":sha(canon(sorted(expected_ids))),"failures":0,"errors":0,"skips":0}
    for name,wanted in input_hashes.items(): assert sha((ROOT/name).read_bytes())==wanted
    for name,wanted in CORE.items(): assert sha((FOLDER/name).read_bytes())==wanted
    for key in ("complete_historical_usage_freshness_audit","future_plan_accepted_or_allocated",
        "native_training_or_collection_started","collection_authorized","scientific_claim_authorized","research_complete"):
        assert payload[key] is False
    assert payload["environment_key_draws"]==0
    return {"status":"PRIMARY_STDLIB_BOUND_SOURCE_EXPRESSIONS_ROLES_AND_FULL_TEST_LOG_AUDIT",
        "source_files":19,"actual_source_bytes":330457,"declared_fixture_claims":35,
        "explicit_gaps":227,"separate_synthetic_envelopes":8,
        "closed_v14_nominal_fixture_labels":603,
        "fixture_union_inclusive_decimal":union(all_rows),"final_suites":final_suites,
        "dynamic_and_embedded_parser_input_coverage_complete":False,
        "independent_agent_or_external_expert":False,"collection_authorized":False,
        "scientific_validation_PASS":False,"research_complete":False}


if __name__=="__main__":
    assert len(sys.argv)==1,"no scope/output overrides"
    print(json.dumps(audit(),sort_keys=True,ensure_ascii=True,allow_nan=False))

