"""One prospective serial v90 child. No old fixture, key allocation or retry."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


def meta(p):
    return {"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()}


def save(p,data):
    with p.open("x",encoding="utf-8",newline="\n") as f:
        json.dump(data,f,sort_keys=True,separators=(",",":"),ensure_ascii=True)
        f.write("\n")


def bindings(contract):
    frozen = json.loads((ROOT/contract["frozen_manifest"]).read_bytes())["sources"]
    for name,expected in frozen.items():
        if meta(ROOT/name)["sha256"] != expected:
            raise RuntimeError("frozen input drift: "+name)
    names = set(frozen) | {contract["frozen_manifest"],contract["reference_input"]["path"]}
    names |= {str(p.relative_to(ROOT)).replace("\\","/") for p in HERE.iterdir() if p.is_file()}
    return {name:meta(ROOT/name) for name in sorted(names)}


def main():
    c=json.loads((HERE/"contract.json").read_bytes())
    parent=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    if parent!=c["parent_commit"]:
        raise RuntimeError("wrong prospective parent; no child")
    out=HERE/"evidence"
    if out.exists():
        raise RuntimeError("exclusive capture already exists; no retry")
    before=bindings(c)
    out.mkdir()
    start=datetime.now(timezone.utc).isoformat()
    cmd=[sys.executable,"-X","utf8","-B",str(HERE/"test_integration.py")]
    save(out/"claim.json",{"role":"NEW_REVISED_LEARNABLE_PATCH_ENGINEERING_NOT_SCIENCE",
        "parent_commit":parent,"command":cmd,"started_at_utc":start,
        "input_binding_before":before,"automatic_retry":False,"budget":c["budget"]})
    env=dict(os.environ);env["PYTHONDONTWRITEBYTECODE"]="1"
    with (out/"stdout.log").open("xb") as stdout,(out/"stderr.log").open("xb") as stderr:
        result=subprocess.run(cmd,cwd=ROOT,env=env,stdout=stdout,stderr=stderr,check=False)
    after=bindings(c)
    receipt={"role":"ACTUAL_ONE_CHILD_EXIT_NOT_SCIENCE_RECEIPT",
        "started_at_utc":start,"completed_at_utc":datetime.now(timezone.utc).isoformat(),
        "child_exit_code":result.returncode,"stdout":meta(out/"stdout.log"),
        "stderr":meta(out/"stderr.log"),"input_binding_after":after,
        "input_bytes_unchanged":before==after,"automatic_retry":False,
        "qualification_migrated":False,"collection_authorized":False}
    receipt["capture_budget_met"] = (receipt["stdout"]["bytes"] <= c["budget"]["stdout_bytes"]
                                    and receipt["stderr"]["bytes"] <= c["budget"]["stderr_bytes"])
    save(out/"exit.json",receipt)
    print(json.dumps({k:v for k,v in receipt.items() if k!="input_binding_after"}))
    return result.returncode if before==after and receipt["capture_budget_met"] else 2


if __name__=="__main__":
    raise SystemExit(main())
