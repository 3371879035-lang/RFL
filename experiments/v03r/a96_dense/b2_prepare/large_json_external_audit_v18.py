"""Primary-agent independent stdlib read-only checker, not an expert/gate.
No candidate extractor, environment generator, trainer or historical program import.
"""
import ast
import hashlib
import json
import math
from pathlib import Path
import re
import stat
import sys

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[3]
SNAPSHOT = FOLDER / "evidence_v18/large_json_snapshot.stdout.log"
SNAPSHOT_SHA = "88f5500fdb0e452b65aabc695639c29fb60d5d5313ea032a49aae06910482ee5"
PAYLOAD_SHA = "c681456e00172fe9fd7bee77b577499a5de1ae44ff9b10c7b280b04cefdbc79c"
TARGETS = (
    ("experiments/v01r/support_cache.json",115542484,
     "4f429347a7c0a039013ef1a401e2a6d2bf29e947cf8e191c7655296a2418a4b1"),
    ("experiments/v01r/support_cache_slice.json",57384499,
     "e535f31614112eed9161b4598468d629758c267593a0dba4933456091c2ca872"))
CORE = {
    "history_large_json_candidate.py":"6469a2d54ab6c468a5ee11be0776115ea8fd811d4748c6671f5180b3ebe52366",
    "test_history_large_json_candidate.py":"8244cc7bf38eb0deb66a73ac9562dd10ed75838108db5bb3015214759343651b",
    "large_json_contract_candidate_v18.json":"43969ce13e5415ea5a3f1038d41fb4385cb7e2eda6abe0823dc17d3a326ef33e"}
ALL_MODULES = ("test_history_seed_audit_candidate","test_history_schedule_candidate",
    "test_history_stream_candidate","test_history_large_json_candidate","test_seed_plan_candidate")


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate member")
        result[key] = value
    return result


def no_constant(text):
    raise ValueError("nonfinite constant")


def finite(text):
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("nonfinite/overflow float")
    return value


def strict(raw):
    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=pairs,
                      parse_float=finite, parse_constant=no_constant)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=True,separators=(",",":"),
                      allow_nan=False).encode("ascii")


def hash_all(path):
    size, h = 0, hashlib.sha256()
    with path.open("rb") as f:
        for raw in iter(lambda:f.read(65536), b""):
            size += len(raw)
            h.update(raw)
    return size,h.hexdigest()


