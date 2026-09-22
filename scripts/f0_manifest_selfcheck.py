r"""Mutation self-check for the $F_0$ manifest generator.

$$\boxed{\text{a manifest that reports digests is evidence only if a wrong tree cannot produce one}}$$

`scripts/f0_manifest.py` asserts the invariants it records: closure ancestry, the calibration summary,
the screening verdicts, the mutation counters, the decoded test inventory, and -- implicitly -- that a
failed assertion leaves no artifact behind. Those assertions are the reason the manifest is worth citing,
so each one is re-run against a deliberately corrupted input, one at a time, and the generator must exit
non-zero **with the expected message**, then the tree must come back byte-identical.

Two verdicts are distinguished that a looser harness would merge:

* a mutation whose expected failure text does not appear is `WRONG_FAILURE_REASON`, not a pass -- the
  generator failing for an unrelated reason (a typo, an import error) proves nothing about the check;
* a mutation-free **control** run must exit 0 and write the artifact. Without it, every "gate went red"
  below would also hold for a generator that is simply broken.

Usage::

    python scripts/f0_manifest_selfcheck.py [--json PATH]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import _mutation_harness as harness  # noqa: E402

MANIFEST = ROOT / "scripts" / "f0_manifest.py"
TMP_OUT = "experiments/v03r/_f0_manifest_selfcheck_tmp.json"
BAD_LIST_NAME = "_f0_selfcheck_bad_testlist.txt"

#: (key, hole the check closes, file to corrupt, old text, new text, expected failure text, gate label,
#:  kind) where kind is "text", "crlf", "bad_test_list" or "no_partial".
MUTATIONS = [
    ("closure_commit_not_ancestor",
     "the manifest could be generated from a tree that does not contain the A89 closure at all",
     "scripts/f0_manifest.py", 'CLOSURE_COMMIT = "a4451cc"', 'CLOSURE_COMMIT = "deadbeef"',
     "is not an ancestor", "manifest::closure_ancestry", "text"),
    ("calibration_counter_changed",
     "a calibration artifact that silently lost a cell would still be fingerprinted as 18/18 evidence",
     "experiments/v03r/calibration_report.json", '"calibrated": 18', '"calibrated": 17',
     "no longer 18/18", "manifest::calibration_summary", "text"),
    ("mutation_power_lost",
     "a mutation self-check that no longer fails its gate would be recorded as gate evidence",
     "experiments/v03r/b2_view_gate_selfcheck.json", '"n_gate_is_real": 45', '"n_gate_is_real": 44',
     "no longer fails its gate", "manifest::mutation_power", "text"),
    ("screening_verdict_renamed",
     "the screening artifact's aggregate verdict could go unread while the manifest still looks complete",
     "experiments/v03r/structural_screening.json", '"verdict":', '"verdict_renamed":',
     "no aggregate verdict field found", "manifest::screening_verdict", "text"),
    ("artifact_not_lf",
     "an artifact stored with CRLF would be digested from bytes that no checkout of this revision "
     "reproduces, so the fingerprint would be of one machine rather than of the revision",
     "experiments/v03r/structural_screening.json", None, None,
     "would not survive a checkout", "manifest::line_endings", "crlf"),
    ("test_list_from_another_tree",
     "a collected-test listing naming files that do not exist here would be fingerprinted as this tree's",
     None, None, None, "test listing names files that do not exist", "manifest::test_inventory",
     "bad_test_list"),
    ("no_partial_manifest",
     "a failed run could leave a well-formed-looking artifact behind, which would be read as the manifest",
     "experiments/v03r/calibration_report.json", '"calibrated": 18', '"calibrated": 17',
     "no longer 18/18", "manifest::fail_closed_write", "no_partial"),
    ("u2_enumeration_reordered",
     "the master evaluation sample's order is F0's definition of which scenes 'the first N' names, so a "
     "re-ordered enumerator would silently redefine every N_eval candidate while every count still "
     "matched -- the check keeps two ordered defences (agreement of the two representations, then "
     "monotonicity in A88's order) and this mutation trips the first",
     "src/rfl_rebuild/b2/unaffected.py", "key=lambda scene: scene.key",
     "key=lambda scene: (scene.base_option, scene.kappa, scene.phase, scene.error_flag, scene.cause_rank)",
     "disagree element-wise", "manifest::eval_sample_order", "text"),
    ("dirty_code_tree",
     "the manifest could be generated from an uncommitted instrument, so it would pin a working tree "
     "rather than a revision -- the defect the review of revision 1 found in the shipped manifest",
     "scripts/f0_manifest.py", 'CLOSURE_COMMIT = "a4451cc"',
     'CLOSURE_COMMIT = "a4451cc"  # uncommitted probe edit',
     "the instrument is dirty", "manifest::clean_execution_revision", "dirty"),
]

def run_manifest(extra_argv=(), *, allow_dirty: bool = True):
    """Run the generator into a throwaway path; return (exit code, diagnostic tail, output path).

    Mutation runs pass ``--allow-dirty`` because they corrupt an input on purpose; the generator then
    stamps its output ``MUTATION-PROBE`` so it can never be mistaken for evidence. The dirty-tree
    mutation is the one case that runs *without* the flag, because refusing a dirty instrument is
    exactly what it tests.
    """
    out = ROOT / TMP_OUT
    if out.exists():
        out.unlink()
    argv = ["--out", TMP_OUT]
    if allow_dirty:
        argv.append("--allow-dirty")
    proc = subprocess.run(
        [sys.executable, str(MANIFEST), *argv, *extra_argv],
        cwd=ROOT, capture_output=True, text=True,
    )
    lines = [ln for ln in (proc.stdout + proc.stderr).strip().splitlines() if ln.strip()]
    return proc.returncode, "\n".join(lines[-12:]), out


def bad_listing_path() -> pathlib.Path:
    path = ROOT / "experiments" / "v03r" / BAD_LIST_NAME
    path.write_text(
        "tests/rebuild/test_that_does_not_exist.py::test_absent\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Mutation self-check for the F0 manifest generator.")
    ap.add_argument("--json", default="experiments/v03r/f0_manifest_selfcheck.json")
    args = ap.parse_args(argv)

    files = [MANIFEST] + [ROOT / m[2] for m in MUTATIONS if m[2]]
    before = {p: harness.digest(p) for p in files}
    results = []

    # Control: with nothing corrupted, the probe path must succeed, write its artifact, and label itself
    # as a probe rather than as evidence.
    code, tail, out = run_manifest()
    control_detail = ""
    control_ok = False
    if code == 0 and out.is_file():
        probe = json.loads(out.read_text(encoding="utf-8"))
        control_ok = (
            probe["status"].startswith("MUTATION-PROBE")
            and probe["repo"]["execution_revision"] is None
            and probe["repo"]["code_tree_clean"] is False
            and probe["currently_authorises"] == []
        )
        control_detail = "probe labelled, execution_revision nulled, authorises nothing" if control_ok \
            else f"probe self-labelling wrong: {probe['status']!r}"
    else:
        control_detail = f"exit {code}: {tail.splitlines()[-1] if tail else 'no output'}"
    print(f"[{'CONTROL_OK' if control_ok else 'CONTROL_FAILED':20}] mutation-free run -- {control_detail}")
    if out.exists():
        out.unlink()

    for key, hole, rel, old, new, expect, gate, kind in MUTATIONS:
        record = {"mutation": key, "hole": hole, "gate": gate, "site": rel,
                  "expected_failure_text": expect}
        extra_argv = ()
        temporary = None
        path = ROOT / rel if rel else None
        original_bytes = path.read_bytes() if path else None
        original = harness.read(path) if (path is not None and old is not None) else None
        if old is not None:
            count = original.count(old)
            if count != 1:
                record.update(verdict="MUTATION_NOT_APPLIED",
                              detail=f"the anchor matched {count} times, expected exactly 1")
                results.append(record)
                print(f"[{record['verdict']:20}] {key}")
                continue
        try:
            if kind == "crlf":
                path.write_bytes(original_bytes.replace(b"\n", b"\r\n"))
            elif old is not None:
                harness.write(path, original.replace(old, new))
            if kind == "bad_test_list":
                temporary = bad_listing_path()
                extra_argv = ("--test-list", str(temporary))
            code, tail, out = run_manifest(extra_argv, allow_dirty=(kind != "dirty"))
        finally:
            if path is not None:
                path.write_bytes(original_bytes)
            if temporary is not None and temporary.exists():
                temporary.unlink()
        verdict = harness.verdict_for(code, tail, expect)
        if kind == "no_partial" and out.exists():
            verdict = "WRONG_FAILURE_REASON"
            record["detail"] = "the generator failed but still wrote its artifact"
        if out.exists():
            out.unlink()
        record.update(exit_code=code, tail=harness.normalize_diagnostic_tail(tail), verdict=verdict)
        results.append(record)
        print(f"[{verdict:20}] {key:34} -> {gate}")

    after = {p: harness.digest(p) for p in files}
    restored = before == after
    real = sum(1 for r in results if r["verdict"] == "GATE_IS_REAL")
    counts = {v: sum(1 for r in results if r["verdict"] == v)
              for v in ("NOT_A_GATE", "NODE_NOT_FOUND", "HARNESS_ERROR",
                        "MUTATION_NOT_APPLIED", "WRONG_FAILURE_REASON")}
    payload = {
        "check": "F0 manifest generator mutation self-check",
        "n_mutations": len(MUTATIONS),
        "n_gate_is_real": real,
        "n_not_a_gate": counts["NOT_A_GATE"],
        "n_node_not_found": counts["NODE_NOT_FOUND"],
        "n_harness_error": counts["HARNESS_ERROR"],
        "n_mutation_not_applied": counts["MUTATION_NOT_APPLIED"],
        "n_wrong_failure_reason": counts["WRONG_FAILURE_REASON"],
        "control_run_ok": control_ok,
        "tree_restored_byte_identical": restored,
        "stale_node_ids": [],
        "note": ("stale_node_ids is empty by construction: this check's gates are generator assertions "
                 "rather than pytest nodes, so there is no node id to go stale."),
        "results": results,
    }
    out_path = ROOT / args.json
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    ok = control_ok and restored and real == len(MUTATIONS)
    print(f"\n  mutations            : {len(MUTATIONS)}")
    print(f"  gates that went red  : {real}/{len(MUTATIONS)}")
    print(f"  control run          : {'ok' if control_ok else 'FAILED'}")
    print(f"  tree restored        : {restored}")
    print(f"  written              : {args.json}")
    print("  SELF-CHECK " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
