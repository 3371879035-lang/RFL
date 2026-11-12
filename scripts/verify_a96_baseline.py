"""Complete A96 engineering/index verification without any design selection."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from rfl_rebuild.b2.parallel_validation import verify_parallel
from rfl_rebuild.b2.design_lock import publish_new

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--index",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    if a.output.exists(): raise FileExistsError(a.output)
    result=verify_parallel(a.index,progress_folder=a.output.with_suffix(""))
    publish_new(a.output,result)
    print(result["status"],result["records"],len(result["shards"]),flush=True)
    return 0
if __name__ == "__main__": raise SystemExit(main())
