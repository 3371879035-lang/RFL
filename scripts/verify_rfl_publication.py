"""Verify published evidence bytes, optionally from the Git index rather than disk.

Archived sources are checked against their own pre-run manifests. They are not
silently compared with the current, subsequently developed implementation.
"""
import argparse
import gzip
import hashlib
import io
import json
import pathlib
import subprocess
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify(*, staged=False):
    def read(name):
        if staged:
            return subprocess.check_output(["git", "show", f":{name}"], cwd=ROOT)
        return (ROOT / name).read_bytes()

    def require(condition, message):
        if not condition:
            raise RuntimeError(message)

    folders, seen_keys = [], set()
    for folder in ("c1_construction", "c2_construction", "c3_construction", "c3_acquisition_integration"):
        base = f"experiments/v03r/{folder}/"
        manifest_bytes = read(base + "manifest.json")
        manifest = json.loads(manifest_bytes)
        report = json.loads(read(base + "report.json"))
        require(digest(manifest_bytes) == report["manifest_sha256"], f"{folder}: manifest hash")
        archive_bytes = read(base + "frozen_sources.zip")
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            require(len(archive.namelist()) == len(manifest["sources"])
                    and set(archive.namelist()) == set(manifest["sources"]), f"{folder}: archive inventory")
            for name, expected in manifest["sources"].items():
                require(digest(archive.read(name)) == expected, f"{folder}: archived source {name}")
        keys = manifest["keys"]
        require(len(keys) == len(set(keys)) and not seen_keys.intersection(keys), f"{folder}: key reuse")
        seen_keys.update(keys)
        require(report["f0_valid"] is False, f"{folder}: construction promoted to F0")
        record = {"folder": folder, "archived_sources": len(manifest["sources"]),
                  "manifest_sha256": digest(manifest_bytes), "archive_sha256": digest(archive_bytes)}
        if "runs_sha256" in report:
            raw = read(base + "runs.jsonl")
            require(digest(raw) == report["runs_sha256"], f"{folder}: raw run hash")
            rows = [json.loads(line) for line in raw.splitlines()]
            require([r["key"] for r in rows] == keys, f"{folder}: ordered keys")
            record.update(raw_runs=len(rows), raw_runs_sha256=digest(raw))
        if "seedless_sha256" in manifest:
            require(digest(read(base + "seedless.json")) == manifest["seedless_sha256"], f"{folder}: seedless hash")
        if "baseline_index_sha256" in report:
            index_bytes = read(base + "baseline.json")
            require(digest(index_bytes) == report["baseline_index_sha256"], "acquisition index hash")
            index = json.loads(index_bytes)
            require(index["role"] == "OPERATIONAL_REHEARSAL", "integration role")
            require(index["seeds"] == keys, "integration ordered keys")
            rows_total, pairs_total = 0, 0
            for descriptor in index["shards"]:
                data = gzip.decompress(read(base + descriptor["path"]))
                require(digest(data) == descriptor["sha256"], "uncompressed shard hash")
                rows = [json.loads(line) for line in data.splitlines()]
                require([r["episode"] for r in rows] == index["episodes"], "shard episode axis")
                require(all(r["seed"] == descriptor["seed"] for r in rows), "shard seed axis")
                pairs = sum(len(indices) for r in rows for incidence in r["consulted"].values()
                            for ordinal, indices in incidence)
                require(len(rows) == descriptor["records"] and pairs == descriptor["pairs"], "shard counts")
                rows_total += len(rows)
                pairs_total += pairs
            require(rows_total == index["records"] == report["verified_records"], "aggregate record count")
            require(pairs_total == index["pairs"] == report["pairs"], "aggregate pair count")
            record.update(shard_records=rows_total, incidence_pairs=pairs_total)
        folders.append(record)
    return {"verdict": "PASS", "surface": "git-index" if staged else "working-tree",
            "folders": folders, "archived_sources": sum(r["archived_sources"] for r in folders),
            "distinct_operational_keys": len(seen_keys), "scientific_efficacy_claim": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    result = verify(staged=args.staged)
    if args.output:
        with args.output.open("x", encoding="utf-8", newline="\n") as out:
            json.dump(result, out, indent=2, sort_keys=True)
            out.write("\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
