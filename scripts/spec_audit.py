"""Specification audit for ``docs/rebuild/``.

The rebuild's whole claim is that implementation can begin with no design
ambiguity. That claim is checkable, at least mechanically, and this script checks
the part of it that machines can decide:

* every ``NN §X`` cross-reference resolves to a real section in a real document;
* every ``NN-NAME.md`` file reference resolves;
* every document uses numbered ``##`` headings, so it *can* be referenced;
* every filesystem path the spec names actually exists on this branch;
* every invariant (I1..I6) and case (C0..C8) is defined exactly once.

It cannot check whether the design is *good*, or whether a sentence is
ambiguous to a human. It checks that the document set is a closed graph rather
than a pile of forward references.

Usage
-----
    python scripts/spec_audit.py
    python scripts/spec_audit.py --json experiments/spec_audit.json

Exit status is 0 when clean and 1 when anything is unresolved, so it can gate a
commit.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC_DIR = ROOT / "docs" / "rebuild"

# Paths the specification tells an implementer to create or use.
DECLARED_PATHS = (
    "src/rfl_rebuild",
    "tests/semantic",
    "experiments/v01r",
    "experiments/v02r",
    "experiments/v03r",
    "experiments/v04r",
    "scripts/src_fingerprint.py",
    "docs/rebuild/00-INDEX.md",
)

INVARIANTS = ("I1", "I2", "I3", "I4", "I5", "I6")
CASES = ("C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8")
AMENDMENTS = tuple(f"A{i}" for i in range(1, 13))

# Sequences that indicate UTF-8 read as a legacy codepage. This is not
# hypothetical: a PowerShell Get-Content/Set-Content round-trip silently
# destroyed every em dash in 12-AMENDMENTS.md, turning "—" into "鈥?". The file
# still parsed, still rendered as text, and looked fine in a diff summary.
MOJIBAKE = ("\ufffd", "鈥", "锛", "銆", "鈻", "芒€")


def strip_code(text: str) -> str:
    """Remove backticks so `` `03` §2 `` reads as `` 03 §2 ``."""
    return text.replace("`", "")


def load() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(SPEC_DIR.glob("*.md"))}


def sections(text: str) -> set[str]:
    return set(re.findall(r"^#{2,4}\s+(\d+(?:\.\d+)*)", text, re.M))


def audit() -> dict:
    docs = load()
    names = set(docs)
    by_num = {n[:2]: n for n in names}

    problems: list[tuple[str, str, str]] = []
    refs_checked = 0
    unnumbered: list[str] = []

    for name, raw in docs.items():
        text = strip_code(raw)

        secs = sections(raw)
        if not secs:
            unnumbered.append(name)

        for m in re.finditer(r"([0-9]{2})\s*§\s*([0-9]+(?:\.[0-9]+)*)", text):
            refs_checked += 1
            target = by_num.get(m.group(1))
            if target is None:
                problems.append((name, "no-such-document", m.group(1)))
            elif m.group(2) not in sections(docs[target]):
                problems.append((name, "no-such-section", f"{target} §{m.group(2)}"))

        for m in re.finditer(r"([0-9]{2}-[A-Z0-9\-]+\.md)", text):
            refs_checked += 1
            if m.group(1) not in names:
                problems.append((name, "no-such-file-ref", m.group(1)))

    # Every invariant and case must be defined exactly once, in doc 04.
    definitions: dict[str, list[str]] = {k: [] for k in INVARIANTS + CASES}
    for name, raw in docs.items():
        for m in re.finditer(r"^###\s+(I[1-6]|C[0-8])\s+—", raw, re.M):
            definitions[m.group(1)].append(name)
    for key, where in definitions.items():
        if len(where) != 1:
            problems.append(("04-SEMANTIC-INVARIANTS.md", "definition-count",
                             f"{key} defined in {len(where)} places: {where}"))

    missing_paths = [p for p in DECLARED_PATHS if not (ROOT / p).exists()]

    # Amendment references must resolve to an amendment heading.
    amend_doc = docs.get("12-AMENDMENTS.md", "")
    defined_amendments = set(re.findall(r"^##\s+\d+\.\s+(A\d+)\s+—", amend_doc, re.M))
    referenced_amendments: set[str] = set()
    for name, raw in docs.items():
        for m in re.finditer(r"\*\*(A\d+)\*\*", raw):
            if name != "12-AMENDMENTS.md":
                referenced_amendments.add(m.group(1))
    dangling_amendments = sorted(referenced_amendments - defined_amendments)

    # UTF-8 integrity.
    mojibake: list[tuple[str, str]] = []
    for name, raw in docs.items():
        for bad in MOJIBAKE:
            if bad in raw:
                mojibake.append((name, bad))

    return {
        "documents": sorted(names),
        "documents_without_numbered_sections": unnumbered,
        "cross_references_checked": refs_checked,
        "problems": sorted(set(problems)),
        "missing_declared_paths": missing_paths,
        "invariants_defined": {k: v for k, v in definitions.items() if k.startswith("I")},
        "cases_defined": {k: v for k, v in definitions.items() if k.startswith("C")},
        "amendments_defined": sorted(defined_amendments),
        "amendments_referenced": sorted(referenced_amendments),
        "dangling_amendments": dangling_amendments,
        "mojibake": mojibake,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    if not SPEC_DIR.exists():
        print(f"{SPEC_DIR} not found -- run from the rebuild branch")
        return 1

    r = audit()
    print(f"documents: {len(r['documents'])}")
    print(f"cross-references checked: {r['cross_references_checked']}")

    ok = True

    if r["documents_without_numbered_sections"]:
        ok = False
        print("\nDOCUMENTS WITH NO NUMBERED SECTIONS (cannot be referenced by §):")
        for n in r["documents_without_numbered_sections"]:
            print(f"  {n}")

    if r["problems"]:
        ok = False
        print("\nUNRESOLVED REFERENCES:")
        for doc, kind, detail in r["problems"]:
            print(f"  {doc:<34} {kind:<20} {detail}")

    if r["missing_declared_paths"]:
        ok = False
        print("\nDECLARED PATHS THAT DO NOT EXIST:")
        for p in r["missing_declared_paths"]:
            print(f"  {p}")

    undef = [k for k, v in {**r["invariants_defined"], **r["cases_defined"]}.items() if not v]
    if undef:
        ok = False
        print(f"\nUNDEFINED INVARIANTS/CASES: {undef}")

    if r["dangling_amendments"]:
        ok = False
        print("\nAMENDMENT REFERENCES WITH NO SUCH AMENDMENT:")
        for a in r["dangling_amendments"]:
            print(f"  {a}")
    print(
        f"\namendments defined: {len(r['amendments_defined'])} "
        f"{r['amendments_defined']}; referenced from other docs: "
        f"{r['amendments_referenced']}"
    )

    if r["mojibake"]:
        ok = False
        print("\nUTF-8 CORRUPTION DETECTED:")
        for name, bad in r["mojibake"]:
            print(f"  {name}: contains {bad!r}")
        print(
            "  Never round-trip these files through PowerShell "
            "Get-Content/Set-Content; use the editor tools."
        )

    if ok:
        print("\nOK - the specification is a closed reference graph")

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(r, indent=1), encoding="utf-8")
        print(f"\nwrote {args.json}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
