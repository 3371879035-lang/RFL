"""Exclusive one-child v77 finite interface capture; no old fixture or retry."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
def now():
    return datetime.now(timezone.utc).isoformat()
def meta(path):
    with path.open("rb") as f:
        h=hashlib.file_digest(f,"sha256").hexdigest()
    return {"bytes":path.stat().st_size,"sha256":h}
def binding():
    names=subprocess.check_output(["git","ls-files","-z"],cwd=ROOT).decode("utf8").split("\0")
    additions=["experiments/v03r/a96_dense/b2_prepare/oracle_mainline_v77.py"]+[
        str(p.relative_to(ROOT)).replace("\\","/") for p in HERE.iterdir() if p.is_file()]
    return {n:meta(ROOT/n) for n in sorted(set([n for n in names if n]+additions))}
def save(path,value):
    with path.open("x",encoding="utf8",newline="\n") as f:
        json.dump(value,f,ensure_ascii=False,sort_keys=True,separators=(",",":"))
        f.write("\n")
def main():
    contract=json.loads((HERE/"contract.json").read_bytes())
    parent=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    if parent!=contract["parent_commit"]:raise RuntimeError("wrong parent; no child")
    out=HERE/"evidence"
    if out.exists():raise RuntimeError("exclusive output exists; no retry")
    before=binding()
    command=[sys.executable,"-X","utf8","-B",str(HERE/"test_new_integration.py")]
    out.mkdir();start=now()
    save(out/"claim.json",{"role":"FINITE_OWNED_ORIGINAL_BANK_INGREDIENT_NOT_CALIBRATION",
        "parent_commit":parent,"command":command,"cwd":str(ROOT),"started_at_utc":start,
        "input_binding_before":before,"automatic_retry":False})
    env=dict(os.environ);env["PYTHONDONTWRITEBYTECODE"]="1"
    with (out/"stdout.log").open("xb") as stdout,(out/"stderr.log").open("xb") as stderr:
        result=subprocess.run(command,cwd=ROOT,env=env,stdout=stdout,stderr=stderr,check=False)
    end=now();after=binding()
    save(out/"exit.json",{"role":"ACTUAL_FINITE_INTERFACE_CHILD_RECEIPT_NOT_SCIENCE",
        "started_at_utc":start,"completed_at_utc":end,"child_exit_code":result.returncode,
        "stdout":meta(out/"stdout.log"),"stderr":meta(out/"stderr.log"),
        "input_binding_after":after,"input_bytes_unchanged":before==after,
        "automatic_retry":False,"research_complete":False})
    print(json.dumps({"child_exit_code":result.returncode,"input_files":len(before),
        "input_bytes_unchanged":before==after,"stdout":meta(out/"stdout.log"),
        "stderr":meta(out/"stderr.log"),"completed_at_utc":end},sort_keys=True))
    return result.returncode if before==after else 2
if __name__=="__main__":
    sys.exit(main())
