"""Verify archived provenance and every recorded C2/C3 curve point from cell events."""
import hashlib
import json
import pathlib
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rfl_rebuild.b2.evalorder import prefix, prefix_digest
from rfl_rebuild.b2.numerics import mean
from rfl_rebuild.b2.utility import recovery_time


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify(folder):
    path = ROOT / "experiments/v03r" / folder
    manifest = json.loads((path / "manifest.json").read_bytes())
    report = json.loads((path / "report.json").read_bytes())
    static = json.loads((path / "seedless.json").read_bytes())
    assert sha((path / "manifest.json").read_bytes()) == report["manifest_sha256"]
    assert sha((path / "runs.jsonl").read_bytes()) == report["runs_sha256"]
    assert sha((path / "seedless.json").read_bytes()) == manifest["seedless_sha256"]
    with zipfile.ZipFile(path / "frozen_sources.zip") as archive:
        assert set(archive.namelist()) == set(manifest["sources"])
        for name, digest in manifest["sources"].items():
            assert sha(archive.read(name)) == digest, name
    # These current helpers are safe to reuse only if identical to acquisition bytes.
    for name in ("evalorder.py", "numerics.py", "utility.py"):
        rel = f"src/rfl_rebuild/b2/{name}"
        assert sha((ROOT / rel).read_bytes()) == manifest["sources"][rel]
    bank = prefix(manifest["bank_size"])
    assert prefix_digest(len(bank)) == manifest["bank_digest"]
    cells = tuple((u.kappa, u.phase, u.base_option) for u in bank)
    if "rows" in static:
        healthy = next(r["healthy"] for r in static["rows"] if r["bank_size"] == len(bank))
    else:
        healthy = static["healthy"][str(len(bank))]
    keys, points = [], 0
    cap = manifest["budget"]["cap"]
    with (path / "runs.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            keys.append(row["key"])
            state = {tuple(cell): value for cell, value in row["initial_cells"]}
            assert len(state) == 48
            assert len(row["cell_return_events"]) == cap
            assert len(row["curve"]) == cap + 1
            assert mean(state[c] for c in cells) == row["curve"][0]
            points += 1
            for e, (cell, value) in enumerate(row["cell_return_events"], start=1):
                assert tuple(cell) in state
                state[tuple(cell)] = value
                assert mean(state[c] for c in cells) == row["curve"][e], (row["key"], e)
                points += 1
            tau = recovery_time(row["curve"], range(cap + 1), pre_level=healthy, t_max=cap)
            assert tau == row["recovery_episode"]
    assert keys == manifest["keys"] and len(set(keys)) == len(keys)
    return {"folder": folder, "ordered_keys": len(keys), "exact_curve_points": points,
            "archived_sources": len(manifest["sources"]), "verdict": "PASS"}


if __name__ == "__main__":
    results = []
    for folder in ("c2_construction", "c3_construction"):
        result = verify(folder)
        results.append(result)
        print(json.dumps(result), flush=True)
    out = ROOT / "experiments/v03r/c2_c3_record_integrity.json"
    with out.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump({"results": results, "script_sha256": sha(pathlib.Path(__file__).read_bytes())},
                  stream, indent=2, sort_keys=True)
        stream.write("\n")
