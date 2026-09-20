r"""The shared mutation harness for the B1 / Q-substrate / L0 self-checks.

$$\boxed{\text{a gate that passes is not evidence; it is evidence only that the gate
did not look}}$$

Every self-check in ``scripts/`` reverts one fix at a time and requires the gate that
guards it to go **red**. The rules for what counts as red are subtle enough that having
them in three places is itself a risk — the exit-code rule had to be corrected twice, and
the second correction (pytest exits 2/3 on a broken import, not just 1/4/5) would have had
to be applied three times. So the mechanics live here and the tables live in the scripts.

What "red" means, in full:

* ``GATE_IS_REAL`` — pytest exited **1**, and if the mutation declared the text its
  failure must contain, that text is present;
* ``NOT_A_GATE`` — the gate passed, so the mutation did not reach it;
* ``NODE_NOT_FOUND`` — pytest never collected the node (exit 4/5);
* ``HARNESS_ERROR`` — any other non-zero exit (2 interrupted/collection error, 3 internal
  error). These mutations edit **source files**, so a mutation that breaks an import would
  otherwise be reported as a dead gate;
* ``MUTATION_NOT_APPLIED`` — the anchor did not match exactly once, so nothing was tested;
* ``WRONG_FAILURE_REASON`` — the gate failed, but not for the reason the mutation claims.

The tree is always restored in a ``finally`` block, every touched file is re-hashed
afterwards, and the run reports whether it is byte-identical to how it started.

One thing in the artifact is **not** reproducible and must not be: pytest prints CPython
heap addresses (``<function ... at 0x00000171...>``) in some assertion failures, so a stored
diagnostic tail differs byte-for-byte between two runs of the same code. The verdicts were
measured stable across runs, but the artifact is the evidence, and evidence that changes
between identical runs cannot be compared. So the **raw** tail decides the verdict -- it is
the thing ``expect_tail`` matches -- while only a **normalised** copy is stored:

$$\boxed{\text{raw tail decides the verdict}}\qquad
\boxed{\text{normalised tail only enters the JSON artifact}}$$

Normalising before the verdict would have been the wrong repair: it would let a declared
``expected_failure_text`` match text the gate never actually printed, which is the
``WRONG_FAILURE_REASON`` hole reopening as a convenience.

Redaction turned out to be **half** the repair. A second source of drift was measured after
it: a gate that fails comparing a string-keyed set or dict prints that container, whose order
is hash-randomised per process, so ``address_domain`` still produced four distinct artifact
hashes in eight runs. The child's seed is therefore pinned as well (see ``run_node``); the two
mechanisms together are what make "identical inputs give identical artifacts" true rather than
nearly true.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

__all__ = ["check_nodes", "normalize_diagnostic_tail", "run_mutations", "run_node",
           "summarise"]

#: A CPython heap address, as it appears in a pytest assertion tail.
_HEX_ADDR = re.compile(r"0x[0-9A-Fa-f]+")


def normalize_diagnostic_tail(text: str) -> str:
    """Replace heap addresses with a fixed token, for the stored artifact only.

    ``0x<ADDR>`` rather than ``0xADDR``: keeping the ``0x`` makes it obvious in the
    artifact that a number was there and was redacted on purpose, instead of looking like
    a value the gate printed.
    """
    return _HEX_ADDR.sub("0x<ADDR>", text)

#: pytest exits these when it never collected the requested node.
NODE_NOT_FOUND_CODES = (4, 5)


def read(path: pathlib.Path) -> str:
    """Read with no newline translation, so a round trip is byte-faithful.

    ``Path.read_text`` uses universal newlines and ``Path.write_text`` translates ``\\n``
    back to ``os.linesep``; on Windows that silently converts files to CRLF. It has caught
    this project twice — once in a self-check, once in a helper that rewrote six files —
    and the second time it broke multi-line mutation anchors, because the anchor compares
    **working-tree bytes**.
    """
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def write(path: pathlib.Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_nodes(mutations, root: pathlib.Path) -> list:
    """Every mutation's gate must name a test that still exists in its file.

    A renamed gate leaves a stale node id, and because pytest exits non-zero for "not
    found" a stale entry used to be reported ``GATE_IS_REAL`` -- a dead gate wearing a
    pass. The exit-code table catches that at runtime; this catches it before anything
    runs.
    """
    stale = []
    for entry in mutations:
        key, node = entry[0], entry[5]
        rel, _, test = node.partition("::")
        try:
            src = (root / rel).read_text(encoding="utf-8")
        except OSError:
            stale.append([key, node, "test file missing"])
            continue
        if f"def {test}(" not in src:
            stale.append([key, node, "no such test function"])
    return stale


def run_node(node: str, root: pathlib.Path) -> tuple[int, str]:
    """Run one gate with bytecode writing disabled, and return a 12-line tail.

    Bytecode must be off: the mutated and the original file can land in the same mtime
    second, and CPython validates a cached ``.pyc`` on ``(mtime, size)`` — which once
    replayed the *previous* mutation and produced a false ``NOT_A_GATE``.

    A *tail* rather than the last line: with ``-x`` the final line is the "stopping after 1
    failures" banner, so a last-line-only excerpt can never contain the failure reason a
    mutation may declare.

    ``PYTHONHASHSEED`` is pinned for the same reason ``PYTHONDONTWRITEBYTECODE`` is: the
    stored tail must be reproducible. A mutation whose gate fails inside a comparison of a
    **set or dict keyed by strings** prints that container, and its iteration order is
    hash-randomised per process, so the artifact differed between runs that ran identical
    code -- measured on ``address_domain``, which produced four distinct artifact hashes in
    eight runs. Redaction of heap addresses cannot repair that: the text differs in *order*,
    not in a token. Pinning the seed makes the diagnostic deterministic; the verdicts were
    already stable in every measured run, and the ordinary suite still runs unpinned, so
    order-dependence in a gate is still exercised where it would be a real defect.
    """
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="0")
    proc = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", node, "-q", "-p", "no:cacheprovider",
         "--no-header", "-x"],
        cwd=root, capture_output=True, text=True, env=env,
    )
    lines = [ln for ln in (proc.stdout + proc.stderr).strip().splitlines() if ln.strip()]
    return proc.returncode, "\n".join(lines[-12:])


def verdict_for(code: int, tail: str, expect_tail) -> str:
    r"""$$\boxed{\texttt{GATE\_IS\_REAL} \iff \text{pytest exit code} = 1}$$

    plus, when the mutation declares one, the failure text. ``code != 0`` was too
    generous: pytest also exits 2 (interrupted / collection error) and 3 (internal
    error), and these mutations edit source files, so a mutation that accidentally breaks
    an import would have been reported as a dead gate. That is the same mistake as
    counting "node not found" as a pass, one failure mode further out.
    """
    if code == 0:
        return "NOT_A_GATE"
    if code in NODE_NOT_FOUND_CODES:
        return "NODE_NOT_FOUND"
    if code != 1:
        return "HARNESS_ERROR"
    if expect_tail and expect_tail not in tail:
        return "WRONG_FAILURE_REASON"
    return "GATE_IS_REAL"


def run_mutations(mutations, root: pathlib.Path, files) -> tuple[list, bool]:
    """Revert each mutation in turn, require its gate to go red, and restore the tree."""
    before = {p: digest(p) for p in files}
    results = []
    for entry in mutations:
        key, hole, path, old, new, node = entry[:6]
        expect_tail = entry[6] if len(entry) > 6 else None
        original = read(path)
        count = original.count(old)
        record = {"mutation": key, "hole": hole, "gate": node.split("::")[-1],
                  "site": str(path.relative_to(root)), "matched": count,
                  "expected_failure_text": expect_tail}
        if count != 1:
            record.update(verdict="MUTATION_NOT_APPLIED",
                          detail=f"the anchor matched {count} times, expected exactly 1")
            results.append(record)
            print(f"[{record['verdict']:20}] {key}")
            continue
        try:
            write(path, original.replace(old, new))
            code, tail = run_node(node, root)
        finally:
            write(path, original)
        record.update(exit_code=code, tail=normalize_diagnostic_tail(tail),
                      verdict=verdict_for(code, tail, expect_tail))
        results.append(record)
        print(f"[{record['verdict']:20}] {key:34} -> {record['gate']}")
    after = {p: digest(p) for p in files}
    return results, before == after


def summarise(name: str, mutations, results, restored: bool, stale: list,
              root: pathlib.Path, out_path: pathlib.Path) -> int:
    """Write the artifact and print the verdict. Returns the process exit code."""
    real = sum(1 for r in results if r["verdict"] == "GATE_IS_REAL")
    counts = {v: sum(1 for r in results if r["verdict"] == v)
              for v in ("NOT_A_GATE", "NODE_NOT_FOUND", "HARNESS_ERROR",
                        "MUTATION_NOT_APPLIED", "WRONG_FAILURE_REASON")}
    payload = {
        "check": name,
        "n_mutations": len(mutations),
        "n_gate_is_real": real,
        "n_not_a_gate": counts["NOT_A_GATE"],
        "n_node_not_found": counts["NODE_NOT_FOUND"],
        "n_harness_error": counts["HARNESS_ERROR"],
        "n_mutation_not_applied": counts["MUTATION_NOT_APPLIED"],
        "n_wrong_failure_reason": counts["WRONG_FAILURE_REASON"],
        "tree_restored_byte_identical": restored,
        "stale_node_ids": stale,
        "results": results,
    }
    out = out_path if out_path.is_absolute() else root / out_path
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\n  mutations            : {len(mutations)}")
    print(f"  gates that went red  : {real}/{len(mutations)}")
    print(f"  tree restored        : {restored}")
    print(f"  written              : {out.relative_to(root)}")
    ok = restored and real == len(mutations) and not stale
    print("  SELF-CHECK " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1