def safe(path, boundary):
    assert path.is_file() and path.resolve().is_relative_to(boundary.resolve())
    current = boundary
    for part in ("",) + path.relative_to(boundary).parts:
        if part:
            current /= part
        attrs = current.lstat()
        assert not current.is_symlink() and not (getattr(attrs,"st_file_attributes",0) &
                getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",0x400)), current
    return path


def static_cases(modules):
    result = set()
    for module in modules:
        tree = ast.parse((FOLDER/(module+".py")).read_bytes())
        for cls in tree.body:
            if isinstance(cls,ast.ClassDef):
                for method in cls.body:
                    if isinstance(method,ast.FunctionDef) and method.name.startswith("test_"):
                        ident=module+"."+cls.name+"."+method.name
                        assert ident not in result
                        result.add(ident)
    return result


def tests(label,modules,count):
    out = FOLDER/"evidence_v18"/(label+".stdout.log")
    err = FOLDER/"evidence_v18"/(label+".stderr.log")
    raw=err.read_bytes()
    view=raw.decode("utf8").replace("\r\n","\n")
    rows=re.findall(r"^(\w+) \(([^)]+)\) \.\.\. ok$",view,re.M)
    ids=[]
    for method,group in rows:
        ident=group if group.endswith("."+method) else group+"."+method
        ids.append(".".join(ident.split(".")[-3:]))
    expected=static_cases(modules)
    assert len(expected)==count and len(ids)==count and len(set(ids))==count and set(ids)==expected
    assert re.search(r"^Ran "+str(count)+r" tests in [0-9.]+s\n\nOK\n?$",view,re.M)
    assert not re.search(r"^.* \.\.\. (?:FAIL|ERROR|skipped)",view,re.M)
    return {"label":label,"exact_unique_OK_case_count":count,
        "zero_failures_errors_skips":True,"modules":list(modules),
        "canonical_case_IDs_sha256":sha(canonical(ids)),
        "stdout_bytes":out.stat().st_size,"stdout_sha256":hash_all(out)[1],
        "stderr_bytes":len(raw),"stderr_sha256":sha(raw)}


def main():
    assert len(sys.argv)==1,"closed read-only checker"
    self_sha=hash_all(Path(__file__))[1]
    assert all(hash_all(FOLDER/n)[1]==h for n,h in CORE.items())
    raw=SNAPSHOT.read_bytes()
    assert sha(raw)==SNAPSHOT_SHA
    snap=strict(raw); payload=snap["payload"]
    assert snap["payload_sha256"]==PAYLOAD_SHA==sha(canonical(payload))
    assert payload["fixed_target_count"]==2 and payload["total_actual_bytes"]==172926983
    assert payload["full_scope_before_after_actual_SHA_match"] is True
    assert payload["all_two_complete_JSON_syntax_and_declared_fields_parsed"] is True
    assert payload["conservative_exclusion_intervals_decimal_inclusive"]==[]
    for name in ("complete_historical_usage_freshness_audit","collection_authorized",
                 "keys_allocated_or_reserved","native_protocol_or_training_started",
                 "scientific_claim_authorized","research_complete"):
        assert snap[name] is False
    assert snap["environment_key_draws"]==0
    oldroot=ROOT.parent/"RFL-CausalChase-v0.3"
    rows=[]
    for relative,size,digest in TARGETS:
        path=safe(oldroot/relative,oldroot)
        assert hash_all(path)==(size,digest)
        with path.open("rb") as f:
            blob=f.read(128*1024*1024+1)
            assert not f.read(1)
        assert (len(blob),sha(blob))==(size,digest)
        obj=strict(blob)
        del blob
        assert type(obj) is dict
        top_keys=sorted(obj)
        # Visit every container/member, not a head/tail sample. All scalar JSON
        # tokens were also parsed by strict decoder; numbers are NOT identities.
        stack=[obj]
        objects=arrays=scalars=members=0
        while stack:
            value=stack.pop()
            if type(value) is dict:
                objects += 1
                members += len(value)
                for key,child in value.items():
                    # Actual fixed inputs contain NO seed-related members.
                    # If any appear, refuse this zero-declaration audit rather
                    # than import/exercise the candidate extraction rules.
                    assert "seed" not in key.casefold(),key
                    if type(child) in (dict,list):
                        stack.append(child)
                    else:
                        scalars += 1
            else:
                assert type(value) is list
                arrays += 1
                for child in value:
                    if type(child) in (dict,list):
                        stack.append(child)
                    else:
                        scalars += 1
        del obj
        rec=[r for r in payload["file_evidence"] if r["root"]=="RFL-CausalChase-v0.3" and r["path"]==relative]
        assert len(rec)==1
        r=rec[0]
        assert r["bytes"]==size and r["sha256"]==digest==r["v17_actual_sha256"]
        assert r["parse_complete"] is True and r["claims"]==r["issues"]==r["conservative_exclusion_intervals_decimal_inclusive"]==[]
        rows.append({"path":relative,"bytes":size,"sha256":digest,"top_level_members":top_keys,
            "all_JSON_objects_visited":objects,"all_JSON_arrays_visited":arrays,
            "JSON_member_count":members,"JSON_scalar_value_count":scalars,
            "seed_related_member_count":0,"not_statistical_sample_size":True})
    for relative,size,digest in TARGETS:
        assert hash_all(safe(oldroot/relative,oldroot))==(size,digest)
    assert hash_all(SNAPSHOT)[1]==SNAPSHOT_SHA
    assert all(hash_all(FOLDER/n)[1]==h for n,h in CORE.items())
    assert hash_all(Path(__file__))[1]==self_sha
    result={"role":"PRIMARY_STDLIB_CHECK_NOT_INDEPENDENT_AGENT_OR_SCIENTIFIC_GATE",
        "input_files":rows,"both_full_input_hashes_before_after_match":True,
        "candidate_snapshot_actual_sha256":SNAPSHOT_SHA,"candidate_snapshot_payload_sha256":PAYLOAD_SHA,
        "test_accounting":[tests("new_large_json",("test_history_large_json_candidate",),57),
                           tests("history_seed_plan_integration",ALL_MODULES,243)],
        "new57_tests_included_in243_not_additive":True,
        "all_two_JSON_declaration_gaps_closed_with_zero_seed_related_members":True,
        "complete_historical_usage_freshness_audit":False,"keys_allocated_or_reserved":False,
        "environment_key_draws":0,"collection_authorized":False,"research_complete":False}
    print(canonical(result).decode("ascii"))


if __name__=="__main__":
    main()

